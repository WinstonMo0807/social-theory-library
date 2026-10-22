"""Explicit public excerpts join original owner lists and encrypted annotations."""
from hashlib import sha256
import json
from uuid import uuid5

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Edition, Page
from catalog.services.publication_eligibility import public_edition_q
from . import booklists, notebook, privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .models import Annotation, ReadingList, ResearchProject
from .serializers import AnnotationSerializer

SALT = "reading.citation-booklist-undo.v1"


def target(list_id):
    return sha256(f"citation-booklist:{list_id}".encode()).hexdigest()


def receipt(user, list_id, request_id):
    row = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if row and row.target_key != target(list_id):
        raise research.ResearchConflict("此请求属于另一项保存，请核对原结果。")
    return row


def result(user, list_id, saved, undo_token=None):
    # Minimal recovery metadata survives deletion; it cannot recreate a list or note.
    notes = Annotation.objects.filter(user=user, selector__citation_request_id=str(saved.request_id))
    return {"owner_id": str(user.pk), "list_id": str(list_id), "request_id": str(saved.request_id),
        "exists": ReadingList.objects.filter(user=user, pk=list_id).exists(), "undone": not saved.applied_saved,
        "note_ids": [str(pk) for pk in notes.values_list("pk", flat=True)[:20]], "undo_token": undo_token}


def lookup(user, list_id, request_id):
    saved = receipt(user, list_id, request_id)
    if saved is None:
        raise NotFound("尚未查到这次保存的回执，请保留原请求后重试。")
    return result(user, list_id, saved)


@transaction.atomic
def save(request, list_id, data):
    user = request.user
    privacy.lock_owner(user)
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    saved = receipt(user, list_id, data["request_id"])
    if saved:
        if saved.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求的输入已改变，请先核对已保存内容。")
        return result(user, list_id, saved)
    row = ReadingList.objects.select_for_update().filter(user=user, pk=list_id).first()
    if row is None:
        raise NotFound("这份本人书单已不存在。")
    if booklists.version(row) != data["expected_version"]:
        raise research.ResearchConflict("书单已经修改，请重新选择当前版本后保存。")
    privacy.require_retention(user, "saved_knowledge")
    edition = Edition.objects.filter(public_edition_q(), pk=data["edition_id"]).first()
    if edition is None:
        raise ValidationError("该出版版本当前未公开，请重新核对来源。")
    raw = json.loads(json.dumps(data.get("reference"), default=str))
    resolved = research.resolve_reference(raw, AnonymousUser(), strict=True) if raw else None
    if resolved and str(edition.pk) != resolved.get("edition_id"):
        raise ValidationError("所选原文与书目版本不一致。")
    if data["save_excerpt"] and not resolved:
        raise ValidationError("保存摘录需要可复核的原文位置。")
    if data.get("note") and not data["save_excerpt"]:
        raise ValidationError("备注随阅读记录保存，请勾选保存原文与来源，或清空备注。")
    frozen_reference = research.compact_reference(resolved) if resolved else None
    old_item = row.items.filter(work_id=edition.work_id).first()
    previous = None if old_item is None else {"removed_at": old_item.removed_at.isoformat() if old_item.removed_at else None, "order": old_item.order}
    item, _ = booklists.add_work(row, edition.work_id)
    notes = []
    if data["save_excerpt"]:
        privacy.require_retention(user, "personal_notes")
        anchors = resolved.get("anchors") or [resolved]
        if sum(len(anchor["quote"]) for anchor in anchors) > 20000:
            raise ValidationError("本次摘录超过20000字，请缩小选文范围。")
        for index, anchor in enumerate(anchors):
            page = Page.objects.select_related("asset").get(asset_id=anchor["asset_id"], index=anchor["pdf_page"])
            note = AnnotationSerializer(context={"request": request}).create({
                "request_id": uuid5(data["request_id"], f"citation:{index}"), "asset": page.asset, "page": page,
                "kind": "note" if index == 0 and data.get("note") else "highlight", "quote": anchor["quote"],
                "body": data.get("note", "") if index == 0 else "", "tags": [],
                "selector": {"page_index": page.index, "citation_request_id": str(data["request_id"]),
                    "booklist_id": str(row.pk), "citation_reference": research.compact_reference(anchor)}})
            notes.append({"id": str(note.pk), "version": privacy.version(note)})
    # Both the public source and list write are in this transaction. A revision
    # change observed here rolls the whole command back rather than saving stale text.
    if frozen_reference:
        research.resolve_reference(frozen_reference, AnonymousUser(), strict=True)
    if not Edition.objects.filter(public_edition_q(), pk=edition.pk).exists():
        raise research.ResearchConflict("公开来源刚刚撤下，本次保存未完成。")
    saved = KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"],
        target_key=target(list_id), fingerprint=fingerprint, applied_saved=True)
    token = signing.dumps({"owner": str(user.pk), "list": str(row.pk), "request": str(saved.request_id),
        "fingerprint": fingerprint, "version": booklists.version(row), "item": str(item.pk),
        "previous": previous, "notes": notes}, salt=SALT, compress=True)
    return result(user, list_id, saved, token)


@transaction.atomic
def undo(user, list_id, token):
    privacy.lock_owner(user)
    try:
        data = signing.loads(token, salt=SALT, max_age=3600)
    except signing.BadSignature:
        raise ValidationError("撤销凭证已过期或无效，请到书单和阅读记录中管理已保存内容。") from None
    if data.get("owner") != str(user.pk) or data.get("list") != str(list_id):
        raise ValidationError("撤销凭证不属于当前账户和书单。")
    saved = receipt(user, list_id, data["request"])
    if saved is None or saved.fingerprint != data["fingerprint"]:
        raise research.ResearchConflict("未找到对应保存回执。")
    if not saved.applied_saved:
        return result(user, list_id, saved)
    row = ReadingList.objects.select_for_update().filter(user=user, pk=list_id).first()
    if row is None or booklists.version(row) != data["version"]:
        raise research.ResearchConflict("书单已经修改或删除，请在阅读记录和书单中分别管理，避免覆盖后续操作。")
    notes = list(Annotation.objects.select_for_update().filter(user=user, pk__in=[note["id"] for note in data["notes"]]))
    expected = {note["id"]: note["version"] for note in data["notes"]}
    if len(notes) != len(expected) or any(privacy.version(note) != expected[str(note.pk)] for note in notes):
        raise research.ResearchConflict("本次摘录已修改或删除，不能整批撤销。请到阅读记录逐项管理。")
    if any(privacy.linked_memories(user, note.pk) for note in notes):
        raise research.ResearchConflict("摘录已关联学术记忆，请在阅读记录预览删除影响后管理。")
    if notes:
        # Existing encrypted project links must not be silently removed. Bound
        # this rare undo scan; normal privacy operations handle larger accounts.
        projects = list(ResearchProject.objects.filter(user=user).only("id", "data_ciphertext")[:2001])
        if len(projects) > 2000:
            raise research.ResearchConflict("请到阅读记录逐项管理，核对关联后再删除。")
        if any(link.get("category") == "annotations" and link.get("id") in expected
               for project in projects for link in research.unpack(project).get("notebook_links", [])):
            raise research.ResearchConflict("摘录已加入研究，请在阅读记录核对关联后管理。")
    item = row.items.filter(pk=data["item"]).first()
    if item is None:
        raise research.ResearchConflict("书单条目已经改变，请重新读取。")
    previous = data["previous"]
    if previous is None:
        item.delete()
        booklists.touch(row)
    elif previous["removed_at"]:
        item.removed_at, item.order = parse_datetime(previous["removed_at"]), previous["order"]
        item.save(update_fields=["removed_at", "order", "updated_at"])
        booklists.touch(row)
    for note in notes:
        notebook.annotation_retired(user, note.pk, retire=True)
        note.delete()
    saved.applied_saved = False
    saved.save(update_fields=["applied_saved", "updated_at"])
    return result(user, list_id, saved)
