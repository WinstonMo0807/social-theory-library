# 当前问题

更新日期为 2026-08-16。状态依据当前源码、已有测试和历史交接记录。`待核实` 表示本轮没有运行对应环境或生产验收。

## STL-001 bilingual viewpoint retrieval

状态为部分实现，跨语言质量待核实。

默认语义模型为多语种 MiniLM，查询切词同时处理拉丁字符和中文，观点检索也支持语言过滤。现有测试能证明同语种查询的基础行为，但没有发现中文问题检索英文材料、英文问题检索中文材料的专项回归，也没有显式翻译模块。关键词降级不具备可靠的跨语言能力。

下一步需要建立人工判断的中英双向评估集，分别测量召回、排序、页码回链和降级结果。任何模型切换都应建立新索引版本，不覆盖当前活动索引。

证据位置包括 `api/config/settings.py`、`api/catalog/services/semantic_search.py`、`api/catalog/services/semantic_search_v2.py` 和 `docs/search-evaluation.md`。

## STL-002 field-specific web enrichment

状态为部分实现，单字段定向请求尚未实现。

系统已有字段级候选、来源证据、采用、拒绝和人工锁。Provider 会根据 DOI、ISBN、文献类型和题名选择 Crossref、OpenAlex、Open Library、Google Books 或 GROBID。当前刷新端点和后台任务仍以整条 UploadItem 或 edition 为单位，没有接收目标字段参数。

下一步需要定义哪些字段允许独立补充，为每个字段配置来源优先级、超时、限流和证据要求，并保证失败只影响目标字段。真实 Provider 的返回质量和可用性仍需在授权网络与 API Key 条件下验证。

证据位置包括 `api/ingestion/services/provider_gateway.py`、`api/ingestion/services/candidate_store.py`、`api/ingestion/views.py` 和 `web/components/metadata-review.tsx`。

## STL-003 library RAG

状态为源码已接入，生产登录流程待核实。

新实现位于 `api/reading`，支持私人会话、加密消息、语义检索、公开资产复核、引用来源白名单、SSE 输出、取消和 Reader 回链。它依赖 `AI_PROVIDER`、`AI_LIBRARY_MODEL`、语义检索和 `PRIVATE_DATA_ENCRYPTION_KEY`。旧接口 `/api/catalog/library-question/` 固定返回 503，不是当前 RAG 入口。

下一步需要验证登录用户的完整问答流程、访问级别过滤、引用忠实度、模型失败降级、取消、并发限制和私人数据隔离。当前 scoped search 缺口会影响 RAG 范围限定，应先处理 STL-004。

证据位置包括 `api/reading/library_assistant.py`、`api/reading/library_views.py`、`api/reading/models.py`、`api/reading/urls.py`、`api/tests/test_library_assistant.py` 和 `web/components/explore-ask-client.tsx`。

## STL-004 scoped search

状态为存在明确源码缺口。

公共观点检索支持按 `work_id` 限定。书库问答也保存 `LibraryConversation.scope`，但当前 `_scope_filters()` 产生 `work_id`、`document_type`、`author` 等单数键，语义检索读取的却是 `work_ids`、`document_types`、`authors` 等复数键。前端创建会话时也没有提交或编辑 scope。

下一步需要统一 scope schema，为作品、文献类型、作者、理论、主题、年份和概念建立端到端测试，再增加前端范围选择。修复不得放宽访问状态过滤。

证据位置包括 `api/reading/models.py`、`api/reading/serializers.py`、`api/reading/library_assistant.py`、`api/catalog/services/semantic_search.py` 和 `web/components/explore-ask-client.tsx`。

## STL-005 PDF metadata / FOR UPDATE failure

状态为历史问题已在源码修复，当前 PostgreSQL 回归待核实。

历史错误为 PostgreSQL 不允许对可空外连接一侧执行 `FOR UPDATE`。当前查询使用 `select_for_update(of=("self",))`，只锁 `UploadItem` 主表。已有测试断言该查询属性。

下一步是在真实 PostgreSQL 上重跑元数据读取、保存、发布前检查和并发编辑回归。不得以删除事务锁或捕获后忽略数据库异常作为修复方式。

证据位置包括 `api/ingestion/views.py`、`api/tests/test_reader_cover_semantic.py` 和 `docs/release-notes-2.2.2.md`。

## STL-006 auth initialization failure

状态为源码风险已识别，浏览器复现待核实。

后端能够直接从 HttpOnly JWT Cookie 认证。前端只有在 localStorage 存在 `library_session_active` 时才返回 cookie session 标记。管理后台缺少该标记时会直接转到登录页，没有先用现有 Cookie 请求用户状态。Cookie 仍有效但 localStorage 被清理或不可用时，可能被误判为未登录。

下一步需要增加 Cookie 存在但 session hint 缺失的启动测试，并用真实浏览器验证后台和账户页面。修复必须保留鉴权、Cookie 安全属性和 401 处理，不得通过取消登录检查处理。

证据位置包括 `api/accounts/authentication.py`、`api/accounts/cookies.py`、`web/lib/api.ts`、`web/components/admin-shell.tsx` 和 `web/tests/runtime-api.test.mjs`。

## STL-007 resumable large PDF upload

状态为核心续传已实现，跨设备与完整性能力仍有限。

后端已有分片状态查询、原子分片写入、manifest 冲突检查、原子合并、大小与 PDF 头校验。前端使用 2 MiB 分片、三次重试、已接收分片跳过和 localStorage 恢复。现有恢复信息依赖同一浏览器，换设备或清理 localStorage 后不能继续。当前也没有逐分片哈希。

下一步需要评估服务端可恢复会话、过期清理、逐分片完整性、跨浏览器恢复和超大文件的公网超时。验收应使用隔离测试 PDF，不上传馆藏原件，也不能把历史小样本结果写成当前大文件生产验收。

证据位置包括 `api/ingestion/views.py`、`api/ingestion/urls.py`、`api/tests/test_admin_configuration.py`、`web/components/admin-upload.tsx` 和 `web/tests/upload-metrics.test.mjs`。
