from django.conf import settings
from django.db.models import prefetch_related_objects
from django.utils import timezone
from rest_framework import serializers

from catalog.services.text import clean_page_label
from catalog.serializers import CoverCandidateSerializer
from catalog.services.publication_places import serialize_publication_place_evidence

from .models import (
    CandidateEvidence,
    DecisionLog,
    EntityResolutionCandidate,
    MetadataCandidate,
    ProcessingAttempt,
    ReviewTask,
    UploadBatch,
    UploadItem,
)
from .services.metadata import authority_verification_links
from .services.entity_resolution_decisions import available_resolution_actions
from .services.metadata_import_formats import MAX_METADATA_IMPORT_BYTES


class ProcessingAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingAttempt
        fields = (
            "id",
            "stage",
            "attempt_number",
            "status",
            "started_at",
            "finished_at",
            "output_summary",
            "log_excerpt",
            "error_code",
            "error_message",
            "error_kind",
            "idempotency_key",
            "correlation_id",
            "invalidated_at",
            "superseded_by",
        )


class CandidateEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateEvidence
        fields = (
            "id",
            "asset",
            "source_record",
            "page_number",
            "bbox",
            "text_quote",
            "source_kind",
            "external_identifier",
            "extraction_method",
            "model_name",
            "model_revision",
            "created_at",
        )


class MetadataCandidateListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        candidates = list(data.all() if hasattr(data, "all") else data)
        if candidates:
            prefetch_related_objects(candidates, "evidence_records")
        return super().to_representation(candidates)


class MetadataCandidateSerializer(serializers.ModelSerializer):
    evidence_records = CandidateEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = MetadataCandidate
        list_serializer_class = MetadataCandidateListSerializer
        fields = (
            "id",
            "field_name",
            "value",
            "source",
            "evidence",
            "confidence",
            "selected",
            "lifecycle",
            "normalized_value",
            "source_record",
            "conflict_group",
            "score_factors",
            "is_locked",
            "accepted_by",
            "accepted_at",
            "rejected_by",
            "rejected_at",
            "evidence_records",
        )


class EntityResolutionCandidateSerializer(serializers.ModelSerializer):
    available_actions = serializers.SerializerMethodField()
    latest_decision = serializers.SerializerMethodField()

    def get_available_actions(self, obj):
        return available_resolution_actions(obj)

    def get_latest_decision(self, obj):
        decision = (
            DecisionLog.objects.filter(
                resolution_candidate=obj,
                reverts_decision__isnull=True,
            )
            .select_related("reverted_by")
            .order_by("-created_at")
            .first()
        )
        if decision is None:
            return None
        edition = getattr(obj.upload_item, "edition", None)
        can_revert = (
            decision.reverted_at is None
            and edition is not None
            and edition.state != "published"
        )
        return {
            "id": str(decision.id),
            "action": decision.action,
            "created_at": decision.created_at,
            "reverted_at": decision.reverted_at,
            "reverted_by": str(decision.reverted_by_id or ""),
            "reversal_reason": decision.reversal_reason,
            "can_revert": can_revert,
        }

    class Meta:
        model = EntityResolutionCandidate
        fields = (
            "id",
            "target_type",
            "source_name",
            "candidate_entity_type",
            "candidate_entity_id",
            "label",
            "aliases",
            "external_ids",
            "supporting_properties",
            "match_score",
            "match_reasons",
            "conflicts",
            "preview_data",
            "status",
            "reviewed_by",
            "reviewed_at",
            "available_actions",
            "latest_decision",
        )


class EntityResolutionDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=("link_existing", "create_draft", "keep_unresolved", "reject")
    )
    target_type = serializers.ChoiceField(
        choices=("person", "work", "publisher", "organization", "knowledge_node")
    )
    target_id = serializers.UUIDField(required=False, allow_null=True)
    confirm_identity = serializers.BooleanField(default=False)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate(self, attrs):
        action = attrs["action"]
        target_id = attrs.get("target_id")
        if action == "link_existing" and target_id is None:
            raise serializers.ValidationError({"target_id": "关联现有实体时必须提交目标 ID。"})
        if action != "link_existing" and target_id is not None:
            raise serializers.ValidationError({"target_id": "此操作不能提交目标 ID。"})
        return attrs


class EntityResolutionRevertSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)

    def validate_reason(self, value):
        value = " ".join(value.split()).strip()
        if len(value) < 4:
            raise serializers.ValidationError("请简要说明撤销原因。")
        return value


class MetadataImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField()
    format = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def validate_file(self, value):
        if value.size > MAX_METADATA_IMPORT_BYTES:
            raise serializers.ValidationError(
                f"元数据文件不能超过 {MAX_METADATA_IMPORT_BYTES // 1024} KiB。"
            )
        return value


class ReviewTaskSerializer(serializers.ModelSerializer):
    item_title = serializers.SerializerMethodField()
    source_filename = serializers.CharField(source="upload_item.source_filename", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()

    def get_item_title(self, obj):
        if obj.upload_item and obj.upload_item.edition_id:
            return obj.upload_item.edition.work.title
        return ""

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.display_name if obj.assigned_to else ""

    class Meta:
        model = ReviewTask
        fields = (
            "id",
            "upload_item",
            "task_type",
            "target_type",
            "target_id",
            "title",
            "details",
            "status",
            "priority",
            "assigned_to",
            "assigned_to_name",
            "created_by",
            "completed_by",
            "started_at",
            "due_at",
            "completed_at",
            "created_at",
            "updated_at",
            "item_title",
            "source_filename",
        )


class ReviewTaskActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("start", "assign_self", "complete", "reopen", "cancel"))
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class UploadItemSerializer(serializers.ModelSerializer):
    attempts = ProcessingAttemptSerializer(many=True, read_only=True)
    metadata_candidates = MetadataCandidateSerializer(many=True, read_only=True)
    entity_resolution_candidates = EntityResolutionCandidateSerializer(many=True, read_only=True)
    title = serializers.CharField(source="edition.work.title", read_only=True)
    uploaded_by = serializers.CharField(source="batch.created_by.display_name", read_only=True)
    review_data = serializers.SerializerMethodField()
    publication_reasons = serializers.SerializerMethodField()
    publication_preflight = serializers.SerializerMethodField()
    can_publish = serializers.SerializerMethodField()
    can_manage_publication = serializers.SerializerMethodField()
    is_stalled = serializers.SerializerMethodField()
    stalled_seconds = serializers.SerializerMethodField()
    suggested_action = serializers.SerializerMethodField()
    queue_mode = serializers.SerializerMethodField()
    staging = serializers.SerializerMethodField()

    class Meta:
        model = UploadItem
        fields = (
            "id",
            "batch",
            "source_filename",
            "sha256",
            "byte_size",
            "document_type_hint",
            "status",
            "workflow_state",
            "priority",
            "preflight_summary",
            "workflow_updated_at",
            "stage_progress",
            "retry_count",
            "error_code",
            "error_message",
            "dispatch_status",
            "dispatch_kind",
            "dispatch_task_id",
            "dispatch_attempts",
            "last_dispatched_at",
            "dispatch_error",
            "recognized_metadata",
            "edition",
            "asset",
            "replacement_of_asset",
            "title",
            "uploaded_by",
            "review_data",
            "publication_reasons",
            "publication_preflight",
            "can_publish",
            "can_manage_publication",
            "is_stalled",
            "stalled_seconds",
            "suggested_action",
            "queue_mode",
            "staging",
            "attempts",
            "metadata_candidates",
            "entity_resolution_candidates",
            "created_at",
            "updated_at",
        )

    def get_review_data(self, obj):
        if not obj.edition_id:
            return None
        edition = obj.edition
        work = edition.work
        normalized = edition.assets.filter(kind="normalized", is_current=True).first()
        first_page = normalized.pages.order_by("index").first() if normalized else None
        contributions = list(
            edition.contributions.filter(role="author")
            .select_related("person", "person__scholar_profile")
            .order_by("order")
        )
        recognized_authors = obj.recognized_metadata.get("authors", [])
        if not isinstance(recognized_authors, list):
            recognized_authors = [recognized_authors] if recognized_authors else []
        theory_relations = list(
            work.knowledge_relations.filter(
                kind="theory_school",
                theory_school__isnull=False,
            ).select_related("theory_school")
        )
        topic_relations = list(
            work.knowledge_relations.filter(
                kind="topic",
                topic__isnull=False,
            ).select_related("topic")
        )
        discipline_relations = list(
            work.discipline_relations.select_related("discipline").order_by("-is_primary", "discipline__name")
        )
        subdiscipline_relations = list(
            work.subdiscipline_relations.select_related("subdiscipline").order_by(
                "-is_primary",
                "subdiscipline__name",
            )
        )
        return {
            "edition_id": str(edition.id),
            "work_id": str(work.id),
            "title": work.title,
            "subtitle": work.subtitle,
            "document_type": work.document_type,
            "language": work.language,
            "abstract": work.abstract,
            "publication_state": edition.state,
            "ocr_status": edition.ocr_status,
            "semantic_index_status": edition.semantic_index_status,
            "page_label_status": edition.page_label_status,
            "review_status": edition.review_status,
            "review_progress": edition.review_progress,
            "reader_rendition_policy": edition.reader_rendition_policy,
            "first_published_at": edition.first_published_at,
            "last_published_at": edition.last_published_at,
            "public_slug": edition.public_slug,
            "version_label": edition.version_label,
            "publication_year": edition.publication_year,
            "publisher": edition.publisher,
            "publication_place": edition.publication_place,
            "publication_place_evidence": [
                serialize_publication_place_evidence(evidence)
                for evidence in edition.publication_place_evidence.order_by(
                    "display_order",
                    "-confidence",
                )
            ],
            "publication_place_history": [
                {
                    "id": str(revision.id),
                    "action": revision.action,
                    "before": revision.before,
                    "after": revision.after,
                    "reason": revision.reason,
                    "actor": revision.actor.display_name if revision.actor else "系统",
                    "created_at": revision.created_at,
                }
                for revision in edition.publication_metadata_revisions.select_related("actor")[:20]
            ],
            "journal_title": edition.journal_title,
            "volume": edition.volume,
            "issue": edition.issue,
            "page_range": edition.page_range,
            "degree_institution": edition.degree_institution,
            "degree_type": edition.degree_type,
            "report_institution": edition.report_institution,
            "isbn": edition.isbn,
            "doi": edition.doi,
            "authority_links": authority_verification_links(
                title=work.title,
                isbn=edition.isbn,
                doi=edition.doi,
                document_type=work.document_type,
            ),
            "authors": (
                [contribution.person.preferred_name for contribution in contributions]
                if contributions
                else [str(value) for value in recognized_authors if str(value).strip()]
            ),
            "author_refs": [
                {
                    "id": (
                        str(contribution.person.scholar_profile.id)
                        if hasattr(contribution.person, "scholar_profile")
                        else None
                    ),
                    "person_id": str(contribution.person_id),
                    "name": contribution.person.preferred_name,
                    "slug": (
                        contribution.person.scholar_profile.slug
                        if hasattr(contribution.person, "scholar_profile")
                        else ""
                    ),
                }
                for contribution in contributions
            ],
            "theory_schools": [relation.theory_school.name for relation in theory_relations],
            "theory_school_refs": [
                {
                    "id": str(relation.theory_school_id),
                    "name": relation.theory_school.name,
                    "slug": relation.theory_school.slug,
                    "role": relation.role or "local_mention",
                    "strength": relation.strength,
                    "is_primary": relation.is_primary,
                    "review_status": relation.review_status,
                    "evidence_page": relation.evidence_page,
                    "evidence_printed_label": relation.evidence_printed_label,
                    "evidence_text": relation.evidence_text,
                }
                for relation in theory_relations
            ],
            "topics": [relation.topic.name for relation in topic_relations],
            "topic_refs": [
                {
                    "id": str(relation.topic_id),
                    "name": relation.topic.name,
                    "slug": relation.topic.slug,
                    "is_primary": relation.is_primary,
                    "review_status": relation.review_status,
                    "evidence_page": relation.evidence_page,
                    "evidence_printed_label": relation.evidence_printed_label,
                    "evidence_text": relation.evidence_text,
                }
                for relation in topic_relations
            ],
            "discipline_refs": [
                {
                    "id": str(relation.discipline_id),
                    "name": relation.discipline.name,
                    "slug": relation.discipline.slug,
                    "is_primary": relation.is_primary,
                    "review_status": relation.review_status,
                    "evidence_page": relation.evidence_page,
                    "evidence_printed_label": relation.evidence_printed_label,
                    "evidence_text": relation.evidence_text,
                }
                for relation in discipline_relations
            ],
            "subdiscipline_refs": [
                {
                    "id": str(relation.subdiscipline_id),
                    "name": relation.subdiscipline.name,
                    "slug": relation.subdiscipline.slug,
                    "strength": relation.strength,
                    "is_primary": relation.is_primary,
                    "review_status": relation.review_status,
                    "evidence_page": relation.evidence_page,
                    "evidence_printed_label": relation.evidence_printed_label,
                    "evidence_text": relation.evidence_text,
                }
                for relation in subdiscipline_relations
            ],
            "release_impact": {
                "work": {"label": work.title, "href": f"/works/{edition.public_slug}" if edition.public_slug else ""},
                "scholars": [
                    {
                        "label": contribution.person.preferred_name,
                        "href": f"/scholars/{contribution.person.scholar_profile.slug}",
                    }
                    for contribution in contributions
                    if hasattr(contribution.person, "scholar_profile")
                ],
                "disciplines": [
                    {"label": relation.discipline.name, "href": f"/disciplines/{relation.discipline.slug}"}
                    for relation in discipline_relations
                ],
                "theories": [
                    {"label": relation.theory_school.name, "href": f"/theory-schools/{relation.theory_school.slug}"}
                    for relation in theory_relations
                ],
                "subdisciplines": [
                    {"label": relation.subdiscipline.name, "href": f"/subdisciplines/{relation.subdiscipline.slug}"}
                    for relation in subdiscipline_relations
                ],
                "topics": [
                    {"label": relation.topic.name, "href": f"/topics/{relation.topic.slug}"}
                    for relation in topic_relations
                ],
                "search": {"label": "全文检索", "href": f"/explore?q={work.title}"},
            },
            "relation_suggestions": [
                {
                    "kind": relation.kind,
                    "name": (
                        relation.theory_school.name
                        if relation.theory_school_id
                        else relation.topic.name
                        if relation.topic_id
                        else relation.concept.name
                        if relation.concept_id
                        else ""
                    ),
                    "source": relation.source,
                    "confidence": relation.confidence,
                    "approved": relation.approved,
                }
                for relation in work.knowledge_relations.select_related(
                    "theory_school",
                    "topic",
                    "concept",
                ).order_by("-confidence")
            ],
            "locked_fields": list(edition.field_locks.values_list("field_name", flat=True)),
            "normalized_asset_id": str(normalized.id) if normalized else None,
            "page_count": normalized.page_count if normalized else 0,
            "cover_candidates": CoverCandidateSerializer(
                work.cover_candidates.filter(asset=normalized).order_by("-score", "page_index")
                if normalized
                else work.cover_candidates.none(),
                many=True,
                context=self.context,
            ).data,
            "first_page": (
                {
                    "index": first_page.index,
                    "printed_label": clean_page_label(first_page.printed_label),
                    "text": first_page.text[:12000],
                    "text_source": first_page.text_source,
                    "confidence": first_page.confidence,
                    "label_source": first_page.label_source,
                    "label_confidence": first_page.label_confidence,
                    "is_label_manual": first_page.is_label_manual,
                }
                if first_page
                else None
            ),
        }

    def get_publication_reasons(self, obj):
        if not obj.edition_id:
            return ["文献记录尚未建立"]
        from .services.publication import publication_readiness

        return publication_readiness(obj.edition)

    def get_publication_preflight(self, obj):
        if not obj.edition_id:
            return {
                "blockers": ["文献记录尚未建立"],
                "warnings": [],
                "background_tasks": [],
            }
        from .services.publication import publication_preflight

        return publication_preflight(obj.edition)

    def get_can_publish(self, obj):
        return not self.get_publication_reasons(obj)

    def get_can_manage_publication(self, obj):
        from common.capabilities import Capability, has_capability

        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and has_capability(request.user, Capability.PUBLISH_WORK)
        )

    def _stalled_seconds(self, obj):
        active_statuses = {
            UploadItem.Status.RECEIVED,
            UploadItem.Status.VALIDATING,
            UploadItem.Status.DEDUPLICATING,
            UploadItem.Status.EXTRACTING,
            UploadItem.Status.OCR,
            UploadItem.Status.METADATA,
            UploadItem.Status.LINKING,
            UploadItem.Status.INDEXING,
            UploadItem.Status.PREPARING_PUBLIC_ASSET,
            UploadItem.Status.SYNCING_CLOUD,
        }
        if obj.status not in active_statuses:
            return 0
        return max(
            0,
            int((timezone.now() - obj.updated_at).total_seconds()),
        )

    def get_stalled_seconds(self, obj):
        return self._stalled_seconds(obj)

    def get_is_stalled(self, obj):
        if obj.staging_backend == UploadItem.StagingBackend.R2 and obj.staging_status in {
            UploadItem.StagingStatus.UPLOADING,
            UploadItem.StagingStatus.UPLOADED,
            UploadItem.StagingStatus.IMPORTING,
            UploadItem.StagingStatus.IMPORT_FAILED,
            UploadItem.StagingStatus.ABORTED,
            UploadItem.StagingStatus.EXPIRED,
        }:
            return False
        seconds = self._stalled_seconds(obj)
        threshold = (
            settings.INGESTION_QUEUE_STALLED_SECONDS
            if obj.status == UploadItem.Status.RECEIVED
            else settings.INGESTION_STAGE_STALLED_SECONDS
        )
        return seconds >= threshold

    def get_suggested_action(self, obj):
        if obj.staging_backend == UploadItem.StagingBackend.R2:
            if obj.staging_status == UploadItem.StagingStatus.IMPORT_FAILED:
                return "retry_import"
            if obj.staging_status in {
                UploadItem.StagingStatus.UPLOADING,
                UploadItem.StagingStatus.UPLOADED,
                UploadItem.StagingStatus.IMPORTING,
            }:
                return ""
            if obj.staging_status in {
                UploadItem.StagingStatus.ABORTED,
                UploadItem.StagingStatus.EXPIRED,
            }:
                return "replace"
        if self.get_is_stalled(obj):
            return "retry"
        if obj.status in {
            UploadItem.Status.NEEDS_REVIEW,
            UploadItem.Status.READY,
        }:
            return "resume" if obj.edition_id else "review"
        if obj.status == UploadItem.Status.FAILED:
            return "retry"
        return ""

    def get_queue_mode(self, obj):
        return (
            "inline"
            if settings.CELERY_TASK_ALWAYS_EAGER
            else "worker"
        )

    def get_staging(self, obj):
        if obj.staging_backend != UploadItem.StagingBackend.R2:
            return None
        from ingestion.services.r2_staging import serialize_staging_session

        return serialize_staging_session(obj)


class UploadBatchSerializer(serializers.ModelSerializer):
    items = UploadItemSerializer(many=True, read_only=True)

    class Meta:
        model = UploadBatch
        fields = (
            "id",
            "status",
            "source",
            "label",
            "access_policy",
            "ocr_strategy",
            "duplicate_policy",
            "external_enrichment_enabled",
            "ai_suggestions_enabled",
            "expected_count",
            "completed_count",
            "failed_count",
            "notes",
            "items",
            "created_at",
            "updated_at",
        )


class UploadBatchCreateSerializer(serializers.Serializer):
    """Validate the intake policy once, before any file enters the batch."""

    expected_count = serializers.IntegerField(min_value=1, max_value=100)
    label = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    access_policy = serializers.ChoiceField(
        choices=UploadBatch.AccessPolicy.choices,
        required=False,
        default=UploadBatch.AccessPolicy.PUBLIC,
    )
    ocr_strategy = serializers.ChoiceField(
        choices=UploadBatch.OcrStrategy.choices,
        required=False,
        default=UploadBatch.OcrStrategy.AUTO,
    )
    duplicate_policy = serializers.ChoiceField(
        choices=UploadBatch.DuplicatePolicy.choices,
        required=False,
        default=UploadBatch.DuplicatePolicy.REVIEW,
    )
    external_enrichment_enabled = serializers.BooleanField(required=False, default=True)
    ai_suggestions_enabled = serializers.BooleanField(required=False, default=False)


class R2StagingInitSerializer(serializers.Serializer):
    batch_id = serializers.UUIDField()
    source_filename = serializers.CharField(max_length=800)
    file_size = serializers.IntegerField(min_value=5)
    file_last_modified = serializers.IntegerField(min_value=0, required=False, default=0)
    content_type = serializers.CharField(max_length=120, required=False, default="application/pdf")
    client_token = serializers.RegexField(r"^[A-Za-z0-9-]{8,80}$")

    def validate_source_filename(self, value):
        if not value.casefold().endswith(".pdf"):
            raise serializers.ValidationError("只允许上传 PDF。")
        return value

    def validate_file_size(self, value):
        if value > settings.MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("PDF 超过单文件上限。")
        return value

    def validate_content_type(self, value):
        if value.casefold() not in {"application/pdf", "application/octet-stream", ""}:
            raise serializers.ValidationError("只允许 PDF content type。")
        return value


class R2PartSignSerializer(serializers.Serializer):
    part_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=24,
    )


class R2PartRecordSerializer(serializers.Serializer):
    part_number = serializers.IntegerField(min_value=1)
    etag = serializers.CharField(max_length=202)
    size = serializers.IntegerField(min_value=1, required=False)


class R2PartConfirmSerializer(R2PartRecordSerializer):
    size = serializers.IntegerField(min_value=1)
    attempt = serializers.IntegerField(min_value=1, max_value=3, required=False, default=1)


class R2PartFailureSerializer(serializers.Serializer):
    part_number = serializers.IntegerField(min_value=1)
    attempt = serializers.IntegerField(min_value=1, max_value=3)
    http_status = serializers.IntegerField(min_value=0, max_value=599, required=False, default=0)
    error_code = serializers.CharField(max_length=120, required=False, allow_blank=True, default="network_error")


class R2CompleteSerializer(serializers.Serializer):
    parts = R2PartRecordSerializer(many=True, allow_empty=False)


class DisciplineAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    is_primary = serializers.BooleanField(default=False)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    evidence_text = serializers.CharField(required=False, allow_blank=True)


class TheoryAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=(
            "foundational",
            "development",
            "introduction",
            "empirical_application",
            "method_use",
            "criticism",
            "theory_history",
            "local_mention",
        ),
        default="local_mention",
    )
    strength = serializers.ChoiceField(choices=("high", "medium", "low"), default="medium")
    is_primary = serializers.BooleanField(default=False)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    evidence_text = serializers.CharField(required=False, allow_blank=True)


class SubdisciplineAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    strength = serializers.ChoiceField(choices=("high", "medium", "low"), default="medium")
    is_primary = serializers.BooleanField(default=False)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    evidence_text = serializers.CharField(required=False, allow_blank=True)


class TopicAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    is_primary = serializers.BooleanField(default=False)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    evidence_text = serializers.CharField(required=False, allow_blank=True)


class MetadataReviewSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=600)
    subtitle = serializers.CharField(max_length=600, required=False, allow_blank=True)
    document_type = serializers.ChoiceField(choices=("book", "journal_article", "thesis", "report"))
    language = serializers.ChoiceField(choices=("zh-CN", "zh-TW", "en"), default="zh-CN")
    version_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    publication_year = serializers.IntegerField(min_value=1400, max_value=2100, required=False, allow_null=True)
    publisher = serializers.CharField(max_length=300, required=False, allow_blank=True)
    publication_place = serializers.CharField(max_length=200, required=False, allow_blank=True)
    journal_title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    volume = serializers.CharField(max_length=40, required=False, allow_blank=True)
    issue = serializers.CharField(max_length=40, required=False, allow_blank=True)
    page_range = serializers.CharField(max_length=80, required=False, allow_blank=True)
    degree_institution = serializers.CharField(max_length=300, required=False, allow_blank=True)
    degree_type = serializers.CharField(max_length=120, required=False, allow_blank=True)
    report_institution = serializers.CharField(max_length=300, required=False, allow_blank=True)
    isbn = serializers.CharField(max_length=32, required=False, allow_blank=True)
    doi = serializers.CharField(max_length=255, required=False, allow_blank=True)
    abstract = serializers.CharField(required=False, allow_blank=True)
    authors = serializers.ListField(
        child=serializers.CharField(max_length=240),
        required=False,
        default=list,
    )
    author_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    author_person_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    theory_schools = serializers.ListField(
        child=serializers.CharField(max_length=240),
        required=False,
        default=list,
    )
    theory_school_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    theory_assignments = TheoryAssignmentSerializer(many=True, required=False, default=list)
    topics = serializers.ListField(
        child=serializers.CharField(max_length=240),
        required=False,
        default=list,
    )
    topic_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    topic_assignments = TopicAssignmentSerializer(many=True, required=False, default=list)
    discipline_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    discipline_assignments = DisciplineAssignmentSerializer(many=True, required=False, default=list)
    subdiscipline_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    subdiscipline_assignments = SubdisciplineAssignmentSerializer(many=True, required=False, default=list)
    lock_fields = serializers.ListField(
        child=serializers.CharField(max_length=80),
        required=False,
        default=list,
    )
    retry_publication = serializers.BooleanField(default=True)


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)
