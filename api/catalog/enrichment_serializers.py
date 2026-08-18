from __future__ import annotations

import json

from rest_framework import serializers

from catalog.models import (
    EnrichmentCandidate,
    EnrichmentEvidence,
    NewAuthorityCandidate,
    UnknownEntityObservation,
    QueryLexiconCandidate,
    QueryLexiconCandidateEvidence,
)
from catalog.services.knowledge_growth import possible_authority_matches


class EnrichmentEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnrichmentEvidence
        fields = (
            "id",
            "source_record",
            "source_url",
            "canonical_url",
            "source_title",
            "source_domain",
            "source_class",
            "provider",
            "external_identifier",
            "supporting_text",
            "locator",
            "retrieved_at",
            "http_status",
            "content_type",
            "content_checksum",
            "entity_match_evidence",
            "extraction_method",
            "extraction_version",
            "confidence",
            "is_current",
            "superseded_at",
            "created_at",
        )


class EnrichmentCandidateSerializer(serializers.ModelSerializer):
    evidence_records = EnrichmentEvidenceSerializer(many=True, read_only=True)
    evidence_count = serializers.SerializerMethodField()
    independent_source_count = serializers.SerializerMethodField()

    class Meta:
        model = EnrichmentCandidate
        fields = (
            "id",
            "target_type",
            "target_id",
            "field_name",
            "candidate_kind",
            "proposed_value",
            "normalized_value",
            "current_value",
            "source_class",
            "confidence",
            "confidence_factors",
            "conflicts",
            "identity_status",
            "identity_evidence",
            "status",
            "requested_mode",
            "request_id",
            "policy_version",
            "extraction_version",
            "refresh_after",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "accepted_authority_model",
            "accepted_authority_id",
            "evidence_count",
            "independent_source_count",
            "evidence_records",
            "created_at",
            "updated_at",
        )

    def get_evidence_count(self, obj):
        return obj.evidence_records.filter(is_current=True).count()

    def get_independent_source_count(self, obj):
        return obj.evidence_records.filter(is_current=True).values("canonical_url").distinct().count()


class FieldEnrichmentRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=EnrichmentCandidate.TargetType.choices)
    target_id = serializers.UUIDField()
    field_name = serializers.CharField(max_length=96, required=False, allow_blank=False)
    fields = serializers.ListField(
        child=serializers.CharField(max_length=96, allow_blank=False),
        required=False,
        max_length=12,
    )
    current_value = serializers.JSONField(required=False, default=None)
    form_context = serializers.JSONField(required=False, default=dict)
    requested_mode = serializers.ChoiceField(
        choices=EnrichmentCandidate.RequestedMode.choices,
        default=EnrichmentCandidate.RequestedMode.STRUCTURED,
    )
    visibility = serializers.ChoiceField(choices=[("admin", "Admin")], default="admin")

    def validate(self, attrs):
        field_name = str(attrs.get("field_name") or "").strip()
        fields = [str(value).strip() for value in attrs.get("fields") or [] if str(value).strip()]
        if field_name:
            fields.insert(0, field_name)
        fields = list(dict.fromkeys(fields))
        if not fields:
            raise serializers.ValidationError({"fields": "请选择至少一个字段。"})
        attrs["fields"] = fields
        attrs.pop("field_name", None)
        if not isinstance(attrs.get("form_context"), dict):
            raise serializers.ValidationError({"form_context": "form_context 必须是对象。"})
        context_size = len(
            json.dumps(
                {
                    "current_value": attrs.get("current_value"),
                    "form_context": attrs.get("form_context"),
                },
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        )
        if context_size > 20_000:
            raise serializers.ValidationError({"form_context": "字段 context 超过 20 KiB 限制。"})
        return attrs


class EnrichmentDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            ("accept", "接受"),
            ("reject", "拒绝"),
            ("match_existing", "关联已有实体"),
            ("create_draft", "创建草稿"),
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    target_type = serializers.CharField(required=False, allow_blank=True, max_length=32)
    target_id = serializers.UUIDField(required=False, allow_null=True)
    canonical_term = serializers.CharField(required=False, allow_blank=True, max_length=500)
    node_type = serializers.CharField(required=False, allow_blank=True, max_length=32)
    confirm_new = serializers.BooleanField(required=False, default=False)


class UnknownEntityObservationSerializer(serializers.ModelSerializer):
    work_title = serializers.CharField(source="work.title", read_only=True)

    class Meta:
        model = UnknownEntityObservation
        fields = (
            "id",
            "work",
            "work_title",
            "edition",
            "asset",
            "page",
            "document_id",
            "page_number",
            "printed_page_label",
            "terms",
            "languages",
            "entity_guess",
            "evidence_text",
            "start_offset",
            "end_offset",
            "extraction_method",
            "extraction_version",
            "confidence",
            "confidence_factors",
            "source_text_checksum",
            "is_current",
            "created_at",
        )


class NewAuthorityCandidateSerializer(serializers.ModelSerializer):
    observations = UnknownEntityObservationSerializer(many=True, read_only=True)
    evidence_count = serializers.SerializerMethodField()
    independent_work_count = serializers.SerializerMethodField()
    possible_matches = serializers.SerializerMethodField()
    review_kind = serializers.SerializerMethodField()

    class Meta:
        model = NewAuthorityCandidate
        fields = (
            "id",
            "review_kind",
            "entity_type",
            "primary_term",
            "normalized_primary_term",
            "terms",
            "languages",
            "confidence",
            "confidence_factors",
            "possible_matches",
            "status",
            "fingerprint",
            "matched_entity_type",
            "matched_entity_id",
            "draft_entity_type",
            "draft_entity_id",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "evidence_count",
            "independent_work_count",
            "observations",
            "created_at",
            "updated_at",
        )

    def get_review_kind(self, obj):
        return "new_authority"

    def get_evidence_count(self, obj):
        return obj.observations.filter(is_current=True).count()

    def get_independent_work_count(self, obj):
        return obj.observations.filter(is_current=True).values("work_id").distinct().count()

    def get_possible_matches(self, obj):
        return possible_authority_matches(obj)


class QueryLexiconCandidateEvidenceReviewSerializer(serializers.ModelSerializer):
    work_title = serializers.CharField(source="work.title", read_only=True)

    class Meta:
        model = QueryLexiconCandidateEvidence
        fields = (
            "id",
            "work",
            "work_title",
            "edition",
            "asset",
            "page",
            "document_id",
            "page_number",
            "printed_page_label",
            "evidence_text",
            "left_term",
            "right_term",
            "detected_pair",
            "confidence",
            "confidence_factors",
            "ocr_quality",
            "quality_flags",
            "source_text_checksum",
            "extraction_version",
            "is_current",
        )


class QueryLexiconCandidateReviewSerializer(serializers.ModelSerializer):
    evidence_records = QueryLexiconCandidateEvidenceReviewSerializer(
        many=True,
        read_only=True,
    )
    review_kind = serializers.SerializerMethodField()
    target_label = serializers.SerializerMethodField()
    evidence_count = serializers.SerializerMethodField()
    independent_source_count = serializers.SerializerMethodField()

    class Meta:
        model = QueryLexiconCandidate
        fields = (
            "id",
            "review_kind",
            "candidate_type",
            "target_entity_type",
            "target_entity_id",
            "target_label",
            "anchor_term",
            "proposed_term",
            "language",
            "proposed_term_type",
            "confidence",
            "confidence_factors",
            "linking_status",
            "possible_targets",
            "ambiguity",
            "status",
            "displayable",
            "extraction_version",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "evidence_count",
            "independent_source_count",
            "evidence_records",
            "created_at",
            "updated_at",
        )

    def get_review_kind(self, obj):
        return "query_lexicon"

    def get_target_label(self, obj):
        target = next(
            (
                row
                for row in (obj.possible_targets or [])
                if str(row.get("entity_id") or "") == str(obj.target_entity_id or "")
            ),
            None,
        )
        return (target or {}).get("canonical_label", "")

    def get_evidence_count(self, obj):
        return obj.evidence_records.filter(is_current=True).count()

    def get_independent_source_count(self, obj):
        return obj.evidence_records.filter(is_current=True).values("work_id").distinct().count()
