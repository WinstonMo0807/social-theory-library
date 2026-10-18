# STL 4.0 当前接口契约

## 2026-10-18 笔记授权与私人来源

- 笔记新增服务端筛选/计数、origin_note/source_summaries、usage GET/POST、revision删除和研究memory_reminders。实际内容/类型/来源变化撤销旧范围；确认不等于授权。完整字段见[CONFIRMED_NOTES_20261018.md](CONFIRMED_NOTES_20261018.md)。
- 私人来源使用citation-sources集合/原件/文字/OCR/命令接口；稿件manuscript分页、private_source_ids、sources和match_private命令接入真实来源。来源ID/generation/hash/覆盖断点独立校验，公开EvidenceReference不混用。详见[CITATION_PRIVATE_SOURCES_20261018.md](CITATION_PRIVATE_SOURCES_20261018.md)。
- 前后端及OpenAPI同步。0010迁移只编写，未执行；数据/权限/设备负载与视觉验收仍待核实。

更新时间：2026-10-18。当前接口以本文件、相关单元接入记录、实际源码和生成schema为准。`docs/stl-4.0/API_CONTRACT.md`只保留历史追溯，不再作为独立主线；本文不代表全站验收通过。

## 2026-10-18 稿件版本与目录校准

- 稿件版本新增本人`GET/POST /reading/citation-audits/{id}/versions/`，POST使用multipart与request_id、expected_revision、check_changed_only。每版独立加密保存，严格增量比较与恢复时来源复核；详细字段及边界见[CITATION_VERSIONS_20261018.md](CITATION_VERSIONS_20261018.md)。
- 目录沿`/catalog/admin/assets/{id}/outline/`接入当前文件摘要、候选来源及历史；edit新增base_revision_id、逐节点calibration_status和clear_position。保存候选、明确采用、历史恢复分别执行；详细契约见[OUTLINE_CALIBRATION_20261018.md](OUTLINE_CALIBRATION_20261018.md)。
- 前后端类型与OpenAPI已同步。两项均不新增数据库表/迁移，不连接生产，不启动检索质量评测；运行与视觉验收仍待统一阶段。

## U01 公共首页聚合

`GET /api/catalog/home/`

- 认证：`AllowAny`，接口不读取登录用户身份；访客、读者和工作人员得到相同的公开聚合。
- 缓存：响应 `Cache-Control: no-store`。首页内容来自当前公开数据，不能由浏览器或服务端把旧私有结果复用给另一用户。
- 成功：HTTP `200`。所有区域成功且至少一个内容区域有公开内容时 `status=ready`；空馆藏或没有公开策划时仍返回 `200`，并用 `status=empty` 和分区状态说明业务空态。
- 局部故障：HTTP `200`、顶层 `status=partial`。故障区域 `sections.<name>.status=unavailable`、`count=null`，其余区域仍可展示；不得把故障伪装为 `empty`。
- 全部区域故障：HTTP `503`、顶层 `status=unavailable`。响应仍保持同一 JSON 形状，区域消息只给可行动的公开提示，不回传内部异常。

顶层响应：

```json
{
  "schema_version": "4.0",
  "visibility": "public",
  "status": "ready|empty|partial|unavailable",
  "config": "SiteConfig|null",
  "works": "WorkCard[]",
  "random_works": "WorkCard[]",
  "scholars": "ScholarProfile[]",
  "topics": "Topic[]",
  "issues": "RecommendationIssue[]",
  "issue": "RecommendationIssue|null",
  "issue_count": "integer|null",
  "hot_searches": "string[]",
  "sections": "HomeSections"
}
```

`HomeSections` 的每个区域都返回 `{status, source, count, message}`：

| 区域 | 数量/来源 | 公开边界 |
|---|---|---|
| `works` | 最近公开馆藏，最多12项 | 只经过当前正式公开版本和可读资格 |
| `random_works` | 首页随机/推荐馆藏，最多4项 | 先读当前公开推荐快照，再以公开馆藏补足 |
| `scholars` | 当前已发布且人物已核验的学者，最多6项 | 未核验人物不会因推荐快照进入首页 |
| `topics` | 已发布主题，最多5项 | 关系计数只统计当前公开作品及已批准关系 |
| `issues` | 当前公开策划期，最多4项 | 只读已发布修订；未来排期不展示 |
| `issue` | `issues[0]` 或 `null` | 仅为首页首个策划期的同一对象，不复制另一套身份 |
| `issue_count` | 当前公开策划期总数 | 数据不可用时为 `null`，不是零 |
| `hot_searches` | 达到匿名聚合阈值且通过敏感信息过滤的查询 | 不读取个人阅读记录；暂时不可用时显示空列表并保留分区故障状态 |
| `config` | 当前公开站点配置或默认配置 | 不返回草稿；配置区域失败时前端可使用已知默认文案并显示状态 |

## 前端映射

- `web/lib/api/home.server.ts` 只调用上述正式聚合；失败不注入示例馆藏，配置允许使用代码内默认文案以保留导航。
- `web/components/public/home-public-view.tsx` 依据 `sections` 显示空态、局部故障和重载入口；卡片、数量、策划署名和封面来自接口，不从终稿图片造数据。
- `web/components/public/home-interactions.tsx` 的“继续阅读”只在当前会话已认证后请求 `/api/reading/progress/`；未登录、切换账号、401 或网络失败不得显示上一位用户的进度。
- 搜索表单只导航到 `/explore?context=global&q=...`；空查询不提交，查询文本不写入私人存储。
- 学者、主题和随机荐读的轮换在已返回的公开数组内完成，不创建推荐策略、不写入快照，也不改变公开排序。

## 相关正式身份和权限

首页卡片只能导航到由现有适配器生成的作品/版本/Reader 身份。首页不暴露物理文件路径、后台草稿、未发布修订或私人笔记。公开阅读、下载、复制和引用继续由对应的正式接口执行；首页聚合本身不授予额外权限。

## 当前验证边界

已完成 Python 目标模块的 `compileall` 与目标首页前端 ESLint；全量 TypeScript 仍被三个与 U01 无关的旧 live 测试隐式 `any` 错误阻断。尚未运行 Django 测试、前端构建、浏览器验收、逐图视觉回归或部署，因此本契约只记录实现和静态检查，不代表 U01 验收通过。

## 支持与反馈入口

`POST /api/catalog/feedback/`

- 认证：`AllowAny`。登录用户只写入当前账号关联；访客不建立账号身份。
- 请求：`category` 为 `content|function|citation|accessibility|other`，`body` 为 4–5000 字符，`contact` 为可选邮箱，`path` 为发生问题的站内路径。
- 成功：`201`，返回反馈 UUID、`submitted` 状态和不包含内部信息的确认文案。表单不会把 PDF、私人笔记或访问令牌提交到反馈记录。
- 失败：沿用统一 JSON 错误响应；字段错误不会伪装成提交成功。
- 持久化：反馈进入 `catalog.PublicFeedback`，默认状态为 `submitted`，按状态和提交时间索引。迁移已写入 `0067_publicfeedback.py`，尚未在当前环境执行数据库迁移。

## 持续研究与证据比较

`/api/reading/research-projects/` 及其 `turns/`、`selections/`、`comparison/` 子资源继续使用同一 owner-only Django API。项目和轮次写入均携带 `expected_revision`；会话动作携带 `request_id`，重复请求返回第一次结果，内容不一致返回409。

- 轮次明确保存 `parent_id` 与 `scope`；scope 可以是已保存范围、当前可用选材的 passages 或全馆 library。取消只改变当前轮次状态，已有 `result_refs`、项目选材和旧轮次不删除；后台读取跨页轮次时沿同一项目权限和分页约束。
- `ResolvedEvidence.reference_id` 是后端生成的稳定身份；跨页 anchors 使用组合身份。每次读回重新检查 owner、公开版本、DocumentRevision、EvidenceSpan、PDF页码和 content_hash。来源撤回或版本变化时保留身份与个人笔记，但不回显旧正文和 Reader URL。
- 比较矩阵 `dimensions` 最多20项、`cells` 最多200项，行是维度，列由 `column_id`（edition/work/asset）标识文献或版本；保存个人 `note` 与引用身份。读时的 evidence_status 为 selected/partial/unavailable/missing。已保存旧格可以保留失效引用，新格只能引用当前选材，不能由服务生成系统判断。
- 研究页和比较页不把模型、索引、generation 或制品身份作为普通读者控件；这些字段只留在诊断/API契约。

## 观点检索深度阶段

`POST /api/catalog/discovery-search/` 与其状态读取接口继续返回同一 Discovery 会话。首屏 `passages` 使用当前已稳定的 QueryLexicon、稀疏/向量融合、mMARCO 初排和来源校验；启用 `STL_DEEP_RETRIEVAL_ENABLED` 后，后台在同一 `generation` 中追加深度阶段，并在首屏完成交接时换发一个受同一代次约束的深度 `task_id`，避免旧 worker 回写。

- `task_progress.deep` 返回 `baseline_ready`、`deep_queued`、`deep_running`、`completed`、`partial` 或 `unavailable`；旧 worker 状态会在序列化边界映射到这些公开状态。
- 深度阶段只读取独立配置的 EG2 768 维索引，最多保留40个候选，最多20个 BGE 深排候选和10个上下文候选；`passages_deep` 保存同一来源身份上的深度排序和相邻证据上下文。
- `completed` 或 `partial` 的深度排序只有在再次通过发布资格、访问权限、DocumentRevision、EvidenceSpan/页码和原文指纹核对后，才会用于首屏 `passages`；深度服务缺失、超时、取消或任务排队失败时继续返回基础结果。
- `retrieval_identity` 只记录实际返回的索引、embedding、reranker 制品和版本。未配置或未加载的模型保持空值，不把 pipeline 版本写成索引代次，不把 mMARCO 冒充 BGE。
- 该契约不提供模型管理或第三步质量评测页面；生产启用需要隔离制品、generation、allowlist 和服务健康证据。

## 2026-10-18 个人阅读计划（R21）

- `POST /api/reading/reading-plans/` 使用幂等 `request_id`。目标无选材时复用 Discovery；显式 EvidenceReference 或公共路径仍沿同一公开修订身份。创建界面可读取本人研究选材，不写入示例书目。
- `PATCH /api/reading/reading-plans/{id}/` 必带 `expected_revision`。支持目标、基础、预算、顺序、状态、笔记、替换、本人估计和明确采纳建议；`preview=true` 只返回计算结果，不保存、不换revision、不排任务。确认预览仍以原revision再次提交，冲突返回409。
- `weekly_minutes` 1–10080 与 `duration_weeks` 1–52 形成总预算，乘积最多100000分钟；也可使用 `budget_minutes` 或原 `time_budget`。修改预算方式清除旧方式的遮蔽字段。`language_preference`最多160字符，只用于导读提示，不声称已做语言硬筛选。
- `use_confirmed_memories`默认false；`confirmed_memory_ids`最多40，仅本人仍confirmed的笔记。保存、执行任务、写回和读取时检查授权和版本；旧候选撤销状态为 `authorization_changed`。未授权时不会查询所有笔记。本人已明确采纳的文字与完成记录作为人工结果保留。
- 完成项保留原材料与位置，不能用同一请求降回pending后替换。替换普通材料时，如果有相关先修关系，必须显式 `remove_related_prerequisites=true`，只移除相关关系并保留原关系记录；其他关系保留。替换项回到pending。
- 条目读回包含实际公开封面、作者、出版年、availability、来源与阅读URL；所有 URL 以当前发布修订核实，整文件 Reader 也绑定revision。失效材料不提供可点击阅读入口。先修来源也会重新解析。
- `command/` 支持cancel/retry/enhance；`export/`重新校验来源并返回私人记录，浏览器提供打印/保存PDF。JSON与前端schema已重新生成；真实任务/打印分页和全部权限回归待统一验收。

## 2026-10-18 引文体检（R25–R27，部分接入，待统一验收）

视觉来源仅为最终 PDF `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第208–215页的实际页面图像。此处记录已接入的源码契约与未覆盖需求，不把图集审核标签、控件存在或静态检查当作功能及视觉验收。

### 路由、身份与任务

- 前端 `/account/citation-audits` 对应三步上传与本人任务列表；`/account/citation-audits/{id}` 对应解析预览及报告总览；`/account/citation-audits/{id}/issues/{issueId}` 对应单条引文、候选版本、原文与人工核验。issueId 为同一 CitationAudit 的 occurrence ID，不另建报告库或馆藏。
- API 基础路径 `/api/reading/citation-audits/`，列表分页、详情、原稿、OCR、导出及命令均要求登录并过滤本人。响应 `Cache-Control: private, no-store`，`Vary: Cookie, Authorization`。前端读写前后核对 cookie owner，身份变化清空私有视图、待上传文件和预览 URL；会话与权限回归仍待统一执行。
- 复用现有加密 CitationAudit、Celery 任务及共享公开来源。记录有 `revision/status/generation/error_code/completed_units/total_units/poll_after_ms/created_at/updated_at/finished_at`；状态为 queued、running、completed、partial、failed、canceled。进度来自实际阶段 queued/parsing/ocr/matching/checking/report 和处理单元，不估算完成百分比或固定耗时。
- 上传、排队命令及恢复按 owner 序列化，同一 owner 最多两项活动任务；超限返回409。取消增加 generation，使旧 worker 不能回写；已完成的解析、核验和人工决定保留。源码约束不等于真实设备并发与负载测量。

### 能力与创建

- `GET capabilities/` 返回 `accepted_filetypes/max_upload_bytes/max_pdf_pages/max_occurrences/max_active_jobs_per_owner/default_checks`，以及 `checks[]`、`scopes[]`、`ocr`、`analysis`。检查项包含 `id/label/available/required/description`，版本页码还声明 `requires`。本地 OCR/模型的 available 仅表示配置及允许的本地端点资格，`service_verified=false` 明确未进行运行健康探测，不可显示为服务已验收。
- `POST /` 使用 multipart：`file`、UUID `request_id`、可选本人 `project_id`、重复的 `checks` 字段及 `scope`。接受 PDF/DOCX，最大12 MiB；文件签名、PDF页数、DOCX解包和文本规模沿现有解析边界校验。成功返回202及持久记录。幂等身份包括原稿内容摘要、名称、项目和显式选项；相同请求返回已有记录，复用请求ID但改变内容返回409。前端在失败时保留本地文件、选项和相同请求ID。
- 默认检查项为 `citation_identification/bibliography_identity/version_page`。引文识别必选；版本与页码依赖书目身份；不选择某项就不执行相应自动核验。新上传的 `scan_ocr` 必须显式选择且本地 OCR 配置符合条件，默认不执行；未选择扫描识别的扫描部分保留为待核实。历史无 checks 记录沿原有行为兼容。
- `scope` 默认且当前仅接受 `public_library`，使用当前公开且本人可访问的馆藏版本/原文。capabilities 中 `private_materials` 明确 unavailable，私人稿件仅用于本人检查，不进入公共馆藏。没有通过虚构私人来源能力提交范围。
- `deep_analysis` 在上传阶段不可选。报告中须本人选择具体可访问 EvidenceReference，再用 `analyze` 单独发起本地关系分析；配置缺失则明确拒绝，已有结果保留。模型产出属于待核对候选，不替代人工结论。
- `data` 保存 `filename/filetype/manuscript_revision/checks/scope/file_size_bytes/manuscript_stats/bibliography/occurrences/warnings/stage`。统计只记录实际解析的字节、文本单元、字符、PDF页数或DOCX段落/内嵌图像；不适用或尚未解析的统计不填演示值。PDF页码与DOCX XML部件、段落、字符位置分开，不把段落当作Word排版页码。

### 人工决定、来源与局部重查

- `POST {id}/command/` 必带 `expected_revision`，不匹配返回409。前端保留本地决定/校正文案，用户核对最新记录后再提交。活动任务期间除cancel外不能修改核验记录。
- `decision` 接受单条 `occurrence_id` 或批量 `occurrence_ids`（二选一、1–1000项）。决定为 `accepted/ignored/corrected/needs_review`，`note`最多4000字符；任一ID不属于本稿件则整批不保存。`corrected_text`最多4000字符，非空值只允许单条corrected决定，作为本人的校正文案独立保存，不覆盖原稿、原始识别文字或旧决定。前次人工决定进入 `decision_history`。
- `match` 用 `entry_id/edition_id` 确认当前公开的候选版本，保存旧选择并重查该书目关联的引文；`link` 用 `occurrence_id/entry_ids` 保存本人书目对应关系并重查该条。候选仅为身份提示，题名相似、书目存在不等于原文或论断通过。
- `retry` 可带 `occurrence_ids` 仅重查已解析记录中的所选项；更换候选版本只影响相关引文。失败/取消后的重试保留已完成记录，OCR失败导致重新解析时保留 `parse_history` 和人工决定的稳定映射。该局部重查针对同一份原稿，并未实现上传新稿版本后的差异识别或增量重查。
- 每次详情/导出重新核验候选版本的公开资格，以及当前与历史 findings 中 EvidenceReference 的权限、DocumentRevision、EvidenceSpan、页码和内容摘要。来源撤回或改变后清除过时公开正文、Reader链接与模型建议，标记需重新核对；原稿和本人已保存决定仍保留。原文预览复用 Reader/PdfCanvas，与有效来源修订及规范化坐标绑定，不能把失效缓存当成当前证据。

### 预览、下载与未覆盖范围

- `GET {id}/original/` 返回本人加密记录解密后的原始文件附件；按需 PDF 预览使用本地 blob URL 与已有 PdfCanvas，关闭或会话变化时回收。DOCX 预览只显示实际识别的引文附近文本和位置，精确字体/分页仍通过下载原稿查看，不调用外部文档预览服务。
- `GET {id}/ocr/` 返回真实OCR进度和单元状态；带 `unit_id` 可取该单元解析记录。`GET {id}/export/` 返回 `schema_version=1` 的私人记录JSON并重新校验来源；前端保留报告JSON，并在重新核对owner后读取完整export快照，提供打印/保存PDF；打印包含全部引文、书目、实际来源、人工修正与历史，不受当前分页筛选限制。不可访问来源不打印旧片段，会话变化/权限失效/afterprint清除打印快照；打印版式与分页仍待统一验证，不写回Word/PDF原稿。
- 待实施/待验证必须分开保留：私人材料匹配、稿件新版本差异及增量重查、DOCX精确排版/原稿编辑回写尚未覆盖；PDF209的完整三栏解析流程仍需逐图核实。真实设备内存与排队负载、真实OCR/模型、权限与恢复、导出内容及全部桌面/移动视觉验收未运行。B03、B04、B05、B06不能据本次源码接入标记通过。
