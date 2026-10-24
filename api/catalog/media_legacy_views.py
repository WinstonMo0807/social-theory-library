"""Read recorded legacy images; prepare copies through the existing media command."""
from hashlib import sha256
import json
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import urlencode

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import CatalogPublicationRevision, Edition, EditorialRevision
from catalog.services.editorial_issues import EditConflict
from catalog.services.media import MAX_IMAGE_BYTES, WORK_IMAGE_SLOTS, build_rendition, ingest_image
from common.permissions import CanAccessBackOffice
from ingestion.models import AuditEvent


SOURCES = ("current", "editorial", "publication", "before", "after")


class LegacyImageItemSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=SOURCES)
    record_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    label = serializers.CharField()
    fingerprint = serializers.CharField()
    url = serializers.CharField()


class LegacyImageHistorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = LegacyImageItemSerializer(many=True)


def context(object_type, object_id, slot):
    if object_type == "edition":
        target = get_object_or_404(Edition.objects.select_related("work"), pk=object_id)
        serializers.ChoiceField(choices=list(WORK_IMAGE_SLOTS)).run_validation(slot)
    else:
        from catalog.object_media_workspace_views import target_for
        target = target_for(object_type, object_id)
        if slot != ("portrait" if object_type == "scholar_profile" else "hero"):
            raise ValidationError("图片用途与当前对象不一致。")
    return target


def legacy_queries(object_type, target, slot):
    """SQL-paginated original records, never a directory scan or synthesized history."""
    if object_type == "edition":
        config = WORK_IMAGE_SLOTS[slot]
        field = config["field"]
        storage = getattr(target.work, field).storage
        prefix = "public/covers/" if slot == "cover" else "public/recommendations/"
        specifications = [
            ("current", Edition.objects.filter(pk=target.pk), F(f"work__{field}"), "当前作品保留原图"),
            ("editorial", EditorialRevision.objects.filter(target_type="work", target_id=target.work_id),
             KeyTextTransform.from_lookup(f"materialized_preview__{field}"), "作品编辑修订保留原图"),
            ("publication", CatalogPublicationRevision.objects.filter(edition=target),
             KeyTextTransform.from_lookup(f"snapshot__work__{field}"), "本出版版本发布修订保留原图"),
        ]
    else:
        from catalog.services.knowledge_media import image_legacy_file
        scholar = object_type == "scholar_profile"
        file = target.person.portrait if scholar else image_legacy_file(target)
        storage = file.storage
        prefix = "public/people/" if scholar else "public/knowledge/"
        selection = "portrait_selection" if scholar else "image_selection"
        current_field = "person__portrait" if scholar else file.field.name
        events = AuditEvent.objects.filter(object_id=str(target.pk),
            object_type="ScholarProfile" if scholar else object_type,
            action="scholar.portrait_publish" if scholar else "knowledge.image_publish")
        specifications = [
            ("current", type(target).objects.filter(pk=target.pk), F(current_field), "当前对象保留原图"),
            ("editorial", EditorialRevision.objects.filter(target_type=object_type, target_id=target.pk),
             KeyTextTransform.from_lookup(f"materialized_preview__{selection}__legacy_path"), "编辑修订保留原图"),
            ("before", events, KeyTextTransform.from_lookup("before__legacy_path"), "图片发布前保留原图"),
            ("after", events, KeyTextTransform.from_lookup("after__legacy_path"), "图片发布后保留原图"),
        ]
    queries = {}
    for source, query, filename, label in specifications:
        query = query.order_by().annotate(
            legacy_name=Cast(filename, CharField()), legacy_source=Value(source, output_field=CharField()),
            legacy_record=Cast("pk", CharField()), legacy_created=F("updated_at" if source == "current" else "created_at"),
            legacy_label=Value(label, output_field=CharField()),
        ).filter(legacy_name__startswith=prefix).exclude(legacy_name__contains="..").exclude(legacy_name__contains="\\")
        queries[source] = query.values("legacy_record", "legacy_created", "legacy_source", "legacy_label", "legacy_name")
    return queries, storage


def fingerprint(object_type, target, slot, row):
    return sha256(json.dumps([object_type, str(target.pk), slot, row["legacy_source"],
        str(row["legacy_record"]).replace("-", ""), row["legacy_name"]], ensure_ascii=False).encode()).hexdigest()


def resolve(object_type, target, slot, data):
    queries, storage = legacy_queries(object_type, target, slot)
    query = queries.get(data["legacy_source"])
    row = query.filter(pk=data["legacy_record_id"]).first() if query is not None else None
    if not row:
        raise NotFound("当前对象没有这条旧图片记录，原件未被修改。")
    if fingerprint(object_type, target, slot, row) != data["legacy_fingerprint"]:
        raise EditConflict("旧图片记录已变化，请重新读取历史后选择。")
    return row, storage


def prepare_legacy_image(object_type, target, slot, data, actor):
    row, storage = resolve(object_type, target, slot, data)
    name = row["legacy_name"]
    try:
        with storage.open(name, "rb") as source:
            upload = SimpleUploadedFile(PurePosixPath(name).name, source.read(MAX_IMAGE_BYTES + 1),
                content_type=mimetypes.guess_type(name)[0] or "")
    except OSError as error:
        raise ValidationError("这条历史图片的文件暂时无法读取。记录仍保留，请核对存储或选择其他图片。") from error
    media, _ = ingest_image(upload, actor=actor, metadata={"source_label": row["legacy_label"]})
    build_rendition(media.pk, width=320, kind="thumbnail")
    return media


class LegacyImageHistoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OpenApiParameter("slot", required=True), OpenApiParameter("page", type=int)], responses=LegacyImageHistorySerializer)
    def get(self, request, object_type, object_id):
        slot = request.query_params.get("slot", "cover" if object_type == "edition" else "portrait" if object_type == "scholar_profile" else "hero")
        target = context(object_type, object_id, slot)
        queries, _ = legacy_queries(object_type, target, slot)
        parts = list(queries.values())
        paginator = Paginator(parts[0].union(*parts[1:], all=True).order_by("-legacy_created", "legacy_source", "legacy_record"), 12)
        page = paginator.get_page(serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1)))
        results = []
        for row in page.object_list:
            value = {"source": row["legacy_source"], "record_id": str(serializers.UUIDField().run_validation(row["legacy_record"])),
                "label": row["legacy_label"], "created_at": row["legacy_created"], "fingerprint": fingerprint(object_type, target, slot, row)}
            query = urlencode({"slot": slot, "legacy_source": value["source"], "legacy_record_id": value["record_id"], "legacy_fingerprint": value["fingerprint"]})
            value["url"] = f"/api/catalog/admin/media-legacy/{object_type}/{target.pk}/file/?{query}"
            results.append(value)
        return Response({"count": paginator.count, "page": page.number, "pages": paginator.num_pages, "results": results})


class LegacyImageFileView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(exclude=True)
    def get(self, request, object_type, object_id):
        slot = request.query_params.get("slot")
        target = context(object_type, object_id, slot)
        data = {"legacy_source": serializers.ChoiceField(choices=SOURCES).run_validation(request.query_params.get("legacy_source")),
            "legacy_record_id": serializers.UUIDField().run_validation(request.query_params.get("legacy_record_id")),
            "legacy_fingerprint": serializers.CharField(max_length=64).run_validation(request.query_params.get("legacy_fingerprint"))}
        row, storage = resolve(object_type, target, slot, data)
        name = row["legacy_name"]
        content_type = mimetypes.guess_type(name)[0]
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValidationError("此历史格式不支持直接显示，请在原文件管理中核对。")
        try:
            handle = storage.open(name, "rb")
        except OSError:
            return Response({"detail": "历史记录仍保留，图片文件暂不可读，请核对存储。"}, status=503)
        response = FileResponse(handle, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response
