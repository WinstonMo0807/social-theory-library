# 当前问题

更新日期为 2026-08-19。状态依据当前源码、已有测试和本轮可重复的环境检查。`待核实` 表示本轮没有运行对应环境或生产验收。

## Six master issues

1. STL-001　中英文跨语言观点检索质量。
2. STL-002　field-aware 联网候选与多源证据。
3. STL-003　Ask Library 模型、权限和社会科学 RAG。
4. STL-004　各板块首页与全站搜索的明确 entity scope。
5. STL-005　PDF metadata review PostgreSQL locking。
6. STL-006　Admin / Reader Center session bootstrap。

STL-007 以后记录的是支撑性产品或运维 follow-up，不替代这六项 master issue。

## STL-001 bilingual viewpoint retrieval

状态为部分实现。Task 2A 结构性接入和 Task 2B-0 评测工具已完成。Task 2B-0.5 的隔离数据面已经在真实馆藏备份上运行，人工 benchmark 尚未完成。

默认语义模型为多语种 MiniLM，查询切词同时处理拉丁字符和中文，观点检索也支持语言过滤。现有测试能证明同语种查询的基础行为，但没有发现中文问题检索英文材料、英文问题检索中文材料的专项回归，也没有显式翻译模块。关键词降级不具备可靠的跨语言能力。

QueryLexicon 是本问题与 STL-002 的共享基础能力。2026-08-16 已完成 Task 1 核心源码和 Task 1.5 一次性环境验证，见 [query-lexicon-design.md](query-lexicon-design.md)。Task 2A 增加了只供 V2 使用的 search resolver、有界 bilingual branches、ambiguity 保留、entity/cross-language coverage、passage-level language detector 和 evaluation config snapshot。Task 2B-0 又增加了稳定 benchmark schema、V1/V2/lexical/dense 四路 pooling、盲化人工标注包、固定 diagnostic/dev/test split、分组指标、历史 language 审计和 QueryLexicon 双语覆盖审计。英文 entity coverage 的 substring 误命中已经改为拉丁词边界。Task 2B-0.5 新增 search-only bundle、evaluation namespace guard、QueryLexicon 重建、独立 Meilisearch build、snapshot manifest 和 pilot candidate 工具，详细边界见 [semantic-search-evaluation-environment.md](semantic-search-evaluation-environment.md)。

V2 feature flag 仍关闭，尚未作为读者默认检索，也没有执行生产 historical semantic reindex。真实 corpus repair 使用 PostgreSQL 16.14 副本，并在隔离 Meilisearch 1.37.0 中建立 3,881 文档的 repaired shadow UID `semantic_passages_eval_real_corpus_repaired_20260817_r63`。目标 QueryLexicon revision 为 1，shadow SemanticIndexVersion 状态为 ready，没有 activate。生产 migration、生产 QueryLexicon 和公开 V1 index 均未改变。

公开 V1 的索引版本元数据存在既有漂移。数据库中的 active SemanticIndexVersion 记录 2,543 个文档，而同 UID 的生产 Meilisearch 实测为 3,005 个文档。历史 job 已证明 2,543 是最初两个 Asset 的建立数，后来第三个 Asset 的 462 个文档通过没有 index version 的 active incremental path 写入同一 UID，旧代码没有更新版本记录。公开索引 record ID 与 3,005 个 current ready chunk 完全对应，missing 与 extra 都是 0。旧文档缺少新的 `document_id` 字段，另有 schema drift。生产版本记录仍未修改。源码已移除继续制造该漂移的模糊写入路径；新的 job/直接写入必须绑定唯一 active version，历史 null-version job 无法安全回填时以 `INDEX_VERSION_REQUIRED` 失败。

已新增只读一致性命令和 active 文档数同步。`SemanticIndexVersion.document_count` 对 active version 表示当前 UID 的实际文档数，对 ready 或 retired version 表示冻结时的实际数。`expected_document_count` 保留建立快照预期。metadata-only repair 只允许非 active 且 corpus 与 schema 完全一致的版本。公开 active version 必须继续人工审批，不能由命令自动修正。

真实 authority 暴露了新的主要缺口。public active lexicon 只有 5 个实体和 23 条 entry，Person 为 0，只有 3 个实体具备确认的中英文 canonical 或 translation。馆藏中的 Person 均为 draft，`Pierre Bourdieu`、`布尔迪厄` 和 `habitus` 因此没有统一实体扩展。Legacy TheorySchool 映射到 archived KnowledgeNode 的异常也没有被自动修正。这个缺口必须由 authority 审核解决，不能靠 ranking weight 或自动补译名掩盖。

真实数据审计发现 876 个 failed chunk 全部来自同一 draft Work 的 embedding DNS 失败。它们已在 disposable clone 中使用既有 pipeline 幂等恢复，repaired shadow 达到数据库 ready 3,881 与 Meilisearch 3,881 一致。另有两个 2026-08-09 后没有更新的 OCR job，分别使《实践与反思》和《弱者的武器》仍存在正文与 chunk 覆盖缺口。Production Task 3 部署时，新 Beat 首轮 recovery 重排了这两条 stale job；系统随即停止 Beat、非强杀 revoke并协作式暂停。两条现均为 paused，《弱者的武器》只完成了页65至68，未进入semantic或Candidate。它们仍需独立业务决定，不能靠 ranking 处理。

原 34 条 diagnostic 候选已在 repair 前完成 V1、baseline_v2a、lexical、dense 四路 top 10 pooling，共 766 个待判断 candidate。该包现标记为 `pre-corpus-repair`，不得作为正式 qrels，也不应继续人工标注。所有 query 仍无 gold，usable benchmark query 为 0。必须先在 3,881 文档 repaired corpus 上重新 pooling，之后才能比较同一 corpus 上的 shadow baseline 和 shadow V2。

下一步先由管理员决定是否恢复两个 paused OCR job，再在 repaired corpus 上重新 pooling 34 条候选。管理员确认约 30 条 pilot 后，先完成 3 至 5 条 query 的全部盲标。Person 状态、结构化译名和真正英文正文的馆藏仍是独立数据任务。只有 pilot 成功、80 至 120 条工作量可估算且 test split 可封存后，Task 2B-1 才能只用 dev 比较 branch budget、profile 和权重。

证据位置包括 `api/config/settings.py`、`api/catalog/services/semantic_indexing.py`、`api/catalog/services/semantic_index_consistency.py`、`api/catalog/management/commands/audit_semantic_index_consistency.py`、`api/catalog/services/semantic_search.py`、`api/catalog/services/semantic_search_v2.py`、`api/catalog/services/semantic_search_benchmark.py`、`api/catalog/services/semantic_search_evaluation_environment.py`、`api/catalog/services/query_lexicon/search.py`、`api/catalog/services/passage_language.py`、`docs/search-evaluation.md`、`docs/semantic-search-evaluation-environment.md` 和 `evals/semantic_search/task2a_cross_language.schema.json`。

## STL-002 field-specific web enrichment

状态为 Task 5 IMPLEMENTED，等待 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。没有 production deployment、production migration 或真实 Provider crawl。

Task 5 已建立统一 FieldEnrichmentRequest、FieldPolicyRegistry、SourceClass、StructuredSourceAdapter、可替换 WebSearchAdapter、安全 fetch、EnrichmentCandidate/Evidence 与 FieldMutationRegistry。请求按已有 target 与 field 执行。来源优先级、identity gate、证据数、冲突、refresh 和 Accept 路由都由 field policy 集中定义，不再散在前端 draft、Provider 与 serializer。

Wikidata、VIAF、LOC、OpenAlex、Crossref、OpenLibrary、Google Books 与 GROBID 都复用现有实现。可配置 SearXNG 只发现 URL，snippet 不会成为 Evidence。实际页面 fetch 保存 supporting span、canonical URL、title、domain、retrieved time、HTTP metadata 与 checksum，并拒绝私网、回环、link-local 和 redirect 后的 private target。Provider error 会按 unavailable、timeout、rate limited、fetch blocked、invalid source 和 parse failed 分类，其他来源结果仍可显示。

候选分 FACTUAL、CLASSIFICATION 与 INTERPRETIVE。Person 同名没有第二身份因素时不会产生字段候选。理论关系只靠共现不会生成；解释性 relation 默认要求两个独立来源。Accept 在单事务重新验证 policy、identity、evidence、staleness、current value 和 FieldLock，再写 PersonNameVariant、ScholarProfile、Work/Edition、KnowledgeNodeAlias、pending classification、pending KnowledgeRelation、timeline 或 ReadingPath source-of-truth。服务不直接写 QueryLexiconEntry，不自动发布、不自动 Accept，也不触发 semantic reindex。

代表字段已打通 Person identifier/affiliation/name variant、Edition publication year/publisher/ISBN、Work first publication date、KnowledgeNode alias/discipline/subdiscipline、KnowledgeRelation、timeline、Topic discipline 与 ReadingPath item。旧 AuthoritySuggestions 已降为显式只读 identity discovery，不再直接填 draft。旧 Metadata Review 继续兼容，最终是否与通用候选 UI 合并留到综合验收。

新增 migration 为 `catalog.0029_field_enrichment`，只创建 schema/index/constraint 并扩充 relation choices。本阶段没有应用 production migration。SearXNG 未部署，真实 Provider 质量、服务条款、真实 rate limit、网页解析覆盖、PostgreSQL migration 和管理员真实流程都属于最终综合验收。

证据位置包括 `api/catalog/services/field_enrichment/`、`api/catalog/enrichment_views.py`、`api/catalog/models.py`、`api/catalog/migrations/0029_field_enrichment.py`、`web/components/field-enrichment-control.tsx`、`api/tests/test_field_enrichment.py` 和 [field-enrichment-inventory.md](field-enrichment-inventory.md)。

## STL-003 library RAG

状态为 Task 6 IMPLEMENTED，等待 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。本阶段没有 production deployment、production migration、真实模型调用或大型 RAG evaluation。

AI runtime 已按 metadata extraction、Library QA 与可选 field enrichment capability 分离。非密钥 profile 使用私有 SiteSetting 与 AuditEvent，secret 和 endpoint 只通过服务器环境 alias 解析。Admin Settings 可以配置模型与受控生成参数并做安全健康检查。Library QA 不再被 metadata model 的必填校验阻塞，所有 provider HTTP 已收敛到共用 AIClient 的 generate、stream 与 health check。

LibraryQuery 已对齐 Task 4 的 plural scope contract，未知、不可公开和空 corpus scope 都不会静默变成全馆查询。公开 query understanding 只使用 QueryLexicon public_active。LibraryRetrievalService 默认强制 stable V1；experimental_v2 只允许管理员显式 debug，不改变公开 feature flag或 ranking 参数。比较问题使用双方独立约束分支；无法可靠解析两个公开实体时保留可查看的 passage，但不进入模型综合。逐字引文使用 keyword literal path，其他 entity anchor 分支数量有硬上限。

回答只依据已持久化 LibraryEvidence。Evidence 可以定位 Work、Edition、Asset、Page、document ID、原始 passage、实际语言和 Reader URL。无有效公开证据、检索错误、比较双方覆盖不完整、原句未找到或模型未给出有效 citation 时，服务明确返回证据不足，不自由回答。历史 assistant answer 不成为 evidence，馆藏文本没有 system 权限。Ask 不联网、不写 EnrichmentCandidate、QueryLexiconCandidate 或 authority。

Explore Ask 已改用 cookie-first session bootstrap。不可恢复的 401、403、429、认证临时错误与 provider failure 分开处理，只有 401 触发认证重验。Reader、Scholar、Theory 与 Topic 页面共享一个 scope-aware Ask 入口。旧 `/api/catalog/library-question/` 已删除；`_scope_filters`、`retrieve_library_sources` 和无语义的 provider compatibility wrapper 也已删除或改为命名服务。AssistMode.OFF 与 singular scope aliases 仍需在最终 reading migration 中规范化。

新增 migration 为 `reading.0005_library_ai_runtime_rag`，只增加 message runtime/query metadata 与 source Page/language/provenance/deep-link字段，没有 AI 调用、数据扫描、索引重建或 authority mutation。本阶段没有应用 production migration。Task 6 核心后端 35 项和较宽相关选择器 89 项通过；前端 Task 6 Node 4 项、Auth session 13 项、TypeScript、targeted ESLint 与 production build 通过。Django 静态门槛也已通过。

证据位置包括 `api/common/ai_runtime.py`、`api/ingestion/services/ai_client.py`、`api/reading/library_query.py`、`api/reading/library_retrieval.py`、`api/reading/library_assistant.py`、`api/reading/runtime_profiles.py`、`api/reading/migrations/0005_library_ai_runtime_rag.py`、`api/tests/test_library_rag_task6.py`、`web/components/explore-ask-client.tsx` 和 [library-ai-rag-inventory.md](library-ai-rag-inventory.md)。

## STL-004 scoped search

状态为 Task 4 IMPLEMENTED，等待最终综合架构验收。

Task 4 已建立统一 SearchContext 和 SearchService。Scholar、Topic、Subdiscipline、Theory、Work、Discipline 与 ReadingPath 都有明确 entity domain；global 必须显式并按组返回。Entity Search、Semantic/Viewpoint Search、Reader文档内搜索和图谱内筛选保持不同职责。

Public Scholar同时要求Person verified和ScholarProfile published，QueryLexicon匹配只用public_active。Theory采用KnowledgeNode canonical identity并抑制mapped legacy重复；Topic保持独立identity；Work按Work去重Edition。主要目录搜索与分页状态写入URL，Subdiscipline和Admin Scholar不再只筛当前页数组。

旧无context global payload、mixed theory-system search、legacy TheorySchool presentation route和旧array loaders暂时兼容。它们的删除/合并决策留到 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。

Task 6 已让 LibraryConversation scope 复用本节的 plural context contract，并保留有限 legacy singular aliases。最终是否删除兼容 aliases 留到综合验收。

证据位置包括 `api/catalog/services/scoped_search.py`、`api/catalog/views.py`、`api/catalog/knowledge_views.py`、`api/catalog/theory_system_views.py`、`web/lib/search-context.ts`、`web/lib/server-api.ts`、主要目录页面和 `docs/scoped-search-inventory.md`。

## STL-005 PostgreSQL nullable-join FOR UPDATE failure

状态为源码已修复并通过一次性 PostgreSQL 16.15 验证，生产部署待核实。

历史错误为 PostgreSQL 不允许对可空外连接一侧执行 `FOR UPDATE`。2026-08-16 的 P0 修复审计了 `api/ingestion` 中全部锁点。实体消歧、候选持久化、OCR PDF 和后台 backfill 现在都明确限定主表，元数据复核则依次锁 UploadItem、Edition 和 Work。候选持久化还以 UploadItem 父行为并发协调点，能够覆盖当前候选集合为空的情况。没有删除必要锁，也没有捕获后忽略数据库异常。

同一次修复补上 ProcessingJob 的 PostgreSQL 行级 claim、`task_id` 所有权检查和周期恢复。Redis 消息仍只负责唤醒，stalled 或 broker notification 丢失的 OCR、页码和 metadata enrichment 任务会由现有 ingestion recovery task 重新发现。历史 failed UploadItem 可以复用原 PDF、Work、Edition、Asset 和人工锁，从安全预检阶段继续。下架后重新发布的 PublicationEvent 长业务键也会稳定压缩到既有 120 字符字段，不需要 schema migration。

原 69 项 PostgreSQL 回归中的 12 项 ingestion 失败已经通过。第 13 项是 authority provider 线程连接绕过 pytest 主事务所造成的 SourceRecord 测试隔离问题，单独运行通过，不属于本问题。新增 9 项 PostgreSQL integration 全部通过。宽口径 155 项相关回归为 152 项通过，剩余 3 项均是封面测试关闭 FileResponse 后继续使用已关闭测试连接，与 ingestion 修改无关。生产部署、生产历史记录 retry 和真实 Celery worker 被强制终止后的演练仍为 `待核实`。

证据位置包括 `api/ingestion/views.py`、`api/ingestion/tasks.py`、`api/ingestion/services/entity_resolution_decisions.py`、`api/ingestion/services/candidate_store.py`、`api/ingestion/services/ocr_pdf.py`、`api/ingestion/services/processing.py`、`api/tests/test_ingestion_postgres_integration.py` 和 `api/tests/test_ingestion_integration.py`。

## STL-006 auth initialization failure

状态为源码已修复并通过本地真实 Cookie 浏览器验证，生产部署待核实。

根因有两项。第一，前端曾把 `library_session_active` 当作进入受保护页面的前置条件，导致有效 HttpOnly Cookie 在 localStorage 被清理或不可用时无法恢复。第二，Reader Center 曾把 `/auth/me/` 与八类阅读资源放入同一个 `Promise.all`，任一资源的 403、500 或网络错误都会清理会话并跳回登录。

2026-08-16 已建立统一 session bootstrap。Admin、Reader Center 和作品笔记深链接都会先用服务器 Cookie 请求 `/auth/me/`，并区分 loading、authenticated、unauthenticated、forbidden 与 temporary error。只有 refresh 后仍不可恢复的 401 会清 session。403、5xx、429 和网络错误保留会话。Reader Center 使用独立资源状态，一个模块失败时其余模块仍可显示。

同一标签页的 refresh 使用共享 Promise。支持 Web Locks 的浏览器还使用跨标签 refresh lock 与 revision，避免旋转 refresh token 被并发使用。storage、focus 和 pageshow 会触发服务器重验，角色变化和另一标签页 logout 不依赖旧的本地缓存。后端日志现在以无凭据方式区分 `no_cookie`、`expired_session`、`invalid_session`、`user_not_found`、`permission_denied` 和 `refresh_failed`。

本地验证包括 16 项 accounts 测试、13 项前端 session 行为测试和 13 项 Playwright 流程。其中 1 项使用真实 Django API、真实 HttpOnly access/refresh Cookie 与一次性 SQLite 数据库，覆盖读者登录、删除 hint 后刷新、logout 和切换管理员。最终综合阶段又把所有旧 `getStoredAccessToken()` 调用迁移到始终发送 cookie credential 的 `getServerSessionCredential()`，17 项 Auth/Ask 前端回归通过。生产公网与局域网 hostname、HTTPS Secure Cookie、真实 Edge 代理和既有生产 session 仍为 `待核实`。

本任务按边界没有修改 Explore Ask。该 RAG 界面仍有自己的 401/403 合并判断，后续只能在 STL-003 范围内处理，不能据此否定 Admin 与 Reader Center 的本次修复。

证据位置包括 `api/accounts/authentication.py`、`api/accounts/cookies.py`、`api/config/exceptions.py`、`web/lib/api.ts`、`web/lib/session.ts`、`web/lib/use-session-bootstrap.ts`、`web/components/admin-shell.tsx`、`web/components/reader-center.tsx`、`web/tests/auth-session.test.mjs` 和 `web/tests/auth-bootstrap.spec.ts`。

## FINAL INTEGRATED ACCEPTANCE 当前阻塞

本地源码收敛已完成一组安全修复：protected PDF 不再使用 shared public cache，chunk assembly 同步保存 SHA-256，SemanticIndexJob 禁止模糊 active UID 写入并提供 `INDEX_VERSION_REQUIRED`/`MODEL_UNAVAILABLE` 错误码，缺少 active version 时异步 enqueue 不会污染入库状态，旧 Ask 503 route 与未使用 compatibility functions 已删除。2.7 的本地后端、前端、migration drift 和构建门槛通过。

本轮授权使用的临时 RSA 私钥与对应公钥指纹一致，但 2026-08-19 对 `Winston@192.168.5.6:22` 仍返回 `Permission denied (publickey,password)`。本机也没有 Docker 或 PostgreSQL 16 runtime。因此当前生产容器、数据库、NAS、真实模型、真实 Provider、fresh backup、统一 migration rehearsal、clean active index 和浏览器生产联动均不能据称通过。SSH 恢复前不执行 production migration 或公网 cutover。

## STL-007 resumable large PDF upload

状态为核心续传已实现，跨设备与完整性能力仍有限。

后端已有分片状态查询、原子分片写入、manifest 冲突检查、原子合并、大小与 PDF 头校验。前端使用 2 MiB 分片、三次重试、已接收分片跳过和 localStorage 恢复。组装阶段现在同步计算最终 SHA-256 与 byte size，后续 pipeline 可复用摘要，避免 NAS 上再次无意义地完整读取。现有恢复信息仍依赖同一浏览器，换设备或清理 localStorage 后不能继续。

仍需在最终真实环境核验服务端可恢复会话、过期清理、跨浏览器恢复和超大文件的公网超时。验收应使用隔离测试 PDF，不上传馆藏原件，也不能把本地小样本结果写成当前大文件生产验收。

证据位置包括 `api/ingestion/views.py`、`api/ingestion/urls.py`、`api/tests/test_admin_configuration.py`、`web/components/admin-upload.tsx` 和 `web/tests/upload-metrics.test.mjs`。

## STL-008 BackupJob PostgreSQL client compatibility

状态为 resolved。正式 BackupJob 和同一 artifact 的 disposable restore rehearsal 均已通过。

真实根因是 PostgreSQL server 16.14 与原 API 镜像 pg_dump/pg_restore 15.18 不兼容。生产 Worker 日志明确记录 pg_dump 因 server version mismatch 退出，排除了网络、数据库权限和 NAS 目标路径问题。

API 镜像现已固定 PostgreSQL 16 client。BackupJob 在导出前检查 server、pg_dump 和 pg_restore major，密码只通过子进程环境传入，错误会脱敏。API、Worker、Ingestion Worker 与 Beat 已统一使用 pg_dump/pg_restore 16.15。正式 BackupJob 生成 9,944,031-byte artifact，SHA-256 为 `9376ba2f86bde08675f2ad8d335193daea24c40165bc2bd1d8ab4643365c50b6`。

同一 artifact 已恢复到 disposable PostgreSQL 16.14。关键馆藏、authority、ingestion、BackupJob 和 migration 表的数量与 ID hash 均和 source 一致，Django check 通过。该备份与恢复门槛建立时，source 仍是 catalog 0026、ingestion 0010且不含QueryLexicon/Candidate表。随后Production Task 3已在该门槛保护下应用0027/0028/0011。

证据位置包括 `api/Dockerfile`、`api/distribution/database_backup.py`、`api/distribution/tasks.py`、`api/distribution/management/commands/rehearse_database_restore.py`、`api/tests/test_distribution_backup.py`、BackupJob 运行记录和 `docs/PROGRESS.md`。

## STL-009 PDF to QueryLexicon candidate coverage

状态为 Task 3 DONE。Candidate 机制、PostgreSQL migration、完整 authority resolver 和真实 corpus 已通过最终验收；真实结果为 authority coverage gap。

Task 3 已新增 QueryLexiconCandidate/Evidence、deterministic pair extraction、exact batch resolver linking、Person 身份保护、跨 Work evidence 去重、Admin Accept/Reject 和 ProcessingJob 异步恢复。Accept 只写 PersonNameVariant 或 KnowledgeNodeAlias，再由既有 ChangeEvent 更新 QueryLexicon；pending/rejected 不改变 revision，也不直接写 Entry。

PostgreSQL 16.14 完整 authority 副本包含 6 Person、2 KnowledgeNode 及 Discipline、Subdiscipline、TheorySchool、Topic、LegacyKnowledgeMapping。0028/0011 首次应用、回退和重应用均成功，migration 前后 authority、3,881 SemanticChunk、SemanticIndexVersion、ProcessingJob 和 QueryLexicon state hash 不变。

QueryLexicon active revision 为 1。public_active 是 5 entity/23 entry，admin_resolvable 是 12 entity/61 entry。6 个 Person 全部为 draft，public 为 0，但 candidate extraction 可以通过 admin scope 解析其 authoritative canonical term。公开 search 仍只使用 public scope。

最终 5 Work、1,989 Page、3,881 chunk 扫描得到 1,652 observations、1,473 个有效结构 pair 和 1,387 个 unique pair。funnel 为 no canonical anchor 1,473、invalid/noisy 179，其余六类均为 0。两次 commit 完全幂等，Candidate、Evidence 和 authority 增量均为 0。

该结果正式归类为 `REAL CORPUS / AUTHORITY COVERAGE GAP`。Task 3 不再通过扩展规则追求正数 Candidate。后续 authority 编辑可以自然增加 exact anchor coverage，但不得自动发布 Person、创建 KnowledgeNode 或把 generated alias 提升为 verified translation。本问题不要求 semantic reindex，不改变 Task 2B-1，也不启用公开 V2。

2026-08-17 已完成 Production Task 3 Deployment。catalog 0027/0028 与 ingestion 0011 均 applied；生产 QueryLexicon revision 1、generation `af302b64-1b3f-447d-88ca-5ed505bc87e9`、69 entries，public 5/23、admin 12/61。单个真实 Asset 两次 extraction 复用同一 succeeded job，Candidate/Evidence 仍为 0，revision 与 active semantic UID 未变化。公开 V2继续关闭。

证据位置包括 `api/catalog/services/query_lexicon/candidates.py`、`api/catalog/models.py`、`api/ingestion/services/processing.py`、`api/catalog/management/commands/extract_query_lexicon_candidates.py`、`api/tests/test_query_lexicon_candidates.py`、`docs/query-lexicon-design.md` 和 `docs/PROGRESS.md`。

## STL-010 QueryLexicon Candidate review surface

状态为源码已补齐，生产 2.7 部署待核实。Next Admin 已有 Candidate review 页面，Django Admin 继续保留低层维护入口。

生产 API 内部使用真实管理员权限渲染 Candidate 与 Evidence changelist 均为 HTTP 200。status、linking、candidate type、term type、language、extraction version filters，Evidence inline，Accept/Reject actions 和 Asset discovery action 都存在。公网 `/admin/catalog/querylexiconcandidate` 由 Next 管理前端接管并返回 404；当前 Nginx 也没有把 Django `/admin/` 暴露到公网或LAN Edge。

这不影响 Candidate extraction、事务、审核模型或历史单Asset smoke。2.7 部署后仍需在真实权限下确认 Next Admin 页面与 API 的一致性。不得为解决入口问题放宽权限或公开无保护的 Django Admin。

证据位置包括 `api/catalog/admin.py`、`api/config/urls.py`、`deploy/nginx/default.conf.template` 和 `web` 当前管理路由。

## Version 2.7 architecture follow-up

状态为源码已补齐、生产待验证。旧后台入口已整理为统一信息架构，新增 capability contract、Knowledge Workspace、QueryLexicon Workspace、Projection Status 和 System Status Center。Unknown Entity 不再只落入 rejection funnel，而是保留可审计观察并聚合为 NewAuthorityCandidate。Candidate Review 对 field/query lexicon 只允许 accept/reject，对 New Authority 只允许 Match Existing/Create Draft/Reject；统一 envelope 显示标准审核状态并保留领域子状态。Provider 状态页区分 configured、not_configured 与尚未探测的 health unknown。

Projection Refresh 复用现有 `ProcessingJob`、Celery worker 和 recovery，不建立第二套队列。单目标刷新只协调既有 QueryLexicon event、semantic job 和 PDF candidate job，并保持幂等、可重试和非阻断。

后台发布、审核、处理控制和 Ask 实验模式的关键判断已改用同一 capability contract；用户角色字段仍只作为兼容展示和账户治理规则，不作为新后台 API 的唯一授权依据。普通 Admin 可以只读查看 QueryLexicon 与 Semantic Index；reconcile、索引激活和破坏性维护仍受 manage capability 保护。System Status 主导航复用实际 Celery broker/control/heartbeat 证据，旧 System Health route 仅作为兼容诊断入口。

仍需在最终阶段验证真实部署中的容器版本、migration head、队列、NAS、Meilisearch、AI provider 和 web provider。未完成真实环境检查前，不把本地源码状态写成公网已部署。

### 2026-08-19 2.7 门槛刷新

本地源码门槛已再次通过。后端收集 547 项、9 项按环境跳过，前端通用 63 项与 Auth/Scoped Search 17 项通过，Django check、migration drift、compileall、TypeScript、ESLint、Vinext build 和 diff check 通过。目标主机仍拒绝已授权 RSA 公钥，公网 readiness/health 仍报告 2.6.1；因此 FINAL INTEGRATED ACCEPTANCE 与 PUBLIC CUTOVER 继续保持 `BLOCKED`，未执行任何生产 migration、部署、active index 切换、公开 V2、authority publish 或 Candidate accept。

### 2026-08-19 2.7 live deployment update

上述 SSH 阻塞已解除。真实生产已部署 commit `7cd68d30776c0c652e080d147959a3183a92b71b`。catalog 0030、ingestion 0012、reading 0006 已 applied；fresh BackupJob、QueryLexicon reconciliation、clean semantic UID audit 和 active switch 均成功。生产保持 V2 false、Ask stable、AI/Web `NOT_CONFIGURED`，没有自动发布 authority 或 Accept Candidate。

当前总状态为 `PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。尚待用户进行登录后的 Admin、Reader Center、Ask、Candidate Review 人工测试，以及对真实 Provider 配置后的功能验证。

## 2.7 post-cutover usability findings, 2026-08-19

### Reader-owned Ask provider

状态为源码已修复，生产 migration 待核实。读者可以在 Ask 页面配置自己的 OpenAI-compatible、Ollama 或 vLLM 服务。凭据加密保存，不进入浏览器存储、日志或 API response。没有个人连接时，若服务器默认 profile 可用则使用默认服务；两者都不可用时明确显示配置入口和证据边界。`reading.0007_reader_ai_connection` 只创建连接表和索引，不会联网或改馆藏。

### Admin session and upload disappearance

状态为源码已修复，公网人工流程待核实。可见性切换和 pageshow 只做有界后台探测；临时网络/5xx 和单次后台 401 不再把已认证上传工作区卸载。跨标签 logout、明确 403 和后续受保护请求仍会执行服务器权限判断。拖拽上传增加键盘入口、拖拽深度处理、类型提示和现有分片恢复反馈。

匿名浏览器在没有 refresh Cookie 时，SimpleJWT refresh endpoint 会返回 400。客户端过去把它当成认证服务故障；现在只对该 refresh endpoint 将 400/401 统一视为无可恢复会话，正常显示登录提示。其他 API 的 400 不受影响。

Reader 过去使用恒为真的 cookie credential 标记判断登录，导致匿名访客也请求批注、书签、进度与历史接口。它现在复用 session bootstrap，并在 session 确认为 authenticated 后才访问私人记录。退出登录后页面内已加载的私人批注与书签会清除。

### Reader layout

状态为源码已修复。纸本页码是可选工具栏单元，已从隐式网格列中分离并在窄屏隐藏。OCR 状态通知回到文档流，不再覆盖 PDF 页面。尚需在真实生产浏览器以不同缩放、侧栏组合和长标题做人工观察。

### Authority/web enrichment errors

状态为源码已修复。结构化来源和网页来源现在返回部分结果、provider/error 分类和 request id；snippet 仍不被当作证据。没有达到 identity/evidence 门槛时，页面展示拒绝原因和统计，而不是只显示“没有候选”。真实 provider 可用性、条款和内容质量仍需单独核实，不应通过降低身份阈值解决。

生产 smoke 发现 VIAF 会返回 `result: null`。旧解析器对 null 切片导致 TypeError，且并发聚合器让这一家来源的失败清空全部结果。列表字段现先做类型规范化，单个 Provider 的网络或解析失败只形成 warning，本地及其他来源结果继续保留。

Person 字段补全过去只用列表中的第一个中文规范名，VIAF/LOC 经常因此无结果。现在只有首个查询完全没有结构化记录时，才以同一 authority 对象的已确认原文名再查一次。它不会使用生成拼音、unidecode 或低信任 alias，也不会绕过出生年份、标识符、机构和作品等身份条件。

编辑器的身份发现按钮优先使用表单中的原文/外文名称，并显示当前实际检索词。该表单值只帮助管理员发现来源；没有保存和人工审核前，不会成为权威数据或检索词典条目。

### Candidate Review semantics

状态为源码已修复。All Candidates 已改名为候选审核中心，明确它是跨领域 review queue，不是自更新社会科学词典。Metadata、QueryLexicon、Field Enrichment、New Authority 和 Theory task 继续各自写入 source-of-truth；QueryLexicon 仍是 derived projection。统一列表支持准确总数和截断提示。

### Remaining release gate

生产当前仍需为本轮 `reading.0007` 做一次受控 backup、migration plan、migration、统一镜像发布和登录后 smoke。未完成之前不得把读者自助模型配置报告为公网可用，也不切换 semantic index、修改 ranking、发布 draft authority、Accept Candidate 或开启公开 V2。
