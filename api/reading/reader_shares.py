"""Revocable, version-bound grants over an explicit subset of original records."""
from datetime import timedelta
from hashlib import sha256
import secrets

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from common.capabilities import Capability, has_capability
from . import privacy, research, reader_groups, share_scope
from .models import ReadingList, ResearchProject
from .services import decrypt_private_text, encrypt_private_text
from .sharing_models import ReaderGroup, ReaderShare, ReaderShareNotice
from .knowledge_models import KnowledgeSaveReceipt

CANCEL_TARGET = 'reader-share-create-cancelled'


def stopped_request(user, request_id):
    saved = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if saved and saved.target_key != CANCEL_TARGET:
        raise research.ResearchConflict('该请求编号已用于其他操作，请保留原编号核对记录。')
    return saved is not None


def visible(user):
    return ReaderShare.objects.filter(revoked_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True).filter(
        Q(user=user) | Q(group__user=user, group__archived=False) | Q(group__memberships__user=user, group__archived=False)
        | (Q(destination="proposal") if has_capability(user, Capability.REVIEW_CANDIDATE) else Q(pk__isnull=True))).distinct()


def permitted(row, user):
    if row.user_id == user.pk:
        return True
    if row.destination == "proposal":
        return has_capability(user, Capability.REVIEW_CANDIDATE)
    if row.destination != "group" or not row.group_id or row.group.archived:
        return False
    current = reader_groups.member_bindings(row.group)
    payload = research.unpack(row)
    if payload.get("sender_binding") not in current:
        return False
    stored = payload.get("recipient_bindings", [])
    return any(value["user_id"] == str(user.pk) and value in current for value in stored)


def brief(row, user):
    owner = row.user_id == user.pk
    count = 1 + len(research.unpack(row).get('specification', {}).get('additional_sources', []))
    title = "研究内容摘要" if row.source_kind == "research" else "书单内容摘要"
    if owner:
        model = ResearchProject if row.source_kind == "research" else ReadingList
        source = model.objects.filter(user=user, pk=row.source_id).first()
        if source:
            title = research.unpack(source).get("title", title) if row.source_kind == "research" else source.title
    if count > 1:
        title = f'{title} 等 {count} 个对象' if owner else f'{count} 个研究与书单的内容摘要'
    return {"id": str(row.pk), "revision": row.revision, "source_kind": row.source_kind, "source_id": str(row.source_id) if row.user_id == user.pk else None,
        "source_count":count,
        "title": title, "request_id": str(row.request_id) if owner else None,
        "destination": row.destination, "created_at": row.created_at, "expires_at": row.expires_at,
        "revoked": bool(row.revoked_at), "is_owner": row.user_id == user.pk, "review_state": row.review_state}


@transaction.atomic
def receipt(user, request_id):
    privacy.command_owner(user)
    row = ReaderShare.objects.filter(user=user, request_id=request_id).first()
    if row is None:
        if stopped_request(user, request_id):
            raise research.ResearchConflict('这次尚未执行的提交已取消，不会再建立分享。可再次确认取消结果。')
        raise NotFound("未查到本次提交回执，请保留原请求后重试。")
    active = row.revoked_at is None and row.expires_at > timezone.now()
    return {"owner_id": str(user.pk), "request_id": str(request_id), "share": brief(row, user),
        "token": decrypt_private_text(row.token_ciphertext) if active and row.destination == "public" else None}


@transaction.atomic
def create(user, data):
    privacy.command_owner(user)
    if data.get("confirmed") is not True:
        raise ValidationError("请核对完整预览并明确确认分享所选内容。")
    fingerprint = share_scope.digest(data)
    existing = ReaderShare.objects.filter(user=user, request_id=data["request_id"]).first()
    if existing:
        if research.unpack(existing).get("request_fingerprint") != fingerprint:
            raise research.ResearchConflict("原提交的内容已变化，请先查回原结果。")
        return receipt(user, data["request_id"])
    if stopped_request(user, data['request_id']):
        raise research.ResearchConflict('这次提交已在服务器取消，迟到请求不会建立分享。请重新预览后发起新的提交。')
    if ReaderShare.objects.filter(user=user, revoked_at__isnull=True, expires_at__gt=timezone.now()).count() >= 1000:
        raise ValidationError("最多保留1000项有效分享，请先整理已有分享。")
    if data["destination"] == "group":
        reader_groups.group_for(user, data["group_id"], lock=True)
    share_scope.lock_sources(user,data)
    projected, bindings = share_scope.preview(user, data)
    if projected["preview_hash"] != data["preview_hash"]:
        raise research.ResearchConflict("所选内容、来源或接收范围已变化，请重新预览后确认。")
    specification = share_scope.specification(data)
    token = secrets.token_urlsafe(32) if data["destination"] == "public" else ""
    row = ReaderShare.objects.create(user=user, request_id=data["request_id"], source_kind=data["source_kind"], source_id=data["source_id"],
        destination=data["destination"], group_id=data.get("group_id"), expires_at=timezone.now() + timedelta(days=data["expires_days"]),
        token_hash=sha256(token.encode()).hexdigest() if token else "", token_ciphertext=encrypt_private_text(token) if token else b"",
        data_ciphertext=research.pack({"request_fingerprint": fingerprint, "specification": specification, "bindings": bindings,
            "recipient_bindings": projected["destination"]["members"], "sender_binding": projected["destination"].get("sender_binding"),
            "content_hash": share_scope.digest(share_scope.content_fields(projected))}))
    # Check again after persistence; revisions can also change through workers.
    current, current_bindings = share_scope.content(user, specification)
    if current_bindings != bindings or share_scope.digest(current) != research.unpack(row)["content_hash"]:
        raise research.ResearchConflict("内容刚刚更新，本次提交未完成，请重新预览。")
    return receipt(user, data["request_id"])


@transaction.atomic
def stop_create(user, request_id):
    privacy.command_owner(user)
    row = ReaderShare.objects.filter(user=user, request_id=request_id).first()
    if row:
        return {'owner_id':str(user.pk),'request_id':str(request_id),'state':'applied','receipt':receipt(user,request_id)}
    if not stopped_request(user, request_id):
        KnowledgeSaveReceipt.objects.create(user=user,request_id=request_id,target_key=CANCEL_TARGET,
            fingerprint=share_scope.digest({'action':'cancel_pending','request_id':str(request_id)}),applied_saved=False)
    return {'owner_id':str(user.pk),'request_id':str(request_id),'state':'cancelled','receipt':None}


def read(row, user=None, token=None):
    if row.revoked_at or row.expires_at <= timezone.now() or not row.user.is_active:
        raise NotFound("这项分享已撤回、到期或不可用。")
    if token is not None:
        if row.destination != "public" or not secrets.compare_digest(row.token_hash, sha256(token.encode()).hexdigest()):
            raise NotFound("分享链接无效或已撤回。")
    elif user is None or not permitted(row, user):
        raise PermissionDenied("当前账户不在这项分享的接收范围内。")
    payload = research.unpack(row)
    try:
        projected, bindings = share_scope.content(row.user, payload["specification"])
    except (NotFound, ValidationError, research.ResearchConflict):
        raise NotFound("原内容已经修改、删除或撤下，请联系分享者重新选择和确认范围。") from None
    if bindings != payload["bindings"] or share_scope.digest(projected) != payload["content_hash"]:
        raise NotFound("原内容已变化，旧分享不会自动公开新文字，请联系分享者重新确认。")
    current = ReaderShare.objects.select_related("user", "group__user").filter(pk=row.pk, revision=row.revision, revoked_at__isnull=True).first()
    if current is None or current.expires_at <= timezone.now() or not current.user.is_active or (token is None and not permitted(current, user)):
        raise NotFound("分享权限刚刚变化，请重新读取。")
    # Receiver output deliberately omits owner IDs, group rosters, source private
    # route IDs and all request receipts. It contains only the approved summary.
    projected["source"] = {key: projected["source"][key] for key in ("kind", "title")}
    if 'sources' in projected:
        projected['sources'] = [{key:item[key] for key in ('kind','title')} for item in projected['sources']]
    for section in share_scope.SECTIONS:
        projected["sections"][section] = [{key: value for key, value in item.items() if key not in {"id", "version"}}
            for item in projected["sections"][section]]
    return {"id": str(row.pk), "revision": row.revision, **projected, "expires_at": row.expires_at,
        "destination": row.destination, "review_state": row.review_state}


def revoke_record(row):
    data = research.unpack(row)
    row.data_ciphertext = research.pack({"request_fingerprint": data.get("request_fingerprint", "")})
    row.token_ciphertext, row.token_hash, row.revoked_at = b"", "", timezone.now()
    row.revision += 1
    row.save(update_fields=["data_ciphertext", "token_ciphertext", "token_hash", "revoked_at", "revision", "updated_at"])
    row.notices.all().delete()


@transaction.atomic
def revoke(user, pk, expected_revision):
    privacy.lock_owner(user)
    row = ReaderShare.objects.select_for_update().filter(user=user, pk=pk).first()
    if row is None:
        raise NotFound("这项本人分享已不存在。")
    if not row.revoked_at:
        research.expect(row, expected_revision)
        revoke_record(row)
    return brief(row, user)


@transaction.atomic
def notify(user, pk, expected_revision):
    privacy.lock_owner(user)
    row = ReaderShare.objects.filter(user=user, pk=pk).first()
    if row is None:
        raise NotFound("这项本人分享已不存在。")
    if row.destination != "group" or not row.group_id:
        raise ValidationError("此处通知仅面向分享时明确选择的小组成员。")
    group = ReaderGroup.objects.select_for_update().get(pk=row.group_id)
    row = ReaderShare.objects.select_for_update().get(pk=row.pk)
    research.expect(row, expected_revision)
    read(row, user=user)
    current = reader_groups.member_bindings(group)
    if research.unpack(row).get("sender_binding") not in current:
        raise PermissionDenied("本次分享者已不属于原成员关系，不能继续通知，请重新加入并确认分享范围。")
    recipients = [value["user_id"] for value in research.unpack(row)["recipient_bindings"] if value in current and value["user_id"] != str(user.pk)]
    added = 0
    for pk in recipients:
        _, created = ReaderShareNotice.objects.get_or_create(user_id=pk, share=row)
        added += int(created)
    return {"owner_id": str(user.pk), "created": added, "total": row.notices.filter(user_id__in=recipients).count(),
        "channel": "reader_center", "message": "通知已保存在接收者的读者中心；没有发送邮件或外部消息。"}


@transaction.atomic
def review(user, pk, expected_revision, state):
    if not has_capability(user, Capability.REVIEW_CANDIDATE):
        raise PermissionDenied("当前账户没有策划提案审核权限。")
    # Lock only the grant: it never writes to its author's private project.
    row = ReaderShare.objects.select_for_update().filter(pk=pk, destination="proposal").first()
    if row is None:
        raise NotFound("该提案已不存在。")
    read(row, user=user)
    if row.review_state != state:
        research.expect(row, expected_revision)
        row.review_state, row.revision = state, row.revision + 1
        row.save(update_fields=["review_state", "revision", "updated_at"])
    return brief(row, user)
