# Back Office Function Matrix

版本 3.0.2 将 Next Admin 收敛为五种页面模式和五组导航。Django Admin 只保留低层维护与应急入口。以下矩阵描述当前源码职责；3.0.2 的生产状态以部署记录为准。

| 功能 | 日常入口 | 消费者 | Source of truth | 权限 | 重复情况 | 处置 |
| --- | --- | --- | --- | --- | --- | --- |
| 上传与批次 | `/admin/uploads` | Upload workspace | UploadBatch / UploadItem / Asset | `can_upload` | Django Admin 低层检查 | KEEP |
| 当前馆藏工作 | `/admin/intake/<item>#<step>` | WorkflowEditor / Inspector | Work / Edition / Asset / FieldLock / EditionWorkflowDecision | 按 section 使用 metadata、knowledge、publication capability | 旧 review item route redirect | MERGE |
| 正式馆藏维护 | `/admin/library`、`/admin/library/works/<work>` | Work list / Maintenance WorkflowEditor | Work 为根；Edition / Asset 为版本和文件 | `access_back_office`、mutation 由服务端 capability | 旧 UploadItem 列表不再代表馆藏身份 | REBUILD |
| 馆藏发布 | 当前 Workflow 的 publication section；`/admin/publication` 保留队列 | PublishUploadItem / maintenance publication | Edition / PublicationEvent | `can_publish_work` | 无第二发布规则 | KEEP |
| 单项策展 | 当前 Workflow 的 curation section | Work contextual Reading Path / Override | ReadingPathStage / ReadingPathItem / RecommendationOverride | draft path 为 knowledge edit；published path 和推荐按 publish capability | 不覆盖完整路径或 policy | KEEP |
| 候选决定 | Workbench、Inspector、Knowledge Studio | CandidateDecisionProtocol / CandidateDecisionBar | 各专业候选模型及 Evidence | `can_review_candidate` | `/admin/candidates` 为 advanced/compatibility | ABSORB |
| 未知实体 | Knowledge Workspace | NewAuthorityCandidate review | Person / KnowledgeNode / Topic 草稿 | `can_create_authority`、`can_review_candidate` | 旧 rejection funnel 仍保留原始记录 | REBUILD |
| Scholar、Discipline、Theory、Topic | 四个一级 Directory 与 Object Workspace | KnowledgeObjectEditorAdapter、对象专业 editor、Context Inspector | Canonical objects + EditorialRevision + DomainChangeEvent | `can_edit_draft_authority`、发布按对象 capability | legacy bulk route 保留 advanced | ABSORB |
| Knowledge Studio | `/admin/knowledge` | Knowledge health、Completeness、Growth、Preview、Impact | 读取 Canonical/Derived/Projection；写入复用既有 mutation | Administrator 全馆管理；Editor 按授权对象 | 不建立第二套 Knowledge API | NEW |
| QueryLexicon | Processing Center advanced | Search、resolver、RAG、候选提取 | Authority + QueryLexiconChangeEvent；词典为 Projection | 查看需 `can_view_query_lexicon`；reconcile 需 `can_manage_query_lexicon` | `/admin/query-lexicon` 保留 advanced route | ABSORB |
| Semantic index | Processing Center advanced | semantic search | SemanticIndexVersion / SemanticChunk | 查看需 `can_view_semantic_index`；激活/重建需 `can_manage_semantic_index` | `/admin/semantic-index` 保留 advanced route | ABSORB |
| Ask Library / AI | Processing Center 与设置 | Library runtime | AIRuntimeProfile / ProviderCredentialSecret / server environment | Provider secret 仅 Owner；普通配置按 capability | 旧 Ask adapter 只作兼容 | MERGE |
| Processing Center | `/admin/processing` | Research、AI、OCR、Worker、Projection、恢复 | 各专业任务表 + CapabilityDemand + Health snapshot | Administrator；敏感操作仅 Owner | 不把 ProcessingJob 变成万能任务表 | REBUILD |
| Projection refresh | 对象页 Frontend Impact / Processing Center | 九类 projection executor | DomainChangeEvent + ProjectionState/Task | 对象编辑与安全恢复按 capability | ProcessingJob 只承担专业执行 | REFACTOR |
| Claim Gold | Processing Center benchmark workflow | Viewpoint activation gate | ClaimBenchmarkJudgment + EvidenceSpan | Administrator 编辑；激活仍需 Owner policy | 不自动生成 Gold | NEW |
| Backup / storage | `/admin/distribution` | BackupJob | BackupJob / NAS | `can_run_backup` | 不建立第二套备份系统 | KEEP |
| 用户与角色 | `/admin/users` | Auth/session | accounts.User | `can_manage_users` | Django Admin 保留超级管理员维护 | KEEP |

## 三条持续增长 Lane

- Collection Lane 负责文件有效、可阅读、元数据确认和出版。
- Knowledge Lane 负责馆藏观察、实体匹配、候选、证据和草稿 authority。
- Projection Lane 负责 QueryLexicon、Semantic Index、Scoped Search、RAG 和缓存等派生结果。

任何派生任务失败都保留 ProcessingJob 错误，不回滚已经确认的馆藏出版状态。

## 五组一级导航

- 工作包含今日工作、上传与上架、待处理和发布准备。
- 馆藏包含作品、版本与文件、馆藏质量。
- 知识包含 Knowledge Studio、学者、学科、理论传统和主题。子学科、Concept、Debate、关系与时间轴从相应 Object Workspace 进入。
- 策展包含阅读路径和推荐。
- 系统包含 Processing Center、备份与存储、审计统计、用户权限和系统设置。QueryLexicon、Semantic 与旧状态页位于 Processing advanced tools。

## Source of truth 边界

Work、Edition、Asset、Page 文本、Person、PersonNameVariant、KnowledgeNode、KnowledgeNodeAlias、Topic、关系、时间线、ReadingPathStage、ReadingPathItem 和 RecommendationOverride 是权威数据。EditionWorkflowDecision、Candidate、Evidence、Job、Audit 是工作流数据。SemanticChunk、QueryLexiconEntry 和公开索引是派生数据。Meilisearch 与运行时缓存只负责索引和缓存。

## 兼容入口

`/admin/review` 保留队列；`/admin/review/<item>` redirect 到 Intake bibliography。带 item 的旧 publication URL redirect 到 Intake publication。旧候选、QueryLexicon、Semantic、理论关系、时间轴和 `/admin/system-health` 暂保留为 advanced/compatibility adapter。退役条件是新 Workspace 达到功能 parity、连续观察期没有正常导航或写入依赖、旧 mutation 不再绕过 EditorialRevision 与 DomainChangeEvent。
