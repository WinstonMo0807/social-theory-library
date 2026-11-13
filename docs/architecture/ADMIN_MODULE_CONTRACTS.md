# 管理模块调用链与保存契约

[架构目录](README.md) · [完整入口](ADMIN_PAGE_INVENTORY.md) · [API声明表](inventory/api-views-services.csv)

下面的 `/catalog/...`、`/ingestion/...`、`/auth/...` 均经前端同源 `/api` 前缀。URL家族不是一条万能接口；每个具体 Django path、View位置和直接service引用见API表。所有 PostgreSQL 表名/字段见[模型字段表](inventory/model-fields.csv)。M编号覆盖完整入口表，兼容路由最终回到相应模块。

## M00

**今日工作、搜索、统计。** `/admin`、`/admin/search` 使用 `AdminDashboard`，`/admin/analytics` 使用 `AdminAnalytics`。进入目的是定位待处理工作与运行概况，展示上传、处理、复核、发布等汇总和受权限约束的链接；搜索与筛选不等于修改。客户端调用 ingestion dashboard、catalog backoffice/analytics 相关GET，分别进入 `ingestion.views.DashboardView` 和 catalog后台读取服务，汇总 UploadItem、ProcessingJob、ReviewTask、公开使用事件等。无需填写新业务对象；刷新失败保留错误/重试。不能将汇总计数当成一次全站业务验收。

## M01

**上传、收件、元数据复核与手工编目。** `/uploads` → `UploadSourceContext` + `AdminUpload`；`/intake/[itemId]` → `IntakeWorkspace`；`/cataloging/[sessionId]` → `CatalogingWorkbench` → `WorkflowEditor`；`/cataloging/new` → `ManualCatalogForm`；`/review` → `ReviewQueue`。

管理员选文件/批次、材料类型，核对题名、责任者、出版信息和候选，再决定创建新Work、附加Edition或复用既有版本。`manual-catalog.tsx` 先GET查重，保存才发送命令；空白页面不会自动建书目。责任者分别保存person_id、role与是否新建，支持作者/译者/编者/主编/校注/研究对象等，不把所有人写成作者。

调用链：`apiRequest` / cataloging client / `useCatalogCommand` → `/ingestion/batches/...`、`/ingestion/items/...`、`/catalog/admin/manual-catalog/`、`cataloging-sessions/...` → `BatchCreateView`、`BatchItemChunkUploadView`、`MetadataReviewView`、`ManualCatalogView`、cataloging views → `pipeline`、`candidate_decisions`、`cataloging_sessions`、`work_editor`。写入 UploadBatch、UploadItem、CatalogingSession、Work、Edition、Contribution、MetadataCandidate、FieldLock、DecisionLog、CatalogFieldDecision。

上传依赖异步文件处理；手工建纯书目不必先OCR。编辑和候选决定要求上传/元数据/候选 capability，发布另检权限。分片失败、队列派发失败、重复请求和命令结果未知有独立状态/回执；不得靠再传一遍消除重复风险。草稿保存不自动公开；公共书目最终读 CatalogPublicationRevision.snapshot，责任者经贡献投影过滤。

## M02

**统一馆藏工作台。** `/library` → `WorkLibrary`；`/library/works/[workId]?edition=...` → `WorkflowEditor`；`/files` → `WorkFilesWorkspace`。显示当前版本、书目信息、知识关系、文件、字段锁、处理与发布状态。父层传workId/editionId，子字段组件回传draft与dirty状态；同一Work的版本字段必须携带edition。

`useApiResource`、workspace/command hooks → `/catalog/admin/library/works/{workId}/...` → `WorkMaintenanceWorkspaceView`、`WorkWorkspaceEditsView`、`WorkMaintenanceSectionView` → `admin_workspace.build_admin_workspace`、`workspace_edits.save_workspace_edits`、`work_editor.save_workflow_section`。写Work/Edition/Contribution及相关关系，已公开对象的变更经 EditorialRevision 草稿。文件命令进入既有入库/处理服务，保留原件与派生版本。

字段锁高于机器候选；维护保存、确认字段与发布是不同命令。冲突使用预期版本/409，网络结果未知核对回执。公开消费是活动版本快照、当前允许公开的关系和受保护文件；后台尚未发布的abstract、封面或责任者不应直接混入公开响应。

## M03

**文件工具。** `/library/assets/[assetId]/ocr` → `OCRWorkspaceView`；`/page-mapping` → `PageMappingWorkspace`；`/outline` → `DocumentOutlineWorkspace`。显示文件身份、页级处理、页码映射、自动目录与人工修正。填写页标签/分段、目录标题/目标页等，不覆盖原始PDF。

前端API进入 ingestion OCR/processing接口、catalog asset page-label/outline接口；核心为 `ocr_workspace`、`document_outline.correct_outline`、`outline_exports.queue_export`、page label服务。写Page及其修订、DocumentRevision、DocumentOutlineRevision、ProcessingJob和新Asset派生。目录自动识别/自动采用已有实现；人工校准保存后仍需等待带书签PDF生成，正文修订与目录修订分开。

权限按元数据编辑、重试/处理能力和文件访问校验；暂停/继续/取消/恢复基于任务真实状态。旧证据和笔记锚点不能被新OCR假装仍有效。公开Reader读取清单、当前目录与获准的阅读/下载副本。本轮只审查源码，未在生产运行OCR或修正目录。

## M04

**发布、审核预览与历史。** `/publication` → `PublicationDesk`；`/[itemId]` → `PublicationReviewEntry`；`/preview/works/[editionId]` → `AdminWorkPagePreview`；`/preview/knowledge/[type]/[id]` 根据review/frame选择 `KnowledgePublicationReview` 或公开样式预览；`/publication/knowledge/...` → `KnowledgeHistory`。

管理员核对字段变化、新关联对象、阅读文件、警告与影响后发布。馆藏接口包括 `editions/{id}/publication/prepare|history|rollback` 和 work维护publication；知识接口包括 `editorial-revisions/{id}/publish`、`knowledge-preview`、`knowledge-publications/...`。View → `publication_commands`、`editorial_revision`、`knowledge_publication`。数据为 EditorialRevision、PublicationBundle/Item、CatalogPublicationRevision、KnowledgePublicationEvent、ProjectionState、AuditEvent。

正式公开条件是有效活动快照，不是单看Edition.state。事务提交后派发投影任务；元数据激活与全文/检索就绪可能不同步。KnowledgePublishControl记录prepare-public/prepare/publish阶段，以owner+对象+edit_version避免错账户重试；预览版本变化需重新核对。失败看事件和回执、用原命令重试或合法历史回滚，不能重建原件。发布和撤回分别校验capability，馆长敏感恢复另控。

## M05

**人物规范库。** `/people` 与 `/scholars/people` → `PersonAuthorityWorkspace`。管理员管理同名异人、异名同物、生卒年、外文名、标识和关系影响；它不是学者文章编辑器。

`/catalog/admin/people/workspace/`、`people/{id}/workspace/`、merge-preview/merge/rollback → `person_authority_views`、`person_resolution_views` → `person_authority`、`person_resolution`、`person_merges`。写 Person、PersonNameVariant、合并记录及关联修订。查找候选可供编目复用；合并需馆长专属capability、先预览影响，保留记录及回滚约束。人物记录存在不等于ScholarProfile已公开。公开作者署名由Contribution与活动书目快照决定；公开学者页还需档案可见性。此轮没有合并人物。

## M06

**学者与人物关系。** `/scholars`、`/[scholarId]` → `ScholarsAdmin`，`/relations` → `ScholarKnowledgeRelations`。填写档案简介、学术资料、外文名/异名、肖像、时间线与关系；人物身份字段和学者公开文字分属Person与ScholarProfile。

`/catalog/admin/scholars/...` → `AdminScholarDetailView` → `save_scholar_editorial_patch`、`scholar_prose`、`editorial_revision`；关系进入 shared_curation及人物—节点关系服务。写ScholarProfile、Person、EditorialRevision、ScholarRelation、PersonNodeRelation和证据。复用富文本、字段助手、useScholarSave、KnowledgePublishControl，保存草稿后预览/发布；关系方向、类型、证据及原文修订需单独核对。

公开 `public_scholars` 及学者详情读取发布数据与当前可见关联；内部编辑说明、未发布关系不应出现。版本冲突保留输入，账号变化清理状态，待定发布按回执恢复。新增/编辑/发布/合并的权限不同，不因侧栏可见便可全部执行。

## M07

**理论传统、概念、争论、研究问题、关系与时间线。** 当前主入口 `/theories`、`/[nodeId]` → `TheoryNodesAdmin`；`/relations` → `TheoryRelationsAdmin`；`/timeline` → `NormalizedTimelineAdmin`。旧knowledge/theory节点路由由兼容组件归并。

节点表单包含中外文名、异名、摘要/定义、问题、命题、边界、学科/主题、时期、材料和内部编辑说明。关系表单独立表达source/target、type、direction、证据和置信度，不能把“引用”默认为“继承”。时间线使用事件日期精度、参与者角色与来源。

`theory-system-admin.tsx` 经apiRequest、useScholarSave、专用命令与KnowledgePublishControl → `theory-system/nodes|relations`、timeline接口 → `theory_system_views`、`knowledge_views`、`node_editor_views` → `editorial_drafts`、`editorial_revision`、关系/时间线服务。写 KnowledgeNode/Alias、KnowledgeRelation、TheoryTimelineEvent、TimelineEventRelation、EvidenceSnippet、EditorialRevision及canonical revision。公开图谱只读已发布关系与合格端点；保存、审核和发布分离，merge有独立预览与回执，不在本轮操作。

## M08

**主题、学科和子学科。** `/topics/[entityId]` 使用 `TaxonomyAdmin`；`/theories/disciplines`、`/subdisciplines` 使用 `DisciplinesAdmin`、`SubdisciplinesAdmin`。主题组织研究问题，学科组织学术领域，子学科关联父学科；不能通过同一个名称列表代替它们。

填写名称、slug、简介、层次/归属、图像、相关理论/主题/代表材料与编辑说明。调用 topics、disciplines、subdisciplines管理API → `views` / `knowledge_views` → editorial草稿与public_topics/发布服务。写 Topic、Discipline、Subdiscipline及连接模型、EditorialRevision。未发布对象只能在管理预览看见；公开读取实时过滤撤回端点，即使历史书目快照仍保留关联。保存冲突重新核对版本；需edit authority，正式发布需publish authority。

## M09

**公共阅读路径。** `/theories/reading-paths` → `ReadingPathWorkbench`。管理员编排目标、先修知识、问题、阶段、材料、页码、替代项、顺序和学习依赖。`path` query决定选中路径，路径候选/路线也有独立命令。

`/catalog/admin/theory-system/reading-paths/...` → `AdminReadingPathDetailView`、`PathValidationView`、`PathPreviewView`、route views → `reading_paths`、editorial修订及path命令服务。写 ReadingPath、ReadingPathStage、ReadingPathItem、路线候选与EditorialRevision；Item可锚定Edition、Asset、DocumentRevision，不能只保存书名。AI增强依赖异步能力，人工编排本身不必调用模型。

保存/结构校验/预览/发布分开；expected version与command receipt用于冲突和超时恢复。公开 `public_reading_paths` 读取发布路径、材料可见性与真实章节依据；读者自己的PersonalReadingPlan不属于这张公开表。

## M10

**原文证据独立编辑器。** `/preview/evidence/[objectType]/[objectId]` → `EvidenceCurationEditor`。虽在preview路径下，它是可编辑工作区，不能当只读公开页。管理员选择原文、比较/导读结构和引用顺序。

`curation-workspace.client` → `admin/evidence-curation/{type}/{id}` PUT / publish POST → `AdminEvidenceCurationView` / `PublishEvidenceCurationView` → `shared_curation.save_curation/publish_curation`。写 EvidenceCuration、EvidenceCurationReference和EditorialRevision，来源为EvidenceSpan/Passage及修订。保存仅草稿；单独publish要求CanPublishAuthority。读取失败/版本冲突保留草稿并刷新；公开 `PublicEvidenceCurationView` 经同服务public=True过滤来源。

## M11

**特别策划项目、文章与推荐。** `/recommendations` 默认 `CurationProjectWorkspace`；`?view=home|legacy` 到 `RecommendationIssueList`；`issues/[id]` 为 `RecommendationIssueEditor`，预览有 `IssuePreviewFrame`。

管理员建立项目目标、团队可见性、选材与文章，再填写文章标题、导语、正文块、公开署名、关联知识、封面和发布时间。项目使用 `curation-projects` → curation_project_views → curation_projects；文章使用editorial issue接口 → editorial_issues/editorial_blocks；助手使用editorial_assistance。写 CurationProject、RecommendationIssue、EditorialRevision、ProcessingJob、AuditEvent，权威来源只引用已有馆藏/知识/证据。

项目保存不发布文章；文章草稿、即时发布、排期和位置摆放分别管理。助手生成outline/guide/comparison候选，采用只写草稿；账号/项目权限、源修订和文章edit_version均检查。失败通过回执与历史恢复；公开 `public_editorial` 选择当前有效或到期排期修订，公开署名不自动泄露账号身份。本轮只审查实现，未读取进行中的首期PDF项目内容。

旧自动推荐与人工覆盖仍有 `RecommendationPolicy/Override/Snapshot`。刷新策略不等于发表策划文章，`WorkCurationEditor`中的推荐覆盖也应显示写入范围。

## M12

**页面编排。** `/content` → `PlacementDirectory`；`/[pageType]/[pageId]` → `PlacementWorkspace`。管理员选择已经存在的文章/路径/知识/原文来源，设置分组、顺序和位置，并核对影响页面。

`useContentPlacements` → `/catalog/admin/content-placements/...` → `AdminPlacementView`、sources/uses/history/parent-preview/receipt views → `content_placements`。版位状态和命令具有版本、回执及历史；不复制一份新的书目正文。公开 `PublicPlacementView` 使用正式版位与来源可见性过滤。页面布局保存/发布不应暗中发布来源对象；权限由编辑与发布capability及父对象约束共同决定。

## M13

**网站内容与欢迎页。** `/about`、`/welcome` 和about preview复用 `SiteContentEditor`。编辑站名、介绍、导航、欢迎三版文案、展示选书及网站内容块；与学者/文章正文不同。

`SiteContentEditor`转出`site-workspace.tsx`，通过`useSiteContent`读取`/catalog/admin/site-content/`，保存/历史/命令回执/发布审核分别进入`editorial_issue_views.py`、`site_history.py`、`site_commands.py`与`site_publication_review.py`中的对应View，再由`editorial_issues`服务维护`SiteSetting`和`EditorialRevision`。公开 `site.server.ts` / `home.server.ts`读取生效配置；权限按编辑、审核、发布能力分别检查。

重要范围是共享网站草稿：发布一次可能涉及草稿中其他栏目，必须在界面说明完整范围。版本冲突与历史恢复不能只按当前tab推断。欢迎演示选书需当前公开，撤回来源不能继续泄漏。顶部Logo和进入/home约定保持。

## M14

**媒体库与嵌入选择。** `/media` → `MediaLibrary`；其他编辑器内 `InlineMediaPicker` / object media workspace。管理员看媒体用途、上传/选择图像、裁切版本和描述，不直接覆盖已有文件。

media collection、media/{id}/workspace、renditions、media-objects、edition media-workspace → `media_views` / `media_library_views` / `object_media_workspace_views` → `services/media.py`与选择服务。写MediaAsset、MediaRendition、对象的rendition指针、审计及必要草稿。更新媒体描述与将某张图发布到书目是两类动作，公开消费者仍检验活动引用；上传失败不能用不存在的ID伪造成功。来源图、历史裁切与使用引用保留；请求范围按owner与capability核对。

## M15

**处理中心。** `/processing` → `ProcessingCenter`。展示真实ProcessingJob、UploadItem、步骤、进度、错误和恢复动作，支持按任务权限重试、暂停、继续、取消等。接口 `ingestion/processing...` → `ProcessingCenterView` → `processing_center/workspace/commands/retry/recovery`。

任务记录、task_id/processing_token、heartbeat、lease和attempt决定谁可以提交结果；保存一个状态标签不代表服务执行成功。后台队列异步运行，旧任务不能覆盖新尝试。重试能力与普通编辑不同；不可把failed隐藏成空列表。处理中心无直接公开正文，结果经文件修订、发布与索引后才成为读者可见来源。

## M16

**运行维护、设置、词表、索引和诊断。** `/processing/status|settings|query-lexicon|semantic-index|health`及旧路径；组件包括SystemStatusCenter、SettingsAdmin、QueryLexiconWorkspace、SemanticIndexAdmin/IndexMaintenance、AdminSystemHealth、CandidateReview、KnowledgeWorkspaceDiagnostics。

状态读取、配置写入、诊断、索引切换和候选决定是不同API。catalog系统/模型/Provider/词表/semantic与ingestion health View分别进入common AI runtime、query_lexicon、semantic_indexing、projection及system_health服务。写配置模型、候选/任务、ProjectionState与AuditEvent，索引只是派生存储。馆长专属权限控制密钥、模型/Provider、全局投影、词表管理与索引切换，普通admin多为状态读取/有限运维。

不得把“未探测”写成正常，不可将按需停止等同崩溃。密钥不回显；配置失败看真实响应；索引失败保留活动版本并查看处理回执。这轮没有变更配置、触发探测或重建索引。

## M17

**存储、备份、分发与回收。** `/storage`、`/backups` → `StorageWorkspace`；`/distribution` → `DistributionAdmin`；`/recycle` → `RecycleBin`。管理员看文件/备份/分发状态、引用影响与回收记录。distribution API及其存储/备份服务处理CloudObject、存储任务、回收/恢复与审计记录，数据库和NAS文件职责分开。

备份验证、恢复预演、真正恢复和永久删除不是一项操作。馆长专属backup/destructive/recovery capability控制敏感动作；文件清单不等于允许删除。公开消费者是受保护下载/图片与已激活馆藏；回收、恢复要尊重仍被历史/私人锚点引用的对象。本轮没有执行任何备份、回收、恢复或删除命令。

## M18

**账户与权限。** `/users` → `AccountWorkspace` → auth账户管理API → accounts View/ownership/capability服务 → User、恢复/会话与审计数据。显示账号、角色与状态，填写账号管理字段；角色分配与馆长身份须后端裁决。头像/私人研究内容不是管理员可任意查看的目录。

账号保存立即影响认证/权限，不能套用内容草稿发布机制；相关动作有单独权限与确认范围。失败不显示新权限已生效。公开署名只来自显式发布的byline，不自动从User扩散。此轮未进入用户列表导出私密信息或变更账号。

## M19

**支持与校准。** `/support/feedback` → `FeedbackWorkspace`；`/support/parallel-calibrations` → `ParallelCalibrationWorkspace`。前者处理PublicFeedback工作流，后者处理读者提交的版本平行校准及权限过滤。API位于catalog public-feedback和reading parallel相关views。管理员回复/采用属于写操作，本轮只审查源代码。校准材料可关联具体asset/revision/page，不把读者私人笔记自动变为公开知识。

## M20

**视觉复核。** `/visual-review` → `VisualReviewWorkspace`。这是单独入口，不能因侧栏不常见而遗漏；用于界面核对的列表、状态与相关工作记录，不构成公开知识消费者。代码与页面目录保留，不把旧PDF图集、参考图数量或标记当成全站完成证据。此轮的文档截图单列实际访问范围。

## 共通的失败恢复规则

| 情形 | 代码已有机制 | 管理员应看到什么 |
| --- | --- | --- |
| 未登录/权限撤销/账户切换 | Session bootstrap、owner header、private/no-store、清理内存 | 重新登录或无权访问，不继续显示旧账户资料 |
| 同时编辑 | If-Match / expected version、409、数据库锁 | 竞争版本与保留的本地输入，不静默覆盖 |
| 请求超时但可能已写入 | requestId、fingerprint、receipt、pending phase | 先核对原请求，确认结果后再继续 |
| 保存草稿成功 | EditorialRevision/本地确认版本 | 草稿已保存，公开状态仍独立 |
| 发布命令已收但投影未完成 | publication event、outbox/ProjectionState、任务恢复 | 分开显示正式版本与搜索/全文准备状态 |
| OCR/Provider/队列失败 | ProcessingJob错误、attempt/token、重试/暂停 | 真实失败原因与可用动作，原件和人工确认不丢失 |

该表是关键机制的共同解释，并不保证每个遗留页面的提示完全一致；待真实写入验收的场景见[问题与待核项](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md)。
