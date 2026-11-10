"""Human paragraph continuity, with immutable history and a guarded undo."""
from uuid import uuid4

from django.db import transaction
from rest_framework.exceptions import ValidationError

from catalog import models as m
from catalog.services.intelligence_changes import uuid_value
from catalog.services.knowledge_core import require_editor
from catalog.services.knowledge_sources import current_structure, require_revision_access, digest, create_anchor, locator


def paragraph_ranges(revision, actor, pages):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    if not isinstance(pages, list) or len(pages) != 2 or any(type(p) is not int for p in pages) or not 1 <= pages[0] <= pages[1] <= revision.asset.page_count or pages[1]-pages[0] > 4:
        raise ValidationError("请选择连续1至5页进行段落校正。")
    structure = current_structure(revision)
    if not structure:
        raise ValidationError("请先准备正文结构。")
    nodes = structure.nodes.filter(kind="paragraph", segments__page__page_number__range=pages).distinct().prefetch_related("segments__page")
    rows = []
    for node in nodes:
        rows.append({"id": str(node.pk), "human_corrected": bool(node.source.get("human_corrected")),
            "segments": [{"page_number": s.page.page_number, "printed_label": s.page.printed_label,
                "start": s.start, "end": s.end, "exact": s.page.text[s.start:s.end]} for s in node.segments.all()]})
    return {"structure_id": str(structure.pk), "base_hash": structure.input_hash, "paragraphs": rows,
        "last_correction": structure.coverage.get("human_correction")}


@transaction.atomic
def correct_paragraph(revision, actor, *, node_ids, base_hash, reason, request_id, operation="join"):
    require_editor(actor)
    revision = m.DocumentRevision.objects.select_for_update().select_related("asset__edition").get(pk=revision.pk)
    require_revision_access(revision, actor, editorial=True)
    if not revision.is_active:
        raise ValidationError("历史正文只供核验，请在当前正文修订中校正结构。")
    if operation not in {"join", "undo"} or not isinstance(reason, str) or not 2 <= len(reason.strip()) <= 1000:
        raise ValidationError("请填写2至1000字的校正依据。")
    if not isinstance(node_ids, list) or len(node_ids) > 20:
        raise ValidationError("请选择2至20个完整段落。")
    ids = [uuid_value(v) for v in node_ids]
    request_key = str(uuid_value(request_id))
    fingerprint = digest([str(actor.pk), base_hash, sorted(map(str, ids)), reason.strip(), operation])
    previous_result = revision.structures.filter(coverage__human_correction__request_id=request_key).first()
    if previous_result:
        if previous_result.coverage["human_correction"]["request_hash"] != fingerprint:
            raise ValidationError("此请求标识已用于不同的段落校正。")
        return correction_result(previous_result, actor)
    previous = current_structure(revision)
    if not previous or previous.input_hash != base_hash:
        raise ValidationError("正文结构已有新版本，请重新读取段落后核对。")
    source = previous
    selected = []
    if operation == "undo":
        last = previous.coverage.get("human_correction", {})
        if not last.get("previous_structure_id") or ids:
            raise ValidationError("当前结构没有可撤销的人工校正。")
        source = revision.structures.get(pk=last["previous_structure_id"])
        if source.outline_revision_id != previous.outline_revision_id:
            raise ValidationError("目录已经改变，请在当前目录下重新校正。")
    nodes = list(source.nodes.prefetch_related("segments__page"))
    if operation == "join":
        selected = [n for n in nodes if n.pk in ids]
        if not 2 <= len(ids) == len(set(ids)) == len(selected) <= 20 or any(n.kind != "paragraph" for n in selected):
            raise ValidationError("请选择当前结构中的2至20个完整正文段落，脚注和标题不能并入正文。")
        if len({n.parent_id for n in selected}) != 1 or any(n.parent_id in ids for n in nodes):
            raise ValidationError("所选段落须位于同一小节且不含子节点。")
        intervening = [n for n in nodes if selected[0].order < n.order < selected[-1].order and n.pk not in ids]
        if any(n.kind not in {"footnote", "unresolved"} for n in intervening):
            raise ValidationError("所选段落之间还有正文或标题，请核对连续范围。")
        if any(not (s.end <= 40 or s.start >= len(s.page.text)-40) for n in intervening if n.kind == "unresolved" for s in n.segments.all()):
            raise ValidationError("所选段落之间仍有未识别的正文，请先校准这部分结构。")
        segments = [s for n in selected for s in n.segments.all()]
        positions = [(s.page.page_number, s.start, s.end) for s in segments]
        page_numbers = sorted({p for p, _, _ in positions})
        if not positions or positions != sorted(positions) or any(p == q and b > c for (p,a,b),(q,c,d) in zip(positions, positions[1:])):
            raise ValidationError("段落片段的顺序或范围无效。")
        if page_numbers != list(range(page_numbers[0], page_numbers[-1]+1)) or sum(s.end-s.start for s in segments) > 60000:
            raise ValidationError("校正须为连续页面内、不超过60000字符的一段正文。")
        for s in segments:
            if s.page.document_revision_id != revision.pk or digest(s.page.text) != s.page.content_hash or digest(s.page.text[s.start:s.end]) != s.content_hash:
                raise ValidationError("原文完整性校验失败，未保存结构校正。")
    mapping = {n.pk: uuid4() for n in nodes}
    joined_id = mapping[selected[0].pk] if selected else None
    for n in selected:
        mapping[n.pk] = joined_id
    correction = {"operation": operation, "request_id": request_key, "request_hash": fingerprint,
        "actor_id": str(actor.pk), "reason": reason.strip(), "previous_structure_id": str(previous.pk),
        "source_node_ids": list(map(str, ids)), "node_id": str(joined_id) if joined_id else None}
    coverage = {**source.coverage, "human_correction": correction,
        "human_corrected_paragraphs": sum(bool(n.source.get("human_corrected")) for n in nodes if n not in selected) + bool(selected)}
    if selected:
        old_cross = sum(len({s.page.page_number for s in n.segments.all()}) > 1 for n in selected)
        coverage["verified_cross_page_items"] = source.coverage.get("verified_cross_page_items", 0) - old_cross + (len(page_numbers) > 1)
        coverage["paragraph_method"] = "verified_source_ranges_with_human_corrections"
    structure = m.DocumentStructure.objects.create(document_revision=revision, outline_revision=previous.outline_revision,
        parser="human_correction", parser_version=source.parser_version, input_hash=digest(["paragraph-v1", str(previous.pk), request_key, fingerprint]), coverage=coverage)
    new_nodes, new_segments = [], []
    for n in nodes:
        if selected and n in selected[1:]:
            continue
        merged = bool(selected and n.pk == selected[0].pk)
        ranges = segments if merged else list(n.segments.all())
        new_nodes.append(m.DocumentNode(id=mapping[n.pk], structure=structure, document_revision=revision,
            parent_id=mapping.get(n.parent_id), kind=n.kind, order=len(new_nodes), title=n.title,
            content_hash=digest([s.page.text[s.start:s.end] for s in ranges]) if merged else n.content_hash,
            source={"human_corrected": True, "method": "human_paragraph_confirmation", "correction": correction} if merged else n.source))
        new_segments += [m.DocumentNodeSegment(node_id=mapping[n.pk], page=s.page, order=i, start=s.start, end=s.end, content_hash=s.content_hash) for i,s in enumerate(ranges)]
    m.DocumentNode.objects.bulk_create(new_nodes)
    m.DocumentNodeSegment.objects.bulk_create(new_segments)
    m.DocumentNodeReference.objects.bulk_create([m.DocumentNodeReference(source_id=mapping[r.source_id], target_id=mapping[r.target_id],
        kind=r.kind, label=r.label, provenance={**r.provenance, "retained_reference_id": str(r.pk)})
        for r in m.DocumentNodeReference.objects.filter(source__structure=source, target__structure=source)])
    from catalog.services.knowledge_source_updates import schedule_source_update
    schedule_source_update(revision, structure=structure)
    return correction_result(structure, actor)


def correction_result(structure, actor):
    change = structure.coverage["human_correction"]
    anchor = None
    if change.get("node_id"):
        node = structure.nodes.get(pk=change["node_id"])
        anchor = create_anchor(structure.document_revision, [{"page_number": s.page.page_number, "start": s.start,
            "end": s.end, "node_id": str(node.pk)} for s in node.segments.select_related("page")])
    return {"structure_id": str(structure.pk), "base_hash": structure.input_hash, "correction": change,
        "locator": locator(anchor, actor, editorial=True) if anchor else None}
