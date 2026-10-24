"""M08 composes existing private media, PDF candidates and editorial revisions."""
from hashlib import sha256
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Exists, OuterRef, Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.cover_views import cover_state
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.media_views import MediaAssetSerializer
from catalog.models import Edition, EditorialRevision, MediaAsset, MediaRendition, Work
from catalog.services.covers import CoverCandidateUnavailable, prepare_cover_page
from catalog.services.editorial_issues import EditConflict
from catalog.services.media import (PUBLIC_METADATA_FIELDS, RENDITION_WIDTHS, WORK_IMAGE_SLOTS, MEDIA_DISPLAY_USES, DEFAULT_MEDIA_DISPLAY_USES,
    build_rendition, ingest_image, normalize_media_transform, _select_prepared_work_image)
from catalog.services.workspace_edits import workspace_edit_version
from catalog.workspace_receipt_views import actor_for
from common.permissions import CanAccessBackOffice, CanEditMetadata
from ingestion.models import AuditEvent

ACTION = "media.workspace.command"


class MediaTransformSerializer(serializers.Serializer):
    x = serializers.FloatField(min_value=0, max_value=1)
    y = serializers.FloatField(min_value=0, max_value=1)
    width = serializers.FloatField(min_value=0, max_value=1)
    height = serializers.FloatField(min_value=0, max_value=1)
    rotation = serializers.ChoiceField(choices=[0, 90, 180, 270])

    def validate(self, value):
        try:
            return normalize_media_transform(value)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error


class MediaRevisionMetadataSerializer(serializers.Serializer):
    alt_text = serializers.CharField(max_length=1000, allow_blank=True)
    source_label = serializers.CharField(max_length=300, allow_blank=True)
    source_url = serializers.URLField(max_length=1000, allow_blank=True)
    rights = serializers.CharField(max_length=4000, allow_blank=True)
    license = serializers.CharField(max_length=200, allow_blank=True)
    credit = serializers.CharField(max_length=500, allow_blank=True)


class MediaWorkspaceCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=64)
    action = serializers.ChoiceField(choices=["save", "restore", "clear", "pdf_page"])
    slot = serializers.ChoiceField(choices=list(WORK_IMAGE_SLOTS))
    media_id = serializers.UUIDField(required=False)
    rendition_id = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    transform = MediaTransformSerializer(required=False)
    metadata = MediaRevisionMetadataSerializer(required=False)
    display_uses = serializers.ListField(child=serializers.ChoiceField(choices=MEDIA_DISPLAY_USES), max_length=4, required=False)

    def validate(self, value):
        fields = {"save": {"media_id", "transform", "metadata"}, "restore": {"rendition_id"}, "pdf_page": {"page"}, "clear": set()}[value["action"]]
        expected = fields | {"request_id", "expected_version", "action", "slot"}
        if value["action"] == "save" and "display_uses" in self.initial_data:
            expected.add("display_uses")
        if set(self.initial_data) != expected:
            raise serializers.ValidationError("操作参数不完整或含有其他操作的字段，请重新打开媒体编辑。")
        if len(value.get("display_uses", [])) != len(set(value.get("display_uses", []))):
            raise serializers.ValidationError("同一图片用途不能重复。")
        return value


class MediaWorkspaceReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField()
    edition_id = serializers.UUIDField()
    slot = serializers.ChoiceField(choices=list(WORK_IMAGE_SLOTS), allow_null=True)
    media = MediaAssetSerializer(required=False)


class MediaWorkspaceCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class MediaWorkspaceRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    url = serializers.CharField()
    media = MediaAssetSerializer()
    metadata = MediaRevisionMetadataSerializer()
    transform = MediaTransformSerializer(allow_null=True)
    display_uses = serializers.ListField(child=serializers.ChoiceField(choices=MEDIA_DISPLAY_USES))


class MediaWorkspaceHistorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = MediaWorkspaceRevisionSerializer(many=True)


class MediaWorkspacePublicationSerializer(serializers.Serializer):
    state = serializers.CharField()
    revision = serializers.IntegerField(allow_null=True)
    primary_rendition_id = serializers.UUIDField(allow_null=True)


class MediaWorkspaceSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    title = serializers.CharField()
    slot = serializers.ChoiceField(choices=list(WORK_IMAGE_SLOTS))
    version = serializers.CharField()
    has_unpublished_changes = serializers.BooleanField()
    cover = serializers.JSONField()
    current = MediaWorkspaceRevisionSerializer(allow_null=True)
    history = MediaWorkspaceHistorySerializer()
    publication = MediaWorkspacePublicationSerializer()


def selected_rendition(edition, slot):
    draft = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").order_by("-revision").first()
    relation = WORK_IMAGE_SLOTS[slot]["relation"]
    identifier = (draft.materialized_preview if draft else {}).get(relation, getattr(edition.work, f"{relation}_id"))
    return MediaRendition.objects.select_related("media").filter(pk=identifier, kind=WORK_IMAGE_SLOTS[slot]["kind"]).first() if identifier else None


def media_history(edition, slot, current=None):
    config = WORK_IMAGE_SLOTS[slot]
    # Saved commands retain un-published choices as well as formal revision references.
    saved = AuditEvent.objects.filter(action=ACTION, after__work_id=str(edition.work_id), after__slot=slot).annotate(
        rendition_key=Replace(KeyTextTransform("rendition_id", "after"), Value("-"), Value(""), output_field=CharField()),
    ).filter(rendition_key=Replace(Cast(OuterRef("pk"), CharField()), Value("-"), Value("")))
    identifiers = []
    canonical_id = getattr(edition.work, f"{config['relation']}_id")
    if canonical_id:
        identifiers.append(str(canonical_id))
    if current:
        identifiers.append(str(current.pk))
    return MediaRendition.objects.annotate(saved_command=Exists(saved)).filter(kind=config["kind"], requested_width=640).filter(
        Q(saved_command=True) | Q(pk__in=identifiers) | Q(publication_references__catalog_revision__edition__work_id=edition.work_id)
        | Q(editorial_references__editorial_revision__target_type="work", editorial_references__editorial_revision__target_id=edition.work_id)
    ).select_related("media").distinct().order_by("-created_at", "pk")


def rendition_payload(row):
    return {"id": str(row.pk), "created_at": row.created_at, "width": row.width, "height": row.height,
            "url": f"/api/catalog/admin/media/renditions/{row.pk}/file/", "media": MediaAssetSerializer(row.media).data,
            "metadata": {field: row.metadata_snapshot.get(field, "") for field in PUBLIC_METADATA_FIELDS},
            "display_uses": row.metadata_snapshot.get("display_uses", list(DEFAULT_MEDIA_DISPLAY_USES)),
            "transform": row.metadata_snapshot.get("_transform")}


def version_for(edition, cover):
    return sha256(f"{workspace_edit_version(edition)}:{cover['fingerprint']}".encode()).hexdigest()


def receipt(row):
    result = {"owner_id": str(row.actor_id), "request_id": row.request_id, "edition_id": row.object_id,
              "state": "cancelled" if row.after.get("cancelled") else "applied", "next_url": row.after.get("next_url", ""), "slot": row.after.get("slot")}
    if row.after.get("prepared_media_id"):
        result["media"] = MediaAssetSerializer(get_object_or_404(MediaAsset, pk=row.after["prepared_media_id"])).data
    return result


class MediaWorkspaceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(parameters=[OpenApiParameter("slot", enum=list(WORK_IMAGE_SLOTS)), OpenApiParameter("history_page", type=int)], responses=MediaWorkspaceSerializer)
    def get(self, request, edition_id):
        edition = get_object_or_404(Edition.objects.select_related("work", "active_catalog_revision"), pk=edition_id)
        slot = serializers.ChoiceField(choices=list(WORK_IMAGE_SLOTS)).run_validation(request.query_params.get("slot", "cover"))
        cover, _, _ = cover_state(edition, request)
        current = selected_rendition(edition, slot)
        paginator = Paginator(media_history(edition, slot, current), 12)
        page_number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("history_page", 1))
        page = paginator.get_page(page_number)
        publication = edition.active_catalog_revision
        published_media = (publication.snapshot.get("work", {}).get(WORK_IMAGE_SLOTS[slot]["snapshot"]) or {}) if publication else {}
        draft = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").order_by("-revision").first()
        config = WORK_IMAGE_SLOTS[slot]
        return Response({"edition_id": str(edition.pk), "work_id": str(edition.work_id), "title": edition.work.title,
            "slot": slot, "version": version_for(edition, cover), "cover": cover,
            "has_unpublished_changes": bool(draft and {config["field"], config["relation"]}.intersection(draft.patch)),
            "current": rendition_payload(current) if current else None,
            "publication": {"state": edition.state, "revision": publication.revision if publication else None,
                            "primary_rendition_id": published_media.get("primary_rendition_id")},
            "history": {"count": paginator.count, "page": page.number, "pages": paginator.num_pages,
                        "results": [rendition_payload(row) for row in page.object_list]}})

    @extend_schema(request=MediaWorkspaceCommandSerializer, responses=MediaWorkspaceReceiptSerializer)
    @transaction.atomic
    def post(self, request, edition_id):
        actor = actor_for(request, True)
        serializer = MediaWorkspaceCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(request.data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if previous:
            if previous.object_id != str(edition_id) or (not previous.after.get("cancelled") and previous.after.get("signature") != signature):
                raise EditConflict("此请求编号已用于其他媒体操作，请先查回原结果。")
            return Response(receipt(previous))
        edition = get_object_or_404(Edition.objects.select_for_update(), pk=edition_id)
        edition.work = Work.objects.select_for_update().get(pk=edition.work_id)
        cover, asset, _ = cover_state(edition, request)
        if data["expected_version"] != version_for(edition, cover):
            raise EditConflict("材料或当前图片已变化。你的裁切保留，请重新读取并核对后保存。")
        slot, action = data["slot"], data["action"]
        after = {"work_id": str(edition.work_id), "slot": slot, "signature": signature,
                 "next_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#work"}
        try:
            if action == "pdf_page":
                if not asset:
                    raise ValidationError("当前出版版本尚无可选页的PDF。")
                candidate = prepare_cover_page(asset, data["page"])
                with candidate.thumbnail.open("rb") as source:
                    upload = SimpleUploadedFile("pdf-page.jpg", source.read(20 * 1024 * 1024 + 1), content_type="image/jpeg")
                media, _ = ingest_image(upload, actor=actor, metadata={"source_type": "pdf", "source_label": f"馆藏PDF · 实际第{candidate.page_index}页"})
                build_rendition(media.pk, width=320, kind="thumbnail")
                after.update(prepared_media_id=str(media.pk), asset_id=str(asset.pk), candidate_id=str(candidate.pk))
            else:
                primary = None
                if action == "save":
                    get_object_or_404(MediaAsset, pk=data["media_id"])
                    variants = {width: build_rendition(data["media_id"], width=width, kind=WORK_IMAGE_SLOTS[slot]["kind"],
                        transform=data["transform"], metadata_override=data["metadata"], display_uses=data.get("display_uses")) for width in RENDITION_WIDTHS}
                    primary = variants[640]
                elif action == "restore":
                    primary = get_object_or_404(media_history(edition, slot), pk=data["rendition_id"])
                    if not primary.file.storage.exists(primary.file.name):
                        raise ValidationError("历史图片文件暂时不可用，请选择其他版本。")
                _select_prepared_work_image(edition.pk, primary, slot=slot, actor=actor, automatic=False, expected_work_id=edition.work_id)
                after["rendition_id"] = str(primary.pk) if primary else None
        except (ValueError, CoverCandidateUnavailable, OSError) as error:
            raise ValidationError(str(error)) from error
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="edition", object_id=str(edition.pk), request_id=str(data["request_id"]), after=after)
        return Response(receipt(row))


class MediaWorkspaceReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=MediaWorkspaceReceiptSerializer)
    def get(self, request, edition_id, request_id):
        actor = actor_for(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, object_id=str(edition_id), request_id=str(request_id))))

    @extend_schema(request=MediaWorkspaceCancelSerializer, responses=MediaWorkspaceReceiptSerializer)
    @transaction.atomic
    def post(self, request, edition_id, request_id):
        actor = actor_for(request, True)
        serializer = MediaWorkspaceCancelSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只能停止原待定请求。")
        get_object_or_404(Edition, pk=edition_id)
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row and row.object_id != str(edition_id): raise EditConflict("请求不属于当前出版版本。")
        if not row:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="edition", object_id=str(edition_id), request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))


class MediaSourceFileView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(exclude=True)
    def get(self, request, media_id):
        media = get_object_or_404(MediaAsset, pk=media_id)
        try:
            handle = media.file.open("rb")
        except OSError:
            return Response({"detail": "原图暂时无法读取，请重新加载或选用其他图片。"}, status=503)
        response = FileResponse(handle, content_type=media.media_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response
