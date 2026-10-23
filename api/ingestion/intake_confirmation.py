"""Final-atlas intake identity review over the existing upload and catalog store."""
import json
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Asset, DocumentType, Edition, Work
from catalog.services.editorial_issues import EditConflict
from catalog.services.cataloging_sessions import open_cataloging_session, CatalogingSessionConflict
from catalog.services.work_editor import WorkflowEditError
from ingestion.services.entity_resolution_decisions import ResolutionDecisionError
from common.capabilities import Capability, has_capability
from common.permissions import CanEditMetadata
from ingestion.models import AuditEvent, FieldLock, UploadItem
from ingestion.services.catalog_reconciliation import normalize_doi, normalize_isbn, normalize_title
from ingestion.services.dispatch import schedule_upload_item
from ingestion.upload_workspace import UploadWorkspaceItemSerializer

ACTION = "intake_identity.command"
ACTIVE = {"received", "validating", "deduplicating", "extracting", "ocr", "metadata", "linking", "indexing", "preparing_public_asset", "syncing_cloud"}


def actor_for(request, lock=False):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("登录账户已变化，请重新打开收件确认。")
    if not lock:
        return request.user
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前会话不能继续编目操作。")
    return actor


def item_rows():
    return UploadItem.objects.select_related("batch", "edition__work").exclude(status="deleted")


def latest(item, actor=None):
    rows = AuditEvent.objects.filter(action=ACTION, object_id=str(item.pk)).exclude(after__cancelled=True)
    return rows.filter(actor=actor).order_by("-created_at", "-pk").first() if actor else rows.order_by("-created_at", "-pk").first()


def version(item):
    event = latest(item)
    values = [str(item.pk), item.updated_at.isoformat(), str(item.edition_id),
              item.edition.updated_at.isoformat() if item.edition_id else "",
              item.edition.work.updated_at.isoformat() if item.edition_id else "", str(event.pk) if event else ""]
    return sha256("|".join(values).encode()).hexdigest()


def edition_version(edition):
    return f"{edition.updated_at.isoformat()}:{edition.work.updated_at.isoformat()}"


def candidates(item, query="", work_id=None):
    metadata = item.recognized_metadata or {}
    title = str(metadata.get("title") or (item.edition.work.title if item.edition_id else "")).strip()
    if work_id:
        condition = Q(work_id=work_id)
    elif query:
        condition = Q(work__title__icontains=query) | Q(contributions__person__preferred_name__icontains=query) | Q(isbn__icontains=query) | Q(doi__icontains=query)
    else:
        ids = item.entity_resolution_candidates.filter(target_type="work", candidate_entity_type="work").values_list("candidate_entity_id", flat=True)
        # IDs from resolution records are strings; do not cast unchecked legacy values to UUID in SQL.
        from uuid import UUID
        safe = []
        for value in ids[:30]:
            try: safe.append(UUID(str(value)))
            except (ValueError, TypeError, AttributeError): pass
        condition = Q(work_id__in=safe) | Q(pk=item.edition_id)
        if title: condition |= Q(work__title__icontains=title[:160])
        if metadata.get("isbn"): condition |= Q(isbn__iexact=normalize_isbn(metadata["isbn"])) | Q(isbn__iexact=str(metadata["isbn"]))
        if metadata.get("doi"): condition |= Q(doi__iexact=normalize_doi(metadata["doi"]))
        if item.sha256: condition |= Q(assets__sha256=item.sha256, assets__kind="original")
    return Edition.objects.filter(condition).select_related("work").prefetch_related("contributions__person").distinct().annotate(
        intake_priority=Case(When(pk=item.edition_id, then=Value(0)), When(work__title__iexact=title, then=Value(1)), default=Value(2), output_field=IntegerField())
    ).order_by("intake_priority", "-updated_at", "pk")


def candidate_row(edition, item, duplicate_ids):
    metadata = item.recognized_metadata or {}
    authors = [c.person.preferred_name for c in edition.contributions.all() if c.role == "author" and c.approved]
    reasons = []
    if edition.pk in duplicate_ids: reasons.append("原件内容摘要完全一致")
    if normalize_title(edition.work.title) == normalize_title(metadata.get("title")) and edition.work.title: reasons.append("规范题名一致")
    if metadata.get("isbn") and normalize_isbn(metadata["isbn"]) == normalize_isbn(edition.isbn): reasons.append("ISBN一致")
    if metadata.get("doi") and normalize_doi(metadata["doi"]) == normalize_doi(edition.doi): reasons.append("DOI一致")
    incoming_authors = metadata.get("authors") or []
    if isinstance(incoming_authors, list) and set(map(normalize_title, incoming_authors)) & set(map(normalize_title, authors)): reasons.append("已确认作者有交集")
    return {"id": str(edition.pk), "work_id": str(edition.work_id), "version": edition_version(edition),
            "title": edition.work.title, "document_type": edition.work.document_type, "authors": authors,
            "year": edition.publication_year, "publisher": edition.publisher, "language": edition.work.language,
            "version_label": edition.version_label, "isbn": edition.isbn, "doi": edition.doi, "state": edition.state,
            "exact_duplicate": edition.pk in duplicate_ids, "reasons": reasons,
            "cover_url": f"/api/catalog/admin/media/renditions/{edition.work.cover_rendition_id}/file/" if edition.work.cover_rendition_id else "",
            "edit_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}"}


class IntakeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=160, required=False, allow_blank=True)
    work = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)


class IntakeChoiceSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["use_edition", "new_version", "new_work"])
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    candidate_version = serializers.CharField(required=False, allow_blank=True)
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    title = serializers.CharField(max_length=1000, allow_blank=True)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class IntakeCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["save", "defer", "confirm"])
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField()
    choice = IntakeChoiceSerializer()
    confirm = serializers.BooleanField(required=False, default=False)


class IntakeWorkspaceSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    version = serializers.CharField()
    item = UploadWorkspaceItemSerializer()
    batch_id = serializers.UUIDField()
    preview_url = serializers.CharField()
    draft = IntakeChoiceSerializer(allow_null=True)
    candidates = serializers.ListField(child=serializers.JSONField())
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    busy = serializers.BooleanField()
    confirmed = serializers.BooleanField()
    next_url = serializers.CharField(allow_blank=True)


class IntakeReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)


def receipt(event):
    return {"owner_id": str(event.actor_id), "request_id": event.request_id,
            "state": "cancelled" if event.after.get("cancelled") else "applied", "next_url": event.after.get("next_url", "")}


class IntakeConfirmationView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    def handle_exception(self, error):
        if isinstance(error, (CatalogingSessionConflict, WorkflowEditError, ResolutionDecisionError)):
            return super().handle_exception(EditConflict(str(error)))
        return super().handle_exception(error)

    @extend_schema(parameters=[IntakeQuerySerializer], responses=IntakeWorkspaceSerializer)
    def get(self, request, item_id):
        actor = actor_for(request)
        item = get_object_or_404(item_rows().prefetch_related("metadata_candidates", "edition__contributions__person"), pk=item_id)
        query = IntakeQuerySerializer(data=request.query_params); query.is_valid(raise_exception=True)
        params = query.validated_data
        pages = Paginator(candidates(item, params.get("q", ""), params.get("work")), 16)
        page = pages.get_page(params["page"])
        duplicate_ids = set(Asset.objects.filter(kind="original", sha256=item.sha256).values_list("edition_id", flat=True)) if item.sha256 else set()
        saved = latest(item, actor)
        identity = (item.preflight_summary or {}).get("intake_identity") or {}
        return Response({"owner_id": str(actor.pk), "version": version(item),
            "item": UploadWorkspaceItemSerializer(item, context={"request": request}).data,
            "batch_id": str(item.batch_id), "preview_url": f"/api/ingestion/items/{item.pk}/preview/" if item.file else "",
            "draft": saved.after.get("choice") if saved else None,
            "candidates": [candidate_row(row, item, duplicate_ids) for row in page],
            "count": pages.count, "page": page.number, "pages": pages.num_pages,
            "busy": item.status in ACTIVE or item.dispatch_status in {"pending", "queued", "running"},
            "confirmed": bool(identity.get("confirmed")), "next_url": identity.get("next_url", "")})

    @extend_schema(request=IntakeCommandSerializer, responses=IntakeReceiptSerializer)
    @transaction.atomic
    def post(self, request, item_id):
        actor = actor_for(request, True)
        incoming = IntakeCommandSerializer(data=request.data); incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        if set(request.data) - set(IntakeCommandSerializer().fields) or set(request.data.get("choice", {})) - set(IntakeChoiceSerializer().fields):
            raise ValidationError("收件确认包含未支持的字段。")
        fingerprint = salted_hmac(ACTION, json.dumps(request.data, sort_keys=True, ensure_ascii=False)).hexdigest()
        old = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if old:
            if old.after.get("fingerprint") != fingerprint or old.object_id != str(item_id):
                raise EditConflict("原请求已停止或用于不同的收件决定，请查回原记录。")
            return Response(receipt(old))
        item = get_object_or_404(item_rows().select_for_update(of=("self",)), pk=item_id)
        if data["expected_version"] != version(item):
            raise EditConflict("收件或候选版本已更新，当前选择保留，请重新核对。")
        if item.workflow_state in {"cancelled", "archived"} or item.status == "withdrawn":
            raise EditConflict("该收件已经停止或归档，请先在原流程核对恢复。")
        choice = {**data["choice"], "edition_id": str(data["choice"]["edition_id"]) if data["choice"].get("edition_id") else None}
        next_url = ""
        if data["action"] == "confirm":
            if not data["confirm"]: raise ValidationError("请明确确认作品、版本和处理方式。")
            if item.status in ACTIVE or item.dispatch_status in {"pending", "queued", "running"}:
                raise EditConflict("文件任务仍在处理，待当前结果完成后确认身份。")
            if (item.preflight_summary or {}).get("intake_identity", {}).get("confirmed"):
                raise EditConflict("收件身份已确认，后续修改请进入馆藏工作页。")
            target = get_object_or_404(Edition.objects.select_for_update(of=("self", "work")).select_related("work"), pk=choice["edition_id"]) if choice.get("edition_id") else None
            if choice["mode"] != "new_work" and (not target or choice.get("candidate_version") != edition_version(target)):
                raise EditConflict("请重新选择并核对当前出版版本。")
            if target and choice["mode"] != "new_work" and target.work.document_type != choice["document_type"]:
                raise ValidationError("所选作品的文献类型不同，请选择正确材料或建立新作品。")
            duplicate = Asset.objects.filter(kind="original", sha256=item.sha256).first() if item.sha256 else None
            exact = bool(choice["mode"] == "use_edition" and target and duplicate and duplicate.edition_id == target.pk)
            if duplicate and not exact and not item.asset_id:
                raise ValidationError("此原件已经属于馆内版本，请选择内容摘要完全一致的已有版本；不能用同一原件重复建立作品或版本。")
            if item.status == "failed" and not exact:
                raise ValidationError("文件处理失败，请先恢复原文件任务，再确认作品身份。")
            if item.edition_id and target and item.edition_id != target.pk and choice["mode"] == "use_edition":
                raise EditConflict("历史收件已经形成独立版本和文件引用，请在原馆藏核对后追加文件，不能在此移动原件。")
            if choice["mode"] == "new_work":
                if not choice["title"].strip(): raise ValidationError("建立新作品前请确认题名。")
                if item.edition_id:
                    current = item.edition
                    if current.state == "published" or current.work.editions.exclude(pk=current.pk).exists() or current.field_locks.exists() or UploadItem.objects.filter(edition=current).exclude(pk=item.pk).exists():
                        raise EditConflict("已有馆藏不能改作新作品，请保留原记录并进入馆藏修订。")
                    if current.work.title != choice["title"] or current.work.document_type != choice["document_type"]:
                        from catalog.services.work_editor import save_workflow_section
                        save_workflow_section(current, "work", {"title": choice["title"], "document_type": choice["document_type"]}, actor=actor)
                    target = current
                else:
                    work = Work.objects.create(title=choice["title"].strip(), document_type=choice["document_type"], language=str(item.recognized_metadata.get("language") or "zh-CN"))
                    target = Edition.objects.create(work=work)
                    for name, value in {"title": work.title, "document_type": work.document_type}.items():
                        FieldLock.objects.create(edition=target, field_name=name, locked_by=actor, locked_value=value, reason="收件时明确确认作品身份")
            elif choice["mode"] == "new_version":
                if item.edition_id:
                    current = item.edition
                    if current.state != "draft" or current.field_locks.exists() or UploadItem.objects.filter(edition=current).exclude(pk=item.pk).exists(): raise EditConflict("已确认或公开版本不能在收件时改换作品。")
                    if current.work_id != target.work_id:
                        from ingestion.models import EntityResolutionCandidate
                        from ingestion.services.entity_resolution_decisions import decide_entity_resolution
                        candidate, _ = EntityResolutionCandidate.objects.get_or_create(upload_item=item, target_type="work", source_name=current.work.title,
                            candidate_entity_type="work", candidate_entity_id=str(target.work_id), defaults={"label": target.work.title, "match_reasons": ["管理员在收件中明确选定作品"]})
                        decide_entity_resolution(candidate, action="link_existing", target_type="work", target_id=str(target.work_id), confirm_identity=True, actor=actor, reason=choice["note"], correlation_id=str(data["request_id"]))
                        current.refresh_from_db()
                    target = current
                else:
                    target = Edition.objects.create(work=target.work)
            if not target: raise ValidationError("当前操作缺少确定的作品或版本。")
            item.edition = target
            item.document_type_hint = choice["document_type"]
            next_url = f"/admin/library/works/{target.work_id}?edition={target.pk}#bibliography"
            identity = {"confirmed": True, "mode": choice["mode"], "edition_id": str(target.pk), "work_id": str(target.work_id), "request_id": str(data["request_id"]), "next_url": next_url, "setup_pending": choice["mode"] != "use_edition" and not item.asset_id}
            reconciliation_mode = "existing_edition" if choice["mode"] == "use_edition" else "existing_work" if choice["mode"] == "new_version" else "new"
            item.preflight_summary = {**item.preflight_summary, "intake_identity": identity, "catalog_reconciliation": {
                "mode": reconciliation_mode, "work_id": str(target.work_id), "edition_id": str(target.pk), "requires_review": False, "decision_source": "manual_intake_confirmation"}}
            if exact:
                item.status, item.stage_progress = "ready", 100
                item.error_code, item.error_message = "", ""
                item.asset = duplicate
            elif not item.asset_id:
                item.status, item.stage_progress = "received", 25
                item.error_code, item.error_message = "", ""
            item.save(update_fields=["edition", "document_type_hint", "preflight_summary", "status", "stage_progress", "asset", "error_code", "error_message", "updated_at"])
            if exact:
                from ingestion.services.workflow import transition_upload_item
                transition_upload_item(item, UploadItem.WorkflowState.READY, actor=actor, reason="管理员确认复用完全重复原件", force=True)
                from ingestion.services.pipeline import refresh_batch
                refresh_batch(item.batch)
            if not exact and not item.asset_id:
                session, _ = open_cataloging_session(actor=actor, upload_item_id=item.pk, request_key=data["request_id"])
                next_url = f"/admin/cataloging/{session.pk}"
                item.preflight_summary["intake_identity"]["next_url"] = next_url
                item.save(update_fields=["preflight_summary", "updated_at"])
                schedule_upload_item(str(item.pk))
        event = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="UploadItem", object_id=str(item.pk),
            request_id=str(data["request_id"]), after={"fingerprint": fingerprint, "operation": data["action"], "choice": choice, "next_url": next_url})
        return Response(receipt(event))


class IntakeReceiptCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class IntakeReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=IntakeReceiptSerializer)
    def get(self, request, item_id, request_id):
        actor = actor_for(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, object_id=str(item_id), request_id=str(request_id))))

    @extend_schema(request=IntakeReceiptCancelSerializer, responses=IntakeReceiptSerializer)
    @transaction.atomic
    def post(self, request, item_id, request_id):
        actor = actor_for(request, True)
        get_object_or_404(item_rows(), pk=item_id)
        if request.data != {"action": "cancel_pending"}: raise ValidationError("仅接受停止原待定请求。")
        event = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if event and event.object_id != str(item_id): raise EditConflict("此请求不属于当前收件。")
        if not event: event = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="UploadItem", object_id=str(item_id), request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(event))
