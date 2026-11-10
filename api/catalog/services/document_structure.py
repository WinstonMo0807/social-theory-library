"""Docling worker adapter and revision-checked structure import.

PDF parsing is optional and never imports models in the API process. Text and
offsets remain STL's immutable snapshots; Docling provenance is an alignment
candidate, not permission to overwrite OCR or invent PDF coordinates.
"""
from hashlib import sha256
from pathlib import Path
import re

DOCLING_VERSION = "2.149.0"
ADAPTER_VERSION = "stl-docling-v1"


def request_structure(revision, actor, *, pages, request_id):
    from django.db import transaction
    from rest_framework.exceptions import ValidationError
    from catalog.services.knowledge_core import require_editor
    from catalog.services.knowledge_sources import require_revision_access, current_structure, digest
    from catalog.services.intelligence_changes import uuid_value
    from common.task_runtime import queue_or_wait
    from ingestion.models import ProcessingJob
    require_editor(actor)
    require_revision_access(revision,actor,editorial=True)
    if not isinstance(pages,list) or len(pages) != 2 or any(type(v) is not int for v in pages) or not 1 <= pages[0] <= pages[1] <= revision.asset.page_count or pages[1]-pages[0] >= 50:
        raise ValidationError("每次结构解析须指定此修订内连续1至50页；完成后可继续其余范围。")
    structure = current_structure(revision,prepare=True)
    data = {"revision_id":str(revision.pk),"pages":pages,"baseline_hash":structure.input_hash,
        "source_checksum":revision.source_checksum,"parser_version":DOCLING_VERSION}
    with transaction.atomic():
        job,created = ProcessingJob.objects.get_or_create(idempotency_key=f"structure:{uuid_value(request_id)}",defaults={
            "job_type":"document_structure","asset":revision.asset,"edition":revision.asset.edition,
            "created_by":actor,"engine":f"docling-{DOCLING_VERSION}","stats":{"input":data,"model_calls":0}})
        if not created:
            old = job.stats["input"]
            if old["revision_id"] != data["revision_id"] or old["pages"] != pages or job.created_by_id != actor.pk:
                raise ValidationError("请求ID已用于其他解析任务。")
            return job
        result = queue_or_wait(owner_type="processing_job",owner_key=str(job.pk),capability="document_parse",
            idempotency_key=f"structure:{job.pk}",payload={"task_kind":"document_structure","job_id":str(job.pk),**data},
            preferred_queue="structure",publication_blocking=False)
        job.stats={**job.stats,"demand_id":str(result.demand.pk)};job.save(update_fields=["stats","updated_at"])
        from catalog.intelligence_tasks import execute_structure
        def dispatch():
            try: execute_structure.apply_async(args=[str(job.pk)],queue="structure")
            except Exception:
                ProcessingJob.objects.filter(pk=job.pk).update(error_code="queue_unavailable",
                    error_message="队列未连接；任务已保存，可由远程计算节点领取，或恢复队列后重试。")
        transaction.on_commit(dispatch)
    return job


def control_structure(job_id,actor,action):
    from django.db import transaction
    from django.utils import timezone
    from uuid import uuid5
    from rest_framework.exceptions import ValidationError
    from catalog import models as m
    from catalog.services.knowledge_core import require_editor
    from common.task_runtime import _release_executor_load
    from ingestion.models import ProcessingJob
    require_editor(actor)
    with transaction.atomic():
        job=ProcessingJob.objects.get(pk=job_id,job_type="document_structure")
        demand=m.CapabilityDemand.objects.select_for_update().get(pk=job.stats["demand_id"])
        job=ProcessingJob.objects.select_for_update().get(pk=job_id)
        if action=="cancel" and job.status in {"pending","running","failed"}:
            if demand.state=="claimed": _release_executor_load(demand)
            demand.state="canceled";demand.claimed_by=None;demand.lease_token=None;demand.lease_expires_at=None;demand.save()
            job.status="canceled";job.finished_at=timezone.now();job.save()
            return job
        if action=="retry" and job.status in {"failed","canceled"}:
            revision=m.DocumentRevision.objects.get(pk=job.stats["input"]["revision_id"])
            replacement=request_structure(revision,actor,pages=job.stats["input"]["pages"],request_id=uuid5(job.pk,"retry"))
            job.stats={**job.stats,"retry_replacement_id":str(replacement.pk)};job.save(update_fields=["stats","updated_at"])
            return replacement
        raise ValidationError("当前结构任务不能执行该操作。")


def structure_job(demand):
    from ingestion.models import ProcessingJob
    from catalog import models as m
    from rest_framework.exceptions import ValidationError
    from catalog.services.knowledge_sources import require_revision_access, current_structure
    job = ProcessingJob.objects.get(pk=demand.owner_key,job_type="document_structure")
    data = job.stats["input"]
    revision = m.DocumentRevision.objects.select_related("asset__edition").get(pk=data["revision_id"])
    require_revision_access(revision,job.created_by,editorial=True)
    if job.status == "canceled" or demand.payload.get("job_id") != str(job.pk) or demand.payload.get("baseline_hash") != data["baseline_hash"] or revision.source_checksum != revision.asset.sha256:
        raise ValidationError("结构任务或来源文件已变化。")
    structure = current_structure(revision)
    if not structure or structure.input_hash != data["baseline_hash"]:
        raise ValidationError("此任务的目录或结构基准已变化，请按新范围重新发起。")
    return job,revision


def complete_structure(demand, parsed, *, elapsed_ms=0, executor_id=""):
    from django.db import transaction
    from django.utils import timezone
    from ingestion.models import ProcessingJob
    from catalog.models import DocumentRevision
    from rest_framework.exceptions import ValidationError
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().get(pk=demand.owner_key,job_type="document_structure")
        # Serialize different parsing jobs for the same revision before checking
        # the baseline, so an in-flight completion cannot replace newer structure.
        DocumentRevision.objects.select_for_update().get(pk=job.stats["input"]["revision_id"])
        job,revision = structure_job(demand)
        if parsed.get("pages") != job.stats["input"]["pages"]:
            raise ValidationError("返回结构范围与已领取任务不一致。")
        structure = install_structure(revision,parsed)
        job.status="succeeded";job.finished_at=timezone.now();job.progress=100
        job.stats={**job.stats,"structure_id":str(structure.pk),"coverage":structure.coverage,
            "elapsed_ms":elapsed_ms,"executor_id":executor_id,"model_calls":0}
        job.save()
        from catalog.services.knowledge_workspace import invalidate_source
        invalidate_source("document_revision", revision.pk)
        from catalog.services.knowledge_source_updates import schedule_source_update
        schedule_source_update(revision,structure=structure)
        return structure


def parse_pdf(path, *, checksum, pages, artifacts_path):
    from importlib.metadata import version
    if version("docling") != DOCLING_VERSION:
        raise ValueError(f"Structure worker requires Docling {DOCLING_VERSION}.")
    path = Path(path)
    with path.open("rb") as stream:
        if sha256(stream.read()).hexdigest() != checksum:
            raise ValueError("PDF checksum differs from the referenced revision.")
    artifacts = Path(artifacts_path)
    if not str(artifacts_path).strip() or not artifacts.is_dir():
        raise ValueError("Docling layout artifacts are not installed in this computation worker.")
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, HeadingHierarchyOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
    options = PdfPipelineOptions(artifacts_path=artifacts, do_ocr=False, do_table_structure=False,
        enable_remote_services=False, allow_external_plugins=False,
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True))
    result = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options, backend=DoclingParseDocumentBackend)}).convert(
        path, page_range=tuple(pages), raises_on_error=True)
    items = []
    for item, _ in result.document.iterate_items():
        if not getattr(item, "text", ""):
            continue
        items.append({"ref":item.self_ref,"parent":item.parent.cref if item.parent else None,
            "label":str(item.label.value),"level":getattr(item,"level",None),"text":item.text,
            "prov":[p.model_dump(mode="json") for p in item.prov]})
    return {"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":checksum,
        "pages":list(pages),"heading_hierarchy_enabled":True,"ocr_performed":False,
        "items":items,"status":str(result.status.value)}


def align_text(raw, quoted):
    """Align typography, then map each character to an original code point.

    Docling emits straight quotes for the PDF's curly quote glyphs. This is a
    reversible location map, never normalized offsets or replacement source text.
    No spelling correction, OCR substitutions or fuzzy matching are accepted.
    """
    quotes = str.maketrans({"“":'"',"”":'"',"‘":"'","’":"'"})
    positions = [i for i,c in enumerate(raw) if not c.isspace()]
    text = "".join(raw[i] for i in positions).translate(quotes)
    needle = "".join(quoted.split()).translate(quotes)
    begin = text.find(needle) if needle else -1
    if begin < 0 or text.find(needle, begin+1) >= 0:
        return None
    return positions[begin], positions[begin+len(needle)-1]+1


def install_structure(revision, parsed):
    from django.db import transaction
    from rest_framework.exceptions import ValidationError
    from catalog import models as m
    from catalog.services.knowledge_sources import build_structure, current_structure, digest, _heading_kind
    with transaction.atomic():
        revision = m.DocumentRevision.objects.select_for_update().get(pk=revision.pk)
        if (parsed.get("schema") != ADAPTER_VERSION or parsed.get("parser_version") != DOCLING_VERSION
                or parsed.get("source_checksum") != revision.source_checksum or not parsed.get("heading_hierarchy_enabled")
                or parsed.get("ocr_performed") is not False or parsed.get("status") != "success"):
            raise ValidationError("结构产物的来源、解析版本或完成状态不匹配。")
        bounds = parsed.get("pages")
        if not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) is not int for v in bounds) or not 1 <= bounds[0] <= bounds[1] <= revision.asset.page_count:
            raise ValidationError("结构解析范围无效。")
        baseline = build_structure(revision)
        previous = current_structure(revision) or baseline
        parsed_hash = digest(parsed)
        batches = list(previous.coverage.get("parse_batches", []))
        if any(batch["hash"] == parsed_hash for batch in batches):
            return previous
        for node in previous.nodes.filter(source__human_corrected=True).prefetch_related("segments__page"):
            if any(bounds[0] <= s.page.page_number <= bounds[1] for s in node.segments.all()):
                raise ValidationError("所选范围含人工校正段落，自动解析不能覆盖。请排除此范围，或在段落校正中撤销本次校正后重试。")
        pages = list(revision.page_snapshots.all())
        key = digest([ADAPTER_VERSION, previous.input_hash, parsed_hash])
        existing = m.DocumentStructure.objects.filter(document_revision=revision, input_hash=key).first()
        if existing:
            return existing
        starts, by_page, total = {}, {}, 0
        for page in pages:
            if digest(page.text) != page.content_hash:
                raise ValidationError("原文快照完整性校验失败。")
            starts[page.page_number], by_page[page.page_number] = total, page
            total += len(page.text)+1
        mapped, gaps, ignored = [], [], []
        for raw in parsed.get("items", []):
            segments = []
            for prov in raw.get("prov", []):
                page = by_page.get(prov.get("page_no"))
                span = prov.get("charspan")
                if not page or not bounds[0] <= page.page_number <= bounds[1] or not isinstance(span,(list,tuple)) or len(span) != 2 or any(type(v) is not int for v in span) or not 0 <= span[0] < span[1] <= len(raw.get("text", "")):
                    continue
                quote = raw["text"][span[0]:span[1]]
                found = align_text(page.text, quote)
                if found:
                    segments.append((page, *found))
            if not segments or len(segments) != len(raw.get("prov", [])):
                gaps.append({"ref":raw.get("ref"),"label":raw.get("label"),"pages":[p.get("page_no") for p in raw.get("prov",[])],"reason":"raw_text_alignment_unresolved"})
                continue
            segments.sort(key=lambda v:(v[0].page_number,v[1]))
            if any(p.pk == other.pk and a < right and b > left
                   for p,a,b in segments for row in [*mapped,*ignored] for other,left,right in row["segments"]):
                gaps.append({"ref":raw.get("ref"),"reason":"overlapping_parser_ranges"})
                continue
            row = {**raw,"segments":segments,"start":starts[segments[0][0].page_number]+segments[0][1]}
            if raw["label"] in {"page_header","page_footer"}:
                ignored.append(row)
            else:
                mapped.append(row)
        if not mapped:
            raise ValidationError("此范围没有可与原文校验的Docling结构，已有结构保持。扫描页继续使用已保存OCR与目录校准。")
        headings = []
        for node in previous.nodes.exclude(kind__in=["document","paragraph","footnote","table","unresolved"]).prefetch_related("segments__page"):
            segment = node.segments.first()
            if not segment:
                continue
            depth, parent = 1, node.parent
            while parent and parent.kind != "document":
                depth, parent = depth+1, parent.parent
            headings.append({"title":node.title,"kind":node.kind,"level":depth,"start":starts[segment.page.page_number]+segment.start,"source":node.source})
        retained=[]
        for row in mapped:
            title="".join(row.get("text","").split())
            repeated = row["label"] == "section_header" and not any(h["start"]==row["start"] for h in headings) and title and sum(
                title in "".join(p.text[:100].split()) for p in pages) >= 3
            if repeated:
                ignored.append({**row,"label":"page_header"})
            else: retained.append(row)
        mapped=retained
        for row in mapped:
            if row["label"] != "section_header" or any(h["start"] == row["start"] for h in headings):
                continue
            level = row.get("level")
            if type(level) is not int or not 1 <= level <= 6:
                gaps.append({"ref":row["ref"],"reason":"heading_level_unresolved"})
                continue
            headings.append({"title":row["text"][:600],"kind":_heading_kind(row["text"],level),"level":level,
                "start":row["start"],"source":{"docling_ref":row["ref"],"heading_hierarchy_enabled":True}})
        headings.sort(key=lambda h:(h["start"],h["level"]))
        for old in previous.coverage.get("ignored_ranges",[]):
            if not bounds[0] <= old["page"] <= bounds[1]:
                page=by_page[old["page"]]
                ignored.append({"label":old["label"],"segments":[(page,old["start"],old["end"])]})
        # A scoped reparse retains verified nodes from earlier scopes. It must
        # include a whole existing cross-page item if that item is affected.
        for node in previous.nodes.filter(kind__in=["paragraph","footnote","table","references"]).prefetch_related("segments__page"):
            if not node.source.get("docling_ref") and not node.source.get("human_corrected"):
                continue
            segments = [(s.page,s.start,s.end) for s in node.segments.all()]
            affected = [bounds[0] <= p.page_number <= bounds[1] for p,_,_ in segments]
            if any(affected):
                if not all(affected):
                    raise ValidationError("解析范围切断了已核验的跨页段落，请将该段落的全部页面纳入。")
                continue
            mapped.append({"ref":node.source.get("docling_ref",str(node.pk)),"label":node.source.get("label","text"),
                "retained_source":node.source,
                "prov":node.source.get("provenance",[]),"segments":segments,
                "start":starts[segments[0][0].page_number]+segments[0][1]})
        occupied = {}
        for row in [*mapped,*ignored]:
            for p,a,b in row["segments"]:
                occupied.setdefault(p.page_number,[]).append((a,b))
        unmatched = []
        for page in pages:
            cursor = 0
            for a,b in sorted(occupied.get(page.page_number,[]))+[(len(page.text),len(page.text))]:
                if a > cursor and page.text[cursor:a].strip():
                    boundaries = [cursor,*[h["start"]-starts[page.page_number] for h in headings if cursor < h["start"]-starts[page.page_number] < a],a]
                    unmatched += [(page,left,right) for left,right in zip(boundaries,boundaries[1:]) if page.text[left:right].strip()]
                cursor = max(cursor,b)
        pending_ranges = [{"page":p.page_number,"start":a,"end":b} for p,a,b in unmatched if bounds[0] <= p.page_number <= bounds[1]]
        pending_ranges += [r for r in previous.coverage.get("unmatched_ranges",[]) if not bounds[0] <= r["page"] <= bounds[1]]
        gaps += [r for r in previous.coverage.get("alignment_gaps",[]) if not any(bounds[0] <= p <= bounds[1] for p in r.get("pages",[]) if type(p) is int)]
        leaf_rows = [r for r in sorted(mapped,key=lambda r:r["start"]) if r["label"] != "section_header"]
        positions = [("root",-1)]+[(f"heading:{i}",h["start"]) for i,h in enumerate(headings)]+[(f"leaf:{i}",r["start"]) for i,r in enumerate(leaf_rows)]+[(f"raw:{i}",starts[p.page_number]+a) for i,(p,a,b) in enumerate(unmatched)]
        order = {key:i for i,(key,_) in enumerate(sorted(positions,key=lambda row:row[1]))}
        coverage = {**baseline.coverage,"parser_scope":bounds,"parse_batches":[*batches,{"hash":parsed_hash,"pages":bounds}],
            "ignored_ranges":[{"page":p.page_number,"start":a,"end":b,"label":r["label"]} for r in ignored for p,a,b in r["segments"]],
            "docling_items":len(mapped),"alignment_gaps":gaps,
            "paragraph_method":"verified_docling_provenance_with_raw_fallback","cross_page_paragraphs_inferred":False,
            "unmatched_ranges":pending_ranges,"verified_cross_page_items":sum(len({p.page_number for p,_,_ in r["segments"]}) > 1 for r in leaf_rows),
            "structure_status":"needs_structure_review" if gaps or pending_ranges or baseline.coverage.get("unmapped_headings") else "mapped"}
        structure = m.DocumentStructure.objects.create(document_revision=revision,outline_revision=baseline.outline_revision,
            parser="docling",parser_version=DOCLING_VERSION,input_hash=key,coverage=coverage)
        leaves = []
        def make(key, kind, segments, title="", parent=None, source=None):
            node = m.DocumentNode.objects.create(structure=structure,document_revision=revision,parent=parent,kind=kind,
                order=order[key],title=title,content_hash=digest([p.text[a:b] for p,a,b in segments]),source=source or {})
            m.DocumentNodeSegment.objects.bulk_create([m.DocumentNodeSegment(node=node,page=p,order=i,start=a,end=b,
                content_hash=digest(p.text[a:b])) for i,(p,a,b) in enumerate(segments)])
            return node
        def slices(a,b):
            return [(p,max(0,a-starts[p.page_number]),min(len(p.text),b-starts[p.page_number])) for p in pages
                if max(0,a-starts[p.page_number]) < min(len(p.text),b-starts[p.page_number])]
        root = make("root","document",slices(0,total),revision.asset.edition.work.title)
        stack, ranges = [], []
        for i,h in enumerate(headings):
            end = next((v["start"] for v in headings[i+1:] if v["level"] <= h["level"]),total)
            while stack and stack[-1][0] >= h["level"]:
                stack.pop()
            node = make(f"heading:{i}",h["kind"],slices(h["start"],end),h["title"],stack[-1][1] if stack else root,h["source"])
            stack.append((h["level"],node));ranges.append((h["start"],end,node))
        for i,row in enumerate(leaf_rows):
            kind = {"footnote":"footnote","reference":"references","table":"table"}.get(row["label"],"paragraph")
            parent = next((n for a,b,n in reversed(ranges) if a <= row["start"] < b),root)
            node = make(f"leaf:{i}",kind,row["segments"],parent=parent,source={"docling_ref":row["ref"],"label":row["label"],
                "provenance":row["prov"],"geometry_precision":"unverified_docling_coordinates","alignment":"typography_to_raw_codepoints",
                **row.get("retained_source",{})})
            leaves.append((node,row["segments"]))
        # Never omit unmatched original material or pretend parsing covered it.
        for i,(page,a,b) in enumerate(unmatched):
            parent = next((n for left,right,n in reversed(ranges) if left <= starts[page.page_number]+a < right),root)
            pending = any(r["page"] == page.page_number and r["start"] < b and r["end"] > a for r in pending_ranges)
            make(f"raw:{i}","unresolved" if pending else "paragraph",[(page,a,b)],parent=parent,
                source={"method":"retained_raw_text","structure_pending":pending})
        # Explicit, unique note markers may link body and note on the same page.
        for note,segments in leaves:
            if note.kind != "footnote": continue
            page,a,b = segments[0]
            marker = re.match(r"\s*([①-⑳]|\[\d+\]|\(\d+\)|\d+[.)])",page.text[a:b])
            if not marker: continue
            label = marker.group(1)
            same = [n for n,ss in leaves if n.kind == "footnote" and any(p.pk == page.pk and p.text[x:y].lstrip().startswith(label) for p,x,y in ss)]
            if len(same) != 1: continue
            for body,ss in leaves:
                if body.kind == "paragraph" and any(p.pk == page.pk and label in p.text[x:y] for p,x,y in ss):
                    m.DocumentNodeReference.objects.create(source=body,target=note,label=label,
                        provenance={"method":"unique_page_note_marker","page_number":page.page_number})
        return structure
