# 公网业务核对记录

基线见 BASELINE.md。本文记录已读源码与只读运行观察，不是全站验收报告。唯一页面覆盖表为 COVERAGE.csv，API_CONTRACTS.csv 是其接口明细；自动提取的候选字段不等于完整契约。

## 已核实的共同边界

- 公网浏览书目、学者、主题及已发布内容；检索、PDF、下载须登录。匿名 HTTP 实测见 ANONYMOUS_HTTP.json。`common/permissions.py` 的 CanReadLibrary 及具体对象访问过滤仍是后端依据。
- 管理员、编辑、馆长能力不能仅凭页头“馆员”文字判断。`common/capabilities.py` 的能力矩阵见 ROLE_CAPABILITIES.csv；馆长判定使用配置身份，不等同于 superuser。生产账号及邮箱未导出。
- 读者操作通过 `web/lib/api/private-owner.ts` 在调用前后检查所属账号，切换账号必须清理旧私有视图。公开分享只能返回允许分享的投影。
- 公网已启用的语义检索、连续研究和本地助手保留。新 Intelligence Demo 不在本轮范围。开关为真不证明模型、索引或远端服务可用；必须保留未配置与失败状态。
- 公共页面请求使用 no-store。公开书目不能因过期会话消失：loadWork 在会话 401 后退回匿名书目读取。404 与服务不可用分开处理。
- 公网写入未执行。保存、发布、OCR、模型任务、权限、删除、恢复等只读源码核对，之后在独立测试环境验证。

## 网站文案与欢迎页

入口 `/admin/about`、`/admin/about/preview`、`/admin/welcome` 使用 SiteContentEditor / SiteWorkspace 与 useSiteContent。

- GET/PUT `/catalog/admin/site-content/`，POST `publish/`、`restore/`，GET `preview/`、`sources/` 与操作回执入口。详情以 API_CONTRACTS 和 view/service 源码为准。
- 共享草稿包括欢迎、首页、关于、帮助使用说明、导航和页脚。保存草稿与整份发布分开；其他编辑者的变化不能被隐蔽发布。
- 草稿标识 edit_version，写入带 Idempotency-Key 和 X-Editor-Owner；超时保留请求身份，可查询回执或重试原请求；409 保留本地输入，明确选择远端或本地。历史恢复生成新草稿。
- 预览复用实际 HomeFeatureStory、HomePublicView、AboutPublicView、SupportHub、SiteHeader、SiteFooter，并读取相同草稿。不能另造演示卡片。
- 欢迎三组文案同次停留不轮播。标题每行24、引言160、提问60、结果/原文标题24、保存提示40；可跟随公开推荐前三本或自选最多三本。来源撤回显示不可用，不伪造书目。
- 首页精选/学者/主题选项各最多5，关联对象、图片、标题40、说明80、可见性和顺序均需映射预览。关于与说明正文属于实际长文本编辑。
- sessionStorage 保存的是操作回执身份，不代表未保存正文可以刷新恢复。切换面板/预览与离开页面的行为要分开验证。

## 作品与版本详情

入口 `/works/[slug]`，`loadWork → GET /catalog/works/{slug}/ → adaptApiWork → WorkDetailView`。版本 slug 与版本 ID、作品 ID 含义不同，不能合并。

- 图书：原作信息、当前出版版本、责任者、封面、简介；版本表、章节、相关著作/概念/策划/路径、研究资料。文章：刊名卷期页码 DOI、摘要与引用、参考文献入口、本期目录；与图书布局需分别设计。
- 版本操作包含阅读、下载、引用、版本详情；全局收藏、书单、公开链接分享。无全文仍可浏览书目，不能把缺文件当作页面失败。
- 章节责任者与全书责任者分开，保留 outline_revision_id / outline_node_id / document_revision_id；来源失效有 notice。
- 封面弹窗、公开链接复制成功/失败、引用弹窗、书单弹窗必须登记。公共分享链接不带私人笔记。
- 窄屏图书使用分节展开；`#citation`、`#scholars` 会激活相应内容。对象/草稿版变化重新定位；不能声称所有标签刷新保留。
- 管理草稿预览复用 WorkDetailView，但明确已保存草稿版/冲突；不允许在预览中执行公共收藏、引用、下载。后台 PDF 有独立权限入口。

## 学者与主题

- 学者目录实际读取 `/catalog/scholars/`：q、field/period/school 多选、sort(relevance/name/birth/works)、page；view/layout 只控制前端。返回 count/page/page_size/total_pages/next/previous/results、facets、recommendations、curated_topics、related_topics。目录/推荐、网格/列表、窄屏筛选弹窗分开。
- 学者详情与分节读取 `/catalog/scholars/{slug}/?section=...`，保留 overview/works/concepts/questions/timeline/relations/topics/paths/sources/evidence。责任者角色与章级范围、关系方向/类型、来源页、公开版本和候选权限有实质差异；不能仅换标题复用所有分节。
- 主题目录 `/catalog/topics/` 包含父级、多父级、学科、子学科、理论筛选、排序与分页；有层级、重叠/消歧说明。
- 主题详情分节 questions/works/scholars/concepts/articles/paths/evidence；历史、维度、方法等前端分节读取 overview，recent 设置 published 排序，evidence 默认每页1条。保留 planned/no_fulltext/available 与 unavailable_links，不能将“计划收录”画成可阅读。
- 公开对象数据与编排区块分别加载；PublishedPlacements 的对象类型和对象 ID 不得丢失。

## 当前公网只读界面观察

2026-11-10，使用新建 Edge 核查标签，未操作用户原有编辑标签、未提交表单。已观察 `/`、`/home`、`/admin`、`/theories`、`/scholars`、`/topics`、`/recommendations`、`/help`、`/about`、`/register`、`/reset-password`。

- 目录与帮助正常呈现主要标题和真实筛选/搜索表单。注册有 email/username/password/confirmPassword/条款同意；恢复页面有邮件入口和人工恢复申请，未发送邮件。
- `/login` 一次观察未读到主表单，原因未定位，不记为成功或产品缺陷。
- IAB 访问根页一次得到 Cloudflare 502；同时 Edge 根页及12个匿名 API 请求可达，不能将该观察扩大为全站宕机。
- 读者与管理数据不导出，不保存含私人内容的截图。尚未逐页运行观察，尚未验证写入。

## 读者笔记、书单与连续研究

- 笔记工作区 `/account/notes` 和文件限定 `/account/notes/[assetId]`：GET `/reading/notebook/` 的 q/kind/order/booklist/work/project/start/end/asset/page，记录详情 GET/PATCH `/reading/notebook/{annotations|bookmarks}/{id}/`。选择本页、分页后清除选择；编辑期间防止换记录。书签添加笔记有独立 POST 与请求回执。
- NotebookRecord 同时保留保存时摘录 saved_quote、本人 body/tags/label 和当前来源 source_status。来源撤回不删除本人文字。来源预览与回原文、复制引文、PDF/Markdown/BibTeX/RIS 导出、加入研究、删除为不同操作。owner_id 响应身份必须核对。
- 书单目录 GET `/reading/lists/directory/`，详情 GET `/{id}/workspace/`，独立 `command/` 和 `receipt/`；title/description/goal/tags、主动主题关联、作品顺序/移除/恢复/清除、计划、笔记、相关主题学者和导出均存在。移除书单作品不删除独立笔记或馆藏。
- 书单 tab 写入当前 URL，其他搜索/分页在组件状态；不能承诺刷新自动保留全部筛选。未确认写入时保留 list_id/request_id，阻断重复操作，读取回执；400/403/404/409 与未知网络结果分别处理。
- 连续研究基于 `/reading/research-projects/`、`research-turns/`、`research-memories/`、`reading-plans/`、`citation-audits/`。PrivateRecordViewSet 按 user 或 project.user 过滤，职员身份不扩展私有可见范围。
- ResearchRecord 返回 id/revision/data、状态、generation、error_code、poll_after_ms、真实 completed_units/total_units、时间与归属。项目问题/范围/选材/笔记、比较维度、确认记忆、计划是不同数据与命令，不可用单个“保存”掩盖后果。
- 引文体检先查询 capabilities：检查项、上传/页数上限、OCR/分析可用性；上传 PDF/DOCX、选已有私人来源、新版本与仅核对改动均有实际接口。解析、匹配、人工版本关联、decision、重试/取消/分析分别有命令；不生成虚假任务进度。
- 私人来源 `/reading/citation-sources/` 具有独立原件与解析任务；公开馆藏版本与私人来源的标识、generation、定位不得混用。

## PDF 阅读器

- manifest 核对 asset_id、edition_id、work.edition.readable_asset.id 同属一个来源，否则返回分类失败。保留文档 revision、PDF 页与印刷页两套定位。
- ReaderRecords 同时完成本人 annotations 与 bookmarks 所有分页后才发布记录快照。失败/停止不等于空记录；`p` 是两类原始记录接口的分页参数。
- 选文笔记保存带 request_id、asset/page、quote/body/tags/color 和 selector 精确文本/页码/框；未知写入结果核对回执内容，不能凭 UUID 就显示成功。
- useReaderProgress 在阅读650ms后依次 POST progress/history。因此本轮没有通过生产 PDF 阅读器验证翻页/选文，以免改变私人历史；需要隔离测试环境。

## 编目与目录工作区

- `/admin/cataloging/[sessionId]` 先读会话；published/abandoned 显示结束，尚无作品版本显示处理未就绪；有效会话与馆藏维护都进入现有 WorkflowEditor。`/candidates` 参数只展开材料助手，不是另一套编目。
- 真实九段是 file/work/bibliography/contributors/classification/knowledge/reader/curation/publication；hash 保留段落。图书、文章、整期期刊、学位论文、报告、章节、其他资料的书目字段和必填项不同。
- 作品必填题名、文献类型、语言；整期期刊还要求刊名、年份、卷、期，目录论文不可重复；学位论文要求授予单位；报告要求责任机构。责任者需要名字、角色及确认的人物关联，章节责任另行处理。
- WorkflowLivePreview 使用当前 drafts 投影并复用 WorkDetailView，封面单独按版本权限读取。已发现一个明确的现有预览缺口：`workflow-live-preview.tsx` 将 journal_contents 固定为空，且没有投影 work.journalContents；因此编目中修改本期目录不会在相邻实际预览显示。仅登记为本轮字段预览需补齐项，尚未修改业务。
- `/admin/library/assets/[assetId]/outline` 是单一目录校准工作区。树/编辑/PDF、目录搜索、未确认/同页筛选、节点移动/增删、标题/物理页/印刷页/坐标、保存correct、重新识别、任务取消/重试和派生下载都需保留。
- 目录数据包含 active/latest/expected_revision、document_revision_id、来源是否current以及真实job状态；保存修正不等于派生下载已完成。源撤回禁编辑/重建；并发版本变化要保留本地节点并显式处理冲突。
- 区块编排 placements 与父对象草稿不同：位置、分组、reason/local_text、来源与阅读锚点单独版本管理；保存、发布、撤回、历史恢复、仅发布确认来源有不同命令。

## 知识对象、学科与阅读路径编辑

- 学者列表/详情使用 ScholarWorkspace，列表 search/page/editorial_status；新建可绑定既有人物。基本姓名、原文名、异名、生卒、传记、简介、国籍、职业、机构、关注问题、资料来源、必读/推荐作品及理由、选定引语和阅读路径属于实际字段。人物权威记录与学者公开资料并非一个实体。
- `scholar-preview.ts` 将当前输入投影到 PublicScholarDetail，选定作品/路径/引语通过受保护预览接口核实，不能靠名称猜来源。人物关系、事件与概念使用来自独立正式关系，不将历史自由文本升级为已确认事实。
- 主题 `topic-preview.ts` 使用当前文字和服务端核对的 curation/parent；支持问题陈述、形成背景、核心问题、维度、方法及既有时间线格式。已选来源撤回与不可读仍需表现。
- 理论/概念/争论/研究问题的 NodeDraft 含中英文规范名、slug、异名语言/类型、概述、定义、问题、基本命题、理论边界、起止年、时期、父级、主/相关学科、子学科、主题、状态、排序和内部说明。字段/概念用法/关系/材料/影响/历史/预览/原文策展分组有不同写入边界。
- 知识预览 GET/POST `/catalog/admin/knowledge-preview/{type}/{id}/` 绑定编辑账户和 edit_version；版本中途改变返回409。发布检查 `review=1` 必须绑定已保存版本，不接受未保存覆盖。类型不匹配返回404。
- 学科草稿含 code/name/foreign_name/slug/search_aliases/description/introduction/sort_order/curation_level/editorial_status；子学科还含 discipline/parent/research_object/core_questions/formation_period/research_directions/methods/representative_issues。换所属学科清空父级，自身不能作父级。图片另行上传为草稿选择，不直接覆盖公开图片。
- 阅读路径实际字段包括标题/slug、引言、学习目标、受众、难度、估计阅读量/周数、学科、主题、前置说明、策划说明、署名、学习问题/争论；阶段含名称/说明/时间，材料含 work/node/edition/asset/document_revision、页码范围/章节/印刷页、必读、学习目标、推荐理由、先修依赖、替代版本及撤回状态。
- 路径 `validate/` 与 `preview/` POST 不保存。预览字段标题/slug上限240、引言50000、学习目标10000、受众240、估计阅读120；返回 PublicReadingPathSerializer，先后核对 edit_version。客户端450ms延迟且旧输入请求取消；不能用前一对象结果替代正在加载的预览。
- 现有知识表单会保持隐藏字段挂载；切到原文策展/关系时具有独立 dirty/pending/composing 保护。发布回执未确认时锁定相关操作，不能为排版删除这些状态。

## 策划项目和文章

- `/admin/recommendations` 默认是已部署 CurationProjectWorkspace；`view=home|legacy` 使用原 RecommendationIssueList。项目筛选 q/scope/page、project/articles_page/tab 写在URL；articles/materials/missing/settings 为不同面板。
- 项目有 title/question/introduction/visibility/collaborator_ids/cover_rendition_id/planned_for，以及 create/save/duplicate/archive/restore/create_article/attach_article/reorder。项目设置、文章草稿与文章公开不是同一个事务；归档项目不可继续编辑其文章。
- 文章 `useIssueDraft` GET/PUT `/catalog/admin/recommendation-issues/{id}/`，字段 id/slug/title/issue_label/introduction/public_byline/display_from/article_metadata/cover、body_blocks、items。既有选材工作区只保存 question/query/filters/references，不缓存解析原文。
- 当前文章支持10秒自动保存草稿，中文输入法组合时暂停；manualRequired/conflict/pending/recovery/权限变化分别阻断自动保存。保存前固定request_id与body，未知结果先查原保存，不重复创建计划条目。
- 当前文章的 sessionStorage 与网站文案不同：按owner/issue绑定24小时可编辑字段草稿与请求恢复；不保存cookies、原文解析、任务输出，丢权限会清除。这项真实恢复能力需保留。
- 块类型和计划作品/已上架作品不可混同；关联具体公开版本要求确认，移除文章选材保留馆藏。公开文章评论审核也属于现有编辑入口，字段和运行状态尚待后续闭合。

## 文件处理、OCR 与页码校准

- `/admin/processing` 默认进入 ProcessingWorkspace，`surface` 非 documents/overview 时仍进入 LegacyProcessingCenter；旧视图仍可达，不能因默认布局变了就删掉。新队列支持文件分组和任务历史、q/type/status/date_from/date_to/edition/work/file/batch 与 selection/detail_tab 参数；不同 source 的同一 UUID 不能混作一项。
- 任务详情实际有 progress/file/results/issues/logs/settings；手机使用 Dialog，桌面使用相邻详情。结果导出、失败页选择、后续概念对齐、节点转移及超时恢复为独立组件。服务端 actions 决定按钮，不从状态名称自行推导权限。批量操作逐项执行，保留未完成选择与未知结果回执。
- `/ingestion/processing-workspace/` command 绑定 X-Editor-Owner、request_id、job_id/source/expected_version；pause/resume/retry/cancel/recover/configure_followup/retry_followup/transfer 分别校验。任务心跳不使同一投递的命令版本失效；转移须 target/target_version/acknowledge_remote，不得把公网未启用的 remote worker 画成可用。
- 新建任务仅既有 OCR/outline，asset_id/source_version/confirmed 必填；OCR 可选择 page_indexes、语言、布局、质量阈值、跨页/乱码检测、跳过已核验及后续概念对齐。未配置、已有活动任务、来源变化与权限拒绝分别反馈；不在生产探索这些 POST。
- OCR `/ingestion/ocr-workspace/{asset}/` GET 包含 pdf_page/list_page/history_page/status/quality_threshold/detect_spreads/detect_garbled。工作区为页图与结果、问题列表、全文对比、设置、修改影响；当前8页缩略图、跨页选择最多200项人工核验，文字输入与页图相邻，换页有未保存保护。
- OCR save 保存候选，prepare 只读核对 revision/fingerprint，apply 才采用；已公开材料通过正式发布任务更新，稳定旧版仍可阅读。save/prepare/review 要 EDIT_METADATA，apply 要 PUBLISH_WORK，任务动作要 RETRY_JOBS。人工核验不等于 OCR 任务成功。text 最多200000字符，note最多2000；确认修订与重做识别必须保持不同操作。
- 页码校准 `/catalog/admin/assets/{asset}/page-mapping/` 当前页面标签、分段、缺页说明与历史独立。每物理页最多2个40字符标签，page_type 为 front/body/appendix/other/blank；分段 Arabic/Roman/custom/none；缺页 mark/blank 区分仅注明与派生补页。保存、分析、分段、恢复、准备影响、发布和导出由不同 action 处理。
- 页码校准当前表8条分页、分段/搜索/未确认/重号筛选、批量编辑、重号确认、缺页弹窗、撤销本次本地编辑、历史恢复和 PDF 页图均存在。expected_revision/source_fingerprint/prepared_fingerprint 防止对变化来源采用旧预览；副本生成、取消/重试与下载可用性使用真实 jobs。

## 配置、账户与隐私

- `/admin/settings` 实际是 LocalServices；历史 hash 映射至备份、网站文案或 `/admin/processing/settings`。服务总览/模型服务/检查日志/配置管理有 available/partial/offline/model_unloaded/not_configured/disabled/quota_exhausted/untested/stale/changed，不能将配置已存或旧记录当作当前可用。
- 模型配置 `/reading/admin/ai-runtime-profiles/` GET/PUT/PATCH，active/profile 的 capability/provider/model/enabled/temperature/token/timeout/input/retrieval/answer/fallback/reasoning 字段影响下次任务。配置版本并发校验，未知保存先查询/阻止旧版本迟到请求；凭据原文不回传，提交后清空内存输入。敏感地址/凭据别名受 owner 权限限制，HTTPS 才可录入密钥。
- OCR 配置 `/catalog/admin/ocr-runtime/` 与研究来源注册 `/catalog/admin/research-sources/` 分别保存、检查。检查不等于保存，旧检查可能过期/配置变动；服务检查有 request_id/configuration_version 和回执。系统配置需要实际作用说明，不伪造读者页预览。
- `/admin/processing/settings` 保留 OCR/AI/检索/提示词/读者投稿邮箱；`/admin/backups` 复用 SettingsAdmin 的 backups 范围，destination_path/include_originals 提交真实备份任务，记录任务/归档/校验值。投稿邮箱只改变读者自己的邮件应用入口，不等于启用自动邮件。
- `/admin/distribution` 保留 S3 provider 名称、endpoint/bucket/region/public_base_url/credential_reference、启用/默认、预算阈值与通知邮箱；密钥来自部署环境，表单只存引用。实际用量录入 period/egress/cost 的来源为 manual entry，不能设计成实时云账单。
- `/auth/users/workspace/` 账户目录 q/role/state/page/page_size（10/20/50）及 user_id；独立 roles/history/preview/command/receipt。新建、修改、改密码、邀请和撤销邀请分别有输入规则；用户名4–20、显示名120、密码10–128，修改现有账户不提供改用户名/邮箱。
- 账户变化必须先用原输入获取 preview_hash，再确认执行；显示保留/新增/失去的能力、激活后能力及会话撤销。只有馆长可分配 reader/editor/admin，不能授予馆长；不能停用自己或改馆长受保护字段。密码仅在当前弹层内存，sessionStorage 仅最少请求编号。
- `/reading/privacy/` PATCH 保存六类 retention，`automatic_memory_use` 固定false。导出/擦除先建 preview operation，再 confirm；状态 preview/queued/running/completed/partial/failed/canceled，cancel/retry 和 revision 独立。GET 任务会关闭失去活动的旧任务，因此后续运行核查应使用隔离环境。
- 导出 JSON/ZIP/CSV 由当前本人任务下载，folder 为安全上下文文件夹选择并逐项保存，部分本地写入有 incomplete manifest。下载核对 owner/operation/MIME/count，来源变化和失败项保留；擦除范围按 category/id/revision 展示影响，不把删除本人记录误作撤回公开来源。

## 分享、小组、来源订阅和确认笔记

- 分享来源仅已存在的 research/booklist，选择 questions/materials/notes（各最多20项），最多4个附加来源；目标 group/public/proposal。分组目标还校验 group_revision/member_ids，附言200字，有效期1–365天。preview 与 create 分开，创建绑定 preview_hash/confirmed/request_id。
- 公开摘要链接只把分享密钥放 hash，经 X-Share-Key 请求 `/reading/share-links/{id}/`；不在URL query、日志或 Image Gen 中复制密钥。分享撤回使链接/接收范围/通知失效，原研究/书单/笔记保留；策划提案状态修改不会自动发布原内容。
- 小组 `/reading/groups/` 有 campus/team 两种既有类型、创建/改名/归档/离开/移除成员/邀请/撤销邀请及接受邀请；邀请只允许指定账户接受，加入小组不自动获得未分享的私人内容。目录、邀请和成员单独分页；未知写入只保存请求编号与 group_id，不缓存邀请内容。
- 来源订阅 `/account/source-updates` 读取 source-follows 分页及各记录 history_page；显示撤回/变化/不可用、未读数、暂停保存更新、检查失败。取消/标已读/删除分别保留原请求恢复；历史是观察到变化的时间，不伪称确切发生时间。订阅不自动发信，不保存原文正文。
- 已确认笔记 `/account/confirmed-notes` 有 understanding/question/contradiction/concept/method/observation 类别及 confirmed/proposed/ignored；搜索、来源、排序、分页、选择、原文详情、使用授权和导出是不同操作。`memory` 参数定位对象，列表其他筛选为组件状态；仍需完成 usage/保存服务与主研究工作区对应。

## 探索、理论浏览及兼容入口

- `/explore` 先核对读者身份，支持 exact/semantic/ask 与作品、学者、学科、子学科、理论、主题、阅读路径范围。类型、语言、年份、作者、权限、排序、重写与多值筛选保存在 URL；无查询时是入口，不能画成伪结果。`/explore/ask` 复用 ask；opinions 有查询时跳 evidence，无查询保留范围选择。
- DiscoverySearchWorkspace 创建 POST `/catalog/discovery-search/`，后续 GET 结果用 X-Discovery-Token/cursor/limit/sort；expand/cancel/retry 带 generation，context 按 result_id。移除材料核对 edition/generation，来源改变后不能保留过期原文上下文。候选、已读取、失败数量均来自响应。
- 理论目录 `/catalog/theory-system/directory/` 按 type/discipline/parent/q/page 查询，选中后读取规范节点或子学科并校验类型；不可用与请求失败分开。关系图是已部署业务，graph/list/topics/scholars/works 模式、中心/深度/节点边上限/关系/年代/馆藏筛选和缩放位置由 URL 保存。不是本轮新增关系图。
- 时间轴有事件类型、年代窗口、精度范围、不详年代、分组与分页；详情独立请求。`/theory-schools/timeline` 为兼容消费者。概念及旧流派路由先核对类型/canonical URL 再跳转；无规范对应时保留 LegacyTheoryPublicView 与 works/concepts/scholars/neighbors/concept-map/reading-list 子页，不擅自删除。
- 子学科列表的精选区与全部结果独立分页和失败反馈；筛选为 q/discipline/page/featured_page，不把任一区请求失败显示成空库。

## 读者中心、计划与连续研究细节

- ReaderOverview `/reading/reader-center/` 使用 kind/q/order/visibility/page/overview；筛选保留 URL，列表/卡片视图为本地偏好。材料选择最多500项；重命名20项、归档恢复100项；私人研究和体检从原工作区删除，其余擦除由隐私 preview/confirm 处理。
- 阅读计划输入 goal/background/base/read_book_count/budget_minutes/session_minutes/weekly_minutes/duration_weeks/language/memory_ids。约束见 API_FIELD_CONTRACTS：阅读基数不自动等同理解程度，私人笔记须明确选择，最多40条。详情 overview/materials/questions/settings，材料 pending/reading/completed/skipped；建议采用、增强、手动编辑与来源修订分别处理，保留打印/导出。
- 阅读路径跟读 by-path/by-request 查询及创建、状态/书签、删除、复制计划和升级预览是独立入口；expected_source_revision、目标修订、request_id 不可省略。公开路径变化不静默覆盖个人计划。
- 连续研究按本人项目读取分页 turns，退出登录清除；404/410、409 与暂时失败分别处理。范围 saved/selected/library，材料候选有类型、关键词和年代/标题排序；草稿和未知请求回执按 owner/project/turn 保留。比较最多20个维度、单元格笔记8000字符、引用最多400项；生成维度草稿与采用动作分开，不把模型输出当已确认笔记。
- 研究回放支持时间/树、轮次比较、材料/笔记/比较/快照/证据；历史快照与当前来源变化分开。分支复制选择来源/问题/是否带笔记并核对 turn/project revision，不静默复制未授权材料。

## 馆藏文件、存储和媒体

- WorkFilesWorkspace 包含 versions/files/impact/rights/publication，edition/page/impact_page/history_page/tab 保留 URL。切换版本关闭旧弹层并重置对象选择；文件采用先 GET 影响预览再 POST。新版本、补充/替换文件、生成阅读副本、权利说明和公开准备分别有 request_id/expected_version；保存权利说明不会自动授予公开权限。
- 文件接口 `/catalog/admin/works/{work}/files/` 与 editions/upload/adopt/generate-reader/rights/prepare-public 共同工作，PDF 正文以已鉴权文件入口下载；HEAD 检查 MIME/大小/ETag。生成中的副本不能显示成可下载；影响 CSV 有大小限制。
- 存储 `/distribution/storage/` 有 backups/verifications/rehearsals/failed、page/status/asof，备份、归档校验、恢复计划、关闭失活任务、计划/保留设置、清理扫描/排队/取消分别校验 expected_version。恢复计划不等于执行恢复。回收站另有来源类型/状态/操作人/原因/日期筛选，批量最多20项、恢复预览与 keep_separate，保留历史和原请求回执。
- 素材 cover/recommendation/portrait/hero 与作品、学者、知识节点、路径、学科、子学科、主题分别映射。当前/PDF/上传/复用为独立来源；alt_text/source_label/source_url/rights/license/credit 与 crop/display_uses 保存同一对象版本，保存/恢复/清除/历史采用互不替代。
- SavedMediaPagePreview 读取 include_preview=true/expected_version，对 owner/object/type/version/受保护 URL 逐项核对；iframe 只允许对应 `/admin/preview/works` 或 `/admin/preview/knowledge`，收到同源版本确认才显示已加载。支持 fit/1280/390，超时显示未确认，不假称失败或成功。这是已保存完整页；即时裁切修改仍在原工作区，设计须清楚标明二者状态。

## 反馈

- 公开反馈 category 为 content/function/usage/suggestion/other，正文、可选联系、公开页面地址和明确 consent；请求 UUID 未确认时重试原输入。safeFeedbackPath 排除私人/管理/token URL，只保留公开路径及 PDF 物理页；退出登录清空输入。
- `/admin/support/feedback` 要 can_manage_users，q/status/category/page/item 写 URL；submitted/reviewing/resolved 数量与过滤一致。处理字段 status/note/follow_up 只供管理员，标记待回复不发送邮件，找回账号材料也不等于已核实身份。切换对象有未保存/处理中保护。

## 业务盘点闭合范围

当前源码设计输入已闭合，门槛记录见 BUSINESS_GATE.json。157项分别为130个业务/共享模板消费者、19个兼容跳转、3个全局状态，以及5个明确排除或未启用入口。每个有效消费者关联自身操作笔记、UI控件、字段和API契约；共用组件不作为运行验收证据。177处动态调用均补调用方或服务端动作描述来源，未将其误计为177个未知业务接口。

生产观察、隔离角色GET与少量实际交互已单独记录。完整保存、异常恢复、窄屏、每个消费者及外部服务验证仍待实施阶段，不能将“可开始设计”解释为“全站功能已验收”。所有正式图和实现位置当前尚为空，设计覆盖门槛仍未通过。

## 引文体检、反证与独立研究入口补充

- 提交页先读capabilities；当前隔离环境实际呈现基础三项可用、扫描识别和深入分析未开放、任务为空。前端上传上限12MiB，私人来源最多4项；退出清除私人输入。
- 解析页有原稿、文中引用/书目、匹配来源三个区域；原文修正和原文件不同。报告25项本地分页，问题类别、条目、关系、定位与未核实筛选，人工决定及批量决定携带版本；新版本、仅核对改动、原稿下载、JSON与打印互不替代。
- 反证按项目和轮次读取，陈述、子主张、范围可另开轮次；每页12项，支持/不同结论/限定/证据不足/无关为现有过滤。模型建议、本人判断、确认记忆、个人笔记和选材具有不同写入边界。来源失效不能沿用旧原文确认判断。
- 研究目录active/archived/all及分页，焦点返回间隔30秒重读，只有queued/running才5秒刷新；没有目录全文检索输入，不在设计图中添加。开始研究沿既有意见探索入口。

## 理论、人物与时间线补充

- 人物权威库两入口 `/admin/people`、`/admin/scholars/people` 使用同一工作区但保留逐入口验证。标准名240必填、原文名240、国别120、简介10000、异名最多200、人物图文最多100；外部标识类别有命名约束。基本信息、作品职责、相似人物、历史分开；作品职责未完成时阻止换人物基本资料。
- 人物保存通过preview_hash/confirmed/request_id，正式人物、关联学者草稿、合并记录各有状态。关联学者存在待处理草稿时，正式人物编辑受限；相似不等于同一身份。未知结果只在浏览器保存请求编号，停止只取消尚未执行的请求。
- 理论节点即时预览将当前输入投影到实际公开展示组件；关系、引用和作品仍读取已核实正式来源。学者和主题预览支持POST草稿字段，发布前review=1必须绑定已保存edit_version。切换预览不应把保存与发布合并。
- 时间线即时预览复用TheoryTimelinePublicList，将当前事件和相关已存事件排列；日期精度、物理页与印刷页、来源版本、参与者和主要图像均有真实字段。作品版本卡使用当前选定edition。编辑、出处、预览为手机可切换面板，保存/发布/合并不同。
- 已发布关系改动经StagedRelationEditorMixin保存待发布修订；不是直接覆盖公开关系。最初请求published同样先建立draft和发布准备。原关系会员过滤兼顾正式端点与草稿端点，避免编辑后从列表消失。

## 隔离浏览器运行观察（追加）

- `/account` 实际呈现合成用户的继续阅读、资料分类、空计划与空资料。PDF阅读产生的历史只在临时测试库，未触及公网。
- `/account/citation-audits` 实际读回可用检查项、未开放检查项、来源范围和空任务，未上传稿件或触发模型。
- `/admin/theories` 打开合成理论，修改未保存的解释对象，切到页面预览后实际公开组件显示同文；切回基本信息仍保留输入。随后恢复原文本，页面重新显示当前版本已公开，未点击保存或发布。截图 `output/public-visual-20261110/screenshots/baseline-theory-draft-preview.jpg` 只含合成数据。
- 既有缺陷PV-FILTER-01：该目录前端API query使用node_type，后端_node_filter读取type，浏览器“理论传统”中实际混入概念、争论。位置 `web/components/theory-system-admin.tsx:455`、`api/catalog/theory_system_views.py:162`。必要修复是保持页面URL语义，正确转换请求参数；尚未修改。
- 理论列表与编辑区当前上下堆叠，打开预览仍需滚过整个目录。本轮布局目标是缩短寻找编辑和预览的距离，保留目录与当前对象位置关系。

## 确认笔记、评论和并读闭合补充

- 确认笔记由本人原阅读笔记创建，正文20000字，默认proposed且不自动用于研究。PATCH携带expected_revision；修改正文、类别或来源会撤销旧内容的研究/计划授权，默认重新待确认；history保留前内容。删除确认笔记同样撤授权，原阅读笔记保留。导出最多选择40项。
- usage/ GET只列本人project/plan，POST grant/revoke/revoke_all核对笔记及目标各自revision；已归档研究不能新授权，单范围最多40条。授权变更使计划建议失效，不能让旧建议继续显示已适用。使用范围弹窗显示当前目标、暂停、撤销单项/全部；不是全局自动记忆开关。服务 `reading/research.py:1087–1291` 与 `memory.client.ts` 已对应。
- 文章评论分公开、本人、管理员三条查询。署名80字、正文3000字、明确confirm_public，当前public_revision_id与request_id必填。服务端按本人每日最多100条；同请求重试不重复计数。本人可按revision删除，管理员按revision公开/拒绝/撤下且说明240字。旧版评论保留但不能公开到当前新版；公开响应不带账号私人资料。组件 article-comments、article-comment-review 对应 editorial_comment_views/editorial_comments。
- 阅读器保留实际PDF文本层、目录、缩放、定位、引用、下载、笔记和历史进度。引用按edition+pdf_page重新读取，换页立即使旧引用失效，复制失败提供可选文本。阅读偏好为本地motion/outline/highlight，与全站字体、字号、外观偏好并存。
- `mode=parallel`为当前已部署并读入口，左右版本均绑定asset/revision；支持交换、同步/自由定位、候选对齐、手动对齐、术语笔记、私人任务及公共校准提交。来源变更保留旧私人笔记但阻止旧锚点新增；选择当前版本需要明确动作。保存未知先按request_id查原回执，409保留输入。手机“版本/阅读/笔记”和手动“对照/候选/笔记”面板不得隐藏业务。
- 并读内部历史登录提示仍写访客可读，但路由已requireReaderSession；设计和实现使用实际登录权限，并修正该处失配文案，不放开路由或API。
- 其余动态来源逐条补在 DYNAMIC_REQUESTS.csv：服务端publish_url/decision_url、文件preview_url、健康action.endpoint均保留正式鉴权与修订检查，不将字符串接口改为演示动作。
