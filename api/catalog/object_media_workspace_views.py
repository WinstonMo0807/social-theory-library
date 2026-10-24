"""M08 reuses the same immutable crop/history workspace for knowledge images."""
import mimetypes
from pathlib import Path
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.media_workspace_views import (MediaWorkspaceCommandSerializer, MediaWorkspaceSerializer,
    MediaWorkspaceCancelSerializer, MediaWorkspaceReceiptSerializer, rendition_payload)
from catalog.media_views import MediaAssetSerializer
from catalog.models import EditorialRevision, MediaAsset, MediaRendition, ScholarProfile
from catalog.services.editorial_issues import EditConflict
from catalog.services.knowledge_media import (TARGETS, image_fields, image_selection, image_fingerprint,
    image_legacy_file, image_status, select_prepared_knowledge_image)
from catalog.services.scholar_media import (portrait_selection, portrait_selection_fingerprint, select_prepared_scholar_portrait)
from catalog.services.media import RENDITION_WIDTHS, MAX_IMAGE_BYTES, build_rendition, ingest_image
from catalog.services.workspace_edits import _digest
from catalog.workspace_receipt_views import actor_for
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice, CanEditMetadata
from ingestion.models import AuditEvent

MODELS = {**TARGETS, "scholar_profile": ScholarProfile}
ACTION = "media.object_workspace.command"


class ObjectMediaCommandSerializer(MediaWorkspaceCommandSerializer):
    action = serializers.ChoiceField(choices=["save", "restore", "clear", "legacy"])
    slot = serializers.ChoiceField(choices=["portrait", "hero"])

    def validate(self, value):
        if value["action"] == "legacy":
            if set(self.initial_data) != {"request_id", "expected_version", "action", "slot"}:
                raise serializers.ValidationError("旧图仅从当前对象读取，不接受任意文件路径。")
            return value
        return super().validate(value)


class ObjectMediaWorkspaceSerializer(MediaWorkspaceSerializer):
    edition_id = serializers.UUIDField(allow_null=True)
    work_id = serializers.UUIDField(allow_null=True)
    target_type = serializers.ChoiceField(choices=list(MODELS))
    target_id = serializers.UUIDField()
    editor_url = serializers.CharField()
    slot = serializers.ChoiceField(choices=["portrait", "hero"])


class ObjectMediaReceiptSerializer(MediaWorkspaceReceiptSerializer):
    edition_id = serializers.UUIDField(allow_null=True)
    target_type = serializers.ChoiceField(choices=list(MODELS))
    target_id = serializers.UUIDField()
    slot = serializers.ChoiceField(choices=["portrait", "hero"], allow_null=True)


def target_for(object_type, object_id, lock=False):
    if object_type not in MODELS or object_type != "scholar_profile" and not settings.THEORY_SYSTEM_ENABLED:
        raise NotFound("此图片对象尚未启用。")
    query = MODELS[object_type].objects.all()
    if object_type == "scholar_profile": query = query.select_related("person")
    if lock: query = query.select_for_update()
    return get_object_or_404(query, pk=object_id)


def info(target, object_type):
    scholar = object_type == "scholar_profile"
    draft = EditorialRevision.objects.filter(target_type=object_type, target_id=target.pk, status="draft").order_by("-revision").first()
    canonical = portrait_selection(target) if scholar else image_selection(target)
    key = "portrait_selection" if scholar else "image_selection"
    selected = (draft.materialized_preview.get(key) if draft else None) or canonical
    version = portrait_selection_fingerprint(target, draft=draft) if scholar else image_fingerprint(target, draft)
    return draft, canonical, selected, version


def history_for(target, object_type, current=None):
    kind = "portrait" if object_type == "scholar_profile" else "hero"
    canonical = target.person.portrait_rendition_id if kind == "portrait" else getattr(target, f"{image_fields(target)[0]}_id")
    return MediaRendition.objects.filter(kind=kind, requested_width=640).filter(
        Q(pk__in=[row for row in [canonical, current] if row]) |
        Q(editorial_references__editorial_revision__target_type=object_type, editorial_references__editorial_revision__target_id=target.pk)
    ).select_related("media").distinct().order_by("-created_at", "pk")


def editor_url(object_type, object_id):
    return {"scholar_profile":f"/admin/scholars/{object_id}", "knowledge_node":f"/admin/theories/{object_id}",
        "reading_path":f"/admin/reading-paths?path={object_id}", "topic":f"/admin/topics/{object_id}",
        "discipline":f"/admin/theories/disciplines?discipline={object_id}",
        "subdiscipline":f"/admin/theories/subdisciplines?subdiscipline={object_id}"}[object_type]


def receipt(row):
    result = {"owner_id":str(row.actor_id), "request_id":row.request_id, "target_type":row.after["target_type"],
        "target_id":row.object_id, "edition_id":None, "state":"cancelled" if row.after.get("cancelled") else "applied",
        "next_url":row.after.get("next_url", ""), "slot":row.after.get("slot")}
    if row.after.get("prepared_media_id"):
        result["media"] = MediaAssetSerializer(get_object_or_404(MediaAsset,pk=row.after["prepared_media_id"])).data
    return result


class ObjectMediaBase(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    def actor(self, request, object_type, *, lock=False):
        actor = actor_for(request, lock)
        if object_type != "scholar_profile" and not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
            raise PermissionDenied("当前账户没有知识内容的图片编辑权限。")
        return actor


class ObjectMediaWorkspaceView(ObjectMediaBase):
    @extend_schema(parameters=[OpenApiParameter("history_page", type=int)], responses=ObjectMediaWorkspaceSerializer)
    def get(self, request, object_type, object_id):
        target = target_for(object_type, object_id)
        draft, canonical, selected, version = info(target, object_type)
        kind = "portrait" if object_type == "scholar_profile" else "hero"
        current = MediaRendition.objects.select_related("media").filter(pk=selected["rendition_id"], kind=kind).first() if selected["rendition_id"] else None
        if selected["rendition_id"] and current is None:
            raise EditConflict("当前图片修订缺失，请从历史记录核对，不能当作空图片覆盖。")
        paginator = Paginator(history_for(target, object_type, selected["rendition_id"]), 12)
        number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("history_page", 1))
        page = paginator.get_page(number)
        status = target.editorial_status if object_type == "scholar_profile" else image_status(target)
        return Response({"target_type":object_type,"target_id":str(target.pk),"edition_id":None,"work_id":None,
            "editor_url":editor_url(object_type,target.pk), "title":target.person.preferred_name if kind=="portrait" else getattr(target,"name",getattr(target,"canonical_name_zh",getattr(target,"title",""))),
            "slot":kind,"version":version,"has_unpublished_changes":selected!=canonical,
            "current":rendition_payload(current) if current else None,
            "cover":{"image_url":f"/api/catalog/admin/media-objects/{object_type}/{target.pk}/legacy/" if selected.get("legacy_path") and not current else "",
                "page_count":0,"asset_id":None,"state":"not_applicable","has_unpublished_cover":selected!=canonical,"results":[]},
            "publication":{"state":status,"revision":None,"primary_rendition_id":canonical["rendition_id"] if status=="published" else None},
            "history":{"count":paginator.count,"page":page.number,"pages":paginator.num_pages,"results":[rendition_payload(row) for row in page.object_list]}})

    @extend_schema(request=ObjectMediaCommandSerializer, responses=ObjectMediaReceiptSerializer)
    @transaction.atomic
    def post(self, request, object_type, object_id):
        actor = self.actor(request, object_type, lock=True)
        check=ObjectMediaCommandSerializer(data=request.data);check.is_valid(raise_exception=True);data=check.validated_data
        signature=_digest({**data,"target_type":object_type,"target_id":object_id})
        previous=AuditEvent.objects.filter(actor=actor,action=ACTION,request_id=str(data["request_id"])).first()
        if previous:
            if previous.object_id!=str(object_id) or previous.after["target_type"]!=object_type or previous.after.get("cancelled") or previous.after.get("signature")!=signature:
                raise EditConflict("原请求已停止或内容不匹配，请先查回原操作。")
            return Response(receipt(previous))
        target=target_for(object_type,object_id,lock=True)
        status=target.editorial_status if object_type=="scholar_profile" else image_status(target)
        if status in {"archived","merged","rejected"} or object_type=="scholar_profile" and target.person.authority_status in {"merged","rejected"}:
            raise EditConflict("该对象已经停用，请先恢复并核对身份，再处理图片。")
        draft,_,selected,version=info(target,object_type)
        kind="portrait" if object_type=="scholar_profile" else "hero"
        if data["slot"]!=kind or data["expected_version"]!=version:
            raise EditConflict("对象或当前图片已经变化，请保留裁切并重新核对。")
        try:
            primary=None
            prepared=None
            if data["action"]=="legacy":
                file=target.person.portrait if object_type=="scholar_profile" else image_legacy_file(target)
                if not file or selected.get("legacy_path")!=file.name or selected.get("rendition_id"):
                    raise ValidationError("当前选图不是旧文件，请重新读取后核对。")
                with file.open("rb") as source:
                    upload=SimpleUploadedFile(Path(file.name).name,source.read(MAX_IMAGE_BYTES+1),content_type=mimetypes.guess_type(file.name)[0] or "")
                prepared,_=ingest_image(upload,actor=actor,metadata={"source_label":"原对象保留图片"})
                build_rendition(prepared.pk,width=320,kind="thumbnail")
            elif data["action"]=="save":
                get_object_or_404(MediaAsset,pk=data["media_id"])
                variants={width:build_rendition(data["media_id"],width=width,kind=kind,transform=data["transform"],metadata_override=data["metadata"]) for width in RENDITION_WIDTHS}
                primary=variants[640]
            elif data["action"]=="restore":
                primary=get_object_or_404(history_for(target,object_type,selected["rendition_id"]),pk=data["rendition_id"])
                if not primary.file.storage.exists(primary.file.name):raise ValidationError("历史文件暂时不可读，请选择其他版本。")
            if data["action"]=="legacy":
                pass  # Preparing a copy never changes the object's selected image.
            elif object_type=="scholar_profile":
                select_prepared_scholar_portrait(target.pk,primary,actor=actor,expected_person_id=target.person_id,fingerprint=version)
            else:
                select_prepared_knowledge_image(object_type,target.pk,primary,actor=actor,fingerprint=version)
        except (ValueError,OSError) as error:
            raise ValidationError(str(error)) from error
        row=AuditEvent.objects.create(actor=actor,action=ACTION,object_type=target._meta.label,object_id=str(target.pk),request_id=str(data["request_id"]),
            after={"target_type":object_type,"slot":kind,"signature":signature,"rendition_id":str(primary.pk) if primary else None,
                "prepared_media_id":str(prepared.pk) if prepared else None,"next_url":editor_url(object_type,target.pk)})
        return Response(receipt(row))


class ObjectMediaReceiptView(ObjectMediaBase):
    @extend_schema(responses=ObjectMediaReceiptSerializer)
    def get(self, request, object_type, object_id, request_id):
        actor=self.actor(request,object_type)
        row=get_object_or_404(AuditEvent,actor=actor,action=ACTION,object_id=str(object_id),after__target_type=object_type,request_id=str(request_id))
        return Response(receipt(row))

    @extend_schema(request=MediaWorkspaceCancelSerializer, responses=ObjectMediaReceiptSerializer)
    @transaction.atomic
    def post(self, request, object_type, object_id, request_id):
        actor=self.actor(request,object_type,lock=True)
        if object_type not in MODELS:raise NotFound("不支持的图片对象。")
        if request.data!={"action":"cancel_pending"}:raise ValidationError("仅接受停止原请求。")
        row=AuditEvent.objects.filter(actor=actor,action=ACTION,request_id=str(request_id)).first()
        if row and (row.object_id!=str(object_id) or row.after["target_type"]!=object_type):raise EditConflict("原请求属于其他对象。")
        if not row:row=AuditEvent.objects.create(actor=actor,action=ACTION,object_type=MODELS[object_type]._meta.label,object_id=str(object_id),request_id=str(request_id),after={"target_type":object_type,"cancelled":True})
        return Response(receipt(row))


class ObjectMediaLegacyFileView(AdminPrivateResponseMixin, APIView):
    permission_classes=[CanAccessBackOffice]
    @extend_schema(exclude=True)
    def get(self,request,object_type,object_id):
        target=target_for(object_type,object_id)
        file=target.person.portrait if object_type=="scholar_profile" else image_legacy_file(target)
        if not file:raise NotFound("尚无旧图片。")
        try:handle=file.open("rb")
        except OSError:return Response({"detail":"旧图片文件暂时无法读取。"},status=503)
        response=FileResponse(handle);response["X-Content-Type-Options"]="nosniff"
        return response
