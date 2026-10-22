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
