"""Owner-only derived PDFs. Original DOCX and authoritative paragraph locators stay unchanged."""
import base64
from datetime import timedelta
import hashlib
from pathlib import PurePosixPath
import re
import time
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import httpx
from rest_framework.exceptions import NotFound, ValidationError

from .models import CitationAudit
from .research import ResearchConflict, owned, unpack
from .services import decrypt_private_text, encrypt_private_text

MAX_BYTES = 32 * 1024 * 1024
MAX_PAGES = 1000
ACTIVE = {"queued", "running"}
NOTICE = "这是根据保留的 DOCX 生成的分页预览；字体与分页可能和本机 Word 不同。引文定位仍以原稿部件、段落和字符范围为准，未推测页码或高亮。"
ERRORS = {"disabled": "分页预览服务尚未启用，可继续查看真实解析文字或下载原稿。",
    "queue_unavailable": "分页预览暂时无法排队；原稿和解析文字保留，可稍后重试。",
    "conversion_unavailable": "分页预览暂时不可用；可重试或继续查看真实解析文字。",
    "conversion_timeout": "分页预览等待或处理超时；原稿保留，可稍后重试。",
    "active_content": "此稿件包含不能安全转换的嵌入内容；请查看解析文字或下载原稿。",
    "external_content": "此稿件包含外部关联内容，未联网读取；请查看解析文字或下载原稿。",
    "invalid_package": "此稿件暂不能生成分页预览；原稿与已解析内容保留。",
    "output_size": "派生预览超过处理上限；请查看解析文字或下载原稿。",
    "busy": "分页预览服务正在处理其他文件，请稍后重试。",
    "source_changed": "稿件的处理版本已变化；可基于当前原稿重新生成预览。",
    "canceled": "已取消分页预览，原稿和引文检查任务保留。"}


def enabled():
    return bool(getattr(settings, "DOCX_PREVIEW_ENABLED", False))


def identity(audit):
    return {"content_hash": audit.content_hash, "source_generation": audit.generation,
            "manuscript_revision": unpack(audit).get("manuscript_revision", 1)}


def expired(state):
    at = parse_datetime(state.get("requested_at", ""))
    return not at or at < timezone.now() - timedelta(minutes=10)


def status(audit):
    state = audit.preview_state or {}
    current = identity(audit)
    value = state.get("status", "not_generated")
    if state and any(state.get(key) != val for key, val in current.items()):
        value = "source_changed"
    elif value in ACTIVE and expired(state):
        value = "failed"
    error = "conversion_timeout" if value == "failed" and state.get("status") in ACTIVE else state.get("error_code", "")
    return {"audit_id": str(audit.id), "audit_revision": audit.revision, **current,
        "preview_revision": state.get("revision", 0), "preview_generation": state.get("generation", 0),
        "status": value, "enabled": enabled(), "page_count": state.get("page_count") if value == "completed" else None,
        "converter_version": state.get("converter_version") if value == "completed" else None,
        "fonts_version": state.get("fonts_version") if value == "completed" else None,
        "poll_after_ms": 2000 if value in ACTIVE else None, "notice": NOTICE,
        "message": ERRORS.get(value, ERRORS.get(error, "")) if enabled() else ERRORS["disabled"]}


@transaction.atomic
def command(user, pk, purpose, data):
    from .privacy import command_owner
    user = command_owner(user)
    audit = owned(CitationAudit, user, pk, lock=True)
    if audit.purpose != purpose:
        raise NotFound("私人记录类型不符。")
    if unpack(audit).get("filetype") != "docx":
        raise ValidationError({"file": "PDF 原稿可直接预览，无需转换。"})
    state = audit.preview_state or {}
    current = identity(audit)
    action = data["action"]
    request_id = str(data["request_id"])
    # Receipt replay comes before revision checks, including a lost completed response.
    if state.get("request_id") == request_id:
        if state.get("action") != action or any(state.get(key) != val for key, val in current.items()):
            raise ResearchConflict("此请求已用于另一稿件版本或预览操作，请重新读取状态。")
        return audit
    if data["expected_preview_revision"] != state.get("revision", 0) or data["source_generation"] != audit.generation:
        raise ResearchConflict("预览或稿件状态已更新，请重新读取后再操作；原稿未改变。")
    if action == "generate" and status(audit)["status"] in {*ACTIVE, "completed"}:
        return audit
    if action == "generate" and not enabled():
        raise ValidationError({"preview": ERRORS["disabled"]})
    if action == "generate":
        recent = (timezone.now() - timedelta(minutes=10)).isoformat()
        if CitationAudit.objects.filter(user=user, preview_state__status__in=list(ACTIVE),
                preview_state__requested_at__gte=recent).exclude(pk=audit.pk).count() >= 2:
            raise ValidationError({"preview": "本人已有两项分页预览正在处理，请稍后重试。"})
    generation = state.get("generation", 0) + 1
    audit.preview_state = {**current, "generation": generation, "revision": state.get("revision", 0) + 1,
        "request_id": request_id, "action": action, "status": "queued" if action == "generate" else "canceled",
        "task_id": str(uuid4()), "requested_at": timezone.now().isoformat()}
    audit.preview_ciphertext = b""
    audit.save(update_fields=["preview_state", "preview_ciphertext"])
    if action == "generate":
        task_id = audit.preview_state["task_id"]
        transaction.on_commit(lambda: enqueue(audit.id, generation, task_id))
    return audit


def enqueue(audit_id, generation, task_id):
    try:
        render_document_preview.apply_async(args=[str(audit_id), generation, task_id], task_id=task_id)
    except Exception:
        finish(audit_id, generation, task_id, error="queue_unavailable")


def matches(audit, generation, task_id):
    state = audit.preview_state or {}
    return (state.get("generation") == generation and state.get("task_id") == task_id
            and state.get("status") in ACTIVE and all(state.get(key) == val for key, val in identity(audit).items()))


@transaction.atomic
def finish(audit_id, generation, task_id, *, pdf=None, metadata=None, error=""):
    audit = CitationAudit.objects.select_for_update().filter(pk=audit_id).first()
    if audit is None or not matches(audit, generation, task_id):
        return
    state = audit.preview_state
    if expired(state):
        # The same absolute request deadline governs status, quota and workers.
        # A late conversion cannot resurrect an expired request or its bytes.
        pdf, metadata, error = None, None, "conversion_timeout"
    audit.preview_state = {**state, **(metadata or {}), "revision": state.get("revision", 0) + 1,
        "status": "completed" if pdf is not None else "failed", "error_code": error, "finished_at": timezone.now().isoformat()}
    audit.preview_ciphertext = encrypt_private_text(base64.b64encode(pdf).decode("ascii")) if pdf is not None else b""
    audit.save(update_fields=["preview_state", "preview_ciphertext"])


class PreviewError(RuntimeError):
    pass


def convert(blob, digest):
    socket = str(getattr(settings, "DOCX_PREVIEW_SOCKET", "/run/docx-preview/preview.sock"))
    # Never accept a URL, arbitrary filesystem path, outbound proxy, or user-supplied endpoint.
    if socket != "/run/docx-preview/preview.sock" or not PurePosixPath(socket).is_absolute():
        raise PreviewError("conversion_unavailable")
    timeout = min(100, max(80, int(getattr(settings, "DOCX_PREVIEW_TIMEOUT_SECONDS", 90))))
    started = time.monotonic()
    try:
        from common.on_demand import ensure_service
        ensure_service("docx", unix_socket=socket)
        with httpx.Client(transport=httpx.HTTPTransport(uds=socket), trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(timeout, connect=3)) as client:
            with client.stream("POST", "http://docx-preview/convert", content=blob,
                    headers={"Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}) as response:
                result = bytearray()
                for part in response.iter_bytes():
                    result.extend(part)
                    if len(result) > (MAX_BYTES if response.status_code == 200 else 4096):
                        raise PreviewError("output_size")
                    if time.monotonic() - started > timeout:
                        raise PreviewError("conversion_timeout")
                if response.status_code != 200:
                    import json
                    code = json.loads(result).get("code", "conversion_unavailable")
                    raise PreviewError(code if code in ERRORS else "conversion_unavailable")
                converter, fonts = response.headers.get("X-Converter-Version", ""), response.headers.get("X-Fonts-Version", "")
                if (response.headers.get("X-Source-SHA256") != digest or response.headers.get("X-Preview-Protocol") != "1"
                        or response.headers.get("X-Output-SHA256") != hashlib.sha256(result).hexdigest()
                        or not 1 <= len(converter) <= 200 or not re.fullmatch(r"[0-9a-f]{64}", fonts)
                        or response.headers.get("Content-Type") != "application/pdf" or not result.startswith(b"%PDF-")):
                    raise PreviewError("conversion_unavailable")
        import fitz
        with fitz.open(stream=bytes(result), filetype="pdf") as document:
            if document.needs_pass or not 1 <= document.page_count <= MAX_PAGES:
                raise PreviewError("output_size")
            if any(page.rect.width > 20000 or page.rect.height > 20000 for page in document):
                raise PreviewError("output_size")
            metadata = {"page_count": document.page_count, "output_hash": hashlib.sha256(result).hexdigest(),
                        "converter_version": converter, "fonts_version": fonts}
        return bytes(result), metadata
    except PreviewError:
        raise
    except httpx.TimeoutException as exc:
        raise PreviewError("conversion_timeout") from exc
    except (httpx.HTTPError, ValueError, TypeError, RuntimeError, OSError) as exc:
        raise PreviewError("conversion_unavailable") from exc


@shared_task(soft_time_limit=110, time_limit=120)
def render_document_preview(audit_id, generation, task_id):
    try:
        with transaction.atomic():
            audit = CitationAudit.objects.select_for_update().filter(pk=audit_id).first()
            if audit is None or not matches(audit, generation, task_id) or audit.preview_state.get("status") != "queued":
                return
            if expired(audit.preview_state):
                finish(audit_id, generation, task_id, error="conversion_timeout")
                return
            audit.preview_state = {**audit.preview_state, "status": "running"}
            audit.save(update_fields=["preview_state"])
            blob = base64.b64decode(decrypt_private_text(audit.original_ciphertext))
            digest = audit.content_hash
        if not enabled() or hashlib.sha256(blob).hexdigest() != digest:
            raise PreviewError("conversion_unavailable")
        pdf, metadata = convert(blob, digest)
        finish(audit_id, generation, task_id, pdf=pdf, metadata=metadata)
    except Exception as exc:
        # Exceptions from parsers/Office may contain private data. Store only known codes.
        code = str(exc) if isinstance(exc, PreviewError) and str(exc) in ERRORS else "conversion_unavailable"
        finish(audit_id, generation, task_id, error=code)


def document(audit, generation):
    # The view's owner-filtered record may predate a source reparse or deletion.
    # Load bytes and their identity together, then recheck after decryption.
    def current_record():
        record = CitationAudit.objects.filter(pk=audit.pk, user_id=audit.user_id, purpose=audit.purpose).defer("original_ciphertext").first()
        if record is None:
            raise NotFound("私人稿件不存在或不可访问。")
        return record

    current = current_record()
    if status(current)["status"] != "completed" or generation != current.preview_state.get("generation"):
        raise ResearchConflict("此分页预览尚未完成或版本已变化，请重新读取状态。")
    source = identity(current)
    encrypted_hash = hashlib.sha256(bytes(current.preview_ciphertext)).digest()
    blob = base64.b64decode(decrypt_private_text(current.preview_ciphertext))
    if not blob or len(blob) > MAX_BYTES or hashlib.sha256(blob).hexdigest() != current.preview_state.get("output_hash"):
        raise NotFound("派生预览暂不可读取；原稿仍保留。")
    latest = current_record()
    if (status(latest)["status"] != "completed" or identity(latest) != source
            or latest.preview_state != current.preview_state
            or hashlib.sha256(bytes(latest.preview_ciphertext)).digest() != encrypted_hash):
        raise ResearchConflict("读取期间稿件或派生预览已有变化，请重新读取当前版本。")
    return blob
