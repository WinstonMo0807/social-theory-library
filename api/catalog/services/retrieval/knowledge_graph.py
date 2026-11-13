"""Query-local evidence graph, projected from published source-specific assertions.

Personalized PageRank ranks a small bipartite retrieval graph. It does not infer
academic relations, merge identities, or count agreement as scholarly truth.
No graph database, generated community report, or model call is involved.
"""
from collections import defaultdict
from uuid import UUID

from django.db.models import Exists, OuterRef, Prefetch, Q

from catalog import models as m
from catalog.discovery_index_models import DiscoveryDocument
from catalog.services.knowledge_public import assertion_public, public_entities
from catalog.services.publication_eligibility import active_document_revision_q, current_retrieval_source_q

VERSION = "source_assertion_ppr_v1"
ENTITY_SEEDS = 8
RAW_SEEDS = 8
ASSERTIONS = 32
ROUNDS = 2
ANCHORS = 64
PASSAGES = 80
# General mentions/cooccurrence never open another expansion hop. These codes
# retain their original direction, expression and evidence stance in the path.
BRIDGE_PREDICATES = {"uses", "criticizes", "inherits", "develops", "cites", "responds_to",
    "proposes", "defines", "interprets", "explains", "influences", "influence", "criticism"}


def _statements(queryset):
    # Oversized editorial records remain readable through the knowledge API;
    # they do not monopolize an interactive query's expansion budget.
    return queryset.annotate(
        too_many_sources=Exists(m.AssertionSource.objects.filter(assertion_id=OuterRef("pk"))[32:33]),
        too_many_participants=Exists(m.AssertionParticipant.objects.filter(assertion_id=OuterRef("pk"))[64:65]),
        too_many_evidence=Exists(m.AssertionEvidence.objects.filter(assertion_id=OuterRef("pk"))[64:65]),
    ).filter(too_many_sources=False, too_many_participants=False, too_many_evidence=False).prefetch_related(
        Prefetch("sources", queryset=m.AssertionSource.objects.select_related(
            "document_revision__asset", "attribution"), to_attr="retrieval_sources"),
        Prefetch("participants", queryset=m.AssertionParticipant.objects.select_related("entity"),
            to_attr="retrieval_participants"))


def _source_overlap(rows):
    result = Q(pk__in=[])
    for row in rows[:RAW_SEEDS]:
        if row.get("document_revision_id") and row.get("pdf_page") and row.get("end_offset", 0) > row.get("start_offset", 0):
            result |= Q(anchor__document_revision_id=row["document_revision_id"],
                anchor__segments__page__page_number=row["pdf_page"],
                anchor__segments__start__lt=row["end_offset"], anchor__segments__end__gt=row["start_offset"])
    return result


def _current_segments(anchor_ids, access_statuses):
    return m.EvidenceSegment.objects.filter(anchor_id__in=anchor_ids).filter(
        active_document_revision_q(revision_prefix="anchor__document_revision"),
        current_retrieval_source_q(asset_prefix="anchor__document_revision__asset", access_statuses=access_statuses),
    ).select_related("anchor", "page").order_by("anchor_id", "order")


def _valid_segment(segment):
    from catalog.services.knowledge_sources import digest
    return (segment.page.document_revision_id == segment.anchor.document_revision_id
        and digest(segment.page.text) == segment.page.content_hash
        and 0 <= segment.start < segment.end <= len(segment.page.text)
        and digest(segment.page.text[segment.start:segment.end]) == segment.content_hash)


def _ppr(adjacency, seeds):
    """Deterministic personalized random walk; dangling mass returns to seeds."""
    total = sum(seeds.values())
    if not total:
        return {}, 0
    restart = {key: value / total for key, value in seeds.items()}
    scores = {key: restart.get(key, 0.0) for key in adjacency}
    for iteration in range(40):
        dangling = sum(value for key, value in scores.items() if not adjacency[key])
        next_scores = {key: (0.15 + 0.85 * dangling) * restart.get(key, 0.0) for key in adjacency}
        for key, neighbors in adjacency.items():
            if neighbors:
                share = 0.85 * scores[key] / len(neighbors)
                for neighbor in neighbors:
                    next_scores[neighbor] += share
        delta = sum(abs(next_scores[key] - scores[key]) for key in scores)
        scores = next_scores
        if delta < 1e-8:
            break
    return scores, iteration + 1


def recall(query, raw_rows, access_statuses, *, generation, scopes, filters):
    """Return original-text document references, plus measured graph coverage."""
    from catalog.services.knowledge_entity_queries import mentioned_entities
    metadata = {"algorithm": VERSION, "status": "no_evidence", "entity_seeds": 0, "raw_seeds": 0,
        "assertions": 0, "anchors": 0, "candidates": 0, "rounds": 0, "iterations": 0,
        "truncated": False, "limits": {"assertions": ASSERTIONS, "anchors": ANCHORS, "passages": PASSAGES, "rounds": ROUNDS}}
    if not generation or scopes == []:
        return [], metadata
    entities = mentioned_entities(query, public_entities(), limit=ENTITY_SEEDS + 1)
    metadata["truncated"] = len(entities) > ENTITY_SEEDS
    seeds = {f"e:{entity.pk}": 1.0 for entity in entities[:ENTITY_SEEDS]}
    frontier = {entity.pk for entity in entities[:ENTITY_SEEDS]}
    metadata["entity_seeds"] = len(frontier)
    raw_ids = list(m.AssertionEvidence.objects.filter(_source_overlap(raw_rows),
        assertion__status="published").order_by("assertion_id").values_list("assertion_id", flat=True).distinct()[:ASSERTIONS + 1])
    metadata["truncated"] |= len(raw_ids) > ASSERTIONS
    raw_ids = set(raw_ids[:ASSERTIONS])
    visible, seen, visibility = {}, set(), {}
    adjacency = defaultdict(set)
    for round_number in range(ROUNDS):
        condition = Q(participants__entity_id__in=frontier)
        if round_number == 0:
            condition |= Q(pk__in=raw_ids)
        remaining = ASSERTIONS - len(seen)
        if remaining <= 0 or (not frontier and not (round_number == 0 and raw_ids)):
            break
        candidates = list(m.Assertion.objects.filter(condition, status="published").exclude(pk__in=seen)
            .order_by("pk").values_list("pk", flat=True).distinct()[:remaining + 1])
        metadata["truncated"] |= len(candidates) > remaining
        selected = candidates[:remaining]
        seen.update(selected)
        next_frontier = set()
        for statement in _statements(m.Assertion.objects.filter(pk__in=selected)):
            if not assertion_public(statement, visibility=visibility):
                continue
            # A bibliographic reference or historical manual confirmation alone
            # cannot supply a graph edge to original-text retrieval.
            if not statement.evidence.exists():
                continue
            visible[statement.pk] = statement
            key = f"a:{statement.pk}"
            adjacency[key]
            if statement.pk in raw_ids:
                seeds[key] = 1.0
            for participant in statement.retrieval_participants:
                if not participant.entity_id:
                    continue
                entity_key = f"e:{participant.entity_id}"
                adjacency[key].add(entity_key)
                adjacency[entity_key].add(key)
                if statement.predicate in BRIDGE_PREDICATES and len(next_frontier) < 64:
                    next_frontier.add(participant.entity_id)
        frontier = next_frontier - frontier
        metadata["rounds"] = round_number + 1
    seeds = {key: value for key, value in seeds.items() if key in adjacency}
    metadata.update(assertions=len(visible), raw_seeds=sum(f"a:{key}" in seeds for key in raw_ids))
    if not seeds:
        return [], metadata
    links = list(m.AssertionEvidence.objects.filter(assertion_id__in=visible)
        .order_by("assertion_id", "anchor_id").values("assertion_id", "anchor_id", "stance")[:ANCHORS + 1])
    metadata["truncated"] |= len(links) > ANCHORS
    links = links[:ANCHORS]
    # Evidence roles affect the explanation, not agreement-weighted voting.
    for link in links:
        a, evidence = f"a:{link['assertion_id']}", f"p:{link['anchor_id']}"
        adjacency[a].add(evidence)
        adjacency[evidence].add(a)
    scores, iterations = _ppr(adjacency, seeds)
    anchors = sorted({link["anchor_id"] for link in links}, key=lambda key: (-scores.get(f"p:{key}", 0), str(key)))
    metadata.update(anchors=len(anchors), iterations=iterations)
    segments = defaultdict(list)
    source_segments = list(_current_segments(anchors, access_statuses)[:257])
    metadata["truncated"] |= len(source_segments) > 256
    for segment in source_segments[:256]:
        if _valid_segment(segment):
            segments[segment.anchor_id].append(segment)
    # Each book/version/range is retained independently. Query the active index
    # projection under exactly the same source scopes as lexical/vector recall.
    scope = Q(pk__in=[])
    for parts in segments.values():
        for part in parts:
            scope |= Q(document_revision_id=part.anchor.document_revision_id, payload__pdf_page=part.page.page_number)
    docs = DiscoveryDocument.objects.filter(scope, generation=generation, channel="passages", keyword_ready=True,
        access_status__in=access_statuses)
    if scopes is not None:
        docs = docs.filter(scope_token__in=scopes)
    if filters.get("languages"):
        from catalog.services.semantic_search import _language_filter_values
        docs = docs.filter(payload__language__in=_language_filter_values(filters["languages"]))
    # OCR pages can have many projected lines. Explicitly report this cap; never
    # materialize a whole collection or a dense all-entity similarity matrix.
    documents = list(docs.order_by("pk")[:1201])
    metadata["truncated"] |= len(documents) > 1200
    by_anchor = defaultdict(list)
    for link in links:
        by_anchor[link["anchor_id"]].append(str(link["assertion_id"]))
    candidates, ranks = {}, {}
    for anchor_id in anchors:
        for doc in documents[:1200]:
            start = int(doc.payload.get("source_start_offset") or 0) + doc.start_offset
            end = int(doc.payload.get("source_start_offset") or 0) + doc.end_offset
            if not any(part.anchor.document_revision_id == doc.document_revision_id
                and part.page.page_number == doc.payload.get("pdf_page") and part.start < end and part.end > start
                for part in segments[anchor_id]):
                continue
            key = str(doc.pk)
            value = candidates.setdefault(key, {"id": key, "source_revision": doc.source_revision, "knowledge_assertion_ids": []})
            value["knowledge_assertion_ids"] = list(dict.fromkeys([*value["knowledge_assertion_ids"], *by_anchor[anchor_id]]))[:4]
            ranks[key] = max(ranks.get(key, 0), scores.get(f"p:{anchor_id}", 0))
    metadata["truncated"] |= len(candidates) > PASSAGES
    result = [candidates[key] for key in sorted(candidates, key=lambda key: (-ranks[key], key))[:PASSAGES]]
    metadata.update(candidates=len(result), status="ready" if result else "no_current_originals")
    return result, metadata


def enrich_paths(rows, references):
    """Revalidate explanations on every response, including stored sessions."""
    from catalog.services.academic_vocabulary import PREDICATES
    ids = set()
    requested = {}
    for row in rows:
        values = []
        for value in references.get(row["id"], {}).get("knowledge_assertion_ids", [])[:4]:
            try:
                values.append(UUID(str(value)))
            except (ValueError, TypeError):
                continue
        requested[row["id"]] = values
        ids.update(values)
    if not ids:
        return rows
    visibility = {}
    statements = {s.pk: s for s in _statements(m.Assertion.objects.filter(pk__in=sorted(ids, key=str)[:ASSERTIONS], status="published"))
        if assertion_public(s, visibility=visibility)}
    segments = defaultdict(list)
    links = list(m.AssertionEvidence.objects.filter(assertion_id__in=statements)
        .order_by("assertion_id", "anchor_id")[:ANCHORS])
    by_anchor = defaultdict(list)
    for link in links:
        by_anchor[link.anchor_id].append(link)
    for part in m.EvidenceSegment.objects.filter(anchor_id__in=by_anchor).select_related("anchor", "page").order_by("anchor_id", "order")[:256]:
        if _valid_segment(part):
            for link in by_anchor[part.anchor_id]:
                segments[link.assertion_id].append((part, link.stance))
    for row in rows:
        paths = []
        for identity in requested[row["id"]]:
            statement = statements.get(identity)
            if not statement:
                continue
            overlaps = [(part, stance) for part, stance in segments[identity]
                if str(part.anchor.document_revision_id) == row.get("document_revision_id")
                and part.page.page_number == row.get("pdf_page")
                and part.start < row.get("end_offset", 0) and part.end > row.get("start_offset", 0)]
            if overlaps:
                paths.append({"assertion_id": str(identity), "predicate": statement.predicate,
                    "predicate_label":PREDICATES.get(statement.predicate, statement.predicate),
                    "direction": statement.direction, "expression": statement.expression,
                    "evidence": [{"anchor_id": str(part.anchor_id), "stance": stance} for part, stance in overlaps],
                    "participants": [{"entity_id": str(p.entity_id) if p.entity_id else None,
                        "work_id": str(p.work_id) if p.work_id else None, "role": p.role} for p in statement.retrieval_participants],
                    "meaning": "retrieval_relatedness"})
        row["knowledge_paths"] = paths
        row["knowledge_assertion_ids"] = [path["assertion_id"] for path in paths]
    return rows
