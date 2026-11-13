"""Ordered, bounded synthesis. Original window products remain authoritative.

Chapter batches do not depend on the preceding book summary. Only the final
ordered fold has that dependency, so an unchanged later chapter can be reused.
There is no sampling, unordered reduce or implicit parallel Provider traffic.
"""
from rest_framework.exceptions import ValidationError
from catalog.services.intelligence_provider import fits_input


def analysis_windows(run, config, lease):
    """Persist range planning once, including before all windows have finished.

    The plan contains offsets, not a second copy of the book. Each resume reads
    and verifies immutable page text; it does not rebuild thousands of OCR nodes.
    """
    from django.conf import settings
    from catalog.services import intelligence as runner
    from catalog.services.knowledge_sources import current_structure, digest
    from catalog.services.intelligence_provider import identity
    structure = current_structure(run.document_revision)
    def inputs():
        return {"structure_id":str(structure.pk), "structure_hash":structure.input_hash,
            "source_manifest_hash":run.coverage.get("source_manifest_hash"),
            "scope":run.scope, "model":identity(config), "selection":runner.SOURCE_SELECTION_VERSION,
            "context_tokens":settings.INTELLIGENCE_CONTEXT_TOKENS, "planner":"ranges-v1"}
    saved = run.artifacts.filter(stage=1, unit="windows", status="succeeded").first() if run.plan_version == 2 else None
    if (saved and structure and run.structure_id == structure.pk and saved.input_manifest == inputs()):
        if saved.output_hash != digest(saved.output):
            raise ValidationError("窗口范围计划哈希不符，不能继续编纂。")
        entries = saved.output["windows"]
        numbers = {r["page_number"] for entry in entries for r in entry["ranges"]}
        snapshots = list(run.document_revision.page_snapshots.filter(page_number__in=numbers)
            .values_list("page_number", "text", "content_hash"))
        pages = {number:text for number,text,_ in snapshots}
        if set(pages) != numbers or any(digest(text) != checksum for _,text,checksum in snapshots):
            raise ValidationError("窗口计划引用的正文快照缺失或哈希不符。")
        for entry in entries:
            for row in entry["ranges"]:
                text = pages[row["page_number"]]
                if not 0 <= row["start"] < row["end"] <= len(text):
                    raise ValidationError("窗口计划原文范围无效。")
                row["text"] = text[row["start"]:row["end"]]
        run.structure = structure
        return entries
    nodes = runner.prepare(run)
    structure = run.structure
    if not config.enabled:
        return None
    planned = list(runner.windows(nodes, config, run.scope))
    paths, groups = runner.chapter_paths(structure, (chapter for chapter, _ in planned), include_groups=True)
    entries = [{"chapter_path":paths[chapter], "group":groups[chapter],
        "completed_node_ids":sorted({r["node_id"] for r in rows if r["node_complete"]}),
        "ranges":runner.source_rows(rows)} for chapter, rows in planned]
    if run.plan_version == 2:
        ranges = [{**entry, "ranges":[{k:v for k,v in row.items() if k != "text"} for row in entry["ranges"]]} for entry in entries]
        runner._save_artifact(run, 1, "windows", inputs(), {"windows":ranges}, lease=lease)
    return entries

CHAPTER_PROMPT = (
    "按sources_in_order的真实原文次序综合本章的这些连续窗口，全部纳入，不抽样。"
    "保留论证发展、主张者、相反解释、概念用法变化及条件；不得按多数意见归并。"
    "这可能只是章内连续范围，不声称读完其他窗口。covered_units须按顺序完整返回source_units。")
FOLD_PROMPT = (
    "在previous基础上按sources_in_order的文献次序继续综合全部给定章节范围。"
    "保留作者论证的发展、前后限定、相反解释、归属及覆盖局限，不按多数意见归并。"
    "covered_units须按顺序完整返回本批source_units；前文已综合范围由previous_source_hash固定。")
WIKI_PROMPT = (
    "一次审阅目标页面与本批全部有原文证据的陈述，返回最多8个局部patch；相关论证可合并成区块。"
    "仅使用本批assertions的id，covered_assertion_ids须按输入顺序完整列出所有陈述id，"
    "无实质变化时patches为空数组。每个patch包含operation、text、reason、assertion_ids；"
    "replace/delete另须提供实际读取的block_id，一批不得反复修改同一区块。"
    "argument_context只是未审核全书论证语境，不能代替原文证据或增加本批陈述之外的事实。"
    "保留主张者、时间变化、条件和相反解释；已有区块仅供避免重复，不作为新增事实证据。"
    "省略的区块未读，不能声称审阅整页；同名身份仍待管理员区分，人工正文受保护，"
    "修改仅为有明确新证据与理由的待审建议。")


def wiki_schema():
    from catalog.services.intelligence import WIKI_SCHEMA, STRING
    return {"type":"object", "required":["patches", "covered_assertion_ids"], "properties":{
        "patches":{"type":"array", "maxItems":8, "items":WIKI_SCHEMA},
        "covered_assertion_ids":{"type":"array", "items":STRING}}}


def validate_wiki_batch(output, data):
    from catalog.services.intelligence import validate_wiki_patch
    if output.get("covered_assertion_ids") != [a["id"] for a in data["assertions"]]:
        raise ValidationError("编纂结果没有覆盖本批全部陈述，未记为完成。")
    patches = output.get("patches")
    if not isinstance(patches, list) or len(patches) > 8:
        raise ValidationError("单批知识页修改超出约定范围。")
    changed, additions = set(), set()
    for patch in patches:
        validate_wiki_patch(patch, data)
        if patch.get("operation", "add") in {"replace", "delete"}:
            key = patch["block_id"]
            if key in changed:
                raise ValidationError("同一批不能反复修改同一区块。")
            changed.add(key)
        elif patch.get("operation", "add") == "add" and patch.get("text", "").strip():
            text = patch["text"].strip()
            if text in additions:
                raise ValidationError("同一批重复提出相同新增正文。")
            additions.add(text)


def wiki_inputs(base, assertions, contexts, config):
    """Pack whole claims using the actual transport budget; account for omissions."""
    schema = wiki_schema()
    template = {**base, "plan":"page-batches-v2", "existing_blocks":[],
        "omitted_context_blocks":[c["block"]["id"] for c in contexts]}
    if not fits_input(config, WIKI_PROMPT, template, schema):
        raise ValidationError("全书论证语境与页面引用清单超过编纂输入预算；未截断，请调整明确预算。")
    batches, batch = [], []
    for assertion in assertions:
        candidate = {**template, "assertions":[*batch, assertion]}
        if batch and not fits_input(config, WIKI_PROMPT, candidate, schema):
            batches.append(batch)
            batch = []
        if not fits_input(config, WIKI_PROMPT, {**template, "assertions":[assertion]}, schema):
            raise ValidationError("单条完整陈述与论证语境超过编纂预算，未裁剪来源。")
        batch.append(assertion)
    if batch:
        batches.append(batch)
    for batch in batches:
        data = {**template, "assertions":batch}
        for context in contexts:
            candidate = {**data, "existing_blocks":[*data["existing_blocks"], context],
                "omitted_context_blocks":[key for key in data["omitted_context_blocks"] if key != context["block"]["id"]]}
            if fits_input(config, WIKI_PROMPT, candidate, schema):
                data = candidate
        yield data


def summary_schema():
    from catalog.services.intelligence import SUMMARY_SCHEMA, STRING
    return {"type":"object", "required":[*SUMMARY_SCHEMA["required"], "covered_units"],
        "properties":{**SUMMARY_SCHEMA["properties"], "covered_units":{"type":"array", "items":STRING}}}


def validate_synthesis(output, data):
    if output.get("covered_units") != data["source_units"]:
        raise ValidationError("综合没有按顺序覆盖本批全部来源产物，未记为完成。")


def _input(sources, **context):
    return {**context, "source_units":[s["unit"] for s in sources], "sources_in_order":sources}


def _summary(artifact):
    return {key:artifact.output[key] for key in ("summary", "development", "limitations")}


def chapter_batches(analyses, groups, config):
    """The same read-only input planner is used by execution and preflight."""
    schema = summary_schema()
    if len(groups) != len(analyses):
        raise ValidationError("章节分组与实际读取窗口不一致，不能综合。")
    pending, current = [], None
    for index, artifact in enumerate(analyses):
        if artifact.unit != f"window:{index}":
            raise ValidationError("分析窗口存在缺失或次序错误，不能综合。")
        group = groups[index]
        item = {"unit":artifact.unit, "source_artifact_hash":artifact.output_hash,
            "first_window":index, "window":index, "chapter":group, "output":artifact.output}
        if pending and (group != current or not fits_input(config, CHAPTER_PROMPT,
                _input([*pending, item], chapter=group, plan="ordered-chapters-v2"), schema)):
            yield _input(pending, chapter=current, plan="ordered-chapters-v2")
            pending = []
        current = group
        if not fits_input(config, CHAPTER_PROMPT,
                _input([item], chapter=group, plan="ordered-chapters-v2"), schema):
            raise ValidationError("单个完整分析产物超过综合输入预算；请调整明确预算，未裁剪产物。")
        pending.append(item)
    if pending:
        yield _input(pending, chapter=current, plan="ordered-chapters-v2")


def synthesize(run, analyses, config, lease):
    from catalog.services.intelligence import _model_artifact
    schema, chapters = summary_schema(), []
    for data in chapter_batches(analyses, run.coverage.get("window_groups", []), config):
        sources = data["sources_in_order"]
        start, end = sources[0]["window"], sources[-1]["window"]
        if len(sources) == 1:
            # No separate model call just to paraphrase one existing analysis.
            chapters.append(sources[0])
            continue
        artifact = _model_artifact(run, 3, f"chapter:{start}:{end}", data,
            CHAPTER_PROMPT, schema, config, lease,
            validate=lambda output:validate_synthesis(output, data))
        chapters.append({"unit":artifact.unit, "source_artifact_hash":artifact.output_hash,
            "first_window":start, "window":end, "chapter":data["chapter"], "output":_summary(artifact)})

    previous, previous_hash, summary, cursor = {"summary":"", "development":[], "limitations":[]}, "", None, 0
    while cursor < len(chapters):
        batch = []
        context = {"previous":previous, "previous_source_hash":previous_hash, "plan":"ordered-chapters-v2"}
        while cursor < len(chapters):
            candidate = _input([*batch, chapters[cursor]], **context)
            if not fits_input(config, FOLD_PROMPT, candidate, schema):
                if not batch:
                    raise ValidationError("已综合语境与下一完整章节产物超过输入预算，未截断任何一项。")
                break
            batch.append(chapters[cursor])
            cursor += 1
        data = _input(batch, **context)
        summary = _model_artifact(run, 3, f"fold:{batch[-1]['window']}", data,
            FOLD_PROMPT, schema, config, lease,
            validate=lambda output:validate_synthesis(output, data))
        previous, previous_hash = _summary(summary), summary.output_hash
    return summary
