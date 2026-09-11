from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice, CanMergeAuthority
from catalog.models import Person
from catalog.services.person_resolution import duplicate_people, person_merge_preview


class PersonDuplicateQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10, required=False)


class PersonMergePreviewQuerySerializer(serializers.Serializer):
    target_person = serializers.UUIDField(required=False)


class PersonResolutionSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    preferred_name = serializers.CharField()
    original_name = serializers.CharField(allow_blank=True)
    birth_year = serializers.IntegerField(allow_null=True)
    death_year = serializers.IntegerField(allow_null=True)
    authority_status = serializers.CharField()


class PersonDuplicateCandidateSerializer(serializers.Serializer):
    person = PersonResolutionSummarySerializer()
    matches = serializers.ListField(child=serializers.JSONField())
    identity_conflicts = serializers.ListField(child=serializers.JSONField())


class PersonDuplicateResponseSerializer(serializers.Serializer):
    source = PersonResolutionSummarySerializer()
    results = PersonDuplicateCandidateSerializer(many=True)
    limit = serializers.IntegerField()
    has_more = serializers.BooleanField()
    automatic_merge = serializers.BooleanField()
    matching_policy = serializers.CharField()


class PersonLexiconEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    entity_id = serializers.UUIDField()
    term = serializers.CharField()
    normalized_term = serializers.CharField()
    language = serializers.CharField()
    term_type = serializers.CharField()
    source_kind = serializers.CharField()
    trust_level = serializers.CharField()
    source_ref = serializers.CharField(allow_blank=True)
    displayable = serializers.BooleanField()
    public_active = serializers.BooleanField()
    admin_resolvable = serializers.BooleanField()


class PersonLexiconPreviewSerializer(serializers.Serializer):
    scope = serializers.CharField()
    available = serializers.BooleanField()
    status = serializers.CharField()
    generation_id = serializers.UUIDField(allow_null=True)
    revision = serializers.IntegerField(allow_null=True)
    normalization_version = serializers.CharField(allow_blank=True)
    source_registry_version = serializers.CharField(allow_blank=True)
    source = serializers.IntegerField()
    target = serializers.IntegerField()
    source_rows = PersonLexiconEntrySerializer(many=True)
    target_rows = PersonLexiconEntrySerializer(many=True)
    truncated = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)


class PersonMergePreviewResponseSerializer(serializers.Serializer):
    version = serializers.CharField()
    fingerprint = serializers.CharField()
    source = serializers.JSONField()
    target = serializers.JSONField(allow_null=True)
    source_profile = serializers.JSONField(allow_null=True)
    target_profile = serializers.JSONField(allow_null=True)
    references = serializers.ListField(child=serializers.JSONField())
    affected_works = serializers.ListField(child=serializers.JSONField())
    affected_editions = serializers.ListField(child=serializers.JSONField())
    affected_edition_count = serializers.IntegerField()
    publication_revisions = serializers.ListField(child=serializers.JSONField())
    publication_revision_count = serializers.IntegerField()
    editorial_drafts = serializers.ListField(child=serializers.JSONField())
    identity_conflicts = serializers.ListField(child=serializers.JSONField())
    review_issues = serializers.ListField(child=serializers.JSONField())
    lexicon_entries = PersonLexiconPreviewSerializer()
    complete_reference_listing = serializers.BooleanField()
    merge_execution_available = serializers.BooleanField()
    coverage = serializers.JSONField()
    preservation = serializers.ListField(child=serializers.CharField())


class AdminPersonDuplicateView(APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[PersonDuplicateQuerySerializer], responses=PersonDuplicateResponseSerializer)
    def get(self, request, person_id):
        params = PersonDuplicateQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        source = get_object_or_404(Person.objects.prefetch_related("name_variants"), pk=person_id)
        response = Response(PersonDuplicateResponseSerializer(duplicate_people(source, **params.validated_data)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AdminPersonMergePreviewView(APIView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(parameters=[PersonMergePreviewQuerySerializer], responses=PersonMergePreviewResponseSerializer)
    def get(self, request, person_id):
        params = PersonMergePreviewQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        source = get_object_or_404(Person, pk=person_id)
        target_id = params.validated_data.get("target_person")
        target = get_object_or_404(Person, pk=target_id) if target_id else None
        try:
            payload = person_merge_preview(source, target)
        except ValueError as error:
            return Response({"code": "person_preview_conflict", "detail": str(error)}, status=409)
        response = Response(PersonMergePreviewResponseSerializer(payload).data)
        response["Cache-Control"] = "private, no-store"
        return response
