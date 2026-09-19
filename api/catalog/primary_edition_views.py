from django.http import Http404
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition
from catalog.services.editorial_revision import EditorialRevisionError
from catalog.services.primary_editions import prepare_primary_edition, select_primary_edition
from catalog.services.publication_commands import PublicationCommandError
from common.permissions import CanAccessBackOffice, CanPublishWork


class PrimaryEditionRequestSerializer(serializers.Serializer):
    request_key = serializers.UUIDField()
    fingerprint = serializers.CharField(min_length=64, max_length=64)
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("请明确确认主版本切换及其公开影响。")
        return value


class PrimaryEditionView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanPublishWork()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, edition_id):
        try:
            return Response(prepare_primary_edition(edition_id, actor=request.user))
        except Edition.DoesNotExist as error:
            raise Http404 from error
        except PublicationCommandError as error:
            return Response({"code": "publication.primary_conflict", "detail": str(error)}, status=409)

    @extend_schema(request=PrimaryEditionRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, edition_id):
        serializer = PrimaryEditionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = select_primary_edition(edition_id, actor=request.user, fingerprint=serializer.validated_data["fingerprint"],
                                            request_key=serializer.validated_data["request_key"])
        except Edition.DoesNotExist as error:
            raise Http404 from error
        except (PublicationCommandError, EditorialRevisionError) as error:
            return Response({"code": "publication.primary_conflict", "detail": str(error)}, status=409)
        return Response(result)
