# 开发进度

更新日期为 2026-08-19。当前源码版本为 2.7。本文只保留后续开发所需的简明状态，历史生产记录不等于本轮实时验收。

## 已实现

- Django/DRF API、Next/Vinext Web、PostgreSQL、Redis/Celery、Meilisearch 和独立 PaddleOCR 服务已经形成完整源码结构。
- 公开站、Explore、PDF Reader、账户中心和管理后台使用同一 API 与数据模型。
- 馆藏模型覆盖作品、版本、资产、逐页文本、全文段落、语义片段、学者、主题、理论节点和知识关系。
- 入库支持批次、文件级幂等、分片上传、失败重试、处理尝试、元数据候选、人工锁、OCR、页码、索引和发布预检。
- 访客可搜索、阅读、下载、复制和生成引用。登录读者可保存进度、收藏、书单、书签、批注和私人笔记。
- 原文检索、混合观点检索、版本化语义索引、馆藏评估工具和受控降级已经接入源码。
- 新书库问答实现位于 `api/reading`，具有私人会话、加密消息、来源校验、流式输出和 Reader 回链。
- 非 Explore 页面已采用黑、白、暖灰的出版型界面，并完成 Compact Editorial Density Pass。Explore 保持独立冻结范围。
- 当前迁移保存在各 Django app 的 `migrations` 目录，schema 修改继续通过 migration 管理。

## r61 当前生产验收

- 当前 API 为 `social-theory-library-api:2.6.1-r60-20260816-012052`，Web 为 `social-theory-library-web:2.6.1-r61-20260816-051351`。r61 只替换 Web，并刷新 Edge 和 Cloudflared，没有数据库迁移。
- r61 成功包 SHA-256 为 `fdf095df6ed8f8f1b2affb193a3b47ab6a6b95741ea6fb1c02c6a567db7654cb`。成功备份为 `/volume2/library/docker/social-theory-library/storage/backups/pre-compact-density-2.6.1-r61-20260816-051351`。
- 后端 293/293、Django check 和迁移漂移检查通过。前端 lint、TypeScript、45/45 Node 回归和生产构建通过。
- 生产 11 个服务全部 running，8 个健康探针为 healthy，RestartCount 全为 0。两个 Celery worker 回应，active、reserved、scheduled 与两个 Redis 队列均为空。
- 活动语义索引保持 `semantic_passages_20260809143729_4cf87bc9|2543|3005`。语义检索为 hybrid、`fallback_used=false`、4 项。三门学科主题筛选均为 200，学者推荐为三天轮换、automatic、3 项。
- 34 个公开路由在 1440、1920、2560 和 3840 四档完成 136 次检查。最终 Playwright 为 4/4 通过，控制台、页面、请求、坏图、横向溢出和 scope 问题均为 0。
- Explore 预热后等待网络、字体、普通图片、CSS 背景图和稳定 DOM，连续两轮 16/16 对应截图 SHA-256 完全一致。全部保持 `explore-frozen`。旧对照的 9 张差异已确认来自背景图、问答状态或封面加载时序。
- Reader 第 170 页画布、中文 CMap 和真实 Range 206 已通过。撤权后再次确认 readiness 为 200、`pending_migrations=0`，三门主题筛选为 200，语义检索未降级，Explore scope 正确，Range 返回 `%PDF-`。
- 三个 r61 远端暂存目录和两个失败的新镜像标签已删除。成功镜像、成功备份与全部 `pre-r61` 回退标签保留。临时 sudoers、公钥和本地一次性密钥已撤销，新 SSH 连接退出码为 255。
- `/account` 与 `/admin` 只验证了未登录跳转。登录后的账户中心和管理后台仍为 `待核实`，没有绕过认证或读取密码。

## 当前版本管理状态

- 2026-08-16 已在 GitHub 账号 `WinstonMo0807` 下创建 `social-theory-library` 私有仓库，并将安全源码快照推送到 `main`。
- 本地 `main` 正在跟踪 `origin/main`。首次 commit 为 `2c0bcb8b2f568dcbc17ef86d3c3197e1198f6560`。
- 首次快照包含 486 个源码、测试、配置、文档和前端素材文件，总大小约 5.82 MiB。馆藏与运行数据继续只保留在服务器或本地受控目录。
- 七项产品问题的状态、证据和验收要求集中记录在 [ISSUES.md](ISSUES.md)。

## QueryLexicon Task 1 源码状态

- 已新增 Person.merged_into 和结构化 PersonNameVariant。Person.aliases 继续保留为 legacy mixed 兼容字段。
- 已新增 QueryLexiconEntry、Generation、State 和 ChangeEvent。没有建立重复的 SyncJob 状态机。
- authority 的实例写与 bulk 写会在同一事务中保存 durable ChangeEvent。提交后的回调只唤醒批量消费者。
- Source Registry 已区分 canonical、verified 结构化名称、legacy mixed alias 和 generated search variant。
- mapped TheorySchool、Subdiscipline 和 Concept 统一使用 KnowledgeNode canonical identity。
- 全量、单类型和单实体 reconciliation 使用 staging generation。失败保留旧 active，无变化结果保留为 discarded。
- 内部 resolver 已支持 `public_active`、`admin_resolvable`、entity type、同词多实体和 revision 返回。
- `rebuild_query_lexicon` 已支持 dry-run、正式重建和 entity filter，并输出 legacy alias 与 0013 seed 污染审计。
- 这只是本地源码实现。migration 未在生产执行，公共观点检索、PDF candidate、联网补充、RAG、scoped search 和 autocomplete 均未接入。
- Task 1 完成时，PostgreSQL advisory lock、`SKIP LOCKED` 和真实 Redis/Celery 恢复仍待核实。下节记录 Task 1.5 的后续验证结果；生产数据迁移时间和生产 staging 空间仍为 `待核实`。

## QueryLexicon Task 1.5 验证状态

- 已在仓库外启动一次性 PostgreSQL 16.15 与 Redis 7.4.3。数据库、数据目录和端口都与生产隔离，没有连接 NAS、Meilisearch 或活动语义索引。
- 全新 PostgreSQL 数据库从零应用全部 migrations，`catalog.0027_query_lexicon_core` 正常完成。0026 到 0027 的独立 migration test 证明 Person、KnowledgeNode 和 KnowledgeNodeAlias 样本未被改写，0027 只建立空 generation、State 与新 schema。
- migration 后依次运行 dry-run、正式 rebuild、第二次 dry-run和第二次正式 rebuild。首次得到 15 个 entry、revision 1，第二次内容 hash 保持 `34d0b15c539c6f907c9bbc7616e6217bead255b8c7ac9742d58b24351bde0002`，revision 仍为 1。
- PostgreSQL integration 常规组 15 项通过。覆盖 shared 与 exclusive advisory lock、watermark、sequence 与 commit 次序差异、原子 cutover、并发 revision、`SKIP LOCKED`、重复事件、过期 lease、dead-letter、回滚和 merge audit。另有 1 项大数据演练单独通过。
- Redis/Celery integration 4 项通过，真实运行 Celery 5.6.3 Worker 和 Beat。Redis 停止时 broker notification 失败，pending event 留在数据库；Redis 恢复后 Beat 扫描并完成。Worker 在 claim 后退出时，另一 Worker 等 lease 到期后完成。
- merged Person dry-run 现在给出缺失目标、自指、循环、失联 survivor 和无效 survivor 的明确 finding。正式 rebuild 遇到致命异常会停止，不猜测或修改 authority。有效多级 merge 的历史名称归入最终 survivor。
- legacy audit 现在明确输出 unique legacy mixed、generated variant、0013 suspect seed 和 mapping anomaly 计数。PostgreSQL 测试确认疑似 0013 ASCII translation 仍为低信任 `search_variant`，`displayable=false`。
- 1,001 个 Person 的演练生成 6,020 个 entry。bulk create 为 2.338 秒，首次 rebuild 为 52.653 秒，cutover 为 2.699 秒，无变化重试为 29.995 秒。Python `tracemalloc` 峰值为 99.70 MiB。该结果不能代表生产或 10GB 馆藏规模。
- 原有 QueryLexicon 66 项在 PostgreSQL 和 SQLite 均通过。相关旧回归 69 项在 SQLite 通过；同一集合在 PostgreSQL 为 56 项通过、13 项失败，原因是 ingestion 中可空外连接上的无范围 `FOR UPDATE`。本任务未越界修改这些路径。
- Task 1.5 验证阶段仍未应用生产 migration，也没有启用 QueryLexicon 读者搜索、观点检索 V2、PDF candidate、联网、RAG、autocomplete 或任何 semantic reindex。Task 2A 的 V2 query-time 代码随后加入源码，但 feature flag 仍关闭。

## PDF ingestion / metadata review PostgreSQL P0

- 已在与生产隔离的一次性 PostgreSQL 16.15 上复现 Task 1.5 记录的 13 项旧失败。7 项来自实体消歧候选锁定时左连接可空 Edition，5 项来自 MetadataCandidate 锁定时左连接可空 SourceRecord。第 13 项是 authority provider 在线程连接中写入 SourceRecord 所造成的测试隔离问题，不属于 ingestion 锁错误。
- 已审计 `api/ingestion` 全部 `select_for_update()`。实体消歧、候选持久化、OCR PDF 和 backfill 查询只锁主表。Metadata review 明确锁 UploadItem、Edition 和 Work。Edition 与 Work 的非空内连接锁仍保留在 catalog 更新和发布事务中。
- ProcessingJob 使用 PostgreSQL 主行完成 claim。重复 Celery 投递不会重复执行。现有每分钟 ingestion recovery 现在也扫描 stalled、pending 和 queue-unavailable 的 OCR、页码及 metadata enrichment job，并使用新 task ID 恢复。真实多连接 `SKIP LOCKED` 已验证。
- 历史 metadata failed UploadItem 可以在不重新上传 PDF 的情况下重试。测试确认 Work、Edition 和 Asset ID 保持不变，人工 FieldLock 不被覆盖，连续点击 retry 只产生一次有效派发。
- `source_asset=null`、`source_asset` 非空、MetadataCandidate 无 SourceRecord、有 SourceRecord、failed detail API、metadata review PUT、重复 worker claim、worker 中断恢复和 retry 幂等均在 PostgreSQL 实际执行 SQL。新增 9 项 PostgreSQL integration 全部通过。
- 原 12 项 ingestion 失败全部通过。宽口径 155 项 PostgreSQL 相关回归为 152 项通过；剩余 3 项是既有封面测试调用 `FileResponse.close()` 后继续使用已关闭的 TestCase 事务连接。全仓 PostgreSQL 共收集 388 项，377 项通过、5 项跳过、6 项失败。另 3 项失败来自 authority provider 线程写入的 SourceRecord 跨测试残留，和前述封面测试合计为两个既有测试隔离问题。
- 同一套 155 项在 SQLite 为 146 项通过、9 项 PostgreSQL 专项跳过。PostgreSQL 下 `manage.py check`、`makemigrations --check --dry-run` 和 `git diff --check` 均通过。
- 本轮没有 migration，没有连接生产数据库、NAS 或 Meilisearch，也没有修改 QueryLexicon、semantic search 或 embedding 文档模板，因此不会触发 semantic reindex。

## Authentication Bootstrap / Admin / Reader Center P0

- 已确认浏览器生产认证仍以服务器校验的 HttpOnly JWT Cookie 为准。`library_session_active` 只保留为 UI 与性能提示。提示缺失或 localStorage 不可用时，Admin、Reader Center 和作品笔记深链接仍会请求 `/auth/me/` 恢复会话。
- 新增统一 session bootstrap 与 React hook，明确区分 loading、authenticated、unauthenticated、forbidden 和 temporary error。Admin 的读者角色会显示无权限，不再清 session 或伪装成未登录。5xx、429 和网络错误保留会话并允许原地重试。
- Reader Center 已把认证启动和八类个人资源加载拆开。资源使用 `Promise.allSettled`，收藏、历史或其他单项的 500 与网络错误只形成模块错误，不再触发 logout。作品笔记深链接也使用同一 bootstrap。
- refresh 保留同标签页 single-flight，并增加 Web Locks 与 refresh revision 处理跨标签并发。storage、focus 和 pageshow 会重新向服务器确认会话与角色。显式 logout 即使本地 hint 已丢失也会尝试调用服务器端 logout。
- 后端认证诊断不记录 token 或 Cookie 值。401 与 403 日志可以区分 no cookie、过期、无效 session、账户不存在、权限不足和 refresh 失败。
- Cookie 配置未放宽。access 与 refresh 继续为 HttpOnly，生产 Secure 设置保持，SameSite 分别为 Lax 与 Strict，host-only Domain 和既有 Path 保持不变。
- 后端 accounts 测试 16 项通过，认证及相关 reader/admin 定向回归 50 项通过。全仓 SQLite 共收集 396 项，367 项通过，29 项 PostgreSQL 或 Redis 专项跳过。
- 前端生产构建、lint、TypeScript、45 项既有 Node 回归和 13 项新增 session 行为测试通过。Playwright 13 项通过，其中 1 项使用真实 Django API 与真实 HttpOnly Cookie，覆盖读者登录、刷新、logout 和管理员切换。
- 本轮没有 migration，没有连接生产数据库、NAS 或 Meilisearch，也没有修改 QueryLexicon、ingestion locking、semantic search 或 embedding/index 模板。生产 HTTPS、Edge、公网与局域网 hostname 下的登录验收仍为 `待核实`。

## 本轮验证

- 首次提交前的主审计和独立复核均为 0 个阻断项，高置信 Secret 与常见个人邮箱扫描均为 0 项。
- 提交树没有真实 `.env`、PDF、数据库、OCR 数据、日志、归档、wheel、模型、embedding、索引或大于 10 MiB 的 Blob。
- `git diff --cached --check` 退出码为 0；首次 push 后本地 `HEAD` 与 `origin/main` 一致，GitHub API 返回 `PRIVATE`，默认分支为 `main`。
- 后端定向测试 20 项通过，只有两条 pypinyin 第三方弃用警告。
- 前端定向 Node 回归 18 项通过。
- 四份 Compose YAML 均能由 PyYAML 解析。当前环境没有 Docker CLI，`docker compose config` 仍为 `待核实`。
- QueryLexicon 定向测试 66 项在 SQLite 与 PostgreSQL 16.15 均通过，覆盖 Registry、normalization、事务、同步、generation、reconciliation、命令和 resolver。只有两条 pypinyin 第三方弃用警告。
- 相关 authority、backfill、lifecycle、theory system、entity resolution、ingestion 与 authority suggestions 回归 69 项通过。
- QueryLexicon Task 1.5 的 PostgreSQL integration、一次性 Redis/Celery 恢复和 migration rehearsal 已运行。SQLite 与 PostgreSQL 的 `manage.py check`、`makemigrations --check --dry-run` 和 `git diff --check` 均通过。生产 migration 仍未运行。

## 当前问题摘要

- bilingual viewpoint retrieval 具备多语种模型基础，跨语言检索质量待验证。
- field-specific web enrichment 已有字段级候选，但没有单字段定向触发和来源配置。
- library RAG 已接入新 reading API，登录后的真实生产流程待验证。
- scoped search 在书库问答中存在单数与复数参数键不一致，前端也没有提交 scope。
- PDF metadata / FOR UPDATE failure 已通过一次性 PostgreSQL 回归，生产部署与历史记录演练待核实。
- auth initialization failure 已完成源码修复和本地真实 Cookie 浏览器验证，生产部署与公网、局域网登录验收待核实。
- resumable large PDF upload 已支持同浏览器续传，跨设备恢复和逐分片哈希仍缺失。

## QueryLexicon Task 2A

- V2 查询阶段已接入统一 QueryLexicon search resolver。它覆盖 Person、KnowledgeNode、Discipline、Subdiscipline、TheorySchool、Topic 和 Concept，并遵守 mapped legacy 的 KnowledgeNode canonical identity。
- original query 永远保留。补充 branch 使用集中 hard limits，区分 canonical、verified translation、verified alias、historical、legacy mixed 和 generated search variant。高歧义孤立词保留 ambiguity，不强制选择理论实体。
- V2 规则重排新增 literal、entity 和 cross-language coverage。branch fusion 在有限贡献后去重，每个 passage 只保留一个 candidate。V1 没有接入 QueryLexicon。
- 新建或 force rebuild 的 SemanticChunk 使用确定性的 passage language detector，输出 `zh`、`en`、`mixed` 或 `unknown`。`semantic_documents()` 使用 chunk language，历史 chunk 与 active index 没有自动重建。
- SearchEvaluationRun 的 V2 config snapshot 记录 QueryLexicon revision、generation、branch limits、trust/profile 配置和 language detector 版本。Task 2A 双语人工标注格式见 `evals/semantic_search/task2a_cross_language.schema.json`。
- 本地专项测试和既有 V2、SemanticIndex、evaluation 回归已通过。没有新增 migration，没有更换 embedding model，也没有执行 semantic reindex。跨语言质量、Recall、排序和真实馆藏体量仍待 Task 2B 人工 benchmark。

## QueryLexicon Task 2B-0

- 已把跨语言 benchmark schema 扩展为稳定 query ID、五个检索方向、十类 query type、expected entities、四级人工 judgments 和固定 split。10 条模板均为未标注候选，不是 gold。
- 已新增只读 shadow runner。它对同一 query 合并 V1、V2、纯 lexical 和纯 dense top candidates，按稳定段落标识去重，并保存 rank、V2 branch provenance、阶段耗时、branch 数和 candidate 数。指定索引缺少冻结 runtime snapshot 时会停止，不会借用当前配置。
- 已新增静态 annotation package。人工页面使用固定 seed 盲化候选顺序，默认折叠来源算法，没有预选或推荐 grade。人工 judgments 可以合并回冻结数据集。
- 已实现 Recall@5、Recall@20、Precision@5、MRR 和 nDCG@10，并按方向、query type、diagnostic、dev、test 分组。nDCG 使用完整四级人工判断。正式评分会拒绝尚未人工判断的 pooled candidate。性能输出包含 p50、p95、样本足够时的 p99，以及 V2 各阶段耗时。
- `baseline_v2a` 已记录参数 ID 和 config hash。Task 2A 的 weight、profile 和模型均未调整。public V2 feature flag 仍关闭。
- `explicit_rewrite` 是调用者输入，`intent_rewrite` 是固定规则。两者不调用 LLM，均受 branch 与字符上限约束。评测调用可独立关闭 supplemental branch。
- 已修复实体覆盖的确定性英文 substring 误命中。`field`、`capital`、`practice`、`recognition` 和 `structure` 现在使用拉丁词边界。该修改没有改变 ranking weight。
- 当前本地 SQLite 只有 5 个 Work、917 个 Page 和 0 个 SemanticChunk，且没有 QueryLexicon 表。真实可用 benchmark query 为 0，10 条模板全部未标注。历史 language 与 active lexicon 双语覆盖仍需在获准的馆藏数据库副本上运行只读审计。
- 当前 language metadata refresh 归为 B。数据库 language 可重算，但现有 Meilisearch 路径需提交完整 semantic document，源码不能保证保留 embedding。本任务没有执行 refresh 或 semantic reindex。
- 最终本地后端回归为 404 passed、29 skipped。跳过项分别是 25 个 PostgreSQL integration 和 4 个 Celery/Redis integration。Task 2B-0 专项为 22 passed；`manage.py check`、`makemigrations --check --dry-run` 和 `git diff --check` 均通过。两条 benchmark audit/dry-run 命令退出码均为 0。

## QueryLexicon Task 2B-0.5

- 已审计现有 `BackupJob`。它是包含完整数据库和可选原始文件的灾难恢复归档，不能直接当作脱敏 evaluation bundle。本任务复用它作为可选只读来源工件，没有建立第二套通用备份系统。
- 新增独立 `compose.evaluation.yaml`。它只定义 PostgreSQL 16、Meilisearch 1.37 和可选的 source-copy PostgreSQL，全部使用单独 volume 与 evaluation 端口，不启动 API、Web、Redis、Celery、OCR 或 Edge。
- 新增 search-only export/import。导出使用 PostgreSQL repeatable-read read-only 事务，只保留检索需要的馆藏、Page、SemanticChunk、authority 与版本配置。账户、session、Reader 私有数据、原始文件和 secret 均不进入 bundle。每个文件有 SHA-256，manifest 记录 migration heads、数据量、模型、维度、源版本和 config hash。
- Evaluation 写入有硬性保护。数据库必须是 PostgreSQL，名称和 host 必须明确属于 evaluation，Meilisearch URL 必须与单独确认值一致，索引 UID 固定为 `semantic_passages_eval_*`，公开 V2 flag 必须关闭。
- 导入会清理新库中 migration 0013 的确定性 authority seed，拒绝任何账户、session 或 Reader 私有记录，再载入 source authority 并重新派生 QueryLexicon。不会复制旧 QueryLexiconEntry，也不会产生虚假的 outbox event。
- Evaluation Meilisearch 继续使用源 SemanticIndexVersion 冻结的模型、revision、维度、pooling 和 document template。现有源码必须重新提交完整文档，因此 evaluation build 会重新 embedding，但只写隔离 UID，版本保持 ready 而不 activate。
- 新增环境 audit、四路 smoke、历史 language baseline、QueryLexicon coverage、chunk 定位校验和 snapshot manifest。另有 pilot candidate 命令，只提出实际词典和馆藏支持的未标注候选，不输出 passage ID 或自动 gold。
- 源码阶段新增 9 项单元测试通过，2 项真实 PostgreSQL export/import integration 当时因本地没有 PostgreSQL 而跳过。全仓 SQLite 回归为 413 项通过、31 项环境专项跳过、0 项失败。该记录只说明源码阶段状态，后续真实馆藏执行见下节。

## Task 2 真实馆藏 shadow 验证

- 2026-08-16 使用正式备份机制的数据库导出路径取得只读来源。内置 `BackupJob` 因服务端 PostgreSQL 16.14 与 `pg_dump` 15.18 版本不匹配而失败，随后使用 PostgreSQL 16 容器完成备份。`database.dump` 为 10,431,358 bytes，恢复演练在一次性 PostgreSQL 16.14 中通过。生产数据库、活动索引和馆藏原文没有写入。
- 已建立隔离 PostgreSQL 16.14 与 Meilisearch 1.37.0。search-only bundle 包含 3 个可检索 Work、1,106 个 Page、3,005 个 ready SemanticChunk，不含账户、session、Reader 私有数据、原始 PDF 或 secret。目标数据库应用到 `catalog.0027_query_lexicon_core`，生产数据库仍停留在 `catalog.0026_semantic_feedback_deduplication`。
- Evaluation QueryLexicon 由 authority source 重建。revision 为 1，共 14 个实体、69 条 entry。公共可解析范围只有 5 个实体和 23 条 entry，其中 Person 为 0，KnowledgeNode 为 1，其他实体为 4。确认的中英双语实体为 3，中文有而英文缺失的实体为 2。Person authority 当前均为 draft，因此没有擅自提升为 public active。
- Evaluation SemanticIndexVersion 为 `5e017013-52b1-5af9-a3f5-b1a87fead79c`，UID 为 `semantic_passages_eval_real_library_20260816_r62`，文档数为 3,005，状态为 ready。它使用现有 multilingual MiniLM、同一 revision、384 维和同一 pooling。隔离 build 重新计算了 embedding，但没有 activate，也没有修改公开 V1 UID。
- 生产公开 V1 仍使用 `semantic_passages_20260809143729_4cf87bc9`。生产 SemanticIndexVersion 记录为 2,543 个文档，而同 UID 的 Meilisearch 实测为 3,005 个文档。search-only exporter 因此先拒绝导出。只在隔离 source copy 中把冻结版本配置和实测文档数对齐后才继续，生产记录没有被修正。该 metadata drift 需另行审计。
- 首次 evaluation build 将一个 Asset 的 1,214 个文档一次提交，Meilisearch 容器被内存限制终止。语义索引写入现统一按 128 条分批，最大允许 1,000 条。失败不会把冻结的 SemanticChunk 改为 failed。全新目标库重试后以 25 个 batch 写入 3,005 个文档，Meilisearch restart count 为 0。
- 真实馆藏共有 5 个 Work、5 个 Edition、1,989 个 Page 和 3,881 个 SemanticChunk。历史 stored language 全为 `zh-CN`。detector 结果为 zh 2,636、en 438、mixed 547、unknown 260，family 不一致为 1,245 条，占 32.0794%。可检索 3,005 条中的 detector 结果为 zh 2,257、en 182、mixed 306、unknown 260，不一致为 748 条，占 24.8918%。baseline metadata 未刷新。
- 自动 pilot candidate 只能从当前 public lexicon 产生 6 条规范学科名，无法形成平衡的真实 pilot。基于实际 Work 和 passage 另提出 34 条待管理员确认的 diagnostic 候选。方向分布为 zh_to_zh 8、en_to_zh 8、mixed 6、zh_to_en 6、en_to_en 6。所有 expected entity 和 gold judgment 保持为空。
- 34 条候选已在隔离索引完成 V1、baseline_v2a、纯 lexical 和纯 dense 四路 top 10 pooling。共得到 766 个待人工 judgment，单题 unique candidate 中位数 22、p95 为 28，范围 14 至 29。完整运行耗时 62 秒。V1 latency p50 为 557.41ms、p95 为 1,023.52ms；V2 p50 为 286.53ms、p95 为 1,013.44ms。V2 resolver p50 为 5.47ms、p95 为 8.44ms。
- V2 对 34 条 query 全部真实返回结果且没有非预期 fallback。11 条有 supplemental branch，其中 10 条只有 deterministic `intent_rewrite`。仅一条因英文 `sociology` 命中 Discipline 并产生 verified translation branch。`field`、`capital`、`practice`、`recognition`、`structure` 及对应中文困难词没有被强制解析成理论实体。
- 当前 real-data blocker 已从“没有 SemanticChunk”转为 authority 和语料覆盖。`Pierre Bourdieu`、`布尔迪厄` 与 `habitus` 没有 QueryLexicon entity expansion。英文候选大多来自《国家的视角》书后索引，尚不足以支持平衡的英文证据方向。34 条 query 全部未人工标注，usable benchmark query 仍为 0，不能据此比较 V1 与 V2 精度。
- 盲标包位于隔离环境 `annotation/real-pilot-review-20260816`。页面默认隐藏来源、rank、score 和 branch provenance。人工完成 3 至 5 条 query 的完整 judgment 流程仍未进行，Task 2B-1 继续封锁。`baseline_v2a` config hash 保持 `79650a79de2c5c973172d14a6b61c6b72fdd46983b56484501940d23f89bd8c3`，公开 V2 feature flag 仍关闭。

## 真实馆藏 corpus integrity repair

- 2026-08-17 对真实数据库副本中的全部 876 个 failed SemanticChunk 完成逐条 inventory。报告保留 Work、Edition、页码与 chunk locator、chunk ID、状态、错误、时间、索引版本和失败阶段。876 条全部集中在 draft Work《红酒帝国：市场、殖民地与英帝国兴衰三百年》，全部属于 embedding 阶段的 Hugging Face 配置文件 DNS 获取失败。没有发现 chunk text 生成、Meilisearch document write、language validation 或 stale 空错误等其他类别。
- 5 个 Work 的原始状态为 3,005 ready、876 failed。《国家的视角》有 1,329 个 ready chunk，427 个正文页中的 419 页被覆盖。《实践与反思》有 1,214 个 ready chunk，433 个正文页中的 403 页被覆盖。《弱者的武器》有 64 个已有正文页但没有 chunk，OCR job 仍停在 running。《社会学方法的准则》有 462 个 ready chunk，170 个正文页中的 163 页被覆盖。《红酒帝国》有 876 个 failed chunk，372 个正文页中的 367 页只有 failed chunk。
- 恢复只在 disposable PostgreSQL 副本和隔离 Meilisearch UID 中执行。它复用现有 `build_semantic_chunks(force=True)` 与 `index_semantic_asset()`，没有复制 Work、Edition 或 Asset，也没有修改 Page/OCR 原文和 authority。第一次恢复把 876 条 failed 全部变为 ready，用时 84.186 秒。第二次运行仍为 876 条 ready、0 failed，chunk ID、document ID、Page 文本 checksum 和远端文档数均不变。
- 恢复使用 128 条一批，共 7 批。NAS 上两次重复 embedding 在 Meilisearch RSS 约 2.18 GiB 和 2.29 GiB 时被 earlyoom 终止，说明 HTTP 分批不能消除 Meilisearch 内部 embedding 峰值。最终 recovery 与 repaired shadow 在隔离的 Windows Meilisearch 1.37.0 上完成。完整 3,881 文档构建为 32 批，32 个任务全部成功，Meilisearch 任务窗口为 255.771 秒。
- active SemanticIndexVersion 的 2,543 对 3,005 漂移已定位。该版本最初由 1,329 与 1,214 个文档建立，随后《社会学方法的准则》的 462 个文档通过 `index_version=null` 的 active incremental path 写入相同 UID。旧路径没有同步 `SemanticIndexVersion.document_count`。源码现在把 active version 的 `document_count` 定义为当前 UID 实际文档数，把 ready 或 retired version 的值定义为冻结时实际文档数。`expected_document_count` 继续表示建立快照的预期值。
- 新增 `audit_semantic_index_consistency`。默认只读比较版本记录、数据库 ready chunk、稳定 record/document ID 和 Meilisearch 文档。`--repair-metadata` 只允许非 active 且 corpus 与 schema 完全一致的版本，active version 会被拒绝。active asset 的增量写、删除和零 chunk 清理都会同步当前文档数。
- 对公开 UID `semantic_passages_20260809143729_4cf87bc9` 的生产查询保持只读。结果为 Meilisearch 3,005、数据库 current ready 3,005、missing 0、extra 0、record ID 一致。数据库仍记录 2,543，因此 metadata drift 为 true。旧文档都没有 Task 2A 后新增的 `document_id`，schema drift 为 true。生产 UID、版本记录和 SemanticChunk 均未修改。
- repaired shadow SemanticIndexVersion 为 `cf0988a5-841c-423d-b403-ee7c80891098`，UID 为 `semantic_passages_eval_real_corpus_repaired_20260817_r63`，状态为 ready。数据库 ready chunk、unique record ID、unique document ID 和 Meilisearch document count 均为 3,881，missing、extra、ID mismatch 与 schema drift 均为 0。它使用原 multilingual MiniLM、相同 revision 和 384 维，重新计算 embedding，但没有 activate。
- repaired corpus detector 结果为 zh 2,636、en 438、mixed 547、unknown 260。stored language 与 detector 的 exact mismatch 为 3,005 条，占 77.4285%。按语言族比较的 mismatch 为 748 条，占 19.2734%。新恢复的 876 条已保存 passage-level language，旧 3,005 条继续保留历史 `zh-CN` metadata。生产 V1 language metadata 没有刷新。
- 新 shadow baseline 和 shadow V2 已在同一 repaired UID 上分别完成中文 `实践理论` 与英文 `social practice` smoke。V1、V2、pure lexical 和 pure dense 都真实返回结果，公开 V2 flag 保持关闭。旧 34 条候选和 766 个 judgment 已标记为 `pre-corpus-repair`，不得作为正式 qrels。后续必须使用 repaired corpus 重新 pooling。
- 本轮专项测试 9 项通过，语义与评测宽口径回归 113 项通过。Django check 和 migration drift 检查通过。本轮没有 migration，没有修改 ranking、QueryLexicon authority、authentication、ingestion locking 或公开 active index。

## QueryLexicon Task 3 PDF Candidate Extraction

- 已新增 QueryLexiconCandidate 与 QueryLexiconCandidateEvidence。Candidate 保存 target、anchor、proposed term、语言、term type、linking/status、confidence factors、extraction version、fingerprint、reviewer 和 accepted authority reference。Evidence 保存 Work、Edition、Asset、Page、SemanticChunk/document ID、原始 passage、span、bbox、OCR quality、quality flags 和 checksum。
- 第一版只识别可解释的中英文括号、方括号、斜杠、术语表冒号、英文原文为、又译作、旧译作、又称和以下简称。真实样本暴露的致谢前缀、过长 CJK 上下文、前导点号、数字串与短 token 已加入确定性过滤。
- Entity linking 复用 QueryLexicon exact resolver 的 batch API。legacy/generated variant 不能单独绑定 target。Person 即使唯一命中也需当前 Edition 的 approved Contribution、生卒年或 identifier 佐证，否则保持 ambiguous。
- Accept 在单事务内重验 target，写 verified PersonNameVariant 或 KnowledgeNodeAlias，再由既有 AuthorityMixin 生成 ChangeEvent。服务不直接写 QueryLexiconEntry。Reject 保存 reviewer、timestamp 和 reason，Evidence 不删除。已存在 verified authority 为 no-op，不因 PDF provenance 制造虚假 revision。
- ProcessingJob 新增 `query_lexicon_candidates`。SemanticChunk 完整提交后异步排队，现有 ingestion recovery 可恢复 broker 丢失或 stalled job。扫描失败只影响自己的 job，不改变 UploadItem、OCR、publication、SemanticChunk index status 或 SemanticIndexVersion。Asset Admin 提供手动排队，管理命令默认 dry-run。
- 新 migration 为 `catalog.0028_query_lexicon_candidates` 与 `ingestion.0011_query_lexicon_candidate_job_type`。PostgreSQL 16.14 完整 authority 副本从 0027/0010 首次应用、回退和重新应用均通过，首次 9 秒、重应用 8 秒。authority、SemanticChunk、SemanticIndexVersion、ProcessingJob、revision/generation 的 count/hash 在三个边界完全一致，Candidate/Evidence 始终为 0。
- 完整 authority 副本包含 6 Person、0 PersonNameVariant、2 KnowledgeNode、4 KnowledgeNodeAlias、3 Discipline、1 Subdiscipline、1 TheorySchool、1 Topic、0 Concept 和 1 LegacyKnowledgeMapping。QueryLexicon dry-run 为 14 source entity、69 entry、0 diff；正式 rebuild 为 no-op，active revision 1、generation `f1949b23-9edd-49a7-b205-20ed606ab089`。
- public_active 为 5 entity、23 entry；admin_resolvable 为 12 entity、61 entry。Person 共 6 个且全部 draft，因此 public 为 0、admin 为 6 entity/33 entry。KnowledgeNode 共 2 个，1 published、1 archived，因此 public/admin 均为 1 entity/4 entry。
- extraction 与 Accept target revalidation 都显式使用 `admin_resolvable`。公开 V2 resolver 默认仍为 `public_active`，V1 不读取 QueryLexicon。真实 `Pierre Bourdieu` 能以 authoritative canonical 解析到 draft Person，但 public resolver 返回空。
- 最终完整扫描覆盖 5 Work、1,989 Page、3,881 SemanticChunk。Run A dry-run 为 13 秒，Run A commit 与 Run B commit 均为 12 秒。共有 1,652 explicit observations、1,473 个通过结构过滤的 pair、1,387 个 unique pair。
- rejection funnel 完全守恒：no canonical anchor 1,473，invalid/noisy 179；target not admin、low-trust/generated-only、ambiguous、Person identity insufficient、already exists 和 valid Candidate 均为 0。Run A 与 Run B 的 funnel、Candidate/Evidence、revision 和所有 source hash 完全一致。
- 真实 Candidate、Person Candidate、KnowledgeNode Candidate、ambiguous 和 Evidence 均为 0。没有自动 Accept，没有创建未知 authority。结果归类为 `REAL CORPUS / AUTHORITY COVERAGE GAP`，不继续放宽 exact linking 或 identity safety。
- 关键术语中，`布迪厄` 出现于 43 个 chunk、惯习 19、习性 1、field 5、场域 43、practice 20、实践 226；它们都没有作为显式 pair 一侧。`Pierre Bourdieu` 是 draft Person 的 admin authoritative anchor，但在 corpus 中为 0 次且无 pair。habitus 也为 0 次。故均不生成 Candidate。
- PostgreSQL Task 3 专项为 18 passed；PostgreSQL QueryLexicon public/admin 与 Task 2A 回归为 36 passed。最终本地非环境专项全仓回归为 441 passed、31 deselected、2 warnings。Django check、migration drift、compileall 和 git diff check 通过。
- 生产 PostgreSQL、production authority、公开 Meilisearch UID 和 SemanticIndexVersion 均未修改；本轮没有 semantic reindex。Task 3 FINAL ACCEPTANCE 已满足，状态为 DONE。

## STL-008 BackupJob PostgreSQL 16 compatibility

- 真实根因已由生产 Worker 日志复核。PostgreSQL server 为 16.14，原 r60 API、Worker、Ingestion Worker 与 Beat 的 pg_dump/pg_restore 均为 15.18。pg_dump 已连接到 server 后以 version mismatch 主动退出，不是网络、数据库权限或 NAS 路径故障。
- API Dockerfile 现在通过 PGDG 仓库锁定 `postgresql-client-16`，并在镜像构建阶段验证 pg_dump 与 pg_restore major。BackupJob 新增 server/client preflight、错误脱敏、database.dump checksum、server/client 版本和 applied migration heads。备份格式与 BackupJob 管理入口未改变。
- 新增 `rehearse_database_restore`。它只允许空白且名称明确属于 disposable restore 的 PostgreSQL，要求目标名二次确认，校验内部 dump checksum，并同时验证 pg_restore 与 target server、dump client 的 major compatibility。
- 生产采用窄范围镜像 `social-theory-library-api:2.6.1-r60-stl008-20260817-174451`。它基于原 r60，只覆盖 BackupJob 文件和 PostgreSQL 16 client，不包含 catalog 0027/0028 或 ingestion 0011。API、Worker、Ingestion Worker 与 Beat 均使用该镜像，pg_dump/pg_restore 均为 16.15。切换前后 migration plan 为空，readiness 的 pending_migrations 为 0。
- 正式 BackupJob `4e1ee713-2c29-45aa-a47c-b8c965261771` 已成功。artifact 为 `/data/backups/stl008-formal-20260817-175034/library-backup-20260817-095049-4e1ee713.tar.gz`，大小 9,944,031 bytes，SHA-256 为 `9376ba2f86bde08675f2ad8d335193daea24c40165bc2bd1d8ab4643365c50b6`。database.dump 为 10,432,271 bytes，内部 SHA-256 为 `bdaccd6147ea8996e7c2ae9e1d7ac967fdf02b01d74a9f368a1f8d8f285506eb`。任务约 3 秒完成，未包含 ORIGINAL PDF。
- 归档内容、BackupJob metadata 与对应 Worker 日志的 secret 检查均为 0 命中。manifest 记录 server 16.14、pg_dump 16.15、pg_restore 16.15、catalog 0026 与 ingestion 0010 等 applied heads。
- 同一 artifact 已恢复到没有发布端口、没有连接生产 backend network 的 disposable PostgreSQL 16.14。pg_restore 为 16.15，Django check 通过。Work 5、Edition 5、Asset 10、Page 1,989、SemanticChunk 3,881、Person 6、KnowledgeNode 2、UploadItem 9、ProcessingJob 9、BackupJob 2 和 django_migrations 75 的数量与 ID hash 均和 source 一致。
- 恢复库没有 QueryLexiconEntry、State、Generation 或 Candidate 表，证明生产仍停在 catalog 0026 与 ingestion 0010。disposable container、network 和 volume 已删除。正式 artifact、环境文件回退副本、旧 r60 镜像和当前 hotfix 镜像继续保留。
- 本地 BackupJob 与后台配置回归为 25 passed。Django check、makemigrations drift、compileall 和 git diff check 通过。本任务没有 model change 或 migration。
- STL-008 已真实关闭。`PRODUCTION MIGRATION GATE = READY` 只表示可在下一独立任务评估并部署 Task 3 migrations；本轮没有执行 catalog 0027/0028 或 ingestion 0011，也没有开始 Task 4 或 Task 2B-1。

## Production Task 3 Deployment

- 正式 BackupJob `4e1ee713-2c29-45aa-a47c-b8c965261771` 在部署前再次核验为 completed。tar.gz SHA-256 `9376ba2f86bde08675f2ad8d335193daea24c40165bc2bd1d8ab4643365c50b6`，内部 database.dump SHA-256 `bdaccd6147ea8996e7c2ae9e1d7ac967fdf02b01d74a9f368a1f8d8f285506eb`。
- 部署 baseline 为 catalog 0026、ingestion 0010。Work 5、Edition 5、Asset 10、Page 1,989、SemanticChunk 3,881、Person 6、KnowledgeNode 2。active SemanticIndexVersion 为 `a430d353-227f-441b-a200-56ebb87ac69d`，UID `semantic_passages_20260809143729_4cf87bc9`，数据库记录 2,543、Meilisearch 3,005，已知 drift 未修改。V2 flag 为 false。
- 完整 production image 为 `social-theory-library-api:2.6.1-task3-prod-20260817-181038-a611debdf616`，source revision `a611debdf6167cbf3b4448718922b8cf62a375d593e16973f1041634456a9327`，image ID `sha256:2940461440c6047e42af5c9350175795dd5cad1a7418b1e967afbfcd9a7da8d6`。API、Worker、Ingestion Worker 与 Beat 使用同一 image，pg_dump/pg_restore 均为 16.15。
- 新 image 对生产运行 `migrate --plan` 只包含 catalog 0027、0028 与 ingestion 0011。正式 migration 在暂停 Beat 和两个 Worker 后执行，耗时 10.099 秒。迁移后八类核心表的 count 与 ID hash 和 baseline 完全一致，active SemanticIndexVersion 与 UID 未变化。
- 初始 QueryLexicon state 为 revision 0、entry 0。生产 dry-run 为 14 entities、69 expected entries，merge、mapping、orphan 与 ambiguous anomaly 均为 0；legacy mixed 5、generated variant 49、0013 suspect 4、mapped legacy suppressed 1，与 disposable rehearsal 一致。
- 正式 reconciliation 耗时 4.294 秒，revision 0 增至 1，generation `af302b64-1b3f-447d-88ca-5ed505bc87e9`，content hash `0c56fcf6349c2cff7d7dad693c26564773e36de622502a68e5eed0060d6b6aeb`，entry 69。public_active 为 5 entity/23 entry，admin_resolvable 为 12 entity/61 entry。真实 draft Person `George Herbert Mead` 在 admin scope 可解析，在 public scope 为 0。
- Candidate 与 Evidence Django changelist 使用真实生产数据库和管理员权限完成 server-side render，均为 HTTP 200。status/linking/type/language/version filters、Evidence inline、Accept/Reject actions 和 Asset discovery action 均存在。公网 `/admin/catalog/querylexiconcandidate` 由 Next 管理前端接管并返回 404；Django Admin 没有通过公网 `/admin` 暴露，本轮没有新增路由。
- 真实 Asset smoke 使用《社会学方法的准则》Asset `99389cf6-35be-401d-8654-276a5d667c5b`，含 170 text pages、462 ready chunks。ProcessingJob `3e85ef3e-4b7e-4413-a098-9f4bd6943f43` 在 0.371 秒内 succeeded，attempt 1、progress 100。发现 3 个 explicit pairs，全部因 no canonical anchor 拒绝，Candidate/Evidence 为 0。
- 第二次相同 `--queue` 返回同一 job ID 与 idempotency key，没有重复 dispatch。ProcessingJob 仍为 1 条、attempt 1。Page/Chunk hash、Asset/Edition/Work updated_at、QueryLexicon revision/generation 与 active UID 均未变化。
- 公网 V1 查询 `实践理论` 返回 HTTP 200、engine hybrid、fallback false、search_version v1、2 results，端到端约 4,792ms。公开 V2 flag 继续为 false，没有 semantic reindex，SemanticIndexJob active 为 0。
- 新 Beat 首次 recovery 发现两条 2026-08-09 stale OCR job并重排。部署随即停止 Beat，对两个 task 非强杀 revoke，并使用既有协作式暂停。`《实践与反思》`保持48页OCR后paused；`《弱者的武器》`安全完成当前65至68页批次后paused，仍有440页，不生成SemanticChunk或Candidate。Beat恢复后的两个recovery周期均为 candidates 0、requeued 0。
- 最终 API、Worker、Ingestion Worker healthy，Beat running，四个应用容器 RestartCount 0；PostgreSQL、Redis、Meilisearch healthy。部署窗口内七个核心容器的 ERROR/Traceback pattern 均为 0。QueryLexicon pending/dead-letter 为 0，Candidate job 1 succeeded，Candidate/Evidence 为 0。
- 本地定向回归为 114 passed，Django check、makemigrations drift、compileall 与 git diff check 通过。正式回退优先恢复 `.env.pre-production-task3-20260817-182353` 并切回 STL-008 hotfix image，保留 additive schema、QueryLexicon/Candidate 数据与 authority。

Production Task 3 Deployment 状态为 DONE。没有开始 Task 4 或 Task 2B-1。

## Task 4 Unified Scoped Search Architecture

- 已新增统一 SearchContext 与 SearchService。contexts 为 works、scholars、disciplines、subdisciplines、theories、topics、reading_paths 和 global。服务复用现有 Django querysets、QueryLexicon public terms 与既有 serializers/presentation routes，没有新增 retrieval engine、Meilisearch index 或数据库表。
- `/catalog/search/` 继续作为唯一协调 endpoint。显式 scoped context 返回共享 envelope；显式 global envelope 按 entity group 返回。空 global query 不检索，空 scoped query保持browse。无context旧payload继续兼容并带Deprecation header。
- 首页与Explore原文搜索显式提交 `context=global`。Scholars、Topics、Subdisciplines、Theories和legacy TheorySchool页面分别声明自己的context。理论首页不再调用混合Node/Scholar/Work/Passage的theory-system search，只返回theories results。
- Scholars、Topics、Subdisciplines与legacy TheorySchool目录现在保留后端count/page/totalPages并把page写入URL。Subdiscipline删除当前页JS includes；Admin Scholars使用既有Admin SearchFilter并同步URL q；metadata review queue把status发送到后端。
- Public Scholar要求Person verified与ScholarProfile published。匿名不能请求admin visibility。SearchService对Person/KnowledgeNode等QueryLexicon匹配只读取public_active；后台explicit admin scope仍可读取draft。
- Theory results优先使用published KnowledgeNode。mapped TheorySchool被抑制，mapped Subdiscipline返回KnowledgeNode canonical ID；Topic不与同名KnowledgeNode合并；多个Edition仍只返回一个Work。
- deterministic排序为exact canonical、verified public alias、prefix、其他文本match。共享result保存canonical URL、match信息和entity-specific metadata，不丢失对象差异。
- 兼容层保留无context `/catalog/search/` 与 legacy `/theory-schools` presentation route；mixed `/catalog/theory-system/search/` endpoint 和 server-api 旧 array loader 已删除，理论搜索统一走 `context=theories`。
- 新增16项backend scoped-search测试和4项frontend context/URL/error测试。相关既有backend 54项、ingestion-search联动与complete-ingestion共3项、rendered HTML 15项通过。TypeScript、targeted ESLint与Vinext production build通过。
- 本任务没有migration，没有连接生产，没有production/shadow acceptance，没有修改semantic_search_v2 ranking、embedding、Candidate extraction、OCR、ingestion locking、Auth、RAG或web enrichment。

Task 4 源码状态为 IMPLEMENTED。删除兼容层、统一最终导航、全系统性能与production cutover留到 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。

## Task 5 Field-Aware Web Enrichment

- 已新增统一 FieldEnrichmentRequest 与 FieldEnrichmentService。请求包含 target、field、current value、form context、structured/web/full mode 和明确的 admin visibility；页面级请求会合并 query、URL 和 fetch，不会为同一页面的多个字段重复抓取。
- FieldPolicyRegistry 已覆盖 Person、Work/Edition、Discipline、Subdiscipline、KnowledgeNode、Topic 与 ReadingPath。每个字段集中保存 SourceClass priority、identity gate、evidence requirement、conflict policy、refresh policy、value schema 和 mutation adapter。
- AuthorityStructuredAdapter 复用 Wikidata、VIAF、LOC 与 OpenAlex。BibliographicStructuredAdapter 复用 Crossref、OpenLibrary、Google Books、OpenAlex、GROBID、SourceRecord 和现有 provider gateway。旧 provider 未被复制。
- WebSearchAdapter 可替换，当前实现 SearXNG JSON adapter，但默认 URL 为空。本阶段没有部署或调用生产 SearXNG。Search snippet 只用于来源发现，不能写 EnrichmentEvidence。
- SafeWebFetcher 会验证初始 URL、redirect 与 canonical URL，并拒绝 localhost、private、loopback、link-local 与 metadata address。timeout、content type、response bytes、extracted text、redirect、rate interval、有限 retry/backoff 和缓存均有硬上限。
- 新增 EnrichmentCandidate 与 EnrichmentEvidence。一个字段值可合并多个 source evidence；不同值保持独立并展示 conflict。Evidence 保存 actual page supporting text、canonical URL、title、domain、retrieved time、HTTP metadata 与 checksum。
- Person identity 至少需要 identifier overlap，或姓名再加日期、机构或作品。纯同名不会继续生成字段候选。KnowledgeRelation 需要两端实体与明确关系词，同页或同句共现本身无效。
- FieldMutationRegistry 已打通 Person identifier/affiliation/name variant、Edition year/publisher/ISBN、Work first publication date、KnowledgeNode alias/discipline/subdiscipline/relation/timeline、Topic discipline 与 ReadingPath item。Interpretive Accept 只创建 pending/reviewable source object。
- Accept 在单事务锁 Candidate 与 authority，重新验证 policy version、identity、evidence、staleness、current value 和 FieldLock。Reject 保留 Evidence。PersonNameVariant 与 KnowledgeNodeAlias 继续通过 authority ChangeEvent 更新 QueryLexicon，服务不直接写 Entry。
- 旧 AuthoritySuggestions 已改为显式按钮与只读 identity discovery，不再直接改 React draft。Scholar、Discipline、Subdiscipline、Topic 和 KnowledgeNode 编辑页接入共享 FieldEnrichmentControl。Work/Edition 保留既有 Metadata Review 兼容路径。
- 新 migration 为 `catalog.0029_field_enrichment`。它只创建 schema/index/constraint，并增加 KnowledgeRelation `extends` 与 `responds_to` choices；没有数据扫描、联网、authority mutation 或 semantic reindex。本阶段没有应用 production migration。
- Task 5 专项 18 项通过。authority、metadata provider、QueryLexicon、scoped search、theory 与 knowledge 相关选择器共 127 项通过。前端 targeted Node 35 项、TypeScript、targeted ESLint 和 Vinext production build 通过。Django check、migration drift、compileall 与 git diff check 通过。只有既有 pypinyin 与 Vite config warning。

Task 5 源码状态为 IMPLEMENTED。真实 Provider 质量、SearXNG 部署、PostgreSQL migration、公网/LAN 管理流程和旧 candidate/provider 路径合并留到 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。

## Task 6 Library AI Runtime and Social-Science RAG

- 已建立 capability-based AI runtime。metadata extraction、Library QA 与 field enrichment optional 各自选择 profile，不再共享一个模型必填条件。SiteSetting 只保存非密钥配置和 endpoint/credential alias，实际 secret 不进入数据库、API、前端、AuditEvent 或日志。
- 现有 AIClient 已统一 generate、stream 与 health check。Library Assistant 的 provider stream 已收敛为命名的 `LibraryAnswerStream`，删除了无语义的兼容 wrapper。显式同 capability fallback 最多一层，provider timeout、auth、rate limit、parse 和 unavailable 有独立错误代码。
- Admin Settings 已接入 profile GET/PUT 与 test API。Profile 变更使用 IsLibraryAdmin、单事务 SiteSetting 写入和 AuditEvent。enabled、provider、model、temperature、tokens、timeout 与 retrieval profile按下一次请求读取；endpoint 和 secret 仍属于部署环境。
- LibraryQuery 已覆盖 exact scholar、exact theory、conceptual、mechanism、comparison、relation、historical timeline、quoted phrase、mixed language 与 general。它保留 original query，记录 resolved follow-up、QueryLexicon revision、public entity anchors、scope 和 retrieval limits。
- Task 4 的 global、works、scholars、disciplines、subdisciplines、theories、topics 与 reading_paths 已成为严格 retrieval scope。公开 entity resolution 固定使用 QueryLexicon public_active。draft authority 不泄漏；空理论或阅读路径 corpus 不会退化为全馆检索。
- LibraryRetrievalService 复用现有 semantic_search。stable 强制 V1；experimental_v2 只允许 admin debug。比较问题使用各对象约束分支与 shared branch；无法可靠解析两个公开实体时不进入模型综合。quoted phrase 强制 stable keyword literal match；其他 entity anchor 最多三个分支。最终 Evidence 有 passage、work、page 和字符预算，并按 document、page/content 与 work 去重。
- LibraryEvidence 与持久化 source 现包含 Page、document ID、passage language、retrieval provenance 和 Reader URL snapshot。SSE 的 answer token 与最终 citation/evidence metadata 分离，source detail 返回加密保存的原文。无效 citation 会移除；有 evidence 但模型没有有效 citation 时，该回答不会被采用。
- 检索失败、有效 evidence 为零、比较覆盖不足或原句未找到时，使用确定性说明，不调用模型常识。馆藏文本被标为不可信数据，历史回答只作会话语境。Ask 不调用 web enrichment，也不创建 authority 或 Candidate。
- Explore Ask 改用 Auth P0 的 cookie-first bootstrap，区分 401、403、429、temporary/provider error。Reader、Scholar、KnowledgeNode 与 Topic 页面使用同一 Ask link 和 scope 参数。普通 reader 不能请求 debug 或 experimental_v2。
- 新 migration 为 `reading.0005_library_ai_runtime_rag`，只 AddField，不含 RunPython/RunSQL、AI 调用、扫描、authority mutation 或 semantic reindex。本阶段没有连接生产或应用 migration。
- Task 6 核心后端 35 项通过；包含 AI runtime、Library RAG、Auth、Field Enrichment、metadata AI filter 与 Task 2A 的较宽选择器 89 项通过。前端 Task 6 Node 4 项与 Auth session 13 项通过，TypeScript、targeted ESLint 和 Vinext production build 通过。Django check、makemigrations drift、compileall 与 git diff check 通过。只有既有 pypinyin 弃用和 Vite config warning。
- 本阶段没有调用真实模型，也没有 production model quality、citation fidelity 或真实馆藏 latency 结论。没有连接生产、应用 migration、启用公开 V2、修改 semantic ranking 或开始 Task 2B-1。

## FINAL INTEGRATED ACCEPTANCE 2026-08-19 本地收敛增量

- Auth 客户端已删除 `getStoredAccessToken()`，所有原有调用迁移到 `getServerSessionCredential()`。cookie 始终交给服务器验证，`library_session_active` 只保留 UI hint。Auth/Ask 前端 17 项回归通过。
- Candidate 与 Enrichment 表保持业务独立；新增 `/api/catalog/admin/candidate-review/` 聚合 envelope、按 domain 路由的事务 decision endpoint 和 Next Admin `/admin/candidates` 共享证据/状态审核页面。Django Admin 仍是 maintenance fallback，页面不会自动 Accept。
- 删除无消费者的 Ask `_scope_filters`、`retrieve_library_sources`、旧 `/api/catalog/library-question/` route/view，以及 mixed `/api/catalog/theory-system/search/` 和 `searchTheorySystem()`。理论搜索统一使用 `context=theories`。
- 新增 `reading.0006_final_scope_normalization`，只规范历史 conversation 的 `AssistMode.OFF` 与旧 scope 形态，不联网、不调用模型、不改 authority 或索引；当前未应用生产。
- Semantic 写入现在要求唯一 active `SemanticIndexVersion`；历史 null-version job 无法安全回填时以 `INDEX_VERSION_REQUIRED` 失败，离线模型缺失以 `MODEL_UNAVAILABLE` 失败并保留 SemanticChunk。protected asset cache 与 chunk assembly SHA 修复的定向测试通过。
- 生产 SSH 只读身份仍未恢复，真实 PostgreSQL/NAS/容器/Provider/模型和最终 migration rehearsal 仍为待核实。目标主机认证恢复前不执行生产 migration、部署、active UID 切换或公开 V2。

Task 6 源码状态为 IMPLEMENTED。模型选择、真实回答质量、最终 retrieval profile、旧兼容入口删除、数据库 migration 和 production cutover 留到 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。

## FINAL INTEGRATED ACCEPTANCE 当前记录

- Auth 客户端已把所有原先 `getStoredAccessToken()` 的调用迁移到 `getServerSessionCredential()`。HttpOnly cookie 始终交给服务器验证，`library_session_active` 仅保留为 UI hint；401、403、5xx 与网络错误仍保持分离。
- Ask 旧的 `_scope_filters`、`retrieve_library_sources` 已删除，provider stream 改名为 `LibraryAnswerStream`/`stream_library_answer`。无消费者的固定 503 `/api/catalog/library-question/` route、view 和 import 已删除。
- SemanticIndexJob 创建和直接写入现在要求一个明确或唯一可解析的 active `SemanticIndexVersion`。历史 null-version job 在无法证明唯一 active version 时以 `INDEX_VERSION_REQUIRED` 失败；离线模型缺失以 `MODEL_UNAVAILABLE` 失败并保留已生成 SemanticChunk。
- 上传组装继续使用有界流，并在组装时计算 SHA-256；registered、restricted、private PDF 响应使用 `private, no-store, no-transform` 和 `Vary: Cookie`，公开资源仍使用短期 public cache。
- 本轮定向验证：Auth/Ask 前端 17 项通过；SemanticIndexVersion guard 2 项通过；SemanticIndex/processing 相关 6 项通过；chunk upload、registered asset 与 ingestion integration 相关测试分别通过。仅有既有 pypinyin 弃用警告。
- 生产 SSH 只读门槛仍未恢复，真实数据库、NAS、当前容器、真实模型、真实 Provider、统一 migration rehearsal 和最终 cutover 尚未声称通过。目标主机认证恢复前不执行生产 migration、部署、活动 UID 切换或公开 V2。

### 2026-08-19 本地最终回归与当前判定

- 最终后端回归命令 `python -m pytest -q --reuse-db --disable-warnings` 退出码为 0。标记为 PostgreSQL、Redis、Celery 的集成用例仍按环境条件跳过，不替代生产验收。
- Semantic enqueue 在缺少唯一 active version 时记录独立 `INDEX_VERSION_REQUIRED` 失败，不让 upload/publication 失败；replacement 只在新 Asset 激活后排队一次。新增模型缺失和候选审核聚合 endpoint 回归通过。
- Django check、`makemigrations --check --dry-run`、compileall、TypeScript、Vinext build、前端 51 项 Node 回归加 13 项 session 回归、ESLint 和 `git diff --check` 通过。当前工作站没有 Docker 或 PostgreSQL 16 runtime，SSH 临时 RSA 身份仍被拒绝。
- 2.7 新增的 Projection Refresh 已接入现有 `ProcessingJob` 与 Celery dispatch/recovery，按单个 Work、Edition、Asset 或 authority 目标幂等派发，不扫描全馆。
- FINAL INTEGRATED ACCEPTANCE 与 PUBLIC CUTOVER 当前仍为 `BLOCKED`。本轮未执行 production migration、应用部署、active UID switch、public V2 enable、authority publish 或 Candidate accept。

### 2026-08-19 版本 2.7 最终后台与持续增长源码收敛

- 当前源码版本更新为 `2.7`。新增统一 capability snapshot 与 `/api/auth/capabilities/`，前端后台导航按 Dashboard、Library、Knowledge、Review、Search & Intelligence、Operations、Administration 组织。Django Admin 继续作为低层维护入口。
- 新增 catalog migration `0030_knowledgenodealias_is_verified_and_more` 与 ingestion migration `0012_alter_processingjob_job_type`。迁移只创建 UnknownEntityObservation、NewAuthorityCandidate、KnowledgeNodeAlias 来源字段和 ProcessingJob 类型，不联网、不扫描 PDF、不生成候选、不改 authority 或 semantic index。
- 新增 Unknown Entity workflow、Knowledge Workspace、QueryLexicon Workspace、Term Inspector、Projection Status、System Status Center 和 Intake Workspace API/页面。Candidate review envelope 增加 metadata、theory 和 new authority 的只读适配，接受动作仍按各自 source-of-truth 路由。
- 公开 QueryLexicon scope、draft authority 边界、Candidate first、Evidence provenance 和 stable retrieval 默认值保持不变。没有生产 migration、生产部署、semantic reindex、V2 切换、自动发布或自动 Accept。
- 本轮源码检查：`compileall`、`manage.py check`、完整后端回归、前端回归、TypeScript、ESLint、Vinext build、`makemigrations --check --dry-run` 和 `git diff --check` 均已通过。生产迁移与部署仍待目标基础设施可达后执行。

### 2026-08-19 2.7 本地门槛刷新与生产可达性复核

- 2.7 追加的 capability 分层已通过后端回归。普通 Admin 只读查看 QueryLexicon 与 Semantic Index；reconcile、索引激活和破坏性维护仍由对应 manage capability 保护，有限 retry/resume 使用 `can_retry_jobs`。
- System Status Center 现在读取现有 Celery broker、control inventory、ingestion heartbeat、Beat heartbeat 推断、实际 semantic runtime embedding 配置和 Provider configured/unknown 状态。旧 `/admin/system-health` 保留兼容 route，已从主导航移除。
- 后端 `pytest -q --reuse-db --disable-warnings` 退出码 0，共收集 547 项，9 项因环境条件跳过。前端 `npm test` 通过 63 项通用回归和 17 项 Auth/Scoped Search 回归。`manage.py check`、`makemigrations --check --dry-run`、compileall、TypeScript、ESLint、Vinext build 和 `git diff --check` 均通过。
- 公网只读检查仍为旧版本：`/api/ready/` 与 `/api/health/` 均为 HTTP 200，版本 `2.6.1`，`pending_migrations=0`。目标 SSH 端口可达，但服务器明确拒绝临时 RSA 公钥 `SHA256:IHJjqWWKNJBfSQk+LHcwxXPssKxrkC6Pi9M726TuOUg`，因此没有执行 fresh backup、production migration、统一镜像发布、QueryLexicon reconciliation 或 semantic cutover。
- 当前判定保持 `PUBLIC CUTOVER = BLOCKED`，唯一阻塞为生产基础设施 SSH 认证未恢复。源码版本仍为 `2.7`，未把本地通过写成公网部署。

### 2026-08-19 2.7 production cutover completed

- SSH 与无交互 sudo 已恢复。统一 release commit 为 `7cd68d30776c0c652e080d147959a3183a92b71b`。API、Worker、Ingestion Worker、Beat 和 Web 均使用 2.7 image family；API digest 为 `sha256:01fd1936f981c297efc38c86e026a7b41d4b5d50b826a273c7f9807c8bb0a765`，Web digest 为 `sha256:2a2aff9ad9f427a78989bc3b79e546b9717d342e4dbbef43783f2be92b87611a`。
- Fresh BackupJob `85384c9d-db1b-424b-8ff5-a1d61c7f77b5` completed。归档 9,988,531 bytes，SHA-256 `9a35ada044ae56c215f1f6bf63750a7d1842480c3e077152d67888ef712091b9`，database.dump SHA-256 `3d18d2b3766347ec34226ea33ef48d72a799b9673295423b6ed0b29b08d73d4e`，PostgreSQL server 16.14，pg_dump/pg_restore 16.15。
- Production migration 已应用：catalog 0029/0030、ingestion 0012、reading 0005/0006。核心计数保持 5 Work、5 Edition、10 Asset、1,989 Page、3,881 SemanticChunk、6 Person、2 KnowledgeNode、1 Topic。
- QueryLexicon dry-run 无 anomaly。正式 reconciliation 保持 revision 1、active generation `af302b64-1b3f-447d-88ca-5ed505bc87e9`、active 69 entries，public 23、admin 61；同内容候选 generation 被标为 discarded，pending/dead-letter event 为 0。
- Clean semantic UID `semantic_passages_20260818210650_4cf87bc9` 已通过 consistency audit 并激活。DB ready chunks 与 Meilisearch 均为 3,005，missing、extra、mismatched document_id 和 schema drift 均为 0。旧 UID `semantic_passages_20260809143729_4cf87bc9` 保留为 retired 回退版本。
- 3 个真实 Asset 的 candidate extraction jobs 成功，Candidate/Evidence 为 0，revision 未变化。UnknownEntityObservation 807 条、NewAuthorityCandidate 781 条均保持 pending，没有自动创建或发布 Person、KnowledgeNode、Topic。
- 公网 smoke 通过：ready/health 版本 2.7，首页 200，V1 semantic `search_version=v1`、`fallback_used=false`，PDF Range 返回 206 和 `application/pdf`。Celery、Redis、Meilisearch、API、Worker、Ingestion Worker、Beat、Edge healthy；应用 RestartCount 为 0；日志无 schema/exception/secret pattern。
- AI 状态为 `NOT_CONFIGURED`，general web 为 `NOT_CONFIGURED`，本地 embedding 为 available，Ask retrieval profile 为 stable，公开 V2 仍为 false。
- 当前状态：`PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。登录后的 Admin、Reader Center、Candidate Review、Ask Library 和长期公网观察留给用户人工验证。

### 2026-08-19 2.7 post-cutover usability and reader configuration pass

- Ask Library 增加 `ReaderAIConnection` 读者自助配置。连接地址经过公开地址和 SSRF 校验，API Key 使用既有 private-data Fernet 加密，响应、日志、Local Storage 和会话正文均不包含密钥。注册读者仍必须登录，检索范围和证据门槛不变；服务器端 Library QA profile 只作为可选回退与治理入口。
- 后台会话刷新改为可区分的后台探测与显式跨标签会话事件。后台 5xx、网络错误或单次刷新 401 不会卸载正在上传的工作区；跨标签 logout、明确 403 和下一次受保护动作仍由服务器决定。上传拖拽增加键盘入口、拖拽深度计数、类型提示和可恢复队列反馈。
- Reader toolbar 修复带纸本页码控件的隐式网格溢出，OCR 状态条改为正文流内的可换行提示，不再覆盖 PDF 内容。
- Candidate Review 明确为跨领域审核队列，不等同于自更新词典。QueryLexicon 页面改为派生词典说明；System Status、Intake、Knowledge、Semantic Index、System Health 和后台导航补充规范中文和可展开的结构化详情。候选 API 增加按类型准确计数和截断提示，联网来源错误显示 provider 分类、请求编号和部分结果，不再把 provider failure 伪装成空候选。
- Intake Workspace 增加失败重试和单目标 Projection Refresh 入口，仍复用现有 ProcessingJob/Celery，不扫描全馆。新增 `reading.0007_reader_ai_connection` 仅创建读者连接表和索引，不联网、不生成候选、不改 authority 或 semantic index。
- 本地最终门槛：后端全量 pytest 退出码 0；Django check、migration drift、compileall、TypeScript、Vinext build、ESLint、前端完整 68+19 项回归和 `git diff --check` 通过。`reading.0007` 已在 fresh backup 和 migration plan 门槛后应用生产。
- 第一次部署后匿名浏览器 smoke 发现无 refresh Cookie 时 token refresh 返回 400，前端误显示“认证服务暂时不可用”。客户端现将该 endpoint 的 400 与 401 都解释为没有可恢复会话，正常进入登录提示；真实 5xx、403 和网络错误仍保留会话并显示对应状态。新增回归已通过。
- Reader 公网 smoke 进一步发现匿名访客会请求批注、书签、进度和历史四类私有接口。Reader 现复用统一 session bootstrap，只在确认登录后读取或写入私人记录；退出登录后立即清理页面内的私人批注与书签。公开 PDF、引用、搜索和下载不受影响。
- 生产权威候选 smoke 复现 VIAF 的合法 `result: null` 响应。旧解析器因此抛出 TypeError，并让单一 Provider 失败清空本地和其他来源结果。Provider 列表字段现统一做类型规范化，并在每个来源边界隔离解析失败；本地候选和其他成功来源继续返回，失败来源进入 warning/request-id 诊断。新增两项回归通过。
- 字段补全第一次以中文规范名查询外部 authority，若没有任何结构化记录，现在会有界地再查一次已确认的原文名。只使用 canonical/original/verified 名称，最多两个 query，不使用生成拼音或低信任别名。该回退让中文学者可使用 VIAF 等原文名来源，同时保持同名身份和证据门槛。
- 学者、学科、子学科、主题和理论节点编辑器的只读身份发现现在优先使用管理员已填写的原文/外文规范名，并在控件内显示实际检索词。未保存的原名只用于发现候选，不会自动变成 authority 或字段值；Field Enrichment 仍要求先保存并通过身份门槛。
- VIAF Person adapter 现在只接受 personal heading，不再把 uniform-title work 当成人物。若 personal heading 明确含有合法生卒年区间，会保留规范姓名并把日期作为身份证据。双语规范名最多各查一次，所有 observation 仍逐条通过 Person identity gate。

### 2026-08-19 post-cutover production result

- Fresh BackupJob `14a78648-8b26-44c0-a450-24acc3d594f7` completed。归档大小 10,533,832 bytes，SHA-256 `e47cd7ed75b5df09e0eb47e5652ee5d8d3353fadd634e75e9ee6be39bc62950e`，内部 database.dump SHA-256 `ce5e27f532e60dcd6780b873be76bb9451214b12f04af21c2a7ef8a9166d0a28`。
- 新镜像 migration plan 只有 `reading.0007_reader_ai_connection`。Worker 和 Beat 在空队列窗口停止，migration 用时 6 秒并通过 Django check。最终 API、Worker、Ingestion Worker、Beat 和 Web 使用统一 `2.7-7294225` image family，Edge 已刷新。
- 核心计数仍为 Work 5、Edition 5、Asset 10、Page 1,989、SemanticChunk 3,881、Person 6、KnowledgeNode 2。活动 UID 仍为 `semantic_passages_20260818210650_4cf87bc9`，document count 3,005；QueryLexicon revision 1、generation `af302b64-1b3f-447d-88ca-5ed505bc87e9` 均未改变。
- 真实 Provider smoke 中，英文 `Emile Durkheim` 返回 6 条 VIAF 结果；Wikidata timeout 与未配置 OpenAlex 只形成 partial warning。布迪厄字段核对生成 1 条 pending external-identifier candidate、1 条 Evidence，identity confirmed。没有自动 Accept 或 authority mutation。
- 五条真实 V1/V2 对照查询均返回 V2 结果，engine 为 `v2_hybrid` 且 fallback false。按用户明确授权启用公开 V2 后，公网两条 smoke 仍为 V2、fallback false。没有 semantic reindex；Ask retrieval 继续 stable。
