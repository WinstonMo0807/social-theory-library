"""Protected inventory, edition creation, explicit file selection and old-file access."""
import csv
import io

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.edition_file_workspace_serializers import (FileAdoptionPreviewOutput, FileAdoptionResultOutput,
    NewWorkEditionOutput, WorkFileUploadOutput, WorkFilesStateOutput, WorkFileRightsUpdateOutput, WorkFilePublicPreparationResult)
from catalog.models import Asset, Edition
from catalog.services import edition_file_workspace as workspace
from catalog.services.edition_files import EditionFileError
from catalog.services.edition_files import edition_file_result
from catalog.services.edition_file_intake import generate_reader
from common.permissions import CanAccessBackOffice, CanEditMetadata, CanPublishWork, CanViewEvidence
from distribution.views import AssetFileView, _download_mode
from ingestion.models import UploadItem


class WorkFilesQuery(serializers.Serializer):
    edition = serializers.UUIDField(required=False)
    asset = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    impact_page = serializers.IntegerField(min_value=1, default=1)
    history_page = serializers.IntegerField(min_value=1, default=1)


def result(call, *, status=200):
    try:
        return Response(call(), status=status)
    except ObjectDoesNotExist:
        return Response({"detail": "作品、版本或文件不存在。"}, status=404)
    except EditionFileError as error:
        return Response({"detail": str(error), "code": error.code}, status=error.status)


class WorkFilesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice, CanViewEvidence]

    @extend_schema(parameters=[WorkFilesQuery], responses=WorkFilesStateOutput)
    def get(self, request, work_id):
        query = WorkFilesQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        return result(lambda: workspace.state(work_id, request.user, edition_id=data.get("edition"),
            asset_id=data.get("asset"), page=data["page"], impact_page=data["impact_page"], history_page=data["history_page"]))


class NewWorkEditionInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    expected_work_updated_at = serializers.DateTimeField()
    version_label = serializers.CharField(max_length=120)
    publication_year = serializers.IntegerField(min_value=1, max_value=9999, required=False, allow_null=True)
    publisher = serializers.CharField(max_length=300, required=False, allow_blank=True)


class NewWorkEditionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=NewWorkEditionInput, responses={201: NewWorkEditionOutput})
    def post(self, request, work_id):
        schema = NewWorkEditionInput(data=request.data)
        schema.is_valid(raise_exception=True)
        return result(lambda: workspace.create_edition(work_id, request.user, schema.validated_data), status=201)


class FileAdoptionInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    fingerprint = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("请明确确认阅读文件切换与历史保留。")
        return value


class EditionFileAdoptionView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        if getattr(self, "swagger_fake_view", False):
            return [CanAccessBackOffice(), CanViewEvidence()]
        if self.request.method == "POST":
            published = Edition.objects.filter(pk=self.kwargs["edition_id"], state="published").exists()
            return [CanPublishWork()] if published else [CanEditMetadata()]
        return [CanAccessBackOffice(), CanViewEvidence()]

    @extend_schema(responses=FileAdoptionPreviewOutput)
    def get(self, request, edition_id, asset_id):
        return result(lambda: workspace.prepare_adoption(edition_id, asset_id, request.user))

    @extend_schema(request=FileAdoptionInput, responses={202: FileAdoptionResultOutput})
    def post(self, request, edition_id, asset_id):
        schema = FileAdoptionInput(data=request.data)
        schema.is_valid(raise_exception=True)
        return result(lambda: workspace.adopt_file(edition_id, asset_id, request.user, schema.validated_data), status=202)


class WorkFileRightsInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    expected_asset_updated_at = serializers.DateTimeField()
    rights_note = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError("此操作只允许修改版权说明。")
        return super().to_internal_value(data)


class EditionFileRightsView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=WorkFileRightsInput, responses=WorkFileRightsUpdateOutput)
    def patch(self, request, edition_id, asset_id):
        schema = WorkFileRightsInput(data=request.data)
        schema.is_valid(raise_exception=True)
        return result(lambda: workspace.update_rights(edition_id, asset_id, request.user, schema.validated_data))


class GenerateReaderInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    expected_asset_updated_at = serializers.DateTimeField()


class PreparePublicFileInput(GenerateReaderInput):
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("请确认文件将传至公开分发存储。")
        return value


class EditionPreparePublicFileView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishWork]

    @extend_schema(request=PreparePublicFileInput, responses={202: WorkFilePublicPreparationResult})
    def post(self, request, edition_id, asset_id):
        schema = PreparePublicFileInput(data=request.data)
        schema.is_valid(raise_exception=True)
        return result(lambda: workspace.prepare_public_file(edition_id, asset_id, request.user, schema.validated_data), status=202)


class EditionGenerateReaderView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=GenerateReaderInput, responses={202: WorkFileUploadOutput})
    def post(self, request, edition_id, asset_id):
        schema = GenerateReaderInput(data=request.data)
        schema.is_valid(raise_exception=True)
        def perform():
            item = generate_reader(edition_id, asset_id, request.user, schema.validated_data)
            return {**edition_file_result(item, created=False), "request_key": str(schema.validated_data["request_key"])}
        return result(perform, status=202)


class EditionFileRequestView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=WorkFileUploadOutput)
    def get(self, request, edition_id, request_key):
        item = get_object_or_404(UploadItem.objects.select_related("edition__work", "batch"),
                                pk=request_key, edition_id=edition_id, batch__created_by=request.user)
        return Response(edition_file_result(item, created=False))


class EditionFileContentView(AdminPrivateResponseMixin, AssetFileView):
    permission_classes = [CanViewEvidence]
    http_method_names = ["get", "head", "options"]

    def _local_file_available(self):
        return True

    def _resolve_file_assets(self, request, asset_id):
        asset = get_object_or_404(Asset.objects.select_related("edition__work"), pk=asset_id, edition_id=self.kwargs["edition_id"])
        if asset.mime_type != "application/pdf" and not _download_mode(request):
            raise ValidationError("此格式请下载原件；在线阅读使用生成的 PDF 副本。")
        return asset, asset, _download_mode(request)

    def _response_access_status(self, anchor):
        return Asset.AccessStatus.PRIVATE

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    def get(self, request, edition_id, asset_id):
        response = super().get(request, asset_id)
        return self.file_headers(request, response, edition_id, asset_id)

    def head(self, request, edition_id, asset_id):
        response = super().head(request, asset_id)
        return self.file_headers(request, response, edition_id, asset_id)

    def file_headers(self, request, response, edition_id, asset_id):
        if response.status_code in {200, 206}:
            asset = get_object_or_404(Asset, pk=asset_id, edition_id=edition_id)
            response["Content-Type"] = asset.mime_type or "application/octet-stream"
            response["Content-Disposition"] = content_disposition_header(bool(_download_mode(request)), asset.original_filename or f"{asset.pk}.pdf")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


class EditionFileImpactCSVView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice, CanViewEvidence]

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    def get(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        asset = request.query_params.get("asset")
        if asset:
            asset = serializers.UUIDField().run_validation(asset)
            get_object_or_404(edition.assets, pk=asset)
        rows = workspace.impact_rows(edition, asset)
        if rows.count() > 10000:
            raise ValidationError("影响条目超过单次导出上限，请选择具体文件后导出。")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["证据编号", "馆藏证据", "文件编号", "PDF页序", "印刷页码", "审核状态", "维护入口"])
        for row in rows.iterator(chunk_size=200):
            value = workspace.impact_row(row)
            writer.writerow([safe_cell(value[key]) for key in ("id", "title", "asset_id", "file_page_index", "printed_page_label", "status", "href")])
        response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="catalog-file-impact.csv"'
        return response


def safe_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text
