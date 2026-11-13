# 09 · API、服务与前端调用

[架构目录](README.md) · [完整API映射CSV](inventory/api-views-services.csv) · [前端API表达式CSV](inventory/frontend-api-expressions.csv)

静态扫描解析517个path声明，其中516个解析到本仓库函数/类。这里包含健康、schema和Django admin入口，不等于517个独立REST业务能力。继承的HTTP方法、权限mixin、动态服务调用和include前缀需结合源码，不从AST引用数推导运行覆盖率。

## 路由根与请求

`api/config/urls.py`将auth、catalog、ingestion、reading、distribution和capability-worker分配到各应用。Nginx把浏览器`/api`送往API；Web服务端使用内部API地址；`apiRequest`管理同源会话与统一错误，专用客户端补充owner、edit_version、If-Match、requestId与超时。

| 前端场景 | API家族（省略/api） | View → Service | 权威对象 / 公开出口 |
| --- | --- | --- | --- |
| WorkLibrary / WorkflowEditor | catalog/admin/library/works；edits；publication | workflow_views → admin_workspace / workspace_edits / work_editor / publication_commands | Work、Edition、EditorialRevision → public_work_detail |
| ManualCatalogForm | catalog/admin/manual-catalog；commands | ManualCatalogView → cataloging_sessions / work_editor | CatalogingSession、Work、Edition、Contribution |
| AdminUpload / IntakeWorkspace | ingestion/batches；items；metadata/review等 | ingestion.views → pipeline / candidate_decisions / entity_resolution_decisions | UploadItem、候选、决定、锁 → 发布后快照 |
| KnowledgePublishControl | catalog/admin/knowledge-preview；editorial-revisions/publish | backoffice_views / editorial_revision_views → editorial_revision / knowledge_publication | 草稿、canonical revision、事件、投影 |
| Scholar / Topic / Theory编辑器 | catalog/admin/scholars；topics；theory-system/nodes | views / theory_system_views → editorial_drafts / scholar_media / public_topics | 规范实体与独立公开状态 |
| 关系与时间线 | theory-system/relations；scholar-relations；theory-timeline | theory_system_views / shared_curation_views / knowledge_views → 关系、anchor、timeline服务 | KnowledgeRelation、ScholarRelation、TimelineEvent |
| ReadingPathWorkbench | theory-system/reading-paths；validate；preview；routes | theory_system_views / path_editor_views → reading_paths / path命令 | Path、Stage、Item → public_reading_paths |
| EvidenceCurationEditor | catalog/admin/evidence-curation | shared_curation_views → shared_curation | EvidenceCuration、EditorialRevision → public=True读取 |
| CurationProjectWorkspace / IssueEditor | catalog/admin/curation-projects；recommendation-issues | curation_project_views / editorial_issue_views → curation_projects / editorial_issues | 项目、文章、修订 → public_editorial |
| PlacementWorkspace | catalog/admin/content-placements | content_placement_views → content_placements | content_placement修订 → PublicPlacementView |
| SiteContentEditor → site-workspace | catalog/admin/site-content；preview；publish；history | editorial_issue_views / site_history / site_publication_review → editorial_issues | SiteSetting、EditorialRevision → SiteConfigView |
| OCR / outline / page mapping | ingestion处理；catalog/admin/assets/outline等 | outline_views / ingestion.views → document_outline / outline_exports / OCR服务 | Page、DocumentRevision、OutlineRevision、ProcessingJob |
| MediaLibrary / InlineMediaPicker | catalog/admin/media；renditions；media-objects | media*_views → media / object选择服务 | MediaAsset/Rendition → 公开受控图片 |
| Explore / Discovery | catalog/search；discovery-search；semantic-search | catalog / discovery views → discovery_sessions / semantic_search / retrieval | 身份排序会话与派生索引；重新核验来源 |
| Reader | catalog/assets/manifest；outline；search；reading接口 | catalog、reading views → publication eligibility / reading服务 | 获准文件、本人进度/注释 |
| 研究 / 助手 / 引文核对 | reading/library及research等 | reading/*views → library_assistant / local_analysis / research服务 | 本人加密数据与来源，非公共catalog |

## 权限、事务与幂等

View负责认证、capability、serializer输入和HTTP错误；Service负责领域约束、锁、版本、候选决定和事件；Model负责FK、唯一性与持久化。并非所有遗留View都薄到只有一行调用，ingestion/views.py与catalog多导出模块仍承载部分编排，审查时须读方法体。

`AdminEditorialDraftReadMixin`对受保护编辑要求非通配If-Match（缺失返回428）；竞争版本/锁忙返回409。专用命令使用AuditEvent或receipt模型记录actor+requestId+fingerprint。重复ID绑定不同payload应拒绝。`transaction.on_commit`用于数据库成功后派发，队列失败另记状态。

## 契约维护

`web/scripts/generate-api-contracts.mjs`调用Django spectacular，生成 `api/openapi/schema.json` 和 `web/lib/api/generated/schema.ts`。它与本轮静态架构索引不同：前者验证serializer/API契约，后者记录源代码位置与直接引用。不要把CSV当成OpenAPI规范，也不要用AST生成结果证明所有继承HTTP方法已运行。

管理端schema入口受 `CanAccessBackOffice`保护。不得为生成文档开放生产schema或暴露内部凭据。生成命令与环境限制见[测试与质量](14_TESTING_AND_QUALITY.md)。
