from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsKnowledgeEditor
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Contribution, Edition, ScholarProfile


class TimelineParticipantSerializer(serializers.Serializer):
    key = serializers.CharField()
    kind = serializers.ChoiceField(choices=("person", "publisher"))
    person_id = serializers.UUIDField(allow_null=True)
    scholar_id = serializers.UUIDField(allow_null=True)
    publisher_authority_id = serializers.UUIDField(allow_null=True, default=None)
    name = serializers.CharField()
    role = serializers.CharField(allow_blank=True)
    role_label = serializers.CharField()
    href = serializers.CharField(allow_blank=True)
    source = serializers.ChoiceField(choices=("event", "edition"))
    edition_id = serializers.UUIDField(allow_null=True)


class TimelineEditionParticipantsSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    work_title = serializers.CharField()
    version_label = serializers.CharField(allow_blank=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    publisher = serializers.CharField(allow_blank=True)
    publisher_authority_id = serializers.UUIDField(allow_null=True)
    results = TimelineParticipantSerializer(many=True)


class TimelineEditionParticipantsView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=TimelineEditionParticipantsSerializer, parameters=[OpenApiParameter("page", int)])
    def get(self, request, edition_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        edition = get_object_or_404(Edition.objects.select_related("work"), pk=edition_id)
        whole = Q(scope__isnull=True) | Q(scope=None) | Q(scope={}) | (Q(scope__kind="edition") & (
            Q(scope__chapters__isnull=True) | Q(scope__chapters=None) | Q(scope__chapters=[])))
        rows = Contribution.objects.filter(whole, edition=edition, approved=True).select_related("person").order_by("order", "pk")
        # Scope remains visible as a boundary: chapter responsibility is never
        # silently broadened to authorship/translation of the entire edition.
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        pages = Paginator(rows, 24); current = pages.get_page(page)
        profiles = {row.person_id: row for row in ScholarProfile.objects.filter(person_id__in=[item.person_id for item in current.object_list])}
        result = []
        for item in current.object_list:
            profile = profiles.get(item.person_id)
            result.append({"key": f"edition:{edition.pk}:{item.person_id}:{item.role}", "kind": "person",
                "person_id": str(item.person_id), "scholar_id": str(profile.pk) if profile else None,
                "name": item.person.preferred_name, "role": item.role, "role_label": item.get_role_display(),
                "href": f"/admin/scholars/{profile.pk}" if profile else "", "source": "edition", "edition_id": str(edition.pk)})
        return Response(TimelineEditionParticipantsSerializer({"edition_id": edition.pk, "work_id": edition.work_id,
            "work_title": edition.work.title, "version_label": edition.version_label,
            "count": pages.count, "page": current.number, "total_pages": pages.num_pages,
            "pending_count": edition.contributions.filter(approved=False).count(), "publisher": edition.publisher,
            "publisher_authority_id": edition.publisher_authority_id,
            "results": result}).data)
