# Back Office Function Matrix

版本 2.7 将 Next Admin 作为日常运营入口，Django Admin 保留为低层维护入口。以下矩阵描述当前源码中的职责边界。历史发布文档中的入口和版本号不代表当前运行状态。

| 功能 | 日常入口 | 消费者 | Source of truth | 权限 | 重复情况 | 处置 |
| --- | --- | --- | --- | --- | --- | --- |
| 上传与批次 | `/admin/uploads` | Upload workspace | UploadBatch / UploadItem / Asset | `can_upload` | Django Admin 低层检查 | KEEP |
| Intake / metadata review | `/admin/review`、`/admin/intake/<item>` | Metadata review | Work / Edition / Asset / FieldLock | `can_edit_metadata` | 旧 review route 仍被外部链接使用 | MERGE |
| 馆藏发布 | `/admin/publication` | Publication desk | Edition / PublicationEvent | `can_publish_work` | 无第二发布事务 | KEEP |
| 候选审核 | `/admin/candidates` | CandidateReviewShell | 各候选模型及 Evidence | `can_review_candidate` | Django Admin action 保留应急操作 | MERGE |
| 未知实体 | Knowledge Workspace | NewAuthorityCandidate review | Person / KnowledgeNode / Topic 草稿 | `can_create_authority`、`can_review_candidate` | 旧 rejection funnel 仍保留原始记录 | REBUILD |
| 学者、理论、主题 | Knowledge workspace 与对象页 | Scoped Search、Enrichment | Authority models | `can_edit_draft_authority` | legacy presentation models 仅作兼容展示 | MERGE |
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

## Source of truth 边界

Work、Edition、Asset、Page 文本、Person、PersonNameVariant、KnowledgeNode、KnowledgeNodeAlias、Topic、关系、时间线和 ReadingPath 是权威数据。Candidate、Evidence、Job、Audit 是工作流数据。SemanticChunk、QueryLexiconEntry 和公开索引是派生数据。Meilisearch 与运行时缓存只负责索引和缓存。

## 兼容入口

`/admin/review`、旧候选 API、旧理论展示 route 和 `/admin/system-health` 暂保留为 thin adapter。新后台内部使用统一 service；当所有外部链接迁移到 Intake / Knowledge Workspace 与 System Status 后，才删除旧 adapter。
