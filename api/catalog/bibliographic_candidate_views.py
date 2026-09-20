"""Whole bibliographic records, using local evidence or explicit free lookup."""
from collections import OrderedDict
from hashlib import sha256
import json
from urllib.parse import quote

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiTypes

from catalog.contracts.identifiers import normalize_doi, normalize_isbn, valid_doi, valid_isbn
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition, CatalogingSession, Person
from catalog.services.field_decisions import formal_field_values
from common.permissions import CanEditMetadata, CanRunEnrichment
from ingestion.models import MetadataCandidate, FieldLock, UploadItem


FIELDS = {"title", "subtitle", "original_title", "authors", "translators", "publisher", "publication_year",
          "publication_place", "publication_date", "version_label", "isbn", "isbn10", "isbn13", "doi",
          "abstract", "journal_title", "volume", "issue", "page_range", "language", "document_type"}
CONTEXT_FIELDS = {"title", "authors", "isbn", "isbn10", "isbn13", "doi", "publisher", "publication_year", "language", "document_type"}
SOURCE_LABELS = {"crossref": "Crossref DOI记录", "crossref_title": "Crossref文献检索", "openlibrary": "Open Library出版版本",
                 "openlibrary_search": "Open Library ISBN检索", "openlibrary_title": "Open Library作品检索",
                 "local_catalog": "馆内出版版本", "first_pages": "PDF首页本地识别", "pdf_metadata": "PDF本地元数据",
                 "ocr_first_pages": "本地OCR首页", "canonical_first_pages": "馆内文档首页"}


def _named_contributors(values):
    identifiers = [identifier for field in ("authors", "translators") for identifier in values.get(field, [])]
    names = {str(identifier): name for identifier, name in Person.objects.filter(pk__in=identifiers).values_list("id", "preferred_name")} if identifiers else {}
    for field in ("authors", "translators"):
        values[field] = [names[str(identifier)] for identifier in values.get(field, []) if str(identifier) in names]
    return values


class BibliographicLookupSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    query = serializers.CharField(max_length=600, allow_blank=True, required=False, default="")
    allow_external = serializers.BooleanField(required=False, default=False)
    form_context = serializers.DictField(required=False, default=dict)

    def validate_form_context(self, value):
        clean = {key: val for key, val in value.items() if key in CONTEXT_FIELDS}
        if len(json.dumps(clean, ensure_ascii=False).encode()) > 10000:
            raise serializers.ValidationError("书目查询上下文过长。")
        for key, val in clean.items():
            if key == "authors":
                if not isinstance(val, list) or len(val) > 30 or any(not isinstance(name, str) or len(name) > 200 for name in val):
                    raise serializers.ValidationError("作者应为姓名列表。")
            elif not isinstance(val, (str, int, type(None))):
                raise serializers.ValidationError("书目查询只接受文字和年份。")
        return clean


def _group_candidates(candidates):
    groups = OrderedDict()
    for candidate in candidates:
        field = candidate.field_name
        if field not in FIELDS:
            continue
        evidence = candidate.evidence or {}
        source = candidate.source
        source_id = str(evidence.get("source_record_id") or getattr(candidate, "source_record_id", "") or source)
        rank = evidence.get("rank", 0)
        record_url = str(evidence.get("record_url") or evidence.get("source_url") or "")
        if not record_url and evidence.get("doi"):
            record_url = f"https://doi.org/{quote(str(evidence['doi']), safe='/()')}"
        elif not record_url and evidence.get("isbn"):
            record_url = f"https://openlibrary.org/isbn/{quote(str(evidence['isbn']), safe='')}"
        key = f"{source_id}:{rank}:{record_url}"
        row = groups.setdefault(key, {"id": sha256(key.encode()).hexdigest()[:24], "source": source,
            "source_label": SOURCE_LABELS.get(source, source), "source_url": record_url, "fields": {}, "field_actions": {}, "evidence": [],
            "version_status": "identifier_matched" if evidence.get("isbn") or evidence.get("doi") else "needs_confirmation",
            "version_note": "请核对版次后采用；来源提供候选，不覆盖人工值。"})
        # Open Library title search is a Work-level aggregate. Its first
        # publication year/publisher/ISBN cannot identify the held edition.
        if source == "openlibrary_title" and field not in {"title", "authors", "language"}:
            row["version_note"] = "作品级检索结果；尚未核对具体出版版本，请补充ISBN后再查。"
            continue
        row["fields"].setdefault(field, candidate.value)
        if getattr(candidate, "pk", None) and field not in {"authors", "translators"} and not isinstance(candidate.value, (dict, list)):
            row["field_actions"].setdefault(field, {"source_type": "metadata", "source_id": str(candidate.pk), "selected_value": str(candidate.value)})
        safe_evidence = {key: val for key, val in evidence.items() if key in {"record_url", "source_url", "page", "page_range", "rank", "isbn", "doi", "source_record_id", "edition_key", "match_type"}}
        if safe_evidence and safe_evidence not in row["evidence"]:
            row["evidence"].append(safe_evidence)
    return [row for row in groups.values() if row["fields"]]


class BibliographicCandidatesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=BibliographicLookupSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = BibliographicLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        edition = get_object_or_404(Edition.objects.select_related("work"), pk=data["edition_id"])
        current, confirmed = formal_field_values(edition, include_editorial_draft=True)
        current = {key: value for key, value in current.items() if key in FIELDS}
        current = _named_contributors(current)
        context = {key: current.get(key) for key in CONTEXT_FIELDS}
        context.update(data["form_context"])
        title = data["query"] or str(context.get("title") or "")
        fingerprint = sha256(json.dumps([str(edition.pk), title, context], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        candidates = MetadataCandidate.objects.filter(Q(upload_item__edition=edition) | Q(cataloging_session__edition=edition)).exclude(lifecycle__in=["rejected", "superseded"]).select_related("source_record").order_by("source_record_id", "source", "created_at")[:250]
        results = _group_candidates(candidate for candidate in candidates
            if not (candidate.evidence or {}).get("bibliographic_context_fingerprint")
            or candidate.evidence["bibliographic_context_fingerprint"] == fingerprint)
        if title:
            local = Edition.objects.filter(work__title__icontains=title).exclude(pk=edition.pk).select_related("work").order_by("-updated_at")[:8]
            for row in local:
                values, _ = formal_field_values(row, include_editorial_draft=False)
                values = _named_contributors(values)
                fields = {key: value for key, value in values.items() if key in FIELDS and value not in (None, "", [])}
                actions = {}
                session = CatalogingSession.objects.filter(edition=edition).order_by("-updated_at").first()
                if session:
                    for name, value in fields.items():
                        if isinstance(value, (dict, list)) or name in {"authors", "translators"}:
                            continue
                        evidence = {"catalog_edition_id": str(row.pk), "catalog_work_id": str(row.work_id), "source_label": "馆内出版版本", "bibliographic_context_fingerprint": fingerprint}
                        stored, _ = MetadataCandidate.objects.get_or_create(cataloging_session=session, field_name=name, source="local_catalog",
                            value=value, evidence=evidence, defaults={"confidence": 0, "normalized_value": {"value": value}})
                        if stored.lifecycle != "rejected":
                            actions[name] = {"source_type": "metadata", "source_id": str(stored.pk), "selected_value": str(value)}
                results.append({"id": f"edition:{row.pk}", "source": "local_catalog", "source_label": "馆内出版版本", "source_url": "",
                    "fields": fields, "field_actions": actions,
                    "evidence": [{"edition_id": str(row.pk), "work_id": str(row.work_id)}], "version_status": "needs_confirmation",
                    "version_note": "馆内已有版本；确认是否为同一版次，不会自动合并作品。"})
        sources = [{"key": "local", "state": "ready" if results else "no_match", "message": "已读取本地候选和馆内书目。"}]
        if data["allow_external"]:
            if not CanRunEnrichment().has_permission(request, self):
                return Response({"detail": "当前账户没有外部资料查询权限。", "code": "external_lookup_forbidden"}, status=403)
            from ingestion.services.metadata import resolve_doi, resolve_isbn, search_crossref_title, search_openlibrary_title
            from ingestion.services.provider_gateway import invoke_provider, _enabled
            isbn = normalize_isbn(context.get("isbn13") or context.get("isbn10") or context.get("isbn") or "")
            doi = normalize_doi(context.get("doi") or "")
            if isbn and not valid_isbn(isbn):
                return Response({"detail": "ISBN校验未通过，请核对后查询。"}, status=400)
            if doi and not valid_doi(doi):
                return Response({"detail": "DOI格式无效，请核对后查询。"}, status=400)
            item = UploadItem.objects.filter(edition=edition).order_by("-created_at").first()
            operations = []
            if doi:
                operations.append(("crossref", "doi", {"doi": doi}, lambda: resolve_doi(doi)))
            elif isbn:
                operations.append(("openlibrary", "isbn", {"isbn": isbn}, lambda: resolve_isbn(isbn)))
            elif title:
                operations = [("openlibrary", "title", {"title": title}, lambda: search_openlibrary_title(title, language=str(context.get("language") or "zh"))),
                              ("crossref", "title", {"title": title}, lambda: search_crossref_title(title))]
            else:
                return Response({"detail": "请先填写题名、ISBN或DOI。"}, status=400)
            for provider, operation, query, resolver in operations:
                if not _enabled(provider):
                    sources.append({"key": provider, "state": "disabled", "message": "来源未启用；可继续手工填写。"})
                    continue
                values, warnings = invoke_provider(provider=provider, operation=f"whole_record_{operation}", query=query, resolver=resolver, upload_item=item)
                # Reuse the existing candidate ledger so a later explicit
                # workspace save retains source/evidence and undo history.
                from catalog.services.cataloging_sessions import open_cataloging_session
                session, _ = open_cataloging_session(actor=request.user, edition_id=edition.pk, source_type="existing")
                stored = []
                for candidate in values:
                    if candidate.field_name not in FIELDS:
                        continue
                    if candidate.source == "openlibrary_title" and candidate.field_name not in {"title", "authors", "language"}:
                        continue
                    evidence = dict(candidate.evidence or {})
                    evidence["bibliographic_context_fingerprint"] = fingerprint
                    record_id = evidence.get("source_record_id")
                    match = MetadataCandidate.objects.filter(cataloging_session=session, source=candidate.source, field_name=candidate.field_name,
                                                              source_record_id=record_id, value=candidate.value, evidence__bibliographic_context_fingerprint=fingerprint, lifecycle="proposed").first()
                    if match is None:
                        match = MetadataCandidate.objects.create(cataloging_session=session, upload_item=item, source=candidate.source,
                            field_name=candidate.field_name, value=candidate.value, evidence=evidence, source_record_id=record_id,
                            confidence=candidate.confidence, normalized_value={"value": candidate.value})
                    stored.append(match)
                results.extend(_group_candidates(stored))
                sources.append({"key": provider, "state": "failed" if warnings else "ready" if values else "no_match", "message": "；".join(warnings) if warnings else "已查询免费来源。" if values else "没有匹配书目。"})
        else:
            sources.extend({"key": source, "state": "not_checked", "message": "点击查找免费来源后才会联网。"} for source in ("openlibrary", "crossref"))
        from catalog.contracts.fields import FIELD_CONTRACTS
        work_fields = [name for name, contract in FIELD_CONTRACTS.items() if contract.domain_object == "work"]
        locks = FieldLock.objects.filter(Q(edition=edition) | Q(edition__work_id=edition.work_id, field_name__in=work_fields)).values_list("field_name", flat=True).distinct()
        return Response({"results": results, "current_values": current, "locked_fields": list(locks), "confirmed_fields": sorted(confirmed),
                         "context_fingerprint": fingerprint, "sources": sources, "external_requested": data["allow_external"], "manual_available": True})
