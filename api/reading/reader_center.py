"""Read-only projection of existing private records for atlas R22; no second library."""
import heapq
from types import SimpleNamespace

from django.db.models import CharField, F, OuterRef, Subquery, Value
from rest_framework.exceptions import NotFound, ValidationError

from . import research
from .models import Annotation, CitationAudit, PersonalReadingPlan, ReadingList, ResearchMemory, ResearchProject, SavedItem
from .serializers import ReadingProgressSerializer, SavedItemSerializer
from .services import decrypt_private_text, readable_progress_for_user

PAGE_SIZE = 20
SEARCH_LIMIT = 5000
KINDS = {"research": "研究", "notes": "笔记", "plans": "计划", "lists": "书单", "audits": "引文体检", "confirmed": "已确认笔记", "saved": "选材"}
MODELS = {"research": ResearchProject, "notes": Annotation, "plans": PersonalReadingPlan,
          "lists": ReadingList, "audits": CitationAudit, "confirmed": ResearchMemory, "saved": SavedItem}


def collection(user, kind):
    rows = MODELS[kind].objects.filter(user=user)
    if kind == "plans":
        rows = rows.filter(public_path_id__isnull=True)
    elif kind == "audits":
        rows = rows.filter(purpose="manuscript").defer("original_ciphertext", "preview_ciphertext")
    elif kind == "confirmed":
        rows = rows.filter(state="confirmed")
    elif kind == "saved":
        rows = rows.select_related("work")
    return rows


def private_text(row, kind):
    if kind == "notes":
        return decrypt_private_text(row.body_ciphertext), ""
    if kind == "lists":
        return row.title, row.description
    if hasattr(row, "data_ciphertext"):
        data = research.unpack(row)
        title = data.get("body") if kind == "confirmed" else data.get("goal") if kind == "plans" else data.get("title") or data.get("filename")
        return str(title or ""), str(data.get("question") or "")
    return "", ""


def material(user, kind, row, *, text=None):
    title, question = text if text is not None else private_text(row, kind)
    title = title.strip().split("\n")[0][:160] or {"notes": "阅读标记", "plans": "未命名阅读计划", "lists": "未命名书单", "audits": "引文体检", "confirmed": "个人认识", "research": "未命名研究", "saved": "来源暂不可用"}[kind]
    state, path = "saved", ""
    if kind == "research":
        state = "archived" if row.archived else "saved"
        path = f"/account/research/{row.pk}"
    elif kind == "notes":
        state = "source_unavailable" if row.orphaned else "saved"
        path = f"/account/notes/{row.asset_id}#note-{row.pk}" if row.kind == "note" else "/account/notes"
    elif kind == "plans":
        data = research.unpack(row)
        items = data.get("items") or []
        statuses = [item.get("status") for item in items if isinstance(item, dict)]
        state = "completed" if statuses and all(value in {"completed", "skipped"} for value in statuses) else "reading" if "reading" in statuses else "pending"
        path = f"/account/plans/{row.pk}"
    elif kind == "lists":
        path = f"/account?section=lists#list-{row.pk}"
    elif kind == "audits":
        state = row.status
        path = f"/account/citation-audits/{row.pk}"
    elif kind == "confirmed":
        state, path = "confirmed", f"/account/confirmed-notes?memory={row.pk}"
    elif kind == "saved":
        current = SavedItemSerializer(row, context={"request": SimpleNamespace(user=user)}).data
        work = current.get("work_data")
        title = (work or {}).get("title") or "来源暂不可用"
        path = f"/works/{work['slug']}" if work and work.get("slug") else "/account?section=saved"
        state = "saved" if work else "source_unavailable"
    return {"id": str(row.pk), "key": f"{kind}:{row.pk}", "kind": kind, "kind_label": KINDS[kind],
            "title": title, "question": question[:240], "status": state, "href": path,
            "updated_at": row.updated_at.isoformat(), "revision": str(row.revision) if hasattr(row, "revision") else row.updated_at.isoformat()}


def ordered_materials(user, kinds, *, reverse=True):
    branches = [collection(user, name).order_by().annotate(material_kind=Value(name, output_field=CharField()))
                .values_list("id", "updated_at", "material_kind") for name in kinds]
    union = branches[0].union(*branches[1:], all=True) if len(branches) > 1 else branches[0]
    fields = ("-updated_at", "-id", "-material_kind") if reverse else ("updated_at", "id", "material_kind")
    return union.order_by(*fields)


def materials(user, *, kind="all", q="", order="newest", page=1):
    kinds = list(KINDS) if kind == "all" else [kind]
    counts = {name: collection(user, name).count() for name in KINDS}
    total = sum(counts[name] for name in kinds)
    start, stop = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    reverse = order == "newest"
    selected = []
    query = q.casefold().strip()
    if query:
        if total > SEARCH_LIMIT:
            raise ValidationError({"q": "所选范围超过5000条私人资料，请先选择资料类型再搜索；未截断或隐藏结果。"})
        total = 0
        # Encrypted private content stays out of the public search index.
        # Keep only the requested leading window, not all decrypted bodies.
        def matches():
            nonlocal total
            for name in kinds:
                for row in collection(user, name).order_by("id").iterator(chunk_size=100):
                    text = private_text(row, name)
                    descriptor = material(user, name, row, text=text) if name == "saved" else None
                    haystack = descriptor["title"] if descriptor else " ".join(text)
                    if query not in haystack.casefold():
                        continue
                    total += 1
                    yield (row.updated_at, str(row.pk), name)
        pick = heapq.nlargest if reverse else heapq.nsmallest
        selected = pick(stop, matches())[start:stop]
    else:
        # UNION carries identities/timestamps only; SQL applies the global offset.
        # Every branch retains its owner predicate before it enters the union.
        selected = [(stamp, str(pk), name) for pk, stamp, name in ordered_materials(user, kinds, reverse=reverse)[start:stop]]
    if page > 1 and start >= total:
        raise NotFound("这一页已没有资料，请返回第一页。")
    if len(selected) != min(PAGE_SIZE, max(0, total - start)):
        raise research.ResearchConflict("资料在读取时发生变化，请刷新当前页。")
    results = []
    for _, pk, name in selected:
        row = collection(user, name).filter(pk=pk).first()
        if row is None:
            # Never convert a concurrent deletion into a false empty library.
            raise research.ResearchConflict("资料在读取时发生变化，请刷新当前页。")
        results.append(material(user, name, row))
    return {"owner_id": str(user.pk), "count": total, "page": page, "page_size": PAGE_SIZE,
            "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), "counts": counts, "results": results}


def recent_progress_query(user):
    rows = readable_progress_for_user(user)
    latest = rows.filter(asset__edition__work_id=OuterRef("asset__edition__work_id")).order_by("-updated_at", "-created_at", "-id").values("id")[:1]
    return rows.select_related("asset__edition__work").annotate(latest_for_work_id=Subquery(latest)).filter(id=F("latest_for_work_id")).order_by("-updated_at", "-created_at", "-id")[:3]


def recent_reading(request):
    return ReadingProgressSerializer(recent_progress_query(request.user), many=True, context={"request": request}).data


def pending_tasks(user):
    output = []
    # Scan encrypted plans in update order until the visible six tasks are found.
    for plan in collection(user, "plans").order_by("-updated_at", "-id").iterator(chunk_size=25):
        data = research.unpack(plan)
        for item in data.get("items") or []:
            if not isinstance(item, dict) or item.get("status") not in {"pending", "reading"}:
                continue
            output.append({"id": f"{plan.pk}:{item.get('id', len(output))}", "title": str(item.get("title") or data.get("goal") or "阅读任务")[:160],
                "question": str(data.get("goal") or "")[:240], "status": item["status"], "updated_at": plan.updated_at.isoformat(),
                "href": f"/account/plans/{plan.pk}"})
            if len(output) == 6:
                return output
    return output
