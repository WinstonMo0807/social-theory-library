"""Editor-only material selection on the existing issue revision, never public prose."""
from copy import deepcopy

from django.http import Http404
from rest_framework.exceptions import ValidationError

from catalog.services.discovery_sessions import normalize_filters
from catalog.services.editorial_blocks import resolve_target
from catalog.services.editorial_issues import _text


def normalize(value, previous=None):
    # Existing full-resource clients may echo read-only materials. Never persist
    # or trust them; every source is resolved again from its canonical identity.
    if not isinstance(value, dict) or set(value) - {"question", "query", "filters", "references", "materials"}:
        raise ValidationError({"selection_workspace": "选材仅保存问题、检索范围和准确材料身份。"})
    raw_filters = value.get("filters", {})
    allowed = {"year_min", "year_max", "document_types", "languages", "work_ids", "topic_ids", "theory_node_ids", "concepts", "topics", "theories"}
    if not isinstance(raw_filters, dict) or set(raw_filters) - allowed:
        raise ValidationError({"selection_workspace": "选材范围包含不支持的条件。"})
    filters = normalize_filters(raw_filters)
    incoming = value.get("references", [])
    if not isinstance(incoming, list) or len(incoming) > 40:
        raise ValidationError({"selection_workspace": "最多保留40项已选材料。"})
    retained = (previous or {}).get("references", [])
    references = []
    for raw in incoming:
        try:
            reference, _source = resolve_target(raw)
        except (Http404, ValidationError):
            if raw not in retained:
                raise
            reference = deepcopy(raw)
        if reference in references:
            raise ValidationError({"selection_workspace": "同一准确材料不必重复选择。"})
        references.append(reference)
    return {"question": _text(value.get("question", ""), 4000), "query": _text(value.get("query", ""), 200),
            "filters": filters, "references": references}


def present(value):
    result = deepcopy(value or {"question": "", "query": "", "filters": {}, "references": []})
    result["materials"] = []
    for reference in result["references"]:
        try:
            exact, source = resolve_target(reference)
            if exact != reference:
                raise ValidationError("材料修订改变")
            try:
                resolve_target(reference, public=True)
                eligible = True
            except (Http404, ValidationError):
                eligible = False
            result["materials"].append({"target": reference, "source": source, "available": True, "public_eligible": eligible})
        except (Http404, ValidationError):
            result["materials"].append({"target": reference, "source": None, "available": False, "public_eligible": False})
    return result


def related(issue, kind):
    """One-hop recorded relationships from saved, currently public selections."""
    from django.db.models import Q
    from catalog.models import KnowledgeRelation, PersonNodeRelation
    from catalog.services import editorial_issues as ledger
    from catalog.services.contribution_projection import contribution_projection, edition_author_projection
    from catalog.services.publication_eligibility import public_editions
    from catalog.services.scoped_search import public_scholar_queryset
    from catalog.services.shared_curation import identifier, sources
    if kind not in {"person", "node"}:
        raise ValidationError("请选择关联人物或概念。")
    version = ledger.edit_version("recommendation_issue", issue.pk)
    references = ledger.issue_draft_payload(issue).get("selection_workspace", {}).get("references", [])
    candidates, people, nodes, titles, unavailable, truncated = {}, set(), set(), {}, 0, False

    def add(target_kind, key, reason):
        nonlocal truncated
        if target_kind != kind:
            return
        try:
            key = str(identifier(key))
        except ValidationError:
            return
        if key not in candidates and len(candidates) >= 120:
            truncated = True
            return
        reasons = candidates.setdefault(key, [])
        if reason not in reasons and len(reasons) < 6:
            reasons.append(reason)

    for reference in references:
        try:
            exact, source = resolve_target(reference, public=True)
            if exact != reference:
                raise ValidationError("来源修订改变")
        except (Http404, ValidationError):
            unavailable += 1
            continue
        title = source["title"]
        titles[(reference["type"], reference["id"])] = title
        if reference["type"] in {"work", "edition", "span"}:
            edition = public_editions().filter(pk=source["edition_id"]).first()
            if not edition:
                unavailable += 1
                continue
            snapshot = edition.active_catalog_revision.snapshot or {}
            if reference["type"] == "span":
                span = sources("span", public=True).filter(pk=reference["id"], document_revision_id=reference["document_revision_id"]).first()
                if not span:
                    unavailable += 1
                    continue
                authors = contribution_projection(edition).for_range(span.page.asset_id, span.document_revision_id, span.page_number)
            else:
                authors = edition_author_projection(snapshot)
            for key in authors["author_ids"]:
                add("person", key, f"《{title}》所选原文范围的已确认作者" if reference["type"] == "span" else f"《{title}》正式版本的整版作者")
            for node in (snapshot.get("knowledge") or {}).get("nodes") or []:
                if isinstance(node, dict):
                    add("node", node.get("id"), f"《{title}》正式版本关联知识节点；不据此断言该原文讨论此概念")
        elif reference["type"] == "person":
            people.add(reference["id"])
        elif reference["type"] == "node":
            nodes.add(reference["id"])
    links = PersonNodeRelation.objects.filter(status="published", node__status="published", person_id__in=public_scholar_queryset().values("person_id"))
    links = links.filter(node_id__in=nodes) if kind == "person" else links.filter(person_id__in=people)
    for index, link in enumerate(links.order_by("pk")[:121]):
        if index == 120:
            truncated = True
            break
        origin = titles.get(("node", str(link.node_id))) if kind == "person" else titles.get(("person", str(link.person_id)))
        add(kind, link.person_id if kind == "person" else link.node_id, f"{origin} · {link.relation_label or '已发布人物与知识关系'}")
    if kind == "node" and nodes:
        relations = KnowledgeRelation.objects.filter(status="published", source_node__status="published", target_node__status="published").filter(Q(source_node_id__in=nodes)|Q(target_node_id__in=nodes)).select_related("source_node", "target_node").order_by("pk")
        for index, link in enumerate(relations[:121]):
            if index == 120:
                truncated = True
                break
            reason = f"{link.source_node.canonical_name_zh} → {link.get_relation_type_display()} → {link.target_node.canonical_name_zh}" if link.direction == "directed" else f"{link.source_node.canonical_name_zh} ↔ {link.get_relation_type_display()} ↔ {link.target_node.canonical_name_zh}"
            add("node", link.target_node_id if str(link.source_node_id) in nodes else link.source_node_id, reason)
    selected = {(value["type"], value["id"]) for value in references}
    result = []
    for key, reasons in candidates.items():
        if (kind, key) in selected:
            continue
        try:
            target, source = resolve_target({"type": kind, "id": key}, public=True)
        except (Http404, ValidationError):
            continue
        source["public_eligible"] = True
        result.append({"target": target, "source": source, "reasons": reasons})
    ledger._check_version("recommendation_issue", issue.pk, version)
    return sorted(result, key=lambda row: (row["source"]["title"], row["target"]["id"])), {
        "edit_version": version, "truncated": truncated, "unavailable_count": unavailable,
        "notice": "依据当前已保存选材的正式署名、版本知识编目及已发布关系；不推断未记录的影响或相似关系。"}
