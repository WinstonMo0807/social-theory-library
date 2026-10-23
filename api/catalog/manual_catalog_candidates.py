"""Explicit prefill before an Edition exists; source decisions join the original ledger on save."""
from django.core import signing
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.bibliographic_candidate_views import BibliographicLookupSerializer, _group_candidates
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.bibliographic_sources import lookup_sources
from common.permissions import CanEditMetadata, CanRunEnrichment

SALT = "stl4.manual-catalog.prefill"
WORK_FIELDS = {"title", "subtitle", "abstract", "language", "document_type"}
BIBLIOGRAPHY_FIELDS = {"publisher", "publication_year", "publication_place", "version_label", "isbn", "isbn10", "isbn13", "doi", "journal_title", "volume", "issue", "page_range"}
PREFILL_FIELDS = WORK_FIELDS | BIBLIOGRAPHY_FIELDS | {"authors", "translators"}


class ManualLookupInput(BibliographicLookupSerializer):
    edition_id = None
    allow_external = None


class ManualCandidateOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    results = serializers.ListField(child=serializers.JSONField())
    sources = serializers.ListField(child=serializers.JSONField())


class PrefillSelection(serializers.Serializer):
    token = serializers.CharField(max_length=50000)
    fields = serializers.ListField(child=serializers.ChoiceField(choices=sorted(PREFILL_FIELDS)), min_length=1, max_length=30)


def unpack_selections(selections, actor):
    rows, seen = [], set()
    for selection in selections:
        try:
            row = signing.loads(selection["token"], salt=SALT, max_age=86400)
        except signing.BadSignature as error:
            raise ValidationError("预填来源已过期或无法核对。填写仍保留，请重新查询，或移除来源后按人工填写保存。") from error
        if row.get("owner_id") != str(actor.pk): raise PermissionDenied("预填来源不属于当前账户。")
        for field in selection["fields"]:
            canonical = "isbn" if field in {"isbn10", "isbn13"} else field
            if canonical in seen or field not in row["fields"]: raise ValidationError("同一字段只能保留一个实际采用的来源。")
            seen.add(canonical)
            rows.append((field, row))
    return rows


def record_prefills(rows, edition, session, actor, request_id, *, shared_work):
    from catalog.models import CatalogFieldDecision
    from catalog.services.field_decisions import formal_field_values, record_edition_field_decision
    from catalog.services.work_editor import _json_safe
    from catalog.services.field_locks import scoped_locks
    from ingestion.models import MetadataCandidate, SourceRecord
    from django.utils import timezone
    values, _ = formal_field_values(edition)
    result = []
    for field, row in rows:
        if shared_work and field in WORK_FIELDS: raise ValidationError("已有作品的共同信息不能从新版本预填改写。请移除这项来源或回作品工作页核对。")
        proposed = row["fields"][field]
        canonical = "isbn" if field in {"isbn10", "isbn13"} else field
        lock_fields = {canonical, field}
        if canonical == "isbn": lock_fields.update({"isbn10", "isbn13"})
        if field in {"authors", "translators"}: lock_fields.add("contributors")
        if scoped_locks(edition).filter(field_name__in=lock_fields).exists():
            raise ValidationError("所选预填字段已有人工锁，请回材料编辑页核对；本次保存没有覆盖锁定值。")
        final = values.get(canonical)
        # Person names are evidence, never an identity match or permission to create.
        comparison = list(edition.contributions.filter(role="author" if field == "authors" else "translator").order_by("order").values_list("person__preferred_name", flat=True)) if field in {"authors", "translators"} else final
        outcome = "used_unchanged" if comparison == proposed else "used_after_edit"
        source_ids = {str(evidence["source_record_id"]) for evidence in row.get("evidence", []) if evidence.get("source_record_id")}
        if len(source_ids) != 1: raise ValidationError("预填来源记录不完整，请重新查询或按人工填写保存。")
        source = SourceRecord.objects.select_for_update().filter(pk=next(iter(source_ids)), status="succeeded").first()
        if source is None: raise ValidationError("预填来源已不可用，请重新查询或按人工填写保存。")
        candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name=field, value=proposed,
            source=row["source"], source_record=source, confidence=0, normalized_value={"value": proposed},
            evidence={"source_url": row.get("source_url", ""), "records": row.get("evidence", []), "manual_prefill": True},
            lifecycle=MetadataCandidate.Lifecycle.ACCEPTED, selected=True, accepted_by=actor, accepted_at=timezone.now())
        decision = record_edition_field_decision(edition, canonical, actor=actor, value=_json_safe(final),
            status=CatalogFieldDecision.Status.NEEDS_REVIEW, confirmation_method=CatalogFieldDecision.ConfirmationMethod.CANDIDATE,
            candidate_type="metadata", candidate_id=candidate.pk,
            provenance={"source": "manual_catalog_prefill", "suggested_value": proposed, "outcome": outcome, "request_id": str(request_id),
                        "correctness": "not_evaluated", "training_eligibility": "not_reviewed"},
            evidence_summary=row.get("evidence", []) + [{"category": row["source_label"], "summary": "新建书目中明确采用的候选", "locator": {"url": row.get("source_url", "")}}],
            reason="候选预填后按本页人工核对结果保存；未确认发布")
        result.append({"field": canonical, "candidate_id": str(candidate.pk), "decision_id": str(decision.pk), "outcome": outcome})
    return result


class ManualCatalogCandidatesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata, CanRunEnrichment]

    @extend_schema(request=ManualLookupInput, responses=ManualCandidateOutput)
    def post(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("账户已变化，请重新打开书目。")
        incoming = ManualLookupInput(data=request.data); incoming.is_valid(raise_exception=True)
        context = incoming.validated_data["form_context"]
        title = incoming.validated_data["query"] or str(context.get("title") or "")
        results, sources = [], []
        for values, state in lookup_sources(context, title):
            sources.append(state)
            for row in _group_candidates(values):
                row["fields"] = {key: value for key, value in row["fields"].items() if key in PREFILL_FIELDS}
                row.pop("field_actions", None)
                if not row["fields"]: continue
                row["token"] = signing.dumps({**row, "owner_id": str(request.user.pk)}, salt=SALT, compress=True)
                results.append(row)
        return Response({"owner_id": str(request.user.pk), "results": results, "sources": sources})
