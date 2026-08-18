# Library AI Runtime and RAG Inventory

更新日期为 2026-08-18。本文件记录 Task 6 修改前的真实源码状态，只用于架构审计，不是生产模型或真实问答验收记录。

## AI provider and settings

| 项目 | 当前实现 | 结构问题 |
| --- | --- | --- |
| Provider abstraction | `ingestion.services.ai_client.AIClient` 支持 none、Ollama、vLLM、OpenAI-compatible，提供 JSON generation 与 health check | Library streaming 在 reading 中另写一套 HTTP；接口并未统一为 generate / stream / health check |
| Settings source | `AI_PROVIDER`、`AI_BASE_URL`、`AI_API_KEY`、模型名、timeout 和 limits 全来自 environment | 没有 capability profile，也没有 Admin 动态配置层 |
| Metadata model | `AI_METADATA_MODEL`，AIClient 默认且强制验证 | 任一启用的 Provider 都必须先配置 metadata model |
| Library model | `AI_LIBRARY_MODEL`，默认回退到 `AI_METADATA_MODEL` | Library QA 被 metadata model 的必填校验和默认值绑定 |
| Classifier / vision | `AI_CLASSIFIER_MODEL`、`AI_VISION_MODEL` | 只有名称字段，没有统一 capability policy |
| Secret | `AI_API_KEY` 只在服务器环境读取，并放入 Authorization header | 安全边界正确，应继续保持，不写普通数据库或前端 |
| Dynamic settings precedent | `SiteSetting` 已用于 semantic runtime、OCR runtime 和网站设置，写入由 IsLibraryAdmin 保护并产生 AuditEvent | 可复用为非 secret AI runtime profile，不必再建一套 settings table |

## Current prompts

| Prompt | 位置 | 当前边界 |
| --- | --- | --- |
| Metadata candidate extraction | `ingestion/services/ai_metadata.py` inline constant | 只生成候选，有 JSON schema 与 PDF evidence |
| Candidate reconciliation | `ingestion/services/ai_candidate_filter.py` inline constant | 只比较白名单候选，不允许 persistence |
| Authority candidate filter | `catalog/services/authority_suggestions.py` inline constant | 只排序 provider candidates，不允许新 ID |
| Library answer | `reading/library_assistant.py` inline system string | 已要求 citation、证据不足和 corpus prompt-injection 防护，但 query planning、answer synthesis、citation rules 没有分离版本 |

## Current Ask Library path

1. Reader 创建 `LibraryConversation`，保存 assist mode 与任意 JSON scope。
2. Stream endpoint 接收 question 和 assist mode。
3. `_scope_filters()` 从 scope 中挑少数旧 key，未知 key 被静默丢弃。
4. `semantic_search()` 默认按公开 feature flag选择 V1/V2；当前生产 flag 为 V1。
5. 最多保留 8 条、每书 2 条 passage，总 context 约 9,000 字符。
6. 直接在 reading 中调用 Ollama 或 OpenAI-compatible stream。
7. `[S1]` 等 citation 在流式输出时按本次 source key 白名单过滤。
8. Answer、message、source 和 quote 都持久化，私人文本使用 Fernet 加密。

## Current API and permissions

| API | 权限 | 行为 |
| --- | --- | --- |
| `/api/reading/library-conversations/` | IsAuthenticated | 用户只见自己的会话 |
| `.../messages/stream/` | IsAuthenticated + owner | SSE meta、delta、sources、done、error |
| `/api/reading/library-messages/<id>/sources/` | IsAuthenticated + owner | 只返回模型实际引用的来源 |
| source detail | IsAuthenticated + owner | 返回解密摘录与 Reader URL；来源下架后不返回 quote |
| cancel | IsAuthenticated + owner | 协作式取消，不强杀 Worker |
| assistant status | IsAuthenticated | 返回可用状态，隐藏内部 endpoint 与 secret |
| Admin runtime profile | 不存在 | 当前只能改部署环境 |

## Current session and frontend behavior

- Conversation 与 message 私有，history assistant answer 会进入下一轮 prompt，但旧 citation key 会被删除。
- 前端 Explore Ask 自己检查 local token，没有复用 Auth P0 的 cookie-first bootstrap。
- local hint 缺失会被误判未登录。
- 401 与 403 都被当成 unauthenticated；provider 5xx只显示一般失败。
- UI 提供 auto、on、off。off 会跳过馆藏检索并允许模型常识回答，与“Ask Library 只用馆藏”文案冲突。
- Reader、Scholar、Theory、Topic 页面没有共享 Ask scope link。

## Current evidence and citation structure

`LibraryMessageSource` 已保存 Work、Edition、Asset、chunk ID、题名、作者、PDF 页、印刷页、章节、加密 quote 和 cited 标记。它缺少 Page FK/ID、passage language、retrieval branch/provenance、reader URL snapshot，以及 semantic index、QueryLexicon revision 和 runtime profile snapshot。

Citation 过滤的现有基础是正确的。

- corpus 中伪造的 `[S8]` 会先被替换。
- 历史回答中的 citation key 不会进入新一轮。
- 模型输出中不在本次 evidence set 的 source key 会被删除。
- 最终只有实际引用来源标为 cited。

缺口是 API 没有清楚分离 citation 与全部 retrieved evidence，也没有在模型完全未引用 evidence 时阻止无引用回答。

## Current scope mismatch

Task 4 的 contexts 是 works、scholars、disciplines、subdisciplines、theories、topics、reading_paths 和 global。Reading RAG 当前只接受 work_id、author、theory_school、topic 等旧 singular key。UI 提交 theories 或 topics 时会被静默移除，实际检索扩大为 whole library。

## Task 6 consolidation decisions

- 保留现有 LibraryConversation、LibraryMessage、SSE、encryption、source availability 和 Reader。
- 使用 `SiteSetting(key="ai_runtime_profiles")` 保存非 secret capability profiles，AuditEvent 保存变更；secret 与 endpoint继续通过环境 alias 解析。
- 扩展现有 AIClient 的 capability-aware config、generate、stream 与 health check，不新增 provider HTTP stack。
- 新增 LibraryQuery、scope normalization、LibraryRetrievalService 和 LibraryEvidence，但底层只调用现有 semantic_search V1/V2。
- stable retrieval 强制 V1；experimental_v2 只允许 Admin/debug 显式使用。
- 默认 public QueryLexicon scope 为 public_active，不建立 RAG translation dictionary。
- AssistMode.OFF 保留为历史枚举兼容，但新问题不再允许无馆藏模型回答。
- 最终综合验收再决定是否删除 OFF choice、旧 scope key 和旧 inline prompt compatibility wrapper。

## Task 6 implemented architecture

修改后的运行配置由 `common.ai_runtime` 统一解析。三个 capability 都有独立 active profile；Library QA 环境默认不再回退到 metadata model。数据库 profile 只保存非密钥参数与 alias，普通 reader status 不返回 alias、endpoint 或 credential。Admin API 使用 IsLibraryAdmin，保存时生成不含 secret 的 AuditEvent。

`ingestion.services.ai_client.AIClient` 现在是唯一 provider HTTP adapter。Metadata 默认 capability 保持原调用兼容；Library QA 使用自己的模型、temperature、output tokens、timeout 和 input budget。Ollama 与 OpenAI-compatible stream 均解析为统一文本 iterator，provider errors 使用稳定分类。Fallback 只能是已配置的一层同 capability profile。

`reading.library_query.LibraryQuery` 保存 original、normalized 与 follow-up resolved query、语言、社会科学 query type、规范 scope、entity anchors、conversation context、retrieval limits、retrieval profile 和 QueryLexicon revision。QueryLexicon 始终以 public_active 解析公开 Ask。scope 不支持、对象不可公开或 scoped request 缺 ID 时直接返回错误。

`reading.library_retrieval.LibraryRetrievalService` 只调用现有 semantic_search。stable 固定 V1，experimental_v2 有后端 admin/debug 权限门。Entity anchors 映射到 Task 4 scoped entities并和页面 scope 合并；空 domain 带显式 empty 标记，不会被底层的空列表判断扩大为全馆。Comparison、quoted phrase 与一般 entity branches 都有硬上限。比较问题少于两个可靠公开 entity anchor 时明确判定 evidence 不足，不让 shared passage 进入模型综合。Evidence selection 按 document、page/content、per-work、passage 和字符 budget 收敛。

LibraryMessageSource 新增 Page FK、document ID、passage language、retrieval provenance 和 reader URL snapshot。SSE sources event 与 sources API 同时表达 cited sources 与本轮所有 evidence。公开资产关系会在 prompt 前和 persistence 时复核。复核后没有有效 evidence 时不调用模型；模型没有引用任何有效 source 时，最终答案替换为可解释的证据不足答复。

Frontend Ask 使用 shared session bootstrap，不再以 localStorage hint 为登录门槛。Reader、Scholar、KnowledgeNode 与 Topic 通过 `AskLibraryLink` 进入同一个 Explore Ask consumer。URL 带规范 context、entity IDs 和可选 Asset ID，Reader 问答可严格限定当前 PDF 所属 Work。

## Final consolidation candidates

- `LibraryConversation.AssistMode.OFF` 只为历史数据库兼容保留，新 API 已拒绝关闭检索。最终 migration 可以评估删除枚举值和旧 UI 数据。
- `_scope_filters()`、`retrieve_library_sources()` 与 `_provider_stream()` 目前是 Python compatibility wrapper。确认没有外部调用者后可移除。
- `work_id`、`author`、`theory_school`、`topic` 等 singular scope aliases 继续兼容旧会话。最终数据迁移后可只保留 Task 4 plural contract。
- `/api/catalog/library-question/` 仍固定 503。确认没有外部客户端后可删除旧 route，而不是再次实现。
- sources API 暂时同时保留旧 `count/results` citation envelope 与新 `evidence_count/evidence`。最终前端全部切换后可收敛响应格式。
- 环境默认 profile 是无数据库配置时的安全 bootstrap，不应与 SiteSetting 再复制成另一套可编辑设置。最终验收只需决定部署环境 alias 命名规范。
