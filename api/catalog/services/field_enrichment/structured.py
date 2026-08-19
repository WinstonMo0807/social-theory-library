from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from uuid import UUID

from django.utils import timezone

from catalog.models import EnrichmentSourceClass, KnowledgeNode
from catalog.services import authority_suggestions as authority_service
from catalog.services.passage_language import detect_passage_language
from ingestion.models import SourceRecord
from ingestion.services.provider_gateway import refresh_remote_candidates

from .policies import FieldPolicy
from .types import EnrichmentError, FieldObservation
from .values import stable_json


PROVIDER_SOURCE_CLASSES = {
    "wikidata": EnrichmentSourceClass.IDENTIFIER_REGISTRY,
    "viaf": EnrichmentSourceClass.NATIONAL_LIBRARY,
    "loc": EnrichmentSourceClass.NATIONAL_LIBRARY,
    "openalex": EnrichmentSourceClass.ACADEMIC_JOURNAL,
    "crossref": EnrichmentSourceClass.IDENTIFIER_REGISTRY,
    "openlibrary": EnrichmentSourceClass.LIBRARY_CATALOG,
    "google_books": EnrichmentSourceClass.LIBRARY_CATALOG,
    "grobid": EnrichmentSourceClass.ACADEMIC_JOURNAL,
}


def _record(record_id) -> SourceRecord | None:
    if not record_id:
        return None
    try:
        identifier = UUID(str(record_id))
    except (TypeError, ValueError):
        return None
    return SourceRecord.objects.filter(pk=identifier).first()


def _structured_text(row: dict) -> str:
    values = []
    for key in (
        "label",
        "original_name",
        "birth_year",
        "death_year",
        "external_ids",
        "affiliations",
        "description",
    ):
        value = row.get(key)
        if value not in (None, "", [], {}):
            values.append(f"{key}: {stable_json(value)}")
    return "；".join(values)[:4000]


def _authority_entity_type(target_type: str, target) -> str:
    if target_type == "person":
        return "person"
    if target_type in {"discipline", "subdiscipline", "topic"}:
        return target_type
    if target_type == "knowledge_node":
        if target.node_type in {
            KnowledgeNode.NodeType.DISCIPLINE,
            KnowledgeNode.NodeType.SUBDISCIPLINE,
            KnowledgeNode.NodeType.THEORY_TRADITION,
            KnowledgeNode.NodeType.TOPIC,
        }:
            return target.node_type
        return "concept"
    raise ValueError("该 target 不支持 authority structured adapter。")


def _authority_rows(entity_type: str, query: str) -> tuple[list[dict], list[EnrichmentError]]:
    providers = ["wikidata"]
    if entity_type == "person":
        providers.extend(["viaf", "openalex"])
    if not authority_service.CJK_RE.search(query):
        providers.append("loc")
    providers = [value for value in providers if authority_service._provider_enabled(value)]
    rows: list[dict] = []
    errors: list[EnrichmentError] = []
    for provider in providers:
        try:
            rows.extend(authority_service._fetch_provider_with_policy(provider, entity_type, query))
        except authority_service.PROVIDER_RESULT_ERRORS as exc:
            errors.append(
                EnrichmentError(
                    code="provider_unavailable",
                    provider=provider,
                    detail=str(exc)[:300],
                )
            )
    return rows, errors


def _authority_observation(
    *,
    policy: FieldPolicy,
    row: dict,
    value,
    locator_field: str,
    source_class: str | None = None,
) -> FieldObservation:
    provider = str(row.get("provider") or row.get("source") or "authority").casefold()
    record = _record(row.get("source_record_id"))
    source_url = str(row.get("source_url") or "").strip()
    label = str(row.get("label") or row.get("original_name") or "").strip()
    payload = stable_json(row)
    return FieldObservation(
        field_name=policy.field_name,
        value=value,
        provider=provider,
        source_class=source_class or PROVIDER_SOURCE_CLASSES.get(
            provider, EnrichmentSourceClass.UNKNOWN
        ),
        source_url=source_url,
        canonical_url=source_url,
        source_title=f"{row.get('source') or provider} · {label}"[:1000],
        supporting_text=_structured_text(row),
        content_checksum=sha256(payload.encode("utf-8")).hexdigest(),
        retrieved_at=record.retrieved_at if record else timezone.now(),
        locator={"kind": "structured_record", "field": locator_field},
        source_record_id=record.id if record else None,
        external_identifier=str(row.get("id") or "")[:500],
        identity_claims={
            "name": row.get("label"),
            "original_name": row.get("original_name"),
            "aliases": [item.get("name") for item in row.get("aliases") or [] if isinstance(item, dict)],
            "birth_year": row.get("birth_year"),
            "death_year": row.get("death_year"),
            "external_ids": row.get("external_ids") or {},
            "affiliations": row.get("affiliations") or [],
        },
        confidence_factors={"structured_provider": provider, "source_record": bool(record)},
        content_type="application/json",
        extraction_method="structured_provider",
    )


class AuthorityStructuredAdapter:
    name = "authority"

    def collect(self, *, target_type: str, target, policies: tuple[FieldPolicy, ...], context: dict):
        entity_type = _authority_entity_type(target_type, target)
        queries = [
            str(value).strip()
            for value in context.get("canonical_terms") or []
            if len(str(value).strip()) >= 2
        ][:2]
        if not queries:
            return [], [EnrichmentError(code="identity_query_missing", detail="目标缺少可查询规范名。")]
        rows: list[dict] = []
        errors: list[EnrichmentError] = []
        # Chinese authority headings often omit identity attributes that are
        # present in the original-language heading. Query at most two verified
        # canonical terms and let the identity gate judge each observation;
        # never broaden to generated transliterations or arbitrary aliases.
        for query in queries:
            query_rows, query_errors = _authority_rows(entity_type, query)
            rows.extend(query_rows)
            errors.extend(query_errors)
        deduplicated_errors: dict[tuple[str, str, str], EnrichmentError] = {}
        for error in errors:
            deduplicated_errors[(error.provider, error.code, error.detail)] = error
        errors = list(deduplicated_errors.values())
        observations: list[FieldObservation] = []
        canonical = {str(value).strip().casefold() for value in context.get("canonical_terms") or [] if str(value).strip()}
        for row in rows:
            for policy in policies:
                if policy.field_name == "external_identifier":
                    for scheme, value in (row.get("external_ids") or {}).items():
                        if value:
                            observations.append(
                                _authority_observation(
                                    policy=policy,
                                    row=row,
                                    value={"scheme": scheme, "value": value},
                                    locator_field=f"external_ids.{scheme}",
                                    source_class=EnrichmentSourceClass.IDENTIFIER_REGISTRY,
                                )
                            )
                elif policy.field_name == "affiliation":
                    for affiliation in row.get("affiliations") or []:
                        if isinstance(affiliation, dict) and affiliation.get("name"):
                            observations.append(
                                _authority_observation(
                                    policy=policy,
                                    row=row,
                                    value={"name": affiliation["name"]},
                                    locator_field="affiliations",
                                )
                            )
                elif policy.field_name in {"name_variant", "alias", "foreign_name"}:
                    names = []
                    if row.get("original_name"):
                        names.append((row["original_name"], "original_name"))
                    names.extend(
                        (item.get("name"), "aliases")
                        for item in row.get("aliases") or []
                        if isinstance(item, dict) and item.get("name")
                    )
                    for name, locator in names:
                        if str(name).strip().casefold() in canonical:
                            continue
                        language = detect_passage_language(str(name))
                        if policy.field_name == "name_variant":
                            value = {
                                "name": name,
                                "language": language,
                                "variant_type": "transliteration" if language in {"zh", "en"} else "alias",
                            }
                        elif policy.field_name == "alias":
                            value = {
                                "alias": name,
                                "language": language,
                                "alias_type": "translation" if language in {"zh", "en"} else "alias",
                            }
                        else:
                            if language != "en":
                                continue
                            value = name
                        observations.append(
                            _authority_observation(
                                policy=policy,
                                row=row,
                                value=value,
                                locator_field=locator,
                            )
                        )
        return observations, errors


def _bibliographic_source_url(provider: str, evidence: dict) -> str:
    value = str(evidence.get("record_url") or "").strip()
    if value:
        return value
    return {
        "crossref": "https://api.crossref.org",
        "openlibrary": "https://openlibrary.org",
        "google_books": "https://books.google.com",
        "openalex": "https://openalex.org",
        "grobid": "https://grobid.readthedocs.io",
    }.get(provider, "https://example.invalid")


class BibliographicStructuredAdapter:
    name = "bibliographic"

    def collect(self, *, target_type: str, target, policies: tuple[FieldPolicy, ...], context: dict):
        if target_type == "edition":
            edition = target
        elif target_type == "work":
            edition = target.editions.order_by("-is_primary", "-publication_year").first()
            if edition is None:
                return [], [EnrichmentError(code="edition_missing", detail="作品没有可核对的版本。")]
        else:
            return [], [EnrichmentError(code="adapter_target_mismatch", detail="书目 adapter 只支持 Work/Edition。")]
        candidates, warnings = refresh_remote_candidates(edition, upload_item=None)
        errors = [
            EnrichmentError(code="provider_partial_failure", detail=value[:300])
            for value in warnings
        ]
        policies_by_field = {policy.field_name: policy for policy in policies}
        groups: dict[str, list] = defaultdict(list)
        for candidate in candidates:
            key = str((candidate.evidence or {}).get("source_record_id") or candidate.source)
            groups[key].append(candidate)
        observations = []
        for group in groups.values():
            claims: dict = {"external_ids": {}}
            for candidate in group:
                if candidate.field_name == "title":
                    claims["title"] = candidate.value
                elif candidate.field_name in {"authors", "publication_year", "publisher"}:
                    claims[candidate.field_name] = candidate.value
                elif candidate.field_name in {"doi", "isbn"}:
                    claims["external_ids"][candidate.field_name] = candidate.value
            for candidate in group:
                policy = policies_by_field.get(candidate.field_name)
                if policy is None:
                    continue
                evidence = dict(candidate.evidence or {})
                record = _record(evidence.get("source_record_id"))
                provider = str(candidate.source or "bibliographic").casefold()
                source_url = _bibliographic_source_url(provider, evidence)
                exact_text = f"{candidate.field_name}: {stable_json(candidate.value)}"
                observations.append(
                    FieldObservation(
                        field_name=policy.field_name,
                        value=candidate.value,
                        provider=provider,
                        source_class=PROVIDER_SOURCE_CLASSES.get(provider, EnrichmentSourceClass.UNKNOWN),
                        source_url=source_url,
                        canonical_url=source_url,
                        source_title=f"{provider} structured bibliographic record",
                        supporting_text=exact_text,
                        content_checksum=sha256(
                            stable_json({"candidate": candidate.value, "evidence": evidence}).encode("utf-8")
                        ).hexdigest(),
                        retrieved_at=record.retrieved_at if record else timezone.now(),
                        locator={"kind": "structured_record", "field": candidate.field_name},
                        source_record_id=record.id if record else None,
                        external_identifier=str(record.external_id if record else "")[:500],
                        identity_claims=claims,
                        confidence_factors={"provider_confidence": candidate.confidence},
                        content_type="application/json",
                        extraction_method="structured_provider",
                    )
                )
        return observations, errors


STRUCTURED_ADAPTERS = {
    AuthorityStructuredAdapter.name: AuthorityStructuredAdapter(),
    BibliographicStructuredAdapter.name: BibliographicStructuredAdapter(),
}
