# STL 4.0 当前接口契约

更新时间：2026-10-15。本文先记录 U01 首页已经接入的稳定边界；全站领域契约继续以 `docs/stl-4.0/API_CONTRACT.md` 的历史归一记录、源码和生成 schema 为准，不能把本文件当成全站验收通过。

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
