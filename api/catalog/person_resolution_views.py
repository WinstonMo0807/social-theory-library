from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from collections import Counter

from common.permissions import CanAccessBackOffice, CanMergeAuthority
from catalog.models import Person, PersonMergeRecord
from catalog.services.person_resolution import duplicate_people, person_merge_preview
from catalog.services.person_merges import merge_people, prepare_person_merge, rollback_person_merge, rollback_preview
from ingestion.models import AuditEvent


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


class PersonSearchQuerySerializer(serializers.Serializer):
    search = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20, required=False)


class PersonSearchResponseSerializer(serializers.Serializer):
    results = PersonResolutionSummarySerializer(many=True)
    has_more = serializers.BooleanField()


class AdminPersonSearchView(APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[PersonSearchQuerySerializer], responses=PersonSearchResponseSerializer)
    def get(self, request):
        params = PersonSearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        search, limit = params.validated_data["search"], params.validated_data["limit"]
        people = Person.objects.only("id", "preferred_name", "original_name", "birth_year", "death_year", "authority_status")
        if search:
            people = people.filter(
                Q(preferred_name__icontains=search) | Q(original_name__icontains=search)
                | Q(name_variants__name__icontains=search, name_variants__is_verified=True)
            ).distinct()
        rows = list(people.order_by("preferred_name", "pk")[:limit + 1])
        response = Response(PersonSearchResponseSerializer({"results": rows[:limit], "has_more": len(rows) > limit}).data)
        response["Cache-Control"] = "private, no-store"
        return response


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
    execution_policy = serializers.CharField(required=False)
    execution_guidance = serializers.ListField(child=serializers.CharField(), required=False)
    context_impact = serializers.JSONField(required=False)


class PersonMergeRequestSerializer(serializers.Serializer):
    target_person = serializers.UUIDField()
    fingerprint = serializers.RegexField(regex=r"^[a-f0-9]{64}$")
    idempotency_key = serializers.RegexField(regex=r"^[A-Za-z0-9._:-]{1,160}$")
    confirmed = serializers.BooleanField()
    change_note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PersonMergeRollbackRequestSerializer(serializers.Serializer):
    fingerprint = serializers.RegexField(regex=r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()


class PersonMergeRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_person_id = serializers.UUIDField()
    target_person_id = serializers.UUIDField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by_id = serializers.IntegerField(allow_null=True)
    rolled_back_at = serializers.DateTimeField(allow_null=True)
    moved_counts = serializers.JSONField()
    affected_edition_ids = serializers.ListField(child=serializers.UUIDField())
    event_ids = serializers.ListField(child=serializers.UUIDField())
    rollback_event_ids = serializers.ListField(child=serializers.UUIDField())
    rollback = serializers.JSONField()


def _record_response(record):
    try:
        reversal = rollback_preview(record)
    except ValueError as error:
        reversal = {"can_rollback": False, "fingerprint": "", "blockers": [str(error)]}
    rollback_audit = AuditEvent.objects.filter(
        action="person_merge_rollback", object_type="catalog.PersonMergeRecord", object_id=str(record.pk),
    ).order_by("-created_at").first()
    payload = {
        "id": record.pk, "source_person_id": record.source_person_id, "target_person_id": record.target_person_id,
        "status": "rolled_back" if record.rolled_back_at else "applied", "created_at": record.created_at,
        "created_by_id": record.created_by_id, "rolled_back_at": record.rolled_back_at,
        "moved_counts": dict(Counter(row["model"] for row in record.changes)),
        "affected_edition_ids": record.affected_edition_ids, "event_ids": record.event_ids,
        "rollback_event_ids": (rollback_audit.after or {}).get("event_ids", []) if rollback_audit else [],
        "rollback": reversal,
    }
    response = Response(PersonMergeRecordSerializer(payload).data)
    response["Cache-Control"] = "private, no-store"
    return response


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
            payload = prepare_person_merge(source, target) if target else person_merge_preview(source)
        except ValueError as error:
            return Response({"code": "person_preview_conflict", "detail": str(error)}, status=409)
        response = Response(PersonMergePreviewResponseSerializer(payload).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AdminPersonMergeView(APIView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(request=PersonMergeRequestSerializer, responses=PersonMergeRecordSerializer)
    def post(self, request, person_id):
        serializer = PersonMergeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        get_object_or_404(Person, pk=person_id)
        get_object_or_404(Person, pk=data["target_person"])
        try:
            record = merge_people(person_id, data["target_person"], actor=request.user,
                                  expected_fingerprint=data["fingerprint"], idempotency_key=data["idempotency_key"],
                                  confirmed=data["confirmed"], change_note=data.get("change_note", ""))
        except ValueError as error:
            return Response({"code": "person_merge_conflict", "detail": str(error)}, status=409)
        return _record_response(record)


class AdminPersonMergeRecordView(APIView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(responses=PersonMergeRecordSerializer)
    def get(self, request, record_id):
        return _record_response(get_object_or_404(PersonMergeRecord.objects.select_related("source_person", "target_person"), pk=record_id))


class PersonMergeHistoryQuerySerializer(serializers.Serializer):
    source_person = serializers.UUIDField()


class PersonMergeHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_person_id = serializers.UUIDField()
    target_person_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    rolled_back_at = serializers.DateTimeField(allow_null=True)


class AdminPersonMergeHistoryView(APIView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(parameters=[PersonMergeHistoryQuerySerializer], responses=PersonMergeHistoryItemSerializer(many=True))
    def get(self, request):
        params = PersonMergeHistoryQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        # Read-only recovery after navigation or a lost mutation response. No
        # immutable snapshot, private annotation or rollback evaluation here.
        records = PersonMergeRecord.objects.filter(source_person_id=params.validated_data["source_person"]).only(
            "id", "source_person", "target_person", "created_at", "rolled_back_at",
        ).order_by("-created_at", "-pk")[:20]
        response = Response(PersonMergeHistoryItemSerializer(records, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AdminPersonMergeRollbackView(APIView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(request=PersonMergeRollbackRequestSerializer, responses=PersonMergeRecordSerializer)
    def post(self, request, record_id):
        serializer = PersonMergeRollbackRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(PersonMergeRecord, pk=record_id)
        try:
            record = rollback_person_merge(record_id, actor=request.user,
                                           expected_fingerprint=serializer.validated_data["fingerprint"],
                                           confirmed=serializer.validated_data["confirmed"])
        except ValueError as error:
            return Response({"code": "person_rollback_conflict", "detail": str(error)}, status=409)
        return _record_response(record)
