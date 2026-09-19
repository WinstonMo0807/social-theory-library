from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.edition_files import EditionFileError, edition_file_result, submit_edition_file
from common.permissions import IsCatalogEditor


class EditionFileInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["supplement", "replace"])
    file = serializers.FileField()
    request_key = serializers.UUIDField()
    expected_updated_at = serializers.DateTimeField()
    expected_reader_asset_id = serializers.UUIDField(required=False, allow_null=True)
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("请确认当前出版版本、文件操作及历史保留说明。")
        return value


class EditionFileView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsCatalogEditor]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, edition_id):
        serializer = EditionFileInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            item, created = submit_edition_file(
                edition_id=edition_id, actor=request.user, uploaded=data["file"], action=data["action"],
                request_key=data["request_key"], expected_updated_at=data["expected_updated_at"].isoformat(),
                expected_reader_asset_id=data.get("expected_reader_asset_id"),
            )
        except EditionFileError as error:
            return Response({"detail": str(error), "code": error.code}, status=error.status)
        return Response(edition_file_result(item, created=created), status=202 if created else 200)
