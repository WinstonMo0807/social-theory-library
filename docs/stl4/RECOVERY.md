# 中断恢复最短路径

## 2026-10-23 R22总览恢复

前置840ad60，新实现见READER_OVERVIEW_20261023。reader_center.py/views、ReaderOverview复用原私人对象，只读聚合。白名单tmp/stl4-reader-overview-checkpoint-20261023.json；核对git log确认本批提交。96/28/85，R22仍部分，继续批量操作与访客转存。静态脚本reader-center-static/contracts可按需使用；不重跑颜色替换或记录前插，不暂存继承脏改，不运行测试/浏览器/生产。

## 2026-10-23 夜间外观与读者接口接续

最新工作见 CURRENT_PROGRESS 顶部与 READER_APPEARANCE_PRIVACY_20261023。新增 AppearanceProvider、主题按钮、共享 PrivateAccountResponses，复用原 ReaderProfile、问答与私人服务；无表迁移。交互预览 output/preview/stl4-appearance-preview.html，三个生成概念图在本机 Codex generated_images 中。禁止重跑一次性颜色/代码替换；继承脏改不纳入本批。后续按PDF183–190、216–222收口读者全流程。第189图是过期登录浮层，索引route不作为另建会话管理页的依据。不运行测试、浏览器或生产。

## 2026-10-23 知识对象M18恢复

前置4f6e2bd，读KNOWLEDGE_HISTORY_20261023与CURRENT_PROGRESS顶部，核对git log确认本批提交。白名单tmp/stl4-knowledge-history-checkpoint-20261023.json。新工作台/admin/publication/knowledge/{type}/{id}，history GET/POST沿原修订与审计，不建表。保留继承editorial_revision_views.py等脏改；不要重跑history-record或以前wire/record脚本。正式测试/浏览器均未执行，96/26/87不变。最新用户要求继续全站、不测试/不浏览器，补账号读者中心接口核对、夜间模式参考和可交互页面；下一单元先完成这些新增交付，再推进剩余模块。

## 2026-10-23 知识M17工作台恢复

前置d82b148；本批白名单tmp/stl4-knowledge-review-checkpoint-20261023.json，实际提交核对git log。阅读KNOWLEDGE_REVIEW_20261023及CURRENT_PROGRESS最上项。原preview页面?review=1为检查工作台，?frame=1为受认证保护的公开组件子视口；接口review=1强制保存版本、只读预检。发布仍原KnowledgePublishControl与既有修订事务。

不要重跑本次record脚本或之前wire/adjust/links/record脚本。统计96/26/87，M17仍部分；保留全部继承脏改，尤其editorial_revision_views.py。本批没有正式测试/浏览器/构建/迁移/生产操作。下一步知识M18完整历史/撤回/恢复、固定页面统一发布检查，先读唯一PDF相应图。

## 2026-10-23 知识预览版本恢复

前置fbb6864，本批白名单tmp/stl4-knowledge-preview-checkpoint-20261023.json，提交号核对git log。editorial_edit_version提取原保存公式；AdminKnowledgeObjectPreviewView GET/POST携可选edit_version且响应前后重查。完整/编辑内预览清空失败旧内容、owner验证、绑定链接。生成契约226路径，96/26/87不变，无正式验收/生产。

不要重跑tmp/stl4-knowledge-preview-wire/links/record-20261023.py；静态与契约脚本可按需复用。不暂存继承改动。下一步仍为完整知识M17与固定页面/M18其他对象，不能把预览一致性修复当成整个页面验收完成。

## 2026-10-23 知识对象发布恢复

前置ad1b230；本批白名单tmp/stl4-knowledge-publish-checkpoint-20261023.json，实际提交核对git log。读KNOWLEDGE_PUBLICATION_20261023。KnowledgePublishControl复用原规范保存/修订发布，已有修订不改写保存状态；prepare未知需人工核对，publish阶段先查原修订，禁止另建请求冒充恢复。RequiresCapability及IsLibraryStaff/IsKnowledgeEditor带可选owner守卫。统计96/26/87未变，无正式验收/迁移/生产。

不要重跑tmp/stl4-knowledge-publish-wire/adjust/record-20261023.py，不暂存继承editorial_revision_views.py等改动。下一步继续知识对象完整M17、固定页面与M18其他对象；确认弹框不能代替整个页面实施或逐图验收。

## 2026-10-23 NEW-A16恢复

前置791bd9b，本批白名单tmp/stl4-publication-review-checkpoint-20261023.json；核对git log确定检查点。读PUBLICATION_CHECK_20261023，统计96/26/87，正式验收未运行。/admin/publication/[itemId]默认为旧收件ID；object=edition为明确Edition；view=history为独立原发布账本。history?view=review复用desk投影，page-preview接受version/fingerprint与owner校验。不要重跑tmp/stl4-review-wire/adjust/record脚本，不暂存继承修改。下一步继续M17/M18知识对象及固定页面的发布/历史能力，必须先读取唯一PDF相应图。

## 2026-10-22 M18出版版本工作台恢复

M17检查点0e11275；M18本批白名单tmp/stl4-publication-ledger-checkpoint.json，核对git log确认提交。当前源码见PUBLICATION_LEDGER_20261022，统计96/25/88。唯一PDF134–137已读，图136 NEW-A16独立页面仍待实现；继续现有preview/prepare/维护命令，不能把旧itemId默认为editionId。后台GET history?view=desk保留旧数组；无迁移/正式验收/生产。不要重跑tmp编辑或记录脚本，不暂存继承脏改。

## 2026-10-22 0e11275后M18发布历史实施中

M17已保存0e11275（30路径）。已实际读唯一PDF134–137，当前沿原history/prepare/rollback及WorkMaintenance publication接选定版本的历史分页、摘要差异、影响/引用依赖与操作记录。新增desk投影和版本守卫写入中；暂无本批静态/功能验收，96/22/91保持。原PDF/历史/继承脏改均保留。下一步完成UI与契约/定义/静态检查，再保存白名单检查点；不要重跑tmp编辑记录脚本。

## 2026-10-22 M17检查点恢复

前置65c512b，本批见CURRENT_PROGRESS最上项与PUBLICATION_REVIEW_20261022；显式白名单为tmp/stl4-publication-checkpoint.json。核对最新git log确认该批提交，再读唯一PDF134–137接M18发布台/历史/撤回。M17状态96/22/91，只有源码和静态检查证据，无正式验收、迁移或生产操作。接口覆盖226，新增覆盖的是既有preview路由。不要重跑tmp编辑与记录脚本，不暂存继承脏改。素材/草稿原件保留，无数据重置。

## 2026-10-22 65c512b后M17发布检查实施中

关联与审阅已保存65c512b（31路径）。已实际读取唯一PDF131–133，当前接原issue preview GET的review投影、共用发布检查、版本差异、定位修正与带版本约束的真实iframe预览。复用原草稿/CAS/发布指针，不新增表。前后端源码写入中，尚未静态收口或计接入。下一步校验契约/权限/旧测试期望、补验收定义和进度白名单。不要重复运行tmp编辑脚本，不暂存继承修改。

## 2026-10-22 关联材料与审阅恢复

本批前置f07d121，白名单tmp/stl4-related-checkpoint.json（实际提交看Git）。editorial_selection.related与IssueRelatedMaterials接正式关联；assistant候选保存层级/准确段落/原文字；正文heading_level保存、恢复、预览、公开目录一致。225契约已重生。6后端函数/新增3浏览器场景仅定义；TS61377/46da8a退出0。96/19/94保持，M16整组仍部分；下一步继续逐图源码核对并推进下一组。不要重跑tmp修改/记录脚本，不暂存继承脏改，不运行正式验收/生产操作。


## 2026-10-22 f07d121后关联与审阅接续中

来源细节已保存f07d121（24路径）。本批接最终PDF128–130：已有选材的正式署名/版本知识节点/已发布关系，提纲1–3层级，建议关联人工段落并保存生成时文字。仍走原sources/assistant与ProcessingJob，无新模型或检索评测。当前前后端写入中，尚未静态收口；96/19/94保持。不要重跑tmp编辑/记录脚本，不暂存继承改动。下一步补测试定义、契约、静态校验和白名单检查点。

## 2026-10-22 来源信息与真实缩略图接入

前置e14c6ac。本批白名单tmp/stl4-source-details-checkpoint.json，实际提交看Git。新issue-source-summary，原content_placements/editorial_blocks共用展示字段，移除editorial_suggestions重复图片拼接；原文链接含准确修订。source picker/portal增加disabled并守卫更新/移动/追加。完整TS67526/15b29d退出0。4后端测试函数+新增1浏览器仅定义；编辑器场景18。96/19/94不变，接着做M16关联/提纲/正文对比。不要重复运行tmp编辑或记录脚本，不暂存继承脏改。

## 2026-10-22 e14c6ac后来源细节接续中

最新e14c6ac，M16第一批已保存30路径。当前第二批改content_placements/editorial_blocks统一来源展示字段，移除editorial_suggestions重复图片拼接；新IssueSourceSummary与缩略图接文章和选材，原材料选择器补disabled。新增3后端测试函数、原浏览器文件增1场景，仅定义。不要重跑tmp记录/编辑脚本。静态收尾后保存明确白名单；96/19/94不变，继续M16关联/提纲/细致对比。

## 2026-10-22 PDF128–130选材与助手第一批（部分接入）

本批前置155c107，白名单tmp/stl4-selection-checkpoint.json，提交号以Git为准。M16第一批在原编辑器内接IssueSelectionWorkbench/IssueDiscoveryMaterials/IssueAssistanceReview，新增editorial_selection，原assistant服务扩展候选审阅与回执；225契约。96/19/94，M16三图仍部分，继续其关联/提纲/细致对比与M15来源布局。

静态检查已收口；10后端函数与6浏览器场景仅定义。不要重跑本记录脚本，不暂存其他继承修改。助手pending仅组件内，外部导航有提醒，刷新后读任务历史；文章草稿独立有原恢复机制。无迁移/数据清理/正式测试/浏览器/模型/检索质量评测/生产操作。

## 2026-10-22 155c107后接续M16选材工作台

富文本第三批已保存155c107（16路径）。当前按唯一PDF128–130接选材工作台，问题/范围/准确引用保存到原issue修订的selection_workspace，公开payload剔除；接既有Discovery会话、原ProcessingJob助手及逐项修改/采用/忽略。前后端源码写入中，尚未静态收口，不能计完成。不要重跑本次修改脚本或覆盖其他继承脏改。下一步收口权限、任务回执、重试和测试定义，再保存明确白名单。

## 2026-10-22 富文本第三批恢复

前置c79756e。本批白名单tmp/stl4-rich-input-checkpoint.json，实际提交看Git。当前IssueTextEditor使用contentEditable，固定模型/DOM文字，不保存HTML；50步本块历史；同步组合输入保护及纯文字粘贴。完整TS、ESLint、CSS仅静态；17浏览器场景只定义。96/16/97不变，M15来源行/块缩略图仍需细化。唯一PDF128–130已实际读取，图在tmp/pdfs/stl4-authoring-20261022，下一步接M16原editorial_assistance。不要重复运行本记录脚本；不要暂存其他继承改动。

## 2026-10-22 c79756e后继续富文本输入

格式/素材/协作第二批已保存c79756e（34路径）。当前正在将文字格式接为原生可编辑区域，文本/marks模型与API保持原样，增加本块50步撤销、纯文字粘贴、输入法组合期间暂停自动保存。源码刚写入，尚未静态收口或计完成。下一步检查DOM文本/标记读取、选区与恢复、引用只读边界，补验收场景并检查后保存。不要重复提交其他继承脏改。

## 2026-10-22 PDF127第二批恢复

前置3136d5c，当前批白名单tmp/stl4-issue-editor-details-checkpoint.json，实际提交号看Git。新IssueTextEditor/IssueProse、IssueSuggestions/editorial_suggestions、IssueCollaboration/editorial_presence，原issue保存/发布/历史继续复用。225契约。不要重跑此前或本批文档prepend辅助。当前96/16/97；M15仍部分，下一步先补就地富文本编辑/选区与撤销，再读取唯一PDF128–130并接现有editorial_assistance。格式选择与右侧预览已真实接通，但不能写已达到完全所见即所得或视觉无差异。

协作缓存TTL90秒，原Redis共享，LocMem明确仅本进程；观察不写正文、不代替CAS锁。建议只匹配公开资料，原推荐检索方案与质量评测不动。新增测试9后端函数和6浏览器场景仅定义；实际正式验收未运行。保留所有其他脏改，不接生产、不执行清理/迁移/模型。

## 2026-10-22 3136d5c后继续实施

结构编辑/草稿恢复第一批已保存3136d5c（32路径）。当前正补PDF127导读富文本与材料建议，尚未静态收口或计完整。来源原文不允许格式编辑；文字格式仅持久化在当前内容块，复用前台/预览渲染，不增加HTML执行。保持96/16/97，正式验收未运行。


## 2026-10-22 编辑器第一批恢复

前置f94545e。本批白名单tmp/stl4-issue-editor-checkpoint.json，实际提交号看Git。恢复结构编辑器、useIssueDraft/IssueHistory/IssueSourcePicker、历史/来源/只读POST preview、保存回执及223契约一体；不覆盖其他继承修改。源PDF124–127图在tmp/pdfs/stl4-editor-20261022，均已实际读取。

当前96/16/97；M15四图部分。继续先补127富文本工具栏和真实材料候选逐项采用/放弃，再按需读取128–130，结合既有editorial_assistance，不建第二套模型服务。当前协作只展示实际保存者和修订历史，尚无实时在线/光标，不冒充同时在线。测试定义10后端+7浏览器，全部未运行；静态证据见VALIDATION。无迁移或生产操作。


## 2026-10-22 专题编辑器接续中

最新检查点 f94545e（后台搜索/工作提醒）；原有未提交修改保留。唯一PDF124–127已实际读图，当前接结构块编辑、准确来源选择、修订历史和固定保存回执。前后端正在接自动保存、断线查回、恢复与双栏预览，尚未静态收口，不计完成。当前96源码/12部分/101待实施；正式测试、浏览器、构建、迁移、检索测评与生产操作未运行。


## 2026-10-22 搜索与提醒恢复

前置68ceb89；本批白名单tmp/stl4-admin-search-checkpoint.json，实际提交号以Git为准。AdminDashboard searchMode、AdminWorkNotices、共享today_work/curation读模型、两新API及221契约一同恢复。其他继承脏改不纳入。下一步已读唯一PDF124–127（tmp/pdfs/stl4-editor-20261022），接专题编辑器结构块/来源只读/预览及草稿冲突恢复；M01仍部分，M15四页只读未实施完成。仍先全量实施再统一验收，不跑正式测试/浏览器/构建/迁移/生产操作。

## 2026-10-22 68ceb89 后第二批实施中

今日工作第一批已保存为 68ceb89（36 明确路径），其他继承修改保留。当前正接后台跨对象搜索、真实异常工作提醒及移动搜索展开；复用现有权限与 SQL 列表，不建索引/任务表。第二批尚未静态收口，M01仍为部分接入，96/12/101不变。编辑构图需同时核对最终PDF后续专门页面，不能只凭81缩图改写；正式测试、浏览器、构建、迁移及生产操作未运行。

## 2026-10-22 今日工作第一批恢复

前置dd74788。先读TODAY_WORK_20261022和CURRENT_PROGRESS顶部。36路径白名单在tmp/stl4-today-checkpoint.json；不要整批暂存其他继承脏改。M01-main/states仅部分接入，96/12/101；继续补顶部统一搜索、真实通知和81编辑构图。新接口/路由/生成契约219、精确处理ID过滤、权限与样式退役都需一起恢复。不要恢复旧design-v2全局引用，原文件仅保留历史。静态已查，所有正式验收/迁移/生产操作未运行。

## 当前接续点 dd74788 · PDF80/81今日工作

专题文章检查点已保存。当前今日工作实施从 admin-dashboard、admin-shell、admin_queue_query、curation_queue_views 接续；照片在 tmp/pdfs/stl4-admin-home-20261021，已实际读图。curation_queue/backoffice/processing_center 等已有继承未提交成果，按 diff 保护。新单元未计完成；无需重做上轮全文审计，不运行正式验收/浏览器/构建/迁移/生产操作。

## 2026-10-21 专题文章/微展览源码收口

前置9bb2bb4。先读EDITORIAL_20261021及CURRENT_PROGRESS最新项；tmp/stl4-editorial-checkpoint.json为本单元精确路径，不整批暂存其他脏文件。恢复public_editorial、typed正文/分组、公开目录/文章/嵌入Reader、阅读设置、私人书单及评论0021、隐私组、后台编辑/审核、218路径契约与生成类型。其余继承成果保留。

96/10/103是源码统计，不是验收通过。0021及此前迁移均未应用，正式测试/浏览器/构建/质量测评/生产操作未执行。静态检查过程详见VALIDATION；comments只读当前文章公开修订，旧评论留在本人资料与审核队列，不能自动转绑新版。任何未知提交先查原回执，删除后旧请求不得重建。

下一项PDF80/81今日工作和馆藏总览，需实际读图；backoffice/processing_center/admin相关文件已有继承未提交改动，先核对diff和调用链。其余公共/首页/读者缺口及B01–B06不能遗漏。

## 当前接续点9bb2bb4 · 专题文章73–78实施中

主题74路径已保存。当前未提交新增public_editorial.py、editorial-directory.tsx/editorial.module.css、article-metadata-fields.tsx及其前后端接线；editorial_issues/issue_views/serializers、RecommendationIssueView及后台编辑已有继承修改，须保留并按具体差异接续。实际图像位于tmp/pdfs/stl4-curation-20261021。目录关联、正文目录/原文侧栏、微型展览与私人保存继续实施；尚未静态收口、未计入视图。正式测试/浏览器/构建/迁移/检索测评/生产操作均未运行。禁止整批暂存其他脏文件。

## 2026-10-21 主题源码收口

前置ba56939；恢复先读CURRENT_PROGRESS最上方与TOPICS_20261021，核对最新Git提交。tmp/stl4-topics-checkpoint.json为74路径精确白名单；不要纳入其他继承脏改。公开主题/层级/0074、后台新编排与POST预览、媒体、SourceFollow topic/0020、SavedTopic命令及隐私、契约/生成类型一并保存。原代理已不在活动列表，后续由主线继续。

90源码接入、10部分、109待实施只是视图源码统计。迁移、正式测试、浏览器、构建、检索测评与生产操作未运行。PDF73–78六张实际读图在tmp/pdfs/stl4-curation-20261021；下一单元从RecommendationIssue/EditorialRevision/editorial_blocks和现有Reader接续。相关策划前后端文件已有继承修改，先读diff并保留，不能覆盖或整批暂存。没有新生产种子或清理授权。

## 当前接续点 ba56939

2026-10-21学者110路径已保存，保留其余继承未提交修改。先读CURRENT_PROGRESS最上方主题68–71项；不要重做学者或把本地提交当作部署。private代理继续SourceFollow topic/0020，public后端代理继续Topic parent/0074及正式公开投影与DTO，UI代理继续68–71公共页；root接后台编辑/受控预览并完成契约与进度。当前主题未计入已接入视图。原PDF四图已实际读取。

## 2026-10-21 学者源码收口

前置a0720ad。先读SCHOLARS_20261021与本节之后的最终检查点编号；恢复公开学者DTO/投影、0073及Contribution.scope全调用链、SourceFollow/0019及隐私、三路由/公开组件/后台编辑预览、schema与生成类型。tmp/stl4-scholars-checkpoint.json为本次精确白名单；ingestion/views.py只纳入3行范围保留改动，其他继承脏改不得整批提交。

library_retrieval.py继承的第一推荐Discovery adapter已完整审阅并与责任范围一起纳入。当前检索作者投影必须传已验证授权集合，匿名默认public/inherit，空权威作者不能旧payload回填；章节元数据和真实片段统一校验活动正文/目录，未运行索引更新或质量测评。

下一组唯一PDF68–71已实际逐张读取，仅只读预审。主题层级、正式问题/作品/策划/阅读路径成员资格与主题关注继续复用既有身份。不要将无全文等同待购，不造讨论数，不以旧自由文字问题充当规范节点。其余脏文件及所有账号保留；迁移/正式验收/生产操作未执行。

## 2026-10-21 阅读路径检查点

前置4251804。先读READING_PATHS_20261021；恢复catalog稳定材料/正式投影/0072、reading路径命令/0018、两公共路由、六模块预览、后台材料编排、旧理论消费者、账户副本操作及隐私同步。203路径仅静态契约，迁移与正式验收未运行。

不可变source_snapshot仅用于比较公开版本，重新核验的path_snapshot用于输出；不得将私人笔记或进度算成公共版本变化。副本generic PATCH要求nonce+owner，GET/导出也带owner；同账户会话恢复保留原请求并先查回，禁止401自动重放。普通计划不纳入follow，旧reading_path_id有损生成入口拒绝新建，专用另存保留阶段与多章节。

下一组62–66已实际逐图读取，只读审计发现正式别名/同名身份、准确公开版本贡献者角色和列表筛选需要接续。其余原有脏文件不得整批提交；没有生产清理/部署或检索质量测评。

## 2026-10-21 图谱检查点

前置67c5db5，先读GRAPH_20261021。恢复theory_graph投影/graph_serializers、原graph API、新公共页面与四类中心搜索、reading graph保存与0017、privacy、准确schema和生成类型及隔离fixture/spec。全部一起按白名单保存，不能漏掉隐私同步或私人视图的恢复入口。194路径/静态检查不是功能验收；0017未应用。

候选单独授权、单独数组且不保存到私人视图；已保存名称和布局只在本账户解密，恢复后重读当前公开图。未知请求nonce仅在页面内存保留，同owner验证变化可查回，离开前有提示；删除后最小回执防旧请求复活。未映射旧TheorySchool图谱不改绑同名规范节点，旧管理预览保留。下一组PDF58–60已实际读图，先查既有公共路径、阶段、材料版本、私人计划和发布修订；不要重做图谱或运行检索测评/生产清理。

## 2026-10-21 时间线检查点

前置376adc9，先读TIMELINE_20261020。55路径包括0071、时间线投影/来源、四公共路由、管理编辑、准确契约、隔离夹具与15浏览器场景，以及11个PDF依赖延迟导入文件。TS66497/191路径仅静态证据；13后端函数34参数案例全部未执行，迁移未应用。本地Windows仍可能阻止实际PyMuPDF原生操作；不得由schema生成成功推断PDF/OCR可用。

继续PDF52/53/55图谱：新theory_graph服务/graph_serializers、前端graph组件和reading图谱保存新文件在并行实施，尚未接旧路由、隐私和迁移注册，不要漏掉或误纳入时间线检查点。图谱需typed中心、1–3层、有界节点/边、真实关系依据、owner加密视图及固定nonce恢复。旧管理预览保留；普通登录不等于候选关系阅读授权。不要重做时间线，不运行正式验收或检索质量评测。

## 2026-10-20 PDF50/51/54子学科与目录

前置966f5fa，读SUBDISCIPLINE_DIRECTORY_20261020。恢复子学科列表/详情serializer与public projection、Scoped Search独立身份、新directory投影及路由、三页面/类型/13张PDF照片、188路径契约和隔离fixture/spec。列表只有9字段，详情works_page每页48，分页来源与独立编排依据分开；旧work适配、后台preview须一同保留。TS75884仅静态通过，27后端函数45案例和28浏览器场景尚未运行。没有新增迁移或生产操作。

下一项先52/53/55关系图，再56/57时间线，原图均已逐张查看。图谱复用现入口和关系，需typed中心、1–3层、真实关系依据、私人保存视图、可取消读取；不得把登录当成未发布候选的公开授权。时间线需真实同年分组/全筛选总数、作者主题与多类型筛选、准确事件/来源版本及旧关联兼容；不得用上传日期造事件或从共同关联猜因果。两组目前仅预审，没有新代码。旧流派子栏目也仍待视觉接续。

## 2026-10-20 PDF45–49理论条目收口

前置5f692ed，读THEORY_DETAILS_20261020。恢复公共理论投影/旧接口来源保护、content_placements用法、knowledge收藏与0016/privacy、概念/流派/旧主详情/总览、12张PDF装饰图、schema/生成类型及隔离用例。原两份理论dirty diff已备份并继承，legacy两源文件原件在tmp/theory-legacy-publication-before-20261020-171904；只按白名单保存本单元，其余历史成果保留。

185路径是当前契约，不代表功能验收。0016与此前迁移均未应用，夹具与正式用例未执行。旧子栏目只是严格读取真实数据，尚需视觉统一；知识收藏只接受规范节点身份。后续50–57已实际读图，50/51/54优先；保持Subdiscipline独立身份，不创建同名节点，不把层级/精选/潜在关系从名称或数组顺序猜出来。

## 2026-10-20 Reader OCR状态接续

前置0b6c010，读READER_OCR_STATUS_20261020。恢复reader_ocr新服务/serializer/view/urls、UI/hook/client/样式/当前页缩略、ReaderShell接线、schema及类型和用例。旧OCR执行/备份/入库脏文件不纳入。175路径/TS32523仅静态通过，真实OCR/队列/NAS/逐图未验收。后续PDF45–49已读原图，理论旧serializer/views未提交改动须继承；现有content_placements concept_usage可复用，不建平行用法表。

## 2026-10-20 并读接续

前置a5898aa，先读PARALLEL_READER_20261020。新catalog/reading parallel服务、0015、privacy、并读UI、管理校准及入口、schema/生成类型和隔离夹具配置共同恢复。174路径与TS49952静态通过；全部功能/逐图待核实。保存只用本单元白名单，保留继承脏文件；PDF40 OCR轻量状态正在下一单元开发。0014/0015均未应用，不执行夹具、质量评测、生产清理或部署。

## 2026-10-20 阅读器接续

先读READER_20261020。前置42f068a；manifest/次版本权限、ReaderShell/hooks/Viewer坐标、SSR会话、批注加密标签与0014、schema/生成类型/用例须共同恢复。compose只保存web的JWT_ACCESS_COOKIE_NAME新增行，其余继承修改保留。158接口表面与最终TS57106静态通过；运行与逐图未验收。PDF40 OCR细分状态仍部分缺口，继续41–42并读/私人对齐。不要执行旧夹具、迁移、质量测评或生产清理。

## 2026-10-20 作品详情接续

读WORK_DETAIL_20261020，前置d3acba8；PublicWorkDetail、CatalogEdition、共享journal_issues、两种管理预览与生成契约须共同恢复。保留primary公开资格，所选snapshot负责题名/封面/目录。新增文件不是新书库。当前静态通过但功能未正式验收，后续继续PDF36–40 Reader的实际读图与既有源码回溯；不要运行质量评测或生产清理。

## 2026-10-20 PDF32接续

读DISCOVERY_DOCUMENTS_20261020。文献状态复用现有session JSON，作用于原任务、基础/深度scope、读回与上下文；新remove-document接口、生成契约和UI须一起恢复。d69ec44是前置检索检查点。没有新表或迁移。当前33–35图片已实际读取，作品详情旧UI与数据调用链正接续，不能当成已完成。

## 2026-10-20 检索与本人记录接续

PDF23–31源码接入，恢复时读CATALOG_SEARCH、DISCOVERY_PRESENTATION、DISCOVERY_SESSION_CONTROLS三份20261019记录及OPINION_ENTRY、SAVED_READER_BOUNDARIES两份20261020记录。两新接口、生成契约、私人分页所有调用者和9个源PDF装饰素材必须共同恢复。全量TS/静态已通过，正式验收未开始。

下一项是PDF32真实逐文献状态/范围移除及PDF33–35作品详情；不得把通道或索引进度冒充逐书检索完成。不中断等待重复确认，不运行质量测评或再清理生产；其余历史未提交文件保留。

## 2026-10-19 公共交互检查点

先看CURRENT_PROGRESS与HOME_SUPPORT_IMPLEMENTATION、PUBLIC_FEEDBACK、SOURCE_UPDATES、SHARED_CITATION四份单元记录。帮助/反馈/来源/共享引用须整组恢复，反馈模型10行已在e310536，本组配0070迁移，0013亦未执行。原未提交成果继续保留。下一步保存已收口catalog后端及前端，再完成PDF28–32观点入口、真实证据结果与上下文。正式功能/视觉验收仍在全量实施之后，无需等待用户重复“继续”。

## 最新接续：2026-10-18 公共导航

PDF18导航独立保存，见PUBLIC_NAVIGATION_20261018及CURRENT_PROGRESS顶部；ReaderCenter本次仅纳入section同步，后续来源入口/收藏变更仍留工作区。6目标ESLint、导航CSS及当前全量TypeScript通过，不代表浏览器或正式视觉验收。下一步收口10–17帮助/反馈/来源关注、20–22共享引用与23–27馆藏查询。本次检查点记录的0070模型/迁移跨批次问题须在反馈单元配齐，不改写旧提交、不应用迁移。

## 最新接续：2026-10-18 文件、OCR与DOCX

先读CURRENT_PROGRESS顶部及WORK_FILES_20261018.md、OCR_WORKSPACE_20261018.md、DOCX_PRIVATE_PREVIEW_20261018.md。检查点e310536包含68路径源码/单元记录及10项全局记录（共78路径），须共同恢复，迁移0069/0012未执行，实际服务和全站视觉未验收。不要运行旧tmp记录脚本重复插入历史。

下一组10–18帮助/反馈/公共导航已并行修改，不能覆盖或误当已验收；17来源信息/站内关注正在接实际公开身份和本人私人记录。新的反馈管理是该业务闭环的风格补齐，170–172是检索质量评审，不能混算。用户明确授权持续至开发完成，不再等待“继续”。其余原未提交修改保留，不reset/clean，不清生产数据。

## 最新接续：2026-10-18 反证、隐私与页码

先读CURRENT_PROGRESS顶部及COUNTER_EVIDENCE_20261018.md、PRIVACY_OPERATIONS_20261018.md、PAGE_MAPPING_20261018.md。198–200/223–225/116–118源码接入、迁移0068/0011仅编写；代码、路由、任务、生成类型和回归文件须一起恢复。本单元79路径检查点9a7c68c，检查点不代表运行验收。新增已审查继承依赖登记在CHECKPOINT_DEPENDENCIES，剩余历史未提交成果继续保留。

下一步PDF209 DOCX私人派生分页预览已由代理开始独立源码，尚未接线的文件不属于本单元已完成；PDF95–98已实际读图并调查edition_files/pipeline/WorkflowEditor，继续按真实公开文件与引用保护完成。用户授权持续工作至全站开发完成；不要回到旧全量历史审计、重复清理或另行检索质量评测。

## 最新接续：2026-10-18 笔记与私人来源

从CURRENT_PROGRESS顶部、CONFIRMED_NOTES_20261018.md和CITATION_PRIVATE_SOURCES_20261018.md恢复。205–210已接入，新增路由/接口/迁移0010/生成契约/用例必须共同保留；迁移和用例未执行。下一单元是198–200反证、223–225隐私/导出和116–118页码校准，DOCX精确排版仍有缺口。检查点号码见当前进度。不要再次清理旧业务、重做全量历史审计或进行第三步检索质量评测。用户已授权持续开发至完成。

1. 完整读根AGENTS及Ponytail，再读CURRENT_PROGRESS顶部与本目录PROGRESS；读本轮实际需要的开发规则。
2. `git status --short --branch`、`git log -3 --oneline`；先保留所有未提交内容。不能pull/reset覆盖当前单主线。
3. 以MASTER_SPEC和最终PDF为目标；ATLAS_INDEX是209有效视图索引，旧审核标记不是完成证据。只按CSV的最终页码渲染唯一终稿PDF；不读取历史独立图作为视觉替代。
4. 只核对PROGRESS最后未完成单元的真实代码、API_CONTRACT和DECISIONS，不重复审计全部历史。分别记录实现/静态检查/正式验收/上线。
5. 完成业务单元时更新契约、索引、PROGRESS及CURRENT_PROGRESS，执行允许的静态检查并形成Git检查点。不要仅把工作写在回复中。
6. 全量实施前不运行正式验收或部署。生产不可逆操作必须按DATA_RESET_PLAN形成新鲜影响范围、备份恢复证据并取得最终确认。

本地PDF/原图/output备份被.gitignore排除，不进入源码提交。恢复到另一台机器时必须一并提供这一份最终PDF；源码仓库不能代替这些外部视觉原件。

## 2026-10-18 接续点

前置检查点a77be7a、15f6252、50cf8ed和b0cbf28保留。最新业务单元为稿件版本与目录校准，恢复时先读CURRENT_PROGRESS顶部及CITATION_VERSIONS_20261018.md、OUTLINE_CALIBRATION_20261018.md；Git检查点提交号见当前进度。新API、前端、生成类型和测试须一并恢复。

本轮已把PDF212新版本/增量比较和112–115目录工作区接入源码。下一步继续私人证据材料、PDF209三栏解析工作台及已确认笔记/隐私等剩余视图。不要把新版本局部重查或目录静态检查写成正式验收。正式测试/逐图回归留待全量实施结束；生产数据未再清理，不运行第三步检索质量评测。其他历史未提交成果继续保留。

### 2026-10-21学者接续

阅读路径检查点a0720ad（72路径）。接续PDF62–66学者；以CURRENT_PROGRESS最新项和实际Git为准。当前分工：public_scholars正式投影、SourceFollow关注复用、学者公共UI、管理资料来源与Contribution准确章节范围。不要再次实施阅读路径，不应用迁移或生产清理。
