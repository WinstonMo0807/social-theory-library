"""Blank-page copies of an explicitly saved mapping; never replace source pages."""
from collections import defaultdict
from uuid import UUID, uuid4

from django.db import transaction

from catalog.models import Asset
from catalog.services.document_outline import OutlineConflict, _source_current
from catalog.services.page_mapping import _guard, source_fingerprint, validate_data, diagnostics
from ingestion.models import ProcessingJob

OPERATION = "page_mapping_export"
PROCESSOR = "page-mapping-blank-copy"


def expanded_mapping(data):
    """The same explicit insertion order drives PDF bytes, page rows and publication."""
    from copy import deepcopy
    missing = defaultdict(list)
    for row in data["missing"]:
        if row.get("action", "mark") == "blank":
            missing[row["after_pdf_page"]].append(row)
    positions, pages, inserted = {}, [], []
    for item in data["pages"]:
        old = item["pdf_page"]
        positions[old] = len(pages) + 1
        pages.append({**deepcopy(item), "pdf_page": positions[old]})
        for row in missing.get(old, []):
            page = {"pdf_page": len(pages) + 1, "labels": [row["label"]], "page_type": "blank",
                "confirmed": True, "note": row["note"], "source_note": "补页空白，无原文内容",
                "source": "manual", "confidence": 1, "override_manual": False}
            pages.append(page)
            inserted.append({**row, "pdf_page": page["pdf_page"]})
    result = {"pages": pages,
        "segments": [{**s, "start": positions[s["start"]], "end": positions[s["end"]] + len(missing.get(s["end"], []))} for s in data["segments"]],
        "missing": [{**row, "after_pdf_page": positions[row["after_pdf_page"]] + len(missing.get(row["after_pdf_page"], []))}
                    for row in data["missing"] if row.get("action", "mark") != "blank"]}
    return result, positions, inserted


def completed_copy(asset, revision):
    job = ProcessingJob.objects.filter(asset=asset, stats__operation=OPERATION,
        stats__mapping_revision_id=str(revision.pk), status="succeeded").order_by("-finished_at").first()
    if job is None:
        return None
    artifact = Asset.objects.filter(pk=job.stats.get("result_asset_id"), source_asset=asset, edition=asset.edition,
        kind=Asset.Kind.WEB_DERIVATIVE, processor=PROCESSOR, status="ready", validation_status="valid").first()
    if not artifact or not artifact.file:
        return None
    details = artifact.validation_details or {}
    if (details.get("mapping_revision_id") != str(revision.pk) or details.get("source_sha256") != asset.sha256
            or not details.get("original_page_identity_roundtrip")
            or artifact.page_count != asset.page_count + sum(row.get("action") == "blank" for row in revision.data["missing"])):
        return None
    return artifact


def staging_copy_matches(staged, parent):
    mapping = (staged.validation_details or {}).get("physical_page_mapping") or {}
    if mapping.get("target_asset_id") != str(staged.pk) or mapping.get("source_asset_id") != str(parent.pk):
        return False
    revision = parent.page_mapping_revisions.filter(pk=mapping.get("mapping_revision_id")).first()
    artifact = completed_copy(parent, revision) if revision else None
    return bool(artifact and str(artifact.pk) == mapping.get("copy_asset_id") and artifact.sha256 == staged.sha256
                and artifact.page_count == staged.page_count and artifact.file.name == staged.file.name)


def remap_contribution_scopes(rows, target):
    """Project existing confirmed chapter identities through saved page-mapping steps."""
    from copy import deepcopy
    from catalog.models import DocumentOutlineRevision
    steps, seen, current = [], set(), target
    while current and current.pk not in seen:
        seen.add(current.pk)
        mapping = (current.validation_details or {}).get("navigation_mapping") or {}
        if mapping.get("target_asset_id") != str(current.pk) or mapping.get("source_asset_id") != str(current.source_asset_id):
            break
        steps.append(mapping)
        current = current.source_asset
    result = deepcopy(rows)
    for mapping in reversed(steps):
        outline = DocumentOutlineRevision.objects.filter(pk=mapping.get("outline_revision_id")).first() if mapping.get("outline_revision_id") else None
        nodes = {str(node.get("id")): node for node in outline.nodes} if outline else {}
        positions = {int(old): new for old, new in mapping["positions"].items()}
        for row in result:
            scope = row.get("scope") or {}
            for chapter in scope.get("chapters", []) if scope.get("kind") == "chapter" else []:
                if chapter.get("asset_id") != mapping["source_asset_id"]:
                    continue
                node = nodes.get(chapter.get("outline_node_id"))
                start, end = chapter.get("page_start"), chapter.get("page_end")
                if (not node or chapter.get("document_revision_id") != mapping["source_document_revision_id"]
                        or chapter.get("outline_revision_id") != mapping["source_outline_revision_id"]
                        or start not in positions or end not in positions or node.get("pdf_page") != positions[start]
                        or str(node.get("title") or "").strip() != chapter.get("title")):
                    raise ValueError("已确认的章节责任定位与本次页码校准不一致，请先从作品编目核对；原发布版本保留。")
                chapter.update(asset_id=mapping["target_asset_id"], document_revision_id=mapping["document_revision_id"],
                    outline_revision_id=mapping["outline_revision_id"], page_start=positions[start],
                    page_end=positions.get(end + 1, mapping["page_count"] + 1) - 1)
    return result


def export_revision(asset, revision_id):
    _source_current(asset)
    revision = asset.page_mapping_revisions.filter(pk=revision_id).first()
    if not revision or revision.source_fingerprint != source_fingerprint(asset):
        raise OutlineConflict("页码候选或来源已变化，请重新保存当前校准后生成副本。")
    data = validate_data(asset, revision.data)
    blanks = [row for row in data["missing"] if row.get("action", "mark") == "blank"]
    if not blanks or any(not row["confirmed"] or not row["note"].strip() for row in blanks):
        raise OutlineConflict("请保存已核对的插入空白页选择及缺页原因。")
    if len({(row["after_pdf_page"], row["label"].strip()) for row in blanks}) != len(blanks):
        raise OutlineConflict("同一位置存在重复补页标签，请合并重复记录后再生成副本。")
    if diagnostics(data)["missing_present"]:
        raise OutlineConflict("缺页标签与现有页面重复，请先核对，不生成重复补页。")
    return revision


@transaction.atomic
def queue_export(asset_id, *, data, actor):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    identity = f"page-mapping-export:{actor.pk}:{UUID(str(data['request_id']))}"
    prior = ProcessingJob.objects.filter(idempotency_key=identity).first()
    if prior:
        if prior.asset_id != asset.pk or prior.stats.get("mapping_revision_id") != str(data["revision_id"]):
            raise OutlineConflict("原请求绑定另一份页码候选，请先核对原任务。")
        return prior
    _guard(asset, data)
    revision = export_revision(asset, data["revision_id"])
    document = asset.document_revisions.filter(is_active=True).first()
    job = ProcessingJob.objects.create(job_type="text_extraction", asset=asset, edition=asset.edition,
        created_by=actor, task_id=str(uuid4()), idempotency_key=identity,
        stats={"operation": OPERATION, "source_sha256": asset.sha256,
               "mapping_revision_id": str(revision.pk), "document_revision_id": str(document.pk) if document else ""})
    from catalog.services.outline_exports import dispatch_export
    transaction.on_commit(lambda: dispatch_export(str(job.pk), job.task_id))
    return job


def write_mapping_copy(source, destination, data, *, page_count, heartbeat):
    """Insert only selected blanks, retaining original page objects and their destinations."""
    import fitz
    insertions = defaultdict(list)
    for row in data["missing"]:
        if row.get("action", "mark") == "blank":
            insertions[row["after_pdf_page"]].append(row)
    expanded, numbers, inserted = expanded_mapping(data)
    labels = ["–".join(row["labels"]) for row in expanded["pages"]]
    positions = {old: number - 1 for old, number in numbers.items()}
    blank_positions = [row["pdf_page"] - 1 for row in inserted]
    with fitz.open(str(source)) as pdf:
        if len(pdf) != page_count or pdf.is_encrypted or pdf.get_sigflags() > 0:
            raise OutlineConflict("原件页数、加密或签名状态不支持补页副本，请核对并保留原件。")
        originals = [pdf.page_xref(i) for i in range(page_count)]
        toc = [row[:3] for row in pdf.get_toc()]
        for row in toc:
            if row[2] > 0:
                row[2] = positions[row[2]] + 1
        for done, (after, missing) in enumerate(sorted(insertions.items(), reverse=True)):
            heartbeat("bookmarks", done, len(insertions))
            rectangle = pdf[after - 1].rect
            for _ in missing:
                pdf.new_page(pno=after, width=rectangle.width, height=rectangle.height)
        pdf.set_page_labels([{"startpage": i, "prefix": label, "style": ""} for i, label in enumerate(labels)])
        heartbeat("writing", 0, 1)
        pdf.save(str(destination), garbage=0, deflate=False)
    heartbeat("validating", 0, 1)
    with fitz.open(str(destination)) as saved:
        if len(saved) != len(labels) or saved.get_toc() != toc:
            raise OutlineConflict("补页副本的页数或原书签落点未回读一致，未提供下载。")
        for old, position in positions.items():
            if old % 100 == 0:
                heartbeat("validating", old, page_count)
            if saved.page_xref(position) != originals[old - 1] or saved[position].get_label() != labels[position]:
                raise OutlineConflict("补页副本的原页面身份或标签不一致，未提供下载。")
        if any(saved[i].get_contents() or saved[i].get_label() != labels[i] for i in blank_positions):
            raise OutlineConflict("新增空白页及缺页标签未回读一致，未提供下载。")
    return len(labels)
