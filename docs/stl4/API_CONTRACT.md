# STL 4.0 当前接口契约

## 2026-10-23 全项目来源与预览（326路径）

新增GET admin/curation-projects/{project_id}/sources/（q/origin/scope/page，ProjectSources）与preview/（ProjectPreview）。来源按项目所有文章当前修订归集、30项分页，附录接口保留；预览最多200篇原文章元信息，选择后沿原受保护预览和公开页，不返回整项目长正文。均按项目可见范围与X-Editor-Owner过滤，private/no-store；无写操作。

## 2026-10-23 项目附录汇总（324路径）

新增GET admin/curation-projects/{project_id}/materials/，沿项目范围读取全部文章当前附录，q/scope/page、30项分页、全项目总量/待补量及具名ProjectMaterials响应。只有当前页正文说明被解析，材料状态复用原文章呈现。未提供正文来源全项目检查完成保证；接口不写业务数据。

## 2026-10-23 M14（323路径）

新增admin/curation-projects列表/固定命令、{project_id}详情、commands/{request_id}查回/停止、people协作者显示名称分页。ProjectValues/Command/Article/Material/Problem/Activity均具名契约；原文章集合补实际page/pages/page_size，后台文章补只读项目上下文（不加入公开payload）。原文章、选材、助手、媒体与发布接口继续复用；项目范围同时过滤旁路。SQL与OpenAPI仅离线静态生成，无接口请求。

## 2026-10-23 索引维护

保留316路径，新增index-maintenance、commands与terms，共319。材料阶段、任务、版本、词条、操作/回执具名契约与TypeScript同步。原Discovery读模型保持兼容。

## 2026-10-23 处理工作区

保留314路径，增加processing-workspace和commands，共316。任务/文件/OCR进度/日志/命令/回执具名序列化器与TypeScript契约同步。旧processing-center接口保留原OCR创建与高级控制协议。

## 2026-10-23 媒体工作区

保留312路径，新增media-workspace读写与commands查回/停止，共314。请求与响应纳入具名序列化器；原图私有文件入口不进入公开契约。原media/cover服务保持兼容，无迁移。

## 2026-10-23 字段助手

保留307，原field-assistant lookup/adopt/reject/create/duplicates五路径纳入312契约。请求身份核对及私人响应沿AdminPrivateResponseMixin，写入核对活跃用户token/编辑能力；新建authority额外CREATE_AUTHORITY。

## 2026-10-23 材料编辑回执

保留305，纳入原works/{work_id}/edits/和新增edits/commands/{request_id}/，共307。原保存CAS和候选来源记录继续使用；保存/停止共用账户锁与请求身份，GET只回当前操作者原请求。

## 2026-10-23 M04手工书目

保留303，manual-catalog GET/POST与commands/{request_id} GET/POST新增2，总305。严格owner/权限/版本/请求；新建作品、新版、直接使用原版分开。DocumentType扩展章节/其他，公开版本新增论文集名/丛书号且只取激活快照，0078未执行。

## 2026-10-23 M03收件身份

保留301，新增items/{item_id}/confirmation GET/POST和commands/{request_id} GET/POST，共303。owner、EDIT_METADATA、目标版本、固定请求、原文权限与未发布状态；不增加迁移。

## 2026-10-23 M02上传批次

保留299，新增upload-workspace GET/POST及commands/{request_id} GET/POST，共301。owner+UPLOAD权限、版本+固定请求编号。批次策略沿原模型，50文件位；transport由服务端配置返回。批次items仅上传所需摘要；原布尔/对象响应类型补明确声明。无新迁移。

## 2026-10-23 M31/M32内容编排

保留298，新增admin/content-placements/pages GET，共299。原sources增加准确版本筛选/作者/文献类型/主题/语言/可读性/排序和scholar/issue类型；24条分页。原save可传groups，item新增display_fields/internal_goal/reason_format；internal_goal从匿名投影移除，富文本限制沿原规范。来源类型、组结构、can_withdraw及公开/编辑URL同步契约。没有新增存储、任务或迁移。

## 2026-10-23 M29首页编排源码接入

保留296条，新增admin/site-content/sources GET（已公开来源20条分页）及commands/{request_id} GET/POST（本人回执/停止未执行请求），共298。原site-content PUT/publish POST必需X-Editor-Owner、固定Idempotency-Key；发布confirm=true。草稿/公开home增加home_layout，null沿用公开推荐、空数组为明确空栏目。home_preview按真实发布来源重算，不含私人记录。通用修订入口排除site_content，网站历史仅本模块30条摘要。

## 2026-10-23 M28回收与恢复

原294契约保留，新纳入原admin/recycle GET/POST与新增kind/object_id详情，共296。恢复POST必须owner、对象版本、固定请求UUID和明确confirmed，拒绝旧仅传id的恢复载荷。新删除控件另向原lifecycle传Idempotency-Key以查回原结果。目录20条/页，详情返回有限管理依赖与30条历史摘要。

## 2026-10-23 M27存储备份与恢复准备

原291条全部保留，新增distribution/storage GET、commands POST、backups/{backup_id} GET，共294。状态聚合、独立校验/演练记录、默认关闭的计划、固定请求回执、账户绑定与计划版本核对；详情/写入限原RUN_BACKUP。缓存候选未扫描时返回null，不伪造零候选。前端使用生成类型。

## 2026-10-23 M26本地模型与服务

原289条全部保留，新增local-services GET及local-services/check POST，共291。返回真实配置/保存观察/任务聚合；POST固定UUID、配置版本与owner，User锁内核对权限，复用原HealthCheckRun；前端使用生成类型。读取不触发模型或Provider检查。

## 2026-10-23 M24公共阅读路径

M24原287全部保留，新增reading-paths/commands/{request_id}及reading-paths/validate，共289。材料增learning_goal/dependencies，公开关系仅含两端可见项；dependencies_valid不是完整发布合格证明。写入owner/If-Match/固定请求，与原发布草稿同步。

## 2026-10-23 M23时间线编辑

M23保留285条，新增事件similar POST和commands/{request_id} GET/POST，合计287。原事件新增精度日期及私有editorial_details；公开只明确新增日期/精度字段，不加入私有核对资料。新建要求固定请求和owner，更新保留If-Match，详见TIMELINE_EDITOR_20261023。

## 2026-10-23 M22主题编辑

新增topics/organization GET（parent/q/exclude/page）、{id}/organization-preview POST只读提议、commands/{request_id} GET/POST。原Scholar commands也增加POST cancel_pending。回执state applied/cancelled，停止时对象ID允许null；已完成写入不被撤销。Topic保存必需owner，新建固定UUID；原If-Match和权限不变。285路径，公开别名沿原正式快照；详细字段见TOPIC_EDITOR_20261023。

## 2026-10-23 M21概念编辑

原content-placements命令增加可选publish.confirmed_only及内部意见/译义候选。新commands/{request_id}/支持GET本人回执和POST cancel_pending（已有则查回、未执行则锁内记录停止）；revision_id可null，state applied/cancelled。写入及回执必需owner，原权限/CAS保留。公开concept_usage允许字段不含内部说明或译义候选。282路径，保留281；类型同步。

## 2026-10-23 M20学者公开编辑

新增学者commands/{request_id}与{scholar_id}/work-selection两GET，原279条路径保留共281；原学者POST可绑定existing_person_id，正文保存固定UUID回执及If-Match，原预览POST增加有界Scholar选择。公共ScholarWork/Detail同步推荐数据。具体身份、参数、失败和恢复见SCHOLAR_EDITOR_20261023；契约生成不等于接口运行。

## 2026-10-23 M19人物规范与身份核对源码接入

catalog/admin/people新增workspace目录、{id}/workspace详情、workspace/preview、workspace/command、workspace/receipts/{id}共五路径，总279。严格操作字段、owner头、版本/预览/明确确认/请求回执；原归并及撤回写入口同样必需X-Editor-Owner。返回当前User绑定，不读取读者私有记录。

## 2026-10-23 NEW-R04研究总览源码接入

原research-projects新增GET directory/，必需X-Reader-Owner，page与scope（active/archived/all），20条摘要及本人最近阅读；无新数据库模型。总274路径，保留此前273。

## 2026-10-23 M25账户管理

auth/users新增workspace/roles/preview/command/receipt/history六路径，共273。actor头+权限+HMAC版本/预览/明确确认/UUID；旧用户PATCH和set-password必须同命令字段，拒绝旧无条件提交。原角色集合/账户表保留，实际能力矩阵来源原服务。

## 2026-10-23 R28接续

新增notebook/export POST（1–20本人版本、PDF/Markdown/BibTeX/RIS、明确摘录/笔记）；原bookmark note增加GET请求回执。267路径，无模型迁移，所有者与内容/来源再核对。

## 2026-10-23 R34受限分享契约

新增groups与shares及share-links共12路径、合计266。见SHARING_WORKSPACE_20261023。私人必需owner头，分享源绑定本人/版本，公开token不进入查询字符串；允许review_candidate仅读明确提案。原privacy collaboration五类与旧export同步，0契约错误/10旧catalog警告；迁移0024仅声明。

## 2026-10-23 引用加入本人书单

原252路径保留，新增lists/{id}/citation（GET回执/POST保存）及undo-citation（POST），共254。强制owner/本人范围、版本、公开来源及回执；签名撤销保护后续编辑和研究/记忆关联。详见CITATION_BOOKLISTS_20261023及生成契约。


## 2026-10-23 R30回放三路径

原249保留；research-projects/{id}/replay（GET/PATCH）、fork-from-replay（POST）、replay-fork-receipt（GET），共252。强制owner，版本及范围核对；详细字段见生成契约与RESEARCH_REPLAY_20261023。


## 2026-10-23 R28五条路径

原244保留，增加notebook列表、choices/{kind}、{category}/{id}、bookmarks/{id}/note、add-to-project，共249。后者GET查回/POST加入研究；全部必需X-Reader-Owner，owner/version/source范围固定。原隐私targets增加bookmarks；原work字段明确可空、书签输出updated_at。见NOTEBOOK_WORKSPACE_20261023。


## 2026-10-23 书单计划三接口

原241路径保留，新增lists/{id}/plan-preview、create-plan及lists/plan-receipt，共244。owner头必需；预览使用expected_version和可选item_ids，生成另携source_token/request_id/原计划设置；返回owner/request/record_id/deleted，不把已删除回执当新建。详见BOOKLIST_PLAN_20261023。

## 2026-10-23 R29书单契约

新增纳入9条原/新书单路径：/reading/lists/及{id}/、add_item/、items/{item_id}/、directory/、{id}/workspace/、command/、receipt/、{id}/export/。共241路径，232旧契约保留。工作台必需owner头；command显式UUID/版本/动作，receipt查回后删除不重建；export为private二进制响应、私人内容显式opt-in。详细限制与0023见BOOKLIST_WORKSPACE_20261023。

## 2026-10-23 原认证接口契约

原228路径保留，新增覆盖/api/auth/login/、register/、password/request/、password/confirm/，共232。GET login初始化CSRF且返回真实密码登录/保持天数/验证码20分钟能力；Cookie模式POST必须先初始化并携CSRF头。POST login原email参数兼容邮箱/用户名，新增remember_me默认true；Register可选username，旧调用兼容。其余业务接口权限不变。受保护私有字段只在有效密码认证后返回。

## 2026-10-23 原资料操作的所选导出

POST /reading/privacy/operations/ export支持categories或targets二选一，1至500条；targets新增research/audits/citation_sources/saved_items类型，erase仍受服务端允许集合限制。saved_items复用原收藏/来源规则。228路径保持。原research-projects/import新增持久回执，已删除转存的旧请求409，不重建；读者须先应用新增0022迁移（本轮未执行）。

## 2026-10-23 读者总览投影

新增GET /api/reading/reader-center/：kind七类或all、q≤180、order newest/oldest、page≥1、overview默认true。响应owner_id/count/page/page_size/total_pages/counts/results及可选recent_reading/pending_tasks。每页20，私人全文搜索最多5000项范围，超过明确400，不截断；并发删除409，页越界404。原权限/no-store/owner保护；无写入，无新表。227旧路径保留，共228。

## 2026-10-23 外观与私人接口边界

原 PATCH /api/auth/me/ reading_preferences 增加 theme=light|dark|system，text_size/font_family保持；其他JSON键不能通过此接口写入，原隐私/研究键合并保留。原身份/能力/退出、阅读历史/导出/荐书、个人模型配置/检测、旧问答会话/消息/流加入可选 X-Reader-Owner 校验，不匹配403，private/no-store及Vary Cookie/Authorization；保持原权限、owner queryset及流no-transform。没有新增路由，原227路径契约不变，JSON字段原来就是开放对象，无生成类型变化。详见READER_APPEARANCE_PRIVACY_20261023。

## 2026-10-23 知识对象M18

GET/POST /api/catalog/admin/knowledge-publications/{object_type}/{object_id}/history/，九种KnowledgeObjectEditorAdapter页面类型（排除work），节点细分类型必须匹配。GET后台权限/private,no-store，可选page(20条)/selected(必须本对象)，返回edit_version、当前状态、history、selected、changes、dependencies、最近20任务与scope。生成前后保存版本不符409，错误对象/页404。

POST另要求PUBLISH_AUTHORITY；action=withdraw|restore、request_key UUID、expected_version精确64位、reason 1–400字符；restore必须source_revision_id，withdraw禁止该字段。锁主体/学者Person，先查原修订+审计摘要回执，再核对版本/人工草稿/主题合并；历史必须本对象曾公开修订，只恢复当时捕获的可编辑字段。202返回原/新revision_id、revision、status、edit_version，不自动发布。冲突409，无效历史400。X-Editor-Owner沿PublicationReadView。新增KnowledgeHistoryResult/Command/Receipt强类型，227路径。

## 2026-10-23 知识M17只读检查投影

既有GET /catalog/admin/knowledge-preview/{object_type}/{object_id}/可携review=1，必须同时携精确edit_version；重复review、非1、缺版本或混入未保存学者选择返回400。版本过期/生成期间改变仍409；主题选择POST不接受review。CanViewEvidence、owner与private/no-store保持。

成功在原预览包内添加publication_review：checked_at/saved_at/current_revision/draft_revision_id、has_draft/withdrawing、actor_label、can_publish、blocking_count/warning_count、checks[{code,severity,title,detail,section}]、changes[{key,label,before,after,changed}]。公开字段按模块比较，其他公开字段纳入基本信息，差异不返回额外私人对象。权限/修订/模型/关系和所选图片检查仅只读；原正式发布仍重新运行原事务规则。当前源码没有全原文自动授权检查。

OpenAPI/schema.ts同步可选review参数，既有226路径不变；返回沿原自由对象和手写KnowledgePreviewPayload同步。不新增表/任务/路由或迁移。iframe回执须同源、准确contentWindow、owner/type/id/version/page全匹配，不把HTTP成功等同渲染就绪。

## 2026-10-23 知识预览保存版本

原GET /catalog/admin/knowledge-preview/{object_type}/{object_id}/及主题只读POST增加可选query edit_version。重复值或与当前保存版本不符返回409 preview_changed；生成前后版本变化同样409，响应不包含perspective。成功响应追加edit_version，沿KnowledgePreviewPayload自由对象内的可选TS字段同步；新发布/完整预览消费者明确核对该值。

学者GET既有选择参数和主题POST parent/curation保持；edit_version仅用于底稿一致性，不将未保存选择写库。CanViewEvidence、可选X-Editor-Owner、private/no-store保持。版本算法提取自原AdminEditorialDraftReadMixin，输入不变；包含主体updated_at、正式revision、最新draft身份/updated_at和学者Person版本，不是所有关联资料快照。OpenAPI/schema.ts已生成，可选参数与409响应均覆盖，226路径不变。

## 2026-10-23 知识发布账户与阶段契约

本批不增加路由/DTO/表。RequiresCapability、IsLibraryStaff、IsKnowledgeEditor接受可选X-Editor-Owner；存在且不等于当前认证user.pk返回403，缺省沿原权限。匹配header不授予任何新能力。当前知识控制器所有原详情GET/PATCH、knowledge-preview及editorial-revisions GET/publish POST均携此头并以withPrivateOwner前后验证。

检查保存版本使用原edit_version；首次公开PATCH精确If-Match。已有draft修订直接发布其原ID与状态，响应核对target_type/target_id/status。浏览器记录prepare/publish阶段及原目标，不接受任意URL；原修订published视为已确认回执，superseded或身份不符禁止发布。未知首次PATCH不自动猜结果。原schema文件未改，此可选头部的全局语义记录于本契约。

## 2026-10-23 NEW-A16出版版本检查

- 既有GET /api/catalog/admin/editions/{edition_id}/publication/history/支持view=review；旧默认数组及view=desk保留。PublicationDesk.review新增nullable强类型PublicationReview（current、保存人/时间/说明、前后文件页数、关联对象增删、五项实际状态与修正入口）。desk默认review=null，review模式不写数据。
- 原GET /api/catalog/admin/page-preview/editions/{edition_id}/可携version与fingerprint；任一存在即要求两个都匹配，返回前后分别核对，不匹配409 publication.changed。X-Editor-Owner不符403；保持CanViewEvidence及private/no-store。此既有端点未新增到226路径契约覆盖，参数与返回沿原手写PreviewPayload同步，本节记录覆盖边界。
- 发布仍POST原WorkMaintenance publication，携edition_id/action/prepared_fingerprint/expected_version/confirm_warnings，未知结果保留原JSON与目标后显式重试。没有新业务路由、数据库表或迁移。
- 前端旧path itemId默认为UploadItem，经原intake上下文解析Edition；?object=edition显式指定Edition，?view=history读取该对象原历史，无列表分页依赖。不能根据UUID长相猜实体类型。

## 2026-10-22 出版版本发布台

原GET editions/{edition_id}/publication/history/增加view=desk、page、revision、impact_page。无view沿原最近50条数组；desk为PublicationDesk，20条历史分页、选定历史摘要差异、现有prepare/publication状态、影响与FileImpactOutput、最近20任务。revision严格属于选定Edition，非法页码400、错误对象404、读取过程中版本变化409。API路径226保持。

原rollback请求增加可选expected_version；维护发布/撤回同样接受该参数，新UI始终发送。保留旧调用兼容，旧流程仍沿其既有保护。恢复幂等回放核对actor/Edition/历史版本/reason，先回放再CAS；发布仍用prepared_fingerprint回执。X-Editor-Owner保护history/prepare/rollback、WorkMaintenance publication及knowledge status/retry；private,no-store。权限仍是CanPublishWork/CanWithdrawWork及原任务发布能力，没有降低权限或新模型。

## 2026-10-22 文章发布检查与素材修正

原GET admin/recommendation-issues/{issue_id}/preview/?review=true&edit_version=返回IssuePublicationReview（checks/changes/当前与草稿修订/时间/can_publish/reader_preview），非review沿旧响应。生成契约IssuePreviewResponse为两种响应联合。原preview此前不在schema_urls覆盖中，本批补入，旧225路径全保留，共226；实际catalog路由没有新增。read权限CanAccessBackOffice，发布CanPublishAuthority；private,no-store及X-Editor-Owner沿原保护。preview POST仍只读。

原媒体collection增加可选rendition_id UUID过滤，准确找回所选图片素材；原PATCH使用expected_updated_at，原renditions POST生成带immutable metadata_snapshot的新版本。collection/upload/detail/renditions补X-Editor-Owner核对。权限不放宽，无迁移；此前图片快照不变。

## 2026-10-22 关联选材与提纲审阅

原sources GET增加related=person|node；结果含reasons及edit_version/truncated/unavailable_count/notice。来源公开校验、CanEditMetadata和private,no-store保持。候选增加可选level(0–3)、target_block_id、original_text；正文增加heading_level(1–3，仅标题)，旧块默认一级。采用仍走原CAS追加与幂等回执。225路径保持，OpenAPI/schema.ts同步生成，0错误/10项既有警告；严格--fail-on-warn检查未标通过。


## 2026-10-22 来源信息与真实缩略图接入

原source字典增加只读authors/image_url/publication_year/publisher/section，前端IssueResolvedSource同步；无新增路由或serializer字段，225契约结构不变。准确版本名称与媒体走已发布snapshot；原文作者复用ContributionProjection.for_range，整书作者仅edition_author_projection，原文reader_url含页码及document_revision_id。未公开资料缺少公开图片/署名时不回退新草稿，不把来源展示信息接受为可写正文。

## 2026-10-22 PDF128–130选材与助手第一批（部分接入）

原issue DTO增加仅后台selection_workspace(question≤4000/query≤200/filters/references≤40)，materials只读重新解析，回传忽略；公开/列表剔除。范围继续原Discovery规范，拒绝access等越权条件；主题/理论规范slug支持再保存。

原sources GET增加id/document_revision_id用于准确引用核对。原assistant POST命令增加dismiss、edits(id→文字≤6000)、task_token；采用/忽略必须request_id，重试/取消保留旧调用兼容。响应增加dismissed_ids/question/created_at/updated_at/created_by/task_token，failed+stage=partial可保留完整候选供采用。

225路径全部保留，CanEditMetadata、owner header/private,no-store沿原权限。所有写入沿RecommendationIssue/EditorialRevision/AuditEvent和ProcessingJob，无schema迁移。公开文章绝不包含策划问题/内部选材状态。

## 2026-10-22 就地富文本输入

沿用c79756e的text/text_marks/text_style与225路径，无新增接口、模型字段或迁移。客户端固定格式的DOM只用于输入，保存仍只发送UTF-16位置和纯文字。撤销为本块50步本地输入历史，不替代后端正式修订历史；中文组合输入结束前不提交保存。

## 2026-10-22 PDF127格式、素材建议与协作

IssueBodyBlock新增可选text_style(paragraph/ordered/unordered)与text_marks（最多200处，start/end为UTF-16边界，kind=strong/em/link，link只接受本站路径或http/https）。原格式缺省保留兼容；保存时同步裁切空白偏移，原始来源不接受改写。后端拒绝非整数/表情中间位置/重叠链接/非法地址，不存任意HTML。

GET catalog/admin/recommendation-issues/{id}/suggestions/，q≤200、kind(all/work/person/concept)、batch1–100；默认已保存关键词/标题，公开匹配，准确target/source/reason/key/token及edit_version/checked_at/has_more/notice。全部类型最多每类1项，分类型每批3项。POST同路径request_id+token：明确放弃候选，令牌绑定actor/issue/version/key/target，一小时有效，重放先查固定回执再校验当前版本；不保存文章。CanEditMetadata。

POST catalog/admin/recommendation-issues/{id}/presence/，session_id UUID、mode(editing/viewing/leave)，CanAccessBackOffice，editing另需CanEditMetadata。返回participants(id/name/is_self/mode/last_seen)、checked_at、expires_after_seconds=90、shared、notice。每专题最多100个短期连接，只保留身份/模式/时间；失联503，本地进程模式明确降级。全部继承owner header/private,no-store。无migration；225契约路径保留223。

## 2026-10-22 专题编辑器第一批

GET admin/recommendation-issues/{id}/history/：24项分页、真实revision/status/created_at/created_by/note/is_current/block_count。GET sources/：type/q/page/work_id/edition_id及node_type=concept，复用准确来源分页。GET原detail支持revision/request_id互斥，跨issue历史404、回执actor隔离。

PUT原detail可选request_id/autosave/restore_revision_id；返回saved_at/by/revision及request_found/applied_revision_id/is_current_revision。POST原preview仅重核body_blocks与restore_revision_id，返回同草稿DTO，不写入；其余字段仍显示已保存值，客户端只合并body与source_problems。CanEditMetadata写/来源，CanAccessBackOffice读；全部private,no-store；提供X-Editor-Owner且与cookie账号不同403。223路径保留221，生成类型同步。


## 2026-10-22 今日工作第一批

GET catalog/admin/today-work/，CanAccessBackOffice/private,no-store；q≤200、category(all/editing/intake/catalog/problems/publication)、kind(空/catalog/curation/processing)、state(空/draft/changes_pending/pending/running/paused/partial/attention/failed/ready)、owner(all/me)、ordering(±updated_at)、page≥1。非法值400。结果含完整counts、20项page/total_pages、checked_at、restricted、owner_basis、真实权限与稳定对象/任务来源、准确url/state/thumbnail。count为工作项，非去重馆藏数；各类别互斥，counts按其他过滤后的完整范围计算。

原 ingestion/processing-center/ GET支持task_id与task_source(processing_job/semantic_index_job)成对过滤；非法身份400，未找到返回空结果，不显示其他任务。完整GET新增VIEW_SYSTEM_STATUS；已有ocr_edition_id及ocr_monitor查看分支和原写权限保留。准确edition/work过滤继承原实现。

219静态契约路径保留此前218；生成类型已同步，不代表正式API验收通过。

## 2026-10-21 专题文章、私人书单与评论

GET catalog/recommendation-issues/?view=directory接q/topic(UUID或slug)/kind/curator/year_from/year_to/sort/page/page_size，标量条件保留逗号。PublicEditorialDirectory返回公开有效修订卡片、完整分页、类型/主题/策划者/年份选项和有界明确关联。旧无view模式保留。article_metadata包含kind、keywords、topic_ids、scholar_ids、reading_path_ids和公开策划资料；item.section_id只能指本篇稳定标题；image区块须说明/来源，可无图片。文章详情增加public_revision_id、curator、reading_minutes、related。预计时间明确估算；公开媒体按实际生效修订授权。

save-list GET/POST均要求X-Reader-Owner及request_id/public_revision_id，POST只复制公开Work清单，GET按原请求查回。响应owner_id、nullable id、title、item_count、saved、receipt、notice；删除后旧请求返回未保存，不复活。隐私saved_knowledge组增加reading_lists叶对象。

reading/article-comments/public/{issue_id}/ GET公开当前版本已审核评论，支持page/page_size和可选public_revision_id核对，不输出owner/审核人。article-comments/{issue_id}/ GET本人全版本列表，POST要求固定request_id、public_revision_id、byline≤80、body≤3000、confirm_public=true；均要求X-Reader-Owner。requests/{request_id}/ GET原提交回执，{comment_id}/ DELETE要求expected_revision。admin/{issue_id}/ GET审核分页、POST id/expected_revision/status(published或rejected)/reason，权限CanPublishAuthority。评论绑定准确公开修订，旧版不迁移；回执最少保留防重，私人接口no-store。隐私独立article_comments导出/删除组。0021未应用。

218路径完整保留原213。契约生成与静态类型通过不代表真实API行为已经验收。

## 2026-10-21 主题与独立私人动作

catalog/topics与slug详情保留原URL，响应改为明确PublicTopicDirectory/PublicTopicDetail。目录q/search、parent重复值最多20（分支并集）、discipline/subdiscipline/theory、sort、page/page_size；详情section、question_type、availability、reading、sort与分页。规范理论与旧流派分别按准确ID/slug匹配；错误分支不放宽查询。八栏目、准确版/原文、真实counts、无全文/明确待购/不可用及旧资料均有结构化字段。

admin/knowledge-preview/topic/{id}/ POST只读预览，body为parent与curation；curation支持规范问题/争论/概念、准确出版版本、ScholarProfile、ReadingPath、RecommendationIssue的UUID数组（一般最多200，issue最多50）及本主题featured_source_id。只覆盖内存草稿，正式视角不变，private/no-store，无任务或版本写入。管理topic集合只GET/POST，详情沿原草稿/发布流程；媒体库支持topic。

reading/source-follows支持topic_id稳定UUID，与scholar_id互斥；继续owner/CAS/request_id/回执查回。SavedTopic独立收藏：GET saved-topics/state/?topic=UUID&request_id=可选；POST saved-topics/command/传topic/saved/expected_version/request_id，要求X-Reader-Owner；返回owner_id/topic_id/saved/version/can_save/record/receipt。旧POST/DELETE同步命令保护，禁PUT/PATCH；撤下收藏只显示安全占位。

schema213路径完整保留205旧路径，0错误/10既有提示，生成类型同步。catalog0074/reading0020未应用；契约为静态结果，不代表运行验收。

## 2026-10-21 学者公开投影与私人关注

既有admin/knowledge-preview/{object_type}/{object_id}/纳入契约，GET仅在scholar支持featured_source_id和reading_path_ids未保存选择覆盖。前者UUID或空清除，后者单个逗号分隔最多100 UUID或空清人工关联；重复/未知参数拒绝。只修改内存中的草稿副本，继续受控预览与真实公开资料投影；自动路径关联和完整分页总数保留。异步选择变更取消旧请求，以本次选择的返回决定预览，错误保留输入并可重试。

catalog/scholars列表与slug详情保留原URL，新增明确PublicScholarDirectory/PublicScholarDetail，含真实筛选/分页、正式资料字段、作品准确版本与责任范围、公开知识/问题/事件/关系/主题/阅读路径。候选关系必须显式请求及双权限；目录curated_topics来自正式人工推荐，与related_topics分开。旧栏目和旧嵌入消费者保持兼容。

Contribution.scope输入为edition或chapter；章节必须给asset_id/document_revision_id/outline_revision_id/outline_node_id/title/page_start/page_end。公开scope附status/notice/reader_href；失效返回chapter unavailable与空chapters，不泄露旧身份。后台省略scope保持原值。

reading/source-follows增加scholar_id（ScholarProfile UUID）和by-request查回。命令响应owner_id/record/receipt，固定request_id及expected_revision，不自动重放401写请求；隐私清除后的回执不能重建记录。schema205路径保留原203，TypeScript生成同步。Discovery/library metadata保留warnings code/message，准确章节筛选不支持或超限会明确报错。0073/0019仅源码，正式接口验收未执行。

## 2026-10-21 公共路径与私人跟读

catalog/theory-system/reading-paths列表按q/search、topic、discipline、node、difficulty、page筛选；详情revision/compare_to选正式版本。PublicReadingPath含稳定stages/items、准确材料身份、available/no_fulltext/unavailable/withdrawn/revision_changed、明确替代书目、学习问题/争论/公开署名与最多50版历史。列表批量投影，既有公共消费者统一DTO；草稿预览仅编辑权限且无私人写入。

reading/path-follows列表/创建、UUID详情/进度/笔记/删除、by-path、by-request、copy-plan、upgrade-preview及upgrade要求X-Reader-Owner；写入request_id固定，已存在对象expected_revision，创建附expected_source_revision，升级附target_revision。返回owner_id/record/receipt。copy的普通reading-plans GET/PATCH/export也核对owner；PATCH新增request_id和item_minutes，旧模型生成入口不能再有损复制路径。删除后回执不重建资料。

本组纳入7条私人路径和2条既有管理路径，203路径完整保留原194；管理集合仅GET/POST，具体对象沿现权限。stage_groups有准确输入结构。schema与TypeScript生成类型同步；0072/0018尚未应用，正式接口验收未执行。

## 2026-10-21 图谱与私人视图契约

GET catalog/theory-system/graph沿原入口，center_kind四类、center slug/UUID、depth1–3、limit≤120、edge_limit≤300、多值node_type/relation_type、discipline、start_year/end_year、三态has_collection、selected_node、works_page及include_candidates。节点键kind:UUID，学者为ScholarProfile；边键实际模型名:UUID。正式边含方向、说明、来源状态和至多6条精确当前原文；candidate_edges独立最多60条，普通账户请求候选403且不泄露数量。返回真实截断、当前子图计数、筛选说明、12个准确公开版本分页；no-store并Vary Cookie/Authorization。

reading/graph-views列表/创建、UUID详情/更新/删除及by-request要求当前X-Reader-Owner。POST固定request_id/data；PATCH增加expected_revision；DELETE以查询携带nonce/版本。响应owner_id、record、receipt，分页20。数据白名单只允许名称、公开中心/筛选/选择/布局；候选不保存。保留最少回执，删除后旧请求返回deleted不复活。隐私沿saved_knowledge组新增graph_views叶对象。0017未应用。194路径保留191旧路径，生成TypeScript同步，正式接口验收待全量完成。

## 2026-10-21 时间线契约

GET /catalog/theory-system/timeline/继续原事件身份，支持topic/author/event_type多值、discipline/node、q、year_from/year_to、has_collection、sort、year、page、focus及related_to。结果包含当前24项分页和完整scope_count/year_groups（按year与event_types计数）/bounds；focus计算真实页。详情增加subject_edition、subject_status、evidence_source、related_events/related_count及knowledge_relations/knowledge_relation_count。事件与来源作品/版本/文件/修订独立，来源须当前授权Page逐字核对。

管理timeline新增date_precision、subject_edition；响应准确声明evidence_file、edit_version及editorial_revision。列表仅GET/POST，详情延续原读写/发布权限。兼容旧公共timeline保留并同步公开过滤和出处资格。Schema新增纳入3个既有时间线路径至191，原188全部保留，生成TypeScript同步。0071未应用，正式API验收未运行。

## 2026-10-20 子学科与真实目录

新增GET catalog/theory-system/directory：type/discipline/parent/q/page，公开真实父级分组与返回路径、每页20条、总数、直属子项数和循环截断提示。无效400、未公开筛选或越界404、真实空结果200。规范关系补source_node_type/target_node_type，不从名称判断概念类型。

既有subdisciplines列表改轻量9字段，featured=true/false在分页前过滤；详情增加公开关联、独立来源与阅读路径，works_page每页48，works_pagination返回count/page/total_pages。非法页400、越界404；同页core_works/works和关系来源一致，编排来源独立。详情discipline/parent可空，列表discipline仅公开id/name/slug。证据版与默认卡片版独立，准确asset/revision/page/edition_label随各自入口。

OpenAPI188路径保留原185路径，前端生成类型同步；没有重复运行路由、新迁移或实际数据修改。详见SUBDISCIPLINE_DIRECTORY_20261020。

## 2026-10-20 PDF45–49理论条目收口

既有content-placements/node/{id}公开响应新增public_detail：确认用法、真实归属、title/explanatory_object/period/context以及准确span/asset/document_revision/page/reader_url；来源失效只计unavailable_usage_count，不回旧正文。规范理论公开书目增加edition_id/document_revision_id/source_status，关系增加逐项复核evidence；has_works在分页前过滤。

新增catalog/theory-system/nodes/{slug}/citation提供当前公开网页条目引用；reading/saved-knowledge/{node_id} GET/POST要求本人X-Reader-Owner。POST为saved/expected_version/request_id，GET可按原request_id查本人回执；同nonce不同内容409，旧已应用回执不重建删除记录。privacy新增saved_knowledge全链；前端隐私写入固定owner且不自动重放401。0016未应用。

旧TheorySchool关系/旧图谱/旧时间轴也在读回时核对当前版本、文件/作品归属、页和访问范围。无可核定位的旧层级原文不公开；明确后台预览保持权限内信息。185路径保留此前175路径，OpenAPI/TypeScript同步；详细语义见THEORY_DETAILS_20261020。

## 2026-10-20 Reader OCR状态

GET/POST distribution/assets/{asset_id}/ocr-status提供安全状态及pause/resume；GET的request_id只查本人已发命令。普通GET仍按当前文件权限；写/查回要求管理能力、X-Reader-Owner、固定nonce、job_id/job_version、source_sha256及document_revision_id。job_version原样回传，不能重格式化时间。已处理内容分unavailable/awaiting_publication/published/admin_preview；没有公开OCR正文。新增1路径至175，原174保留，无新迁移，详见READER_OCR_STATUS_20261020。

## 2026-10-20 并读与独立校准

catalog/parallel的versions/segments/candidates共用激活快照/Asset/DocumentRevision和Discovery首推候选；分页最多20段/6候选，focus返回实际窗口offset，失效来源409。reading/parallel-tasks提供本人列表/详情/nonce查回及CAS保存，X-Reader-Owner必需，任务来源身份不可改。

parallel-calibrations分本人投稿、public和admin表面；书目或单条对齐范围显式确认，私人note/terms不投稿；review/publish/reject独立命令，公开按匿名权限重验且每页最多20记录。新增16路径至174，原158保留；0015只编写，OpenAPI/TS同步，详细payload与边界见PARALLEL_READER_20261020。

## 2026-10-20 Reader版本与私人记录

asset manifest返回PublicReaderManifest/轻量PublicReaderWork，选定Edition/Asset/Revision身份一致。明确次版本的详情、图片与原文定位独立核验自身公开资格，不再依赖主版；馆藏集合规则保持。SSR只按需转发访问cookie，禁止redirect。

Annotation增加可选request_id和加密标签tags；同owner同请求同内容幂等，冲突409，未知结果先查原UUID。PATCH不迁移来源。原annotations/bookmarks/progress/history共7路由纳入契约表面至158，不增加重复运行路由。生成TS已同步，0014未应用，详见READER_20261020。

## 2026-10-20 作品详情与版本

原works/{slug}改PublicWorkDetail，支持当前发布快照slug/Edition UUID；selected edition贯穿元数据/目录/图片。relations为7类真实公开关联预览（每类最多6），CatalogEdition新增access_state而availability保持原二态；不返回受限文件身份。公开图片新增edition_id并重验。共享目录链接使用发布快照身份。151路径未新增，schema与前端类型同步；细节与边界见WORK_DETAIL_20261020。

## 2026-10-20 Discovery逐版本状态

Discovery响应增加documents（状态/当前书目/原文数/最多6个公开版本/200上限标记）。新增POST remove-document（edition_id、expected_generation），仅本会话可见来源、原访问权限和幂等移除，运行中换代继续。新API路径共151，OpenAPI/TS同步；具体状态含义和权限见DISCOVERY_DOCUMENTS_20261020。

## 2026-10-20 公共检索与本人记录

GET /catalog/search/?context=global&scope=catalog 提供Work合并、多版本、同版本过滤、分面与年份分布，公开主版本和当前快照约束。原search其他分支保留，用anyOf描述兼容载荷。GET /reading/search-records/要求owner_id本人，分页最大20，读取不启用保留。

Discovery GET新增sort=relevance|year_desc|year_asc及当前来源bibliography/attribution、真实is_new/added_count；context返回当前书目和同书候选。取消恢复沿expected_generation，cursor绑定排序与代次。共享私人分页带X-Reader-Owner并关闭401重放；具体字段及边界见五份检索单元文档。OpenAPI新增2路径至150，原其他接口保留，生成类型同步。

## 2026-10-19 公共交互检查点

- POST /catalog/feedback/匿名回执；GET/PATCH /catalog/admin/public-feedback/及详情严格管理权限。GET /reading/source-status/匿名复核公开状态；source-follows列表/详情本人隔离，POST要求X-Reader-Owner、nonce与expected_revision。完整字段见对应单元文档。
- POST /reading/citation-preview/公开来源预览，selected_text唯一匹配到真实范围，复用citation_bundle。研究新建/选材增加expected_owner_id，选材增加request_id/note/notes，旧客户端兼容。公开预览不回传未发布或私有正文。
- Schema新增7路径至148，保留原141路径，明确反馈类别/状态/公开来源状态枚举和列表operation ID，前端生成类型同步。隐私分类增加source_follows。源码契约不代表联调或上线通过。

## 2026-10-18 公共导航

PDF18继续使用现有公开会话、GET /explore?q=、/account?section=settings与/logout行为，无新数据库/API。当前标签页仅保存允许的公共来源位置，30分钟到期；账户/后台/认证路径、未知参数、编码目录逃逸不进入返回链接。共享Dialog焦点恢复preventScroll。管理入口以access_back_office能力显示，原服务端权限不变。导航源码接入与静态检查不等于真实浏览器验收。

## 2026-10-18 文件工作台、OCR与私有预览

- 文件接口 `/catalog/admin/works/{id}/files/`、同作品editions、edition files/requests/generate-reader/adopt/rights/prepare-public/content/impact.csv 同步前端和命名serializer；GET/HEAD与Range复用原文件权限，写入使用修订+nonce。采用/公开准备各自明确确认，独立于上传和主版本选择。详见WORK_FILES_20261018.md。
- `/ingestion/ocr-workspace/{asset}/` GET返回真实页状态/筛选/来源指纹/修订和任务；POST save/prepare/apply/review/start/pause/resume/cancel按能力鉴权。人工正文与人工核验分别保存，策略实际传递原worker/provider。详见OCR_WORKSPACE_20261018.md。
- 本人稿件/私人来源的preview和preview-file接口按purpose、owner和代次隔离；预览生成/取消有独立CAS/nonce，下载前后重验，不能将派生PDF位置作为原DOCX精确页码。详见DOCX_PRIVATE_PREVIEW_20261018.md。
- 当前验证表面新增15路径至141；原126条路径内容未变。DocumentRevisionApplyModeEnum供页码/人工正文共享，避免同名mode产生歧义。schema及前端生成类型已同步，正式运行待验收。

## 2026-10-18 反证、资料操作与页码映射

- 研究轮次GET支持mode=all/search/counterargument及order=oldest/newest，在本人项目内解密筛选后分页。反证命题与条件合计最多1200字符；可选文本条件允许清空。decision支持confirm/clear、request_id、relation、note、attribution、scope_note、save_as_note；显式保存笔记与本人决定原子持久化，理由必填，request_id异内容409，旧决定留历史。
- `/reading/privacy/` GET/PATCH本人保留偏好、真实计数和任务，PATCH须expected_revision；`items/?category=&page=`返回真实对象revision。`operations/` POST仅导出或创建删除预览；`command/` confirm/cancel/retry按修订执行；`download/`再次核对本人资料、研究子轮次及公开来源。最多2活动任务、500项/25MiB，失败逐项保存，删除重试重新预览，取消不恢复已完成删除。
- `/catalog/admin/assets/{id}/page-mapping/` GET当前数据/候选/历史、可选revision_id；POST save/analyze/segment/restore/prepare/publish。携带expected_revision/source_fingerprint，写操作携带request_id，publish还需revision_id/prepared_fingerprint。候选不改变当前公开Page；采用有发布权限，公开文件复制正文解释并走既有发布。缺页只为元数据，双页最多两个标签，不生成不存在的物理页。公开Page/EvidenceReference新增printed_labels与printed_label_precision=spread/page/unknown，体检对spread保留页码待核对。
- 输入、State/Revision/Preview响应、枚举、API schema与前端生成类型同步。详情与保护边界见对应单元文档，正式运行和视觉验收仍待核实。

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

## 2026-10-22 管理跨对象搜索与异常工作提醒

GET /api/catalog/admin/search/ 使用TodayWorkPage投影，q≤200、kind(catalog/curation/processing)、state、owner(all/me)、ordering及page，20条一页；空q返回空结果。counts为当前q/state/owner下各类型全量数量，kind仅筛选结果页，不截断分面。包括已发布/已确认资料与历史任务。GET /api/catalog/admin/work-notices/ 返回count/checked_at/results（最多5条），当前failed/paused/partial才提醒。两者CanAccessBackOffice、private/no-store，处理任务仍需VIEW_SYSTEM_STATUS；编辑不可获隐藏计数。均只读、不创建任务/新索引。通知不存在伪造已读状态。
