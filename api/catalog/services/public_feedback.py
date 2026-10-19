"""General site feedback: immutable submissions, explicit handling and receipts."""
import json
import re
from urllib.parse import unquote, urlsplit

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import APIException, ValidationError

from catalog.models import PublicFeedback
from ingestion.models import AuditEvent

CONSENT_VERSION = "feedback-processing-20261018"
PAGE_SIZE = 20
HISTORY_SIZE = 10
ACTION = "public_feedback.updated"


class FeedbackConflict(APIException):
    status_code = 409
    default_detail = "反馈已变化，请核对最新记录；当前输入仍可保留。"
    default_code = "feedback_conflict"


def safe_public_path(raw):
    """Never retain a referrer token or a private/admin path, including legacy rows."""
    value = str(raw or "").strip()
    if len(value) > 400 or not value.startswith("/") or value.startswith("//"):
        return ""
    try:
        for _ in range(4):
            decoded = unquote(value, errors="strict")
            if decoded == value:
                break
            value = decoded
    except UnicodeDecodeError:
        return ""
    if re.search(r"[\\\x00-\x20\x7f]", value) or "%" in value or value.startswith("//"):
        return ""
    parts = urlsplit(value)
    path = parts.path
    if any(segment in {".", ".."} for segment in path.split("/")):
        return ""
    if not re.fullmatch(r"/(?:|(?:explore|works|reader|scholars|topics|theories|theory-schools|subdisciplines|concepts|recommendations|help|about)(?:/[^?#]*)?)", path):
        return ""
    if re.fullmatch(r"/reader/[0-9a-fA-F-]+/?", path):
        pages = re.findall(r"(?:^|&)page=([1-9]\d{0,5})(?:&|$)", parts.query)
        if len(pages) == 1 and sum(item.split("=", 1)[0] == "page" for item in parts.query.split("&")) == 1:
            return f"{path}?page={pages[0]}"
    return path


def fingerprint(value):
    return salted_hmac("stl.public-feedback", json.dumps(value, sort_keys=True, ensure_ascii=False, default=str), algorithm="sha256").hexdigest()


def submit(actor, payload):
    data = {key: payload.get(key, "") for key in ("category", "body", "contact", "path")}
    data["path"] = safe_public_path(data["path"])
    digest = fingerprint({**data, "actor_id": str(actor.pk) if actor else None, "consent": True})
    request_id = payload["request_id"]
    try:
        with transaction.atomic():
            row = PublicFeedback.objects.create(**data, user=actor, request_id=request_id,
                request_fingerprint=digest, consent_at=timezone.now(), consent_version=CONSENT_VERSION)
        return receipt(row), True
    except IntegrityError:
        row = PublicFeedback.objects.filter(request_id=request_id).first()
        if row is None:
            raise
        if not constant_time_compare(row.request_fingerprint, digest):
            raise FeedbackConflict("此提交编号已用于另一份反馈，请保留原请求并核对提交结果。")
        return receipt(row), False


def receipt(row):
    return {"id": str(row.id), "request_id": str(row.request_id), "status": row.status,
            "created_at": row.created_at, "message": "反馈已提交，感谢你的说明。"}


def summary(row):
    return {"id": str(row.id), "category": row.category, "status": row.status,
            "excerpt": " ".join(row.body.split())[:140], "created_at": row.created_at,
            "updated_at": row.updated_at, "revision": row.revision, "follow_up": row.follow_up}


def listing(query):
    rows = PublicFeedback.objects.all()
    if query["q"]:
        rows = rows.filter(body__icontains=query["q"])
    if query["category"]:
        rows = rows.filter(category=query["category"])
    counts = rows.aggregate(total=Count("pk"), **{key: Count("pk", filter=Q(status=key)) for key in PublicFeedback.Status.values})
    if query["status"]:
        rows = rows.filter(status=query["status"])
    count = counts[query["status"]] if query["status"] else counts["total"]
    page = query["page"]
    rows = rows.order_by("-created_at", "-id")[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    return {"count": count, "page": page, "page_size": PAGE_SIZE, "counts": counts, "results": [summary(row) for row in rows]}


def actor_label(actor):
    name = str(getattr(actor, "display_name", "") or "").strip()
    return name if name and "@" not in name else "管理员"


def handling(row):
    return {"status": row.status, "note": row.resolution_note, "follow_up": row.follow_up, "revision": row.revision}


def detail(row, *, history_page=1):
    from reading.source_follow import resolve_public_source

    source = resolve_public_source(row.path)
    source = {key: source[key] for key in ("status", "canonical_path", "title", "authors", "cover_url", "source_type",
        "version_label", "location", "updated_at", "checked_at", "reader_url", "notice")}
    events = AuditEvent.objects.filter(action=ACTION, object_type="public_feedback", object_id=str(row.id)).order_by("-created_at", "-id")
    count = events.count()
    history = []
    for event in events.select_related("actor")[(history_page - 1) * HISTORY_SIZE:history_page * HISTORY_SIZE]:
        history.append({"id": str(event.id), "created_at": event.created_at, "actor": actor_label(event.actor),
            "before": {key: event.before.get(key) for key in ("status", "note", "follow_up", "revision")},
            "after": {key: event.after.get(key) for key in ("status", "note", "follow_up", "revision")}})
    return {**summary(row), "body": row.body, "contact": row.contact, "path": safe_public_path(row.path),
        "consent_at": row.consent_at, "consent_version": row.consent_version,
        "note": row.resolution_note, "handled_by": actor_label(row.handled_by) if row.handled_by_id else "",
        "can_follow_up": bool(row.contact and row.consent_at), "source": source,
        "history": {"count": count, "page": history_page, "page_size": HISTORY_SIZE, "results": history}}


@transaction.atomic
def update(feedback_id, actor, payload):
    row = get_object_or_404(PublicFeedback.objects.select_for_update(of=("self",)).select_related("handled_by"), pk=feedback_id)
    digest = fingerprint(payload)
    prior = AuditEvent.objects.filter(action=ACTION, object_type="public_feedback", object_id=str(row.id), request_id=str(payload["request_id"])).first()
    if prior:
        if prior.actor_id != actor.pk or not constant_time_compare(str(prior.after.get("request_fingerprint", "")), digest):
            raise FeedbackConflict("此处理编号已经用于另一项修改。请重新读取记录。")
        return {"request_id": str(payload["request_id"]), "accepted_revision": prior.after["revision"], "record": detail(row)}
    if row.revision != payload["expected_revision"]:
        raise FeedbackConflict()
    if payload["status"] == PublicFeedback.Status.RESOLVED and len(payload["note"]) < 4:
        raise ValidationError({"note": "标为已处理前，请填写至少 4 字的处理说明。"})
    if row.status == PublicFeedback.Status.RESOLVED and payload["status"] != row.status and len(payload["note"]) < 4:
        raise ValidationError({"note": "重新打开反馈时，请说明原因。"})
    if payload["follow_up"] and (not row.contact or not row.consent_at or payload["status"] == PublicFeedback.Status.RESOLVED):
        raise ValidationError({"follow_up": "只有已同意处理且留有邮箱的未完成反馈可标记待人工回复。"})
    before = handling(row)
    after = {"status": payload["status"], "note": payload["note"], "follow_up": payload["follow_up"]}
    if any(before[key] != value for key, value in after.items()):
        row.status, row.resolution_note, row.follow_up = after["status"], after["note"], after["follow_up"]
        row.revision += 1
        row.handled_by = actor
        row.save(update_fields=["status", "resolution_note", "follow_up", "revision", "handled_by", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=ACTION, object_type="public_feedback", object_id=str(row.id),
        request_id=str(payload["request_id"]), before=before, after={**handling(row), "request_fingerprint": digest})
    return {"request_id": str(payload["request_id"]), "accepted_revision": row.revision, "record": detail(row)}
