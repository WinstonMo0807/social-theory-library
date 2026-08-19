# Back Office Function Matrix

版本 2.8 将 Next Admin 组织为 Work / Edition 当前馆藏工作，Django Admin 保留为低层维护入口。以下矩阵描述当前源码中的职责边界。2.8 尚未部署生产，历史发布文档中的入口和版本号不代表当前运行状态。

| 功能 | 日常入口 | 消费者 | Source of truth | 权限 | 重复情况 | 处置 |
| --- | --- | --- | --- | --- | --- | --- |
| 上传与批次 | `/admin/uploads` | Upload workspace | UploadBatch / UploadItem / Asset | `can_upload` | Django Admin 低层检查 | KEEP |
| 当前馆藏工作 | `/admin/intake/<item>#<step>` | WorkflowEditor / Inspector | Work / Edition / Asset / FieldLock / EditionWorkflowDecision | 按 section 使用 metadata、knowledge、publication capability | 旧 review item route redirect | MERGE |
| 正式馆藏维护 | `/admin/library`、`/admin/library/works/<work>` | Work list / Maintenance WorkflowEditor | Work 为根；Edition / Asset 为版本和文件 | `access_back_office`、mutation 由服务端 capability | 旧 UploadItem 列表不再代表馆藏身份 | REBUILD |
| 馆藏发布 | 当前 Workflow 的 publication section；`/admin/publication` 保留队列 | PublishUploadItem / maintenance publication | Edition / PublicationEvent | `can_publish_work` | 无第二发布规则 | KEEP |
| 单项策展 | 当前 Workflow 的 curation section | Work contextual Reading Path / Override | ReadingPathStage / ReadingPathItem / RecommendationOverride | draft path 为 knowledge edit；published path 和推荐按 publish capability | 不覆盖完整路径或 policy | KEEP |
| 候选审核 | `/admin/candidates` | CandidateReviewShell | 各候选模型及 Evidence | `can_review_candidate` | Django Admin action 保留应急操作 | MERGE |
| 未知实体 | Knowledge Workspace | NewAuthorityCandidate review | Person / KnowledgeNode / Topic 草稿 | `can_create_authority`、`can_review_candidate` | 旧 rejection funnel 仍保留原始记录 | REBUILD |
| 学者、理论、主题 | Knowledge workspace 与对象页；当前 Work 可直接确认关系 | Scoped Search、Enrichment、Workflow RelationEditor | Authority models + Work relations | `can_edit_draft_authority` | legacy presentation models 仅作兼容展示 | MERGE |
| QueryLexicon | `/admin/query-lexicon` | Search、resolver、RAG、候选提取 | Authority + ChangeEvent；词典为派生 | 查看需 `can_view_query_lexicon`；reconcile 需 `can_manage_query_lexicon` | CLI 与后台共用同一 service | MERGE |
| Semantic index | `/admin/semantic-index` | semantic search | SemanticIndexVersion / SemanticChunk | 查看需 `can_view_semantic_index`；激活/重建需 `can_manage_semantic_index`；受控 retry 使用 `can_retry_jobs` | 旧 UID 只保留回退读取 | KEEP |
| Ask Library / AI | `/admin/settings` | Library runtime | SiteSetting / server environment | `can_manage_ai` | 旧 Ask adapter 只作兼容 | MERGE |
| Processing jobs | `/admin/processing` | Celery / ingestion workers | ProcessingJob | `can_retry_jobs` | 内部 job 类型不直接暴露为产品状态 | MERGE |
| Projection refresh | 对象页 Projection Status | QueryLexicon、semantic、PDF candidate jobs | ProcessingJob + 各自派生模型 | `can_edit_metadata` | 不建立第二套队列或 event bus | KEEP |
| System status | `/admin/status` | 运维和人工验证 | runtime health snapshots | `can_view_system_status` | 旧 `/admin/system-health` 保留为兼容诊断 route，不再作为主导航入口 | MERGE |
| Backup / storage | `/admin/distribution` | BackupJob | BackupJob / NAS | `can_run_backup` | 不建立第二套备份系统 | KEEP |
| 用户与角色 | `/admin/users` | Auth/session | accounts.User | `can_manage_users` | Django Admin 保留超级管理员维护 | KEEP |

## 三条持续增长 Lane

- Collection Lane 负责文件有效、可阅读、元数据确认和出版。
- Knowledge Lane 负责馆藏观察、实体匹配、候选、证据和草稿 authority。
- Projection Lane 负责 QueryLexicon、Semantic Index、Scoped Search、RAG 和缓存等派生结果。

任何派生任务失败都保留 ProcessingJob 错误，不回滚已经确认的馆藏出版状态。

## 五组一级导航

- 工作包含今日工作、上传与批次、待处理、发布准备和候选审核。
- 馆藏包含作品、版本与文件、馆藏质量。
- 知识包含学者、学科、子学科、理论与概念、主题、关系与时间轴、QueryLexicon 和语义索引。
- 策展包含阅读路径和推荐。
- 系统包含处理任务、系统状态、备份与存储、审计统计、用户权限和运行设置；实际可见性由 capability 决定。

## Source of truth 边界

Work、Edition、Asset、Page 文本、Person、PersonNameVariant、KnowledgeNode、KnowledgeNodeAlias、Topic、关系、时间线、ReadingPathStage、ReadingPathItem 和 RecommendationOverride 是权威数据。EditionWorkflowDecision、Candidate、Evidence、Job、Audit 是工作流数据。SemanticChunk、QueryLexiconEntry 和公开索引是派生数据。Meilisearch 与运行时缓存只负责索引和缓存。

## 兼容入口

`/admin/review` 保留队列；`/admin/review/<item>` redirect 到 Intake bibliography。带 item 的旧 publication URL redirect 到 Intake publication。旧候选 API、旧理论展示 route 和 `/admin/system-health` 暂保留为 thin adapter。高级 Reading Path、Recommendation、Scholar、Theory 和 Topic 页面继续保留，不删除底层能力。
