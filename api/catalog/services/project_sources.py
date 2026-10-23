"""Read project references from original revisions; resolve only one page of labels."""
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Edition, KnowledgeNode, MediaRendition, Person, ReadingPath, TheoryTimelineEvent
from catalog.services import editorial_blocks, shared_curation
from catalog.services.project_materials import current_articles, valid_id
from catalog.services.publication_eligibility import public_editions


def reference_states(references):
    """Batch the same identities and eligibility predicates used by resolve_target.

    No persisted availability cache: revocation is reflected on every request.
    Page labels still go through the original resolver, including exact-version checks.
    """
    keys = defaultdict(set)
    for ref in references:
        kind = ref.get("type")
        if not isinstance(kind, str): raise ValidationError("来源类型结构不完整，请在原文章核对。")
        if kind in {"work", "edition"}:
            key = valid_id(ref.get("edition_id") if kind == "work" else ref.get("id"))
            if key: keys["edition"].add(key)
        elif kind in {"span", "node", "person", "timeline", "reading_path", "image"}:
            key = valid_id(ref.get("id"))
            if key: keys[kind].add(key)
    saved, public = defaultdict(dict), defaultdict(set)
    from catalog.services.scoped_search import public_scholar_queryset
    models = {"node": KnowledgeNode, "person": Person, "timeline": TheoryTimelineEvent, "reading_path": ReadingPath, "image": MediaRendition}
    for kind, identifiers in keys.items():
        ids = sorted(identifiers)
        # Bound SQL parameters for both SQLite authoring and PostgreSQL deployment.
        for start in range(0, len(ids), 400):
            part = ids[start:start + 400]
            if kind == "edition":
                saved[kind].update((str(pk), str(work)) for pk, work in Edition.objects.filter(pk__in=part).values_list("pk", "work_id"))
                eligible = public_editions().filter(pk__in=part).values_list("pk", flat=True)
            elif kind == "span":
                location = Q(page__index__gte=1, page_number=F("page__index"), document_revision__asset_id=F("page__asset_id")) & (Q(page__asset__page_count__isnull=True) | Q(page__asset__page_count=0) | Q(page__index__lte=F("page__asset__page_count")))
                rows = shared_curation.sources("span").filter(location, pk__in=part, is_stale=False)
                saved[kind].update((str(pk), str(revision)) for pk, revision in rows.values_list("pk", "document_revision_id"))
                eligible = shared_curation.sources("span", public=True).filter(location, pk__in=part).values_list("pk", flat=True)
            else:
                rows = models[kind].objects.filter(pk__in=part)
                saved[kind].update((str(pk), True) for pk in rows.values_list("pk", flat=True))
                eligible = (public_scholar_queryset().filter(person_id__in=part).values_list("person_id", flat=True) if kind == "person" else
                    rows.filter(status="published").values_list("pk", flat=True) if kind in {"node", "reading_path"} else
                    rows.filter(review_status="approved").values_list("pk", flat=True) if kind == "timeline" else rows.values_list("pk", flat=True))
            public[kind].update(map(str, eligible))
    results = []
    for ref in references:
        kind, key = ref.get("type"), valid_id(ref.get("id"))
        group, lookup = ("edition", valid_id(ref.get("edition_id"))) if kind == "work" else (kind, key)
        identity = False
        if lookup and lookup in saved[group]:
            if kind in {"work", "edition"}:
                identity = ref == {"type": kind, "id": key, "edition_id": lookup} and (kind != "work" or saved[group][lookup] == key)
            elif kind == "span":
                identity = ref == {"type": kind, "id": key, "document_revision_id": saved[group][lookup]}
            else:
                identity = ref == {"type": kind, "id": key}
        results.append("public" if identity and lookup in public[group] else "private" if identity else "unavailable")
    return results


def directory(project, params):
    articles, versions = current_articles(project)
    titles = {str(row.pk): row.title for row in articles}
    order = {str(row.pk): index for index, row in enumerate(articles)}
    pointers = []
    for revision in versions.values("target_id", "materialized_preview__title", "materialized_preview__body_blocks", "materialized_preview__selection_workspace").iterator(chunk_size=2):
        article_id = str(revision["target_id"])
        title = revision["materialized_preview__title"] or titles[article_id]
        def add(origin, reference, *, position=None, block_id=None, context=""):
            if not isinstance(reference, dict): raise ValidationError("文章来源结构不完整，请在原文章核对。")
            pointers.append({"article_id": article_id, "article_title": title, "origin": origin, "reference": reference,
                "position": position, "block_id": block_id, "context": str(context)[:240]})
        blocks = revision["materialized_preview__body_blocks"] or []
        selection = revision["materialized_preview__selection_workspace"] or {}
        if not isinstance(blocks, list) or not isinstance(selection, dict): raise ValidationError("文章来源结构不完整，请在原文章核对。")
        try:
            for position, block in enumerate(blocks):
                for reference in editorial_blocks.block_references(block):
                    add("body", reference, position=position, block_id=block.get("id"), context=block.get("text", ""))
                if block.get("type") == "image":
                    add("body", {"type": "image", "id": block.get("image_rendition_id")}, position=position, block_id=block.get("id"), context=block.get("alt_text") or block.get("text", ""))
            for reference in selection.get("references", []): add("selection", reference, context=selection.get("question", ""))
        except (KeyError, TypeError, AttributeError):
            raise ValidationError("文章来源缺少原始身份或区块结构，请在原文章核对；本次未改动记录。")
    states = reference_states([row["reference"] for row in pointers])
    for row, state in zip(pointers, states): row["status"] = state
    totals = {"all": len(pointers), "missing": sum(state != "public" for state in states),
        "body": sum(row["origin"] == "body" for row in pointers), "selection": sum(row["origin"] == "selection" for row in pointers)}
    rows = pointers
    if params.get("origin") in {"body", "selection"}: rows = [row for row in rows if row["origin"] == params["origin"]]
    if params.get("scope") == "missing": rows = [row for row in rows if row["status"] != "public"]
    query = str(params.get("q", "")).strip()[:200].casefold()
    if query: rows = [row for row in rows if query in f"{row['article_title']} {row['context']}".casefold()]
    rows.sort(key=lambda row: (order[row["article_id"]], row["origin"] == "selection", row["position"] or 0))
    page = Paginator(rows, 30).get_page(params.get("page", 1))
    results = []
    for row in page.object_list:
        source, ref = {}, row["reference"]
        if row["status"] != "unavailable":
            try:
                if ref["type"] == "image": source = {"title": "正文图片", "edit_url": "/admin/media"}
                else:
                    exact, source = editorial_blocks.resolve_target(ref, public=row["status"] == "public")
                    if exact != ref: raise ValidationError("来源修订改变")
            except (Http404, ValidationError):
                # The source can be withdrawn between the batch read and label resolution.
                row = {**row, "status": "unavailable"}
                source = {}
        results.append({**row, "title": source.get("title") or "来源暂不可用", "reader_url": source.get("reader_url", ""),
            "source_url": source.get("href") or source.get("work_url") or "", "edit_url": source.get("edit_url", "")})
    return {"results": results, "count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages, "page_size": 30,
        "totals": totals, "article_count": len(articles), "checked_at": timezone.now(),
        "scope_notice": "项目全部文章当前保存的正文引用、正文图片与选材候选，按引用位置计数。待补包括尚未公开、已失效或修订不一致的来源。来源会随发布状态变化；完整文章发布检查仍包含标题、引文出处、图片权利与比较缺口。"}
