"""Explicit account-bound invitations; no email, role change or public roster."""
from datetime import timedelta
from hashlib import sha256
import json
import secrets
from uuid import uuid5

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .services import decrypt_private_text, encrypt_private_text
from .sharing_models import ReaderGroup, ReaderGroupInvite, ReaderGroupMember


def accessible(user):
    return ReaderGroup.objects.filter(archived=False, user__is_active=True).filter(Q(user=user) | Q(memberships__user=user)).distinct()


def group_for(user, pk, *, owner=False, lock=False):
    rows = ReaderGroup.objects.filter(user=user, archived=False) if owner else accessible(user)
    # Lock a base-table row, not a DISTINCT join (PostgreSQL forbids the latter).
    row = rows.filter(pk=research.identifier(pk)).first()
    if row is None:
        raise NotFound("小组已关闭，或当前账户没有访问权限。")
    if lock:
        row = ReaderGroup.objects.select_for_update().get(pk=row.pk)
        if row.archived or not row.user.is_active or (row.user_id != user.pk and not row.memberships.filter(user=user).exists()):
            raise NotFound("小组已关闭。")
    return row


def summary(row, user):
    return {"id": str(row.pk), "title": research.unpack(row).get("title", "未命名小组"), "kind": row.kind,
        "revision": row.revision, "is_owner": row.user_id == user.pk, "archived": row.archived,
        "member_count": row.memberships.filter(user__is_active=True).count() + 1}


def member_bindings(row):
    if row.archived or not row.user.is_active:
        return []
    return [{"user_id": str(row.user_id), "membership_id": f"owner:{row.user_id}"}, *[
        {"user_id": str(member.user_id), "membership_id": str(member.pk)}
        for member in row.memberships.filter(user__is_active=True).order_by("user_id")]]


def invite_output(row, *, owner=False):
    return {"id": str(row.pk), "group_id": str(row.group_id), "recipient": row.user.display_name or row.user.username,
        "expires_at": row.expires_at, "accepted": bool(row.accepted_at), "revoked": bool(row.revoked_at),
        "expired": row.expires_at <= timezone.now(),
        "token": decrypt_private_text(row.token_ciphertext) if owner and not row.accepted_at and not row.revoked_at and row.expires_at > timezone.now() else None}


def detail(user, pk):
    row = group_for(user, pk)
    members = [{"user_id": str(row.user_id), "membership_id": f"owner:{row.user_id}", "name": row.user.display_name or row.user.username, "is_owner": True}]
    members.extend({"user_id": str(member.user_id), "membership_id": str(member.pk), "name": member.user.display_name or member.user.username,
        "is_owner": False} for member in row.memberships.select_related("user").filter(user__is_active=True).order_by("created_at", "id")[:100])
    result = {"owner_id": str(user.pk), "group": summary(row, user), "members": members, "invitations": []}
    if row.user_id == user.pk:
        result["invitations"] = [invite_output(invite, owner=True) for invite in row.invitations.select_related("user").filter(
            revoked_at__isnull=True, accepted_at__isnull=True, expires_at__gt=timezone.now()).order_by("created_at", "id")[:100]]
    if not accessible(user).filter(pk=row.pk, revision=row.revision).exists():
        raise research.ResearchConflict("小组成员正在变化，请重新读取。")
    return result


def receipt_result(user, pk, request_id):
    row = accessible(user).filter(pk=pk).first()
    return {"owner_id": str(user.pk), "group_id": str(pk), "request_id": str(request_id),
        "available": row is not None, "group": summary(row, user) if row else None}


def lookup(user, request_id, group_id=None):
    if group_id is None:
        row = ReaderGroup.objects.filter(user=user, request_id=request_id).first()
        if row is None:
            raise NotFound("尚未查到本次创建回执，请核对小组列表。")
        return receipt_result(user, row.pk, request_id)
    saved = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id,
        target_key=sha256(f"reader-group:{group_id}".encode()).hexdigest()).first()
    if saved is None:
        raise NotFound("尚未查到本次小组操作回执，请核对成员与邀请。")
    return receipt_result(user, group_id, request_id)


@transaction.atomic
def create(user, data):
    privacy.lock_owner(user)
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    row = ReaderGroup.objects.filter(user=user, request_id=data["request_id"]).first()
    if row:
        if research.unpack(row).get("creation_fingerprint") != fingerprint:
            raise research.ResearchConflict("原小组创建请求已经使用，请核对结果。")
        return receipt_result(user, row.pk, data["request_id"])
    if ReaderGroup.objects.filter(user=user, archived=False).count() >= 30:
        raise ValidationError("每个账户最多创建30个使用中的小组，请先整理已有小组。")
    row = ReaderGroup.objects.create(user=user, request_id=data["request_id"], kind=data["kind"],
        data_ciphertext=research.pack({"title": data["title"], "creation_fingerprint": fingerprint}))
    return receipt_result(user, row.pk, data["request_id"])


def archive(row):
    row.archived = True
    payload = research.unpack(row)
    # Keep only the creation fingerprint so delayed retries cannot reopen a group.
    row.data_ciphertext = research.pack({"creation_fingerprint": payload.get("creation_fingerprint", "")})
    row.revision += 1
    row.save(update_fields=["archived", "data_ciphertext", "revision", "updated_at"])
    row.invitations.update(revoked_at=timezone.now(), token_ciphertext=b"")
    row.memberships.all().delete()


@transaction.atomic
def command(user, pk, data):
    privacy.lock_owner(user)
    key = sha256(f"reader-group:{pk}".encode()).hexdigest()
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=data["request_id"]).first()
    if receipt:
        if receipt.target_key != key or receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求已用于其他小组操作。")
        return receipt_result(user, pk, data["request_id"])
    verb = data["action"]
    row = group_for(user, pk, owner=verb != "leave", lock=True)
    research.expect(row, data["expected_revision"])
    if verb == "rename":
        payload = research.unpack(row)
        payload["title"] = data["title"]
        row.data_ciphertext = research.pack(payload)
    elif verb == "archive":
        archive(row)
    elif verb == "leave":
        if row.user_id == user.pk:
            raise ValidationError("小组创建者请关闭小组，不能直接退出。")
        row.memberships.filter(user=user).delete()
        row.invitations.filter(user=user, accepted_at__isnull=True).update(revoked_at=timezone.now(), token_ciphertext=b"")
    elif verb == "remove":
        member = row.memberships.filter(pk=data["membership_id"]).first()
        if member is None:
            raise research.ResearchConflict("该成员已经退出，请重新读取。")
        row.invitations.filter(user=member.user, accepted_at__isnull=True).update(revoked_at=timezone.now(), token_ciphertext=b"")
        member.delete()
    elif verb == "invite":
        recipient = get_user_model().objects.filter(username=data["username"], is_active=True).first()
        if recipient is None or recipient.pk == row.user_id or row.memberships.filter(user=recipient).exists():
            raise ValidationError("请核对收件账户，已加入的成员不需要重复邀请。")
        pending = row.invitations.filter(revoked_at__isnull=True, accepted_at__isnull=True, expires_at__gt=timezone.now())
        if pending.filter(user=recipient).exists():
            raise ValidationError("该账户已有有效邀请，请使用或撤销原邀请。")
        if pending.count() >= 100 or row.memberships.count() >= 99:
            raise ValidationError("小组最多100人，待处理邀请最多100项。")
        token = secrets.token_urlsafe(32)
        ReaderGroupInvite.objects.create(pk=uuid5(data["request_id"], f"reader-group-invite:{row.pk}:{recipient.pk}"), user=recipient, group=row,
            token_hash=sha256(token.encode()).hexdigest(), token_ciphertext=encrypt_private_text(token), expires_at=timezone.now() + timedelta(days=7))
    elif verb == "revoke_invite":
        invite = row.invitations.filter(pk=data["invitation_id"]).first()
        if invite is None:
            raise NotFound("邀请已不存在。")
        invite.revoked_at, invite.token_ciphertext = timezone.now(), b""
        invite.save(update_fields=["revoked_at", "token_ciphertext", "updated_at"])
    if verb != "archive":
        row.revision += 1
        row.save(update_fields=["data_ciphertext", "revision", "updated_at"])
    KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"], target_key=key,
        fingerprint=fingerprint, applied_saved=verb not in {"archive", "leave"})
    return receipt_result(user, pk, data["request_id"])


@transaction.atomic
def accept(user, *, token=None, invitation_id=None):
    privacy.lock_owner(user)
    rows = ReaderGroupInvite.objects.filter(user=user)
    invite = rows.filter(token_hash=sha256(token.encode()).hexdigest()).first() if token else rows.filter(pk=invitation_id).first()
    if invite is None:
        raise NotFound("此邀请不属于当前账户，或已失效。")
    row = ReaderGroup.objects.select_for_update().get(pk=invite.group_id)
    invite.refresh_from_db()
    if invite.accepted_at:
        if invite.membership_id and row.memberships.filter(pk=invite.membership_id, user=user).exists() and not row.archived:
            return {"owner_id": str(user.pk), "group_id": str(row.pk)}
        raise research.ResearchConflict("该邀请已使用；退出或移除后需要创建者重新邀请。")
    if row.archived or not row.user.is_active or invite.revoked_at or invite.expires_at <= timezone.now():
        raise ValidationError("邀请已过期或撤销，请联系创建者重新邀请。")
    if row.memberships.count() >= 99:
        raise ValidationError("小组已达到100人上限。")
    member, _ = ReaderGroupMember.objects.get_or_create(group=row, user=user)
    invite.membership, invite.accepted_at, invite.token_ciphertext = member, timezone.now(), b""
    invite.save(update_fields=["membership", "accepted_at", "token_ciphertext", "updated_at"])
    row.revision += 1
    row.save(update_fields=["revision", "updated_at"])
    return {"owner_id": str(user.pk), "group_id": str(row.pk)}
