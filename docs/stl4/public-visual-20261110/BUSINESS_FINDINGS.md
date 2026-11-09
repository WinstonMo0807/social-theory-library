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

## 尚待逐项闭合

读者工作区、PDF、完整管理任务/编辑字段、动态 API 包装路径、各角色页面观察、未启用/历史入口分类与页面状态仍在核对。未完成前不进行正式出图，也不宣称业务盘点完整。
