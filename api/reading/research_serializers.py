"""Published request contracts for API clients and subsequent frontend type generation."""
from rest_framework import serializers


class EvidenceAnchorInput(serializers.Serializer):
    evidence_span_id = serializers.UUIDField(required=False)
    asset_id = serializers.UUIDField(required=False)
    document_revision_id = serializers.UUIDField(required=False)
    pdf_page = serializers.IntegerField(min_value=1, required=False)
    content_hash = serializers.CharField(max_length=64, required=False)
    selection_start = serializers.IntegerField(min_value=0, required=False)
    selection_end = serializers.IntegerField(min_value=1, required=False)


class EvidenceReferenceInput(EvidenceAnchorInput):
    anchors = EvidenceAnchorInput(many=True, required=False, help_text="跨页引用按顺序传 1—20 个同文件同修订的单页锚点。")


class QueryScopeInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["library", "works", "passages", "filtered"], default="library")
    filters = serializers.JSONField(required=False, help_text="Discovery 同一过滤协议；作品/学者/主题/时期/语言/类型。")
    references = EvidenceReferenceInput(many=True, required=False)
    allow_neighbors = serializers.BooleanField(default=False, help_text="限定段落时始终关闭，不扩大到整书。")


class RevisionInput(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)


class ProjectCreateInput(serializers.Serializer):
    expected_owner_id = serializers.IntegerField(min_value=1, required=False)
    request_id = serializers.UUIDField(help_text="客户端每次新操作生成，重试沿用。")
    title = serializers.CharField(max_length=240, required=False)
    question = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    conversation_id = serializers.UUIDField(required=False)
    scope = QueryScopeInput(required=False)


class ProjectUpdateInput(RevisionInput):
    title = serializers.CharField(max_length=240, required=False)
    question = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    scope = QueryScopeInput(required=False)
    archived = serializers.BooleanField(required=False)
    layout = serializers.JSONField(required=False)


class SelectionInput(RevisionInput):
    expected_owner_id = serializers.IntegerField(min_value=1, required=False)
    request_id = serializers.UUIDField(required=False, help_text="未知响应重试沿用原标识；旧客户端可省略。")
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
    notes = serializers.DictField(child=serializers.CharField(max_length=200, allow_blank=True), required=False)
    action = serializers.ChoiceField(choices=["add", "remove", "undo", "reorder"])
    references = EvidenceReferenceInput(many=True, required=False)
    reference_id = serializers.CharField(required=False)
    order = serializers.ListField(child=serializers.CharField(), max_length=400, required=False)


class ComparisonCellInput(serializers.Serializer):
    dimension = serializers.CharField(max_length=160)
    column_id = serializers.CharField(max_length=160, required=False, allow_blank=True,
        help_text="当前选材的 edition:/work:/asset: 身份，或原比较格的文献身份。")
    author = serializers.CharField(max_length=160, required=False, allow_blank=True)
    reference_ids = serializers.ListField(child=serializers.CharField(), max_length=400, required=False)
    note = serializers.CharField(max_length=8000, required=False, allow_blank=True)


class ComparisonInput(RevisionInput):
    dimensions = serializers.ListField(child=serializers.CharField(max_length=160), max_length=20)
    cells = ComparisonCellInput(many=True)


class ComparisonDraftInput(RevisionInput):
    request_id = serializers.UUIDField()
    dimension = serializers.CharField(max_length=160)
    reference_ids = serializers.ListField(child=serializers.CharField(max_length=180), min_length=1, max_length=20)


class StatementInput(serializers.Serializer):
    proposition = serializers.CharField(max_length=1200)
    subject = serializers.CharField(required=False, allow_blank=True)
    predicate = serializers.CharField(required=False, allow_blank=True)
    object = serializers.CharField(required=False, allow_blank=True)
    polarity = serializers.ChoiceField(choices=["positive", "negative", "mixed", "uncertain"], required=False)
    modality = serializers.CharField(required=False, allow_blank=True)
    qualifiers = serializers.ListField(child=serializers.CharField(), required=False)
    temporal_scope = serializers.JSONField(required=False)
    geographic_scope = serializers.JSONField(required=False)
    population_scope = serializers.JSONField(required=False)


class SubclaimInput(StatementInput):
    id = serializers.UUIDField()


class SubclaimsInput(RevisionInput):
    subclaims = SubclaimInput(many=True, help_text="本人明确拆分的 0—12 个子命题；不自动认定为作者主张或有效反证。")


class TurnCreateInput(RevisionInput):
    request_id = serializers.UUIDField()
    question = serializers.CharField(min_length=2, max_length=1200)
    parent_id = serializers.UUIDField(required=False)
    scope = QueryScopeInput(required=False)
    mode = serializers.ChoiceField(choices=["search", "counterargument"], default="search")
    statement = StatementInput(required=False)
    subclaims = SubclaimInput(many=True, required=False)
    active_subclaim_id = serializers.UUIDField(required=False, allow_null=True)
    return_context = serializers.JSONField(required=False)


class TurnRetryInput(RevisionInput):
    request_id = serializers.UUIDField()


class TurnListInput(serializers.Serializer):
    request_id = serializers.UUIDField(required=False, help_text="仅查回当前本人研究内的原请求。")
    mode = serializers.ChoiceField(choices=["all", "search", "counterargument"], required=False)
    order = serializers.ChoiceField(choices=["oldest", "newest"], required=False)


class TurnExpandInput(TurnRetryInput):
    scope = QueryScopeInput()
    question = serializers.CharField(min_length=2, max_length=1200, required=False)


class ImportedTurnInput(serializers.Serializer):
    local_id = serializers.CharField(max_length=160)
    parent_local_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    question = serializers.CharField(min_length=2, max_length=1200)
    scope = QueryScopeInput(required=False)
    references = EvidenceReferenceInput(many=True, required=False)
    selected_references = EvidenceReferenceInput(many=True, required=False)
    notes = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    created_at = serializers.DateTimeField(required=False)
    status = serializers.ChoiceField(choices=["queued", "running", "completed", "partial", "failed", "canceled"], required=False)


class ImportedComparisonInput(serializers.Serializer):
    dimensions = serializers.ListField(child=serializers.CharField(max_length=160), max_length=20)
    cells = ComparisonCellInput(many=True)


class ProjectImportInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    title = serializers.CharField(max_length=240, required=False)
    question = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    scope = QueryScopeInput(required=False)
    schema_version = serializers.IntegerField(min_value=1, max_value=1)
    local_id = serializers.CharField(max_length=160)
    selections = EvidenceReferenceInput(many=True, required=False)
    notes = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    layout = serializers.JSONField(required=False)
    comparison = ImportedComparisonInput(required=False)
    turns = ImportedTurnInput(many=True, required=False)


class AnalysisDecisionInput(RevisionInput):
    id = serializers.CharField(help_text="分析候选 id，来自轮次返回值。")
    action = serializers.ChoiceField(choices=["confirm", "clear"], required=False)
    request_id = serializers.UUIDField(required=False, help_text="幂等请求；同时保存本人笔记时必需。")
    relation = serializers.ChoiceField(choices=["support", "different_conclusion", "qualification", "reframe", "insufficient_evidence", "unrelated"], required=False)
    note = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    attribution = serializers.ChoiceField(choices=["author_claim", "quoted_claim", "reported_claim", "criticized_claim", "historical_description", "uncertain"], required=False)
    scope_note = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    save_as_note = serializers.BooleanField(required=False)


class MemoryCreateInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    body = serializers.CharField(max_length=20000)
    kind = serializers.ChoiceField(choices=["concept", "understanding", "question", "method", "observation", "contradiction"], default="understanding")
    project_id = serializers.UUIDField(required=False)
    turn_id = serializers.UUIDField(required=False)
    annotation_id = serializers.UUIDField(required=False)
    sources = EvidenceReferenceInput(many=True, required=False)


class MemoryUpdateInput(RevisionInput):
    body = serializers.CharField(max_length=20000, required=False)
    kind = serializers.ChoiceField(choices=["concept", "understanding", "question", "method", "observation", "contradiction"], required=False)
    sources = EvidenceReferenceInput(many=True, required=False)
    state = serializers.ChoiceField(choices=["proposed", "confirmed", "ignored"], required=False)
    refresh_origin = serializers.BooleanField(required=False, help_text="本人已对照当前原笔记后明确更新来源身份；不修改原笔记。")


class MemoryContextInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["project", "plan"])
    id = serializers.UUIDField()


class MemoryUsageTargetInput(MemoryContextInput):
    expected_revision = serializers.IntegerField(min_value=1)


class MemoryUsageInput(RevisionInput):
    action = serializers.ChoiceField(choices=["grant", "revoke", "revoke_all"])
    targets = MemoryUsageTargetInput(many=True, required=False)


class MemoryListInput(serializers.Serializer):
    q = serializers.CharField(max_length=1200, required=False, allow_blank=True)
    state = serializers.ChoiceField(choices=["all", "proposed", "confirmed", "ignored"], required=False)
    kind = serializers.ChoiceField(choices=["all", "concept", "understanding", "question", "method", "observation", "contradiction"], required=False)
    source_status = serializers.ChoiceField(choices=["all", "available", "updated", "unavailable", "no_source"], required=False)
    order = serializers.ChoiceField(choices=["updated_at", "newest"], required=False)


class MemorySearchInput(serializers.Serializer):
    q = serializers.CharField(max_length=1200)
    semantic = serializers.BooleanField(default=False)
    allowed_ids = serializers.ListField(child=serializers.UUIDField(), max_length=400, required=False)
    context = MemoryContextInput(required=False, help_text="仅从此本人研究或计划的显式授权范围中检索。")


class PrerequisiteInput(serializers.Serializer):
    work_id = serializers.UUIDField()
    requires_work_id = serializers.UUIDField()
    reference = EvidenceReferenceInput()


class ReadingPaceInput(serializers.Serializer):
    cjk_chars_per_minute = serializers.IntegerField(min_value=20, max_value=3000, required=False)
    words_per_minute = serializers.IntegerField(min_value=20, max_value=1500, required=False)
    fallback_minutes_per_page = serializers.IntegerField(min_value=1, max_value=60, required=False)


class ItemEstimateInput(serializers.Serializer):
    work_id = serializers.UUIDField()
    difficulty = serializers.ChoiceField(choices=["beginner", "intermediate", "advanced"], required=False)
    minutes = serializers.IntegerField(min_value=1, max_value=100000, required=False)


class PlanPolicyInput(serializers.Serializer):
    time_budget = serializers.CharField(max_length=160, required=False, allow_blank=True)
    budget_minutes = serializers.IntegerField(min_value=1, max_value=100000, allow_null=True, required=False)
    session_minutes = serializers.IntegerField(min_value=5, max_value=480, required=False)
    reading_level = serializers.ChoiceField(choices=["beginner", "intermediate", "advanced"], required=False)
    reading_pace = ReadingPaceInput(required=False)
    prefer_unread = serializers.BooleanField(required=False)
    item_estimates = ItemEstimateInput(many=True, required=False)
    weekly_minutes = serializers.IntegerField(min_value=1, max_value=10080, required=False,
        help_text="与 duration_weeks 成对提供；相乘为总预算，最多 100000 分钟。")
    duration_weeks = serializers.IntegerField(min_value=1, max_value=52, required=False)
    language_preference = serializers.CharField(max_length=160, required=False, allow_blank=True,
        help_text="用于导读提示，不自动排除已选材料。")
    use_confirmed_memories = serializers.BooleanField(required=False, help_text="默认关闭，仅使用显式选择的本人已确认笔记。")
    confirmed_memory_ids = serializers.ListField(child=serializers.UUIDField(), max_length=40, required=False)


class PlanCreateInput(PlanPolicyInput):
    request_id = serializers.UUIDField()
    goal = serializers.CharField(max_length=4000, help_text="无材料时先启动 Discovery；此时问题最多 1200 字符。")
    background = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    time_budget = serializers.CharField(max_length=160, required=False, allow_blank=True)
    project_id = serializers.UUIDField(required=False)
    turn_id = serializers.UUIDField(required=False)
    reading_path_id = serializers.UUIDField(required=False,
        help_text="旧输入不再创建路径副本；请使用path-follows的公开版本确认与copy-plan接口。")
    references = EvidenceReferenceInput(many=True, required=False)
    prerequisites = PrerequisiteInput(many=True, required=False)
    scope = QueryScopeInput(required=False)


class PlanUpdateInput(RevisionInput, PlanPolicyInput):
    request_id = serializers.UUIDField(required=False, help_text="公共路径私人副本写入必需；同一操作重试保持原请求标识。")
    goal = serializers.CharField(max_length=4000, required=False)
    background = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    order = serializers.ListField(child=serializers.UUIDField(), required=False)
    item_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=["pending", "reading", "completed", "skipped"], required=False)
    note = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    item_minutes = serializers.IntegerField(min_value=1, max_value=100000, allow_null=True, required=False,
        help_text="公共路径副本以稳定item_id记录本人时长估计，不按作品合并不同章节。")
    reference = EvidenceReferenceInput(required=False)
    adopt_suggestion = serializers.BooleanField(required=False)
    optimize_order = serializers.BooleanField(required=False)
    preview = serializers.BooleanField(required=False, help_text="只计算调整预览，不写入或增加 revision；确认时以原 revision 再提交。")
    remove_related_prerequisites = serializers.BooleanField(required=False,
        help_text="替换材料时，明确同意移除仅与被替换材料相关的先修关系；其他关系保留。")


class PlanCommandInput(RevisionInput):
    action = serializers.ChoiceField(choices=["cancel", "retry", "enhance"])


class PlanDeleteInput(RevisionInput):
    request_id = serializers.UUIDField(required=False, help_text="公共路径私人副本删除必需；普通私人计划保持既有删除契约。")


class CitationOCROutput(serializers.Serializer):
    progress = serializers.JSONField(read_only=True)
    units = serializers.JSONField(read_only=True, required=False)
    unit = serializers.JSONField(read_only=True, required=False)


class AuditCreateInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    file = serializers.FileField(help_text="DOCX/PDF，最大 12 MiB，仅保存在本人的加密记录中。")
    project_id = serializers.UUIDField(required=False)
    checks = serializers.ListField(child=serializers.ChoiceField(choices=["citation_identification", "bibliography_identity", "version_page", "scan_ocr"]),
        max_length=4, allow_empty=False, required=False, help_text="multipart 使用重复 checks 字段；默认前三项，扫描 OCR 必须显式选择。")
    scope = serializers.ChoiceField(choices=["public_library", "private_materials"], required=False)
    private_source_ids = serializers.ListField(child=serializers.UUIDField(), max_length=4, required=False)


class CitationSourceCreateInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    file = serializers.FileField(help_text="本人私人来源 PDF/DOCX，最大 12 MiB，不进入公开馆藏或索引。")
    title = serializers.CharField(max_length=240, required=False, allow_blank=True)
    citation = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    scan_ocr = serializers.BooleanField(default=False)


class CitationSourceCommandInput(RevisionInput):
    action = serializers.ChoiceField(choices=["cancel", "retry"])


class CitationTextUnitsOutput(serializers.Serializer):
    audit_id = serializers.UUIDField(read_only=True, required=False)
    source_id = serializers.UUIDField(read_only=True, required=False)
    manuscript_revision = serializers.IntegerField(read_only=True, required=False)
    generation = serializers.IntegerField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    page = serializers.IntegerField(read_only=True)
    next_page = serializers.IntegerField(read_only=True, allow_null=True)
    units = serializers.JSONField(read_only=True)
    notice = serializers.CharField(read_only=True)


class AuditVersionInput(RevisionInput):
    request_id = serializers.UUIDField()
    file = serializers.FileField(help_text="新版本 DOCX/PDF，最大 12 MiB；原稿与旧报告保持独立。")
    check_changed_only = serializers.BooleanField(default=True,
        help_text="默认仅重查不能安全复用的引文；取消后检查全部引文。继承原检查项与明确选择的来源范围。")


class AuditVersionSummary(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    manuscript_revision = serializers.IntegerField(read_only=True)
    filename = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True)
    parent_audit_id = serializers.UUIDField(read_only=True, allow_null=True)


class AuditVersionsOutput(serializers.Serializer):
    current_id = serializers.UUIDField(read_only=True)
    versions = AuditVersionSummary(many=True, read_only=True)
    notice = serializers.CharField(read_only=True)
    truncated = serializers.BooleanField(read_only=True)


class AuditCapabilitiesOutput(serializers.Serializer):
    max_upload_bytes = serializers.IntegerField(read_only=True)
    max_pdf_pages = serializers.IntegerField(read_only=True)
    max_occurrences = serializers.IntegerField(read_only=True)
    max_active_jobs_per_owner = serializers.IntegerField(read_only=True)
    accepted_filetypes = serializers.ListField(child=serializers.CharField(), read_only=True)
    default_checks = serializers.ListField(child=serializers.CharField(), read_only=True)
    checks = serializers.JSONField(read_only=True)
    scopes = serializers.JSONField(read_only=True)
    ocr = serializers.JSONField(read_only=True)
    analysis = serializers.JSONField(read_only=True)
    private_sources = serializers.JSONField(read_only=True)


class AuditCommandInput(RevisionInput):
    action = serializers.ChoiceField(choices=["cancel", "match", "match_private", "sources", "link", "decision", "analyze", "retry"])
    source_id = serializers.UUIDField(required=False)
    private_source_ids = serializers.ListField(child=serializers.UUIDField(), max_length=4, required=False)
    entry_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)
    occurrence_id = serializers.UUIDField(required=False)
    occurrence_ids = serializers.ListField(child=serializers.UUIDField(), max_length=1000, required=False)
    entry_ids = serializers.ListField(child=serializers.UUIDField(), max_length=1000, required=False)
    decision = serializers.ChoiceField(choices=["accepted", "ignored", "corrected", "needs_review"], required=False)
    note = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    corrected_text = serializers.CharField(max_length=4000, required=False, allow_blank=True,
        help_text="仅保存本人的校正文案，不改写上传原稿或原始识别文字。")
    reference = EvidenceReferenceInput(required=False)


class ResearchPreferenceInput(serializers.Serializer):
    research_personalization = serializers.BooleanField()


class ResearchAccountCountsOutput(serializers.Serializer):
    research = serializers.IntegerField(min_value=0, read_only=True)
    memories = serializers.IntegerField(min_value=0, read_only=True)
    plans = serializers.IntegerField(min_value=0, read_only=True)
    audits = serializers.IntegerField(min_value=0, read_only=True)


class ResearchAccountOutput(serializers.Serializer):
    counts = ResearchAccountCountsOutput(read_only=True)
    preferences = serializers.BooleanField(read_only=True)
    deletion_notice = serializers.CharField(read_only=True)
