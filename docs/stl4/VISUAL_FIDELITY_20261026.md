# 实际视觉差异与修正记录

2026-10-26。用户明确允许浏览器只读查看、截图并直接与唯一 final-r2 PDF 对照；全部图中资产版权归用户。当前内网是实际开发版本，没有另一套已经完成却未展示的视觉终稿。此前206个B仅表示实现/路由已有，不能证明视觉符合PDF。

## 已观察的明确问题

| 编号 | 证据与触发 | 实际影响与最小范围 | 当前状态 |
| --- | --- | --- | --- |
| VISUAL-01 | `SiteHeader`旧editorial-v2 scope，`home-stl4.css`全局brand-name隐藏；打开首页/引文体检即可看到英文粗黑三行、中文缺失，原SVG与PDF10/208图形不符 | 修正共用品牌资产与页头作用域；保留搜索、菜单、账户、返回和已批准的夜间功能 | r2已在内网显示PDF提取的品牌；其他页面的品牌排法仍须按对应PDF核对，不能批量关闭 |
| VISUAL-02 | PDF208与1222宽实际截图；`citation-audit-upload`字体/画布/图标/选项文案/布局不同；`RouteTransition`旧scope又覆盖新标题颜色与字重 | 仅修改表单视觉、固定文案、移动布局、对应页脚及已确认路由的旧作用域；权限、任务与来源状态保留 | A，r2已部署第一批，残留scope与页脚修正正在形成r3 |
| VISUAL-03 | PDF10右侧书桌、窗光、书籍位置与原`stl4-reading-room.png`及页面构图不同 | 直接提取PDF中的纯插图区域，保持真实标题/搜索/目录为HTML | r2已替换首图；实际首页继续对照，不能宣称整页完成 |
| VISUAL-04 | PDF183与/account实际页面；纸色背景、弱字重、创建按钮、全部同图标、搜索放在资料表下部，身份/退出重复占用标题区 | 恢复对应标题/导航/按钮/搜索位置和色彩，将保留的附属操作折叠；不重做ReaderMaterials或私人API | A，当前正在修改 |

PDF中的示例任务和馆藏数量不是当前数据库事实。没有示例稿件时不伪造文件、统计或任务；这不免除布局、色彩、字体、控件和空状态的视觉责任。

## 已执行与未执行

已实际读取唯一PDF10、14、183、185、208的嵌入图。浏览器仅访问首页、读者中心及引文体检；未提交表单、上传、取消任务、保存批注、修改账户或业务数据。截图在忽略目录`tmp/pdfs/stl4-citation-20261018`，含before-1222、r2桌面和手机结果。文字/字体检查采用浏览器实际computed style，未将单纯源码存在写成验收。

Web构建6476b0→e42963成功；NAS构建59951e→d3357b/e5afe4成功，Web r2 `170e2f693b85`。565862→c4792f已更新隔离项目，API r5、Discovery r2、Web r2。保留原13服务及全部账号/预览数据，未重置或迁移数据库。更新期间短暂502发生在Web尚未完成启动时，日志确认启动后刷新恢复。没有测试、检索质量测评、模型实际推理或生产变更。

所有图像资产只从指定PDF提取，来源坐标记录于`web/public/brand/README.md`。品牌字样是原图资产；页面正文仍为可选择文字。PDF截图是栅格图，当前未取得其中正文对应的原始字体程序，不能把现有字体回退链宣称为已经确认的原字体。

## 恢复与后续

当前优先完成上述确定的视觉修正，更新实际预览后再次对照；继续按八个一级分类组织记录，不对每张图重新展开泛化风险审计。普通读者/管理员无引导复核只看明确操作是否能完成、状态是否真实、入口是否可理解；不借此改写PDF产品形态。

原业务功能、私人数据保护与已接续的检索代码继续保留。深度模型bundle已挂载到现有隔离推理服务，查询主开关仍关闭；不能据容器健康写成EG2/BGE/ConvMemory实际检索已验证。

## r3 已更新实际预览

f06d2a→2e82fc前端构建完成，76e935→ffdcb2镜像构建完成，de295f仅更新Web并重启预览Edge。Web r3镜像前缀5f6857a52fb7；原API r5/Discovery r2及数据库保持。环境恢复点`.env.before-web-r3`只留NAS，不能提交或输出。

浏览器实际确认：引文标题颜色变为rgb(7,30,57)，步骤标题恢复700字重；固定四项页脚已存在真实链接。新增/help/terms复用原公开网站说明的about-open/about-copyright/about-notice，不生成或发布新的政策文本。手机隐藏的返回文字补aria-label。读者中心已恢复白色画布、主操作图标/深墨按钮、六类不同图标和顶部搜索，账户资料及本机转存保留在折叠入口；原API与归属校验不变。

仍未关闭整页视觉A：字体原程序未确认；账号标题/操作的纵向对齐、空库完整呈现及其他页面的品牌变体继续核对。缺少真实稿件/馆藏的状态未操作，不伪造示例数据。这里只关闭已证实并已显示的局部差异，不宣称全站或整类验收通过。

按用户此前指定的grill-me方式，继续沿已采用的[grilling作者规则](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md)按整类自问。当前读者类已核对的事实为：普通读者能找到创建、搜索和资料入口；空任务数量为真实0；新样式不删除权限保护或原请求恢复控件。业务成功与全部状态未操作，仍保留B，不转化为新防御开发项。

## VISUAL-05：关于、帮助和反馈（R33，PDF13–17）

A的证据：实际/about使用208横排品牌、错误的旧stl4-reading-room插图；SupportHero把首页图强行用于所有支持页；support.css的270px最小高度和自然图片比例实际撑到约324px，而PDF14横幅约212px；AboutPublicView通过site-config读取的默认正文被改写。PDF13/14/15/16品牌各有排法；RouteTransition仍给支持页套editorial-v2，覆盖颜色和标题字重。直接涉及SiteHeader、SupportHero、support.css、SiteFooterView和前后端site-config默认值。

最小修复范围：支持类路由退出旧视觉scope；按各图提取品牌、桌面/手机书桌和指南插图片段；恢复关于两列卡片、移动端图标标题/整行正文、各自页脚、帮助文章的三步+纠错提示；真实帮助搜索、引用示例、FAQ和反馈原状态/命令保留。关于的三段默认正文按PDF14恢复，已发布SiteSetting/AboutPageBlock不被脚本改写。PDF16的通常3工作日回复文案属于用户指定产品文案，不是本次测得的实际服务时效；成功状态仍只由真实回执触发。

按整类自问：访客是否能找回帮助首页、是否会把指南示例当馆藏、能否不填邮箱提交、关联来源是否仍排除私人页面、错误/未知回执是否保留？源码确认原公开搜索入口、示例输出标记、可选邮箱、safeFeedbackPath和固定请求重试仍在。视觉操作只浏览，不提交任何反馈或示例复制/导出，也未声称业务验收通过。

本机Web r4预览构建42f76b→b5461b退出0；1637文件制备包SHA256 12c427d445b4992212c3bb01271d2f2119289538b07a478a454df711d9e4d4fa。NAS镜像构建正在进行；API r6只替换catalog/site_config.py，无schema、权限或数据库迁移。原API r5/Web r3与.env恢复点保留。

R33内网更新记录：NAS b9549e→da22d1成功构建API r6 `57c1db0af199` / Web r4 `96130ba6e2c4`；931e12→11a15e实际更新。Web启动前一次502，启动日志就绪后刷新正常。/about显示新正文且品牌/插图正常；测得横幅212.69px、高度56px/700的h1，默认正文18px/29.7px；移动布局无横向溢出。帮助/文章/反馈已只读查看，卡片高度、引用背景及手机反馈精简正文再修入Web r5：dd778f→30e6df本机构建0；包2947f6b817750df1d1cbb0b5ad974f298117f8c00310e4c183f0f2754983c6ed；7eef83→4ebb25构建部署0，镜像`0fdefd11deb0`。保留.env.before-visual-r4和.env.before-web-r5，均NAS私有不可提交。

## 探索组下一项的具体证据

VISUAL-06：PDF23与实际/explore的英雄标题/入口卡片字体及高度明显偏小、底色错误、搜索按钮被压成两行。文件为explore/editorial-landing.css与SiteHeader，既有插图已经从PDF23提取，不必再重做检索功能。

CATALOG-UI-01：2026-10-26浏览器访问/explore/original直接呈现全页载入失败，控制台明确Error: Server API transport cannot run in the browser，入口为catalog-search-workspace客户端chunk。源码CatalogSearchWorkspace第11行导入SiteFooter，第129行调用，后者导入site.server→server-request。本次只需将SiteFooter放回服务端app/explore/original/page.tsx；检索API、守卫、账户与权限不改。已遍历同一SiteFooter直接调用链，只有这一个use-client文件违反边界；不把其他未验收页面推定有同样故障。

## 探索组 r6/r7 与观点入口的直接修正

CATALOG-UI-01已关闭开发项D：r6浏览器实际显示馆藏真实0结果，服务端页脚回到original/page.tsx；未更改server-request保护。VISUAL-06：PDF23桌面主标题60px、搜索按钮不换行、三卡156px图+185px正文和原图STL品牌已实际显示。保留夜间按钮这一已获用户批准的增补。截图after-explore-r6-20261026.png、before-catalog-r6-20261026.png位于原tmp证据目录。

VISUAL-07 A证据：PDF24/26与r6实际馆藏截图；stl4-exact.css仍是纸色横幅、14px介绍、黑色按钮和窄小结果文字；查询和观点入口上下排列；默认筛选为字段勾选而非馆藏范围；卡片标签/版次操作与主图不符。r7恢复最终24主壳，保留25–27高级字段/多选类型/展开版本能力；控制沿用catalogParams/readCatalogSearch，API catalog_search._facets只增加COUNT DISTINCT作品total，避免用版次数求和。空库不添加虚假书/统计。普通读者默认可进馆藏，手机的筛选仍先选择再应用，次级入口/版本下载均保留。未操作有馆藏的业务状态。

r7实际查看：/explore/original载入，显示全部馆藏(0)与0结果，横排搜索、独立原图品牌和白色内容已出现。页脚computed style仍rgb(238,234,226)，来源明确为[data-ui-scope="explore-frozen"] .site-footer覆盖新规则；r8将仅这三条已重做探索路由切换stl4作用域，保留旧全局探索路由。

VISUAL-08 A证据：PDF28与实际opinion入口；标题44px偏小，输入区约94px而非65px，品牌误用208，手机CSS直接隐藏四项范围卡并只显示一个下拉。r8恢复28品牌、54px标题、65px输入、四张范围卡与相应页脚，保留29范围选择底部弹层和原账户历史API。PDF28主图300字符/本机历史与PDF29状态图500字符/登录后保存有冲突：采用29明确状态规格500与本人显式开启账户历史，不虚称云端记录仅在本机。未改历史存储/默认关闭/owner校验，也未执行输入提交。

构建：Web r6本机60ccad→e4a0b2退出0，包18c807d53e6ad58f126d2e8519242a880f73aa8006f53fd6cdcab9f2e0dd80d3，NAS b89433→67398a完成。Web r7本机6d857d→7a7f48退出0，包c6bdc702acd78c8f0c434f2413ee16a785d93b2cdcea0f54b98ae2c3dc41b836；NAS62f62f→3030a0完成，Web `8cea9f46792c` / API `36667a3509da`。备份.env.before-web-r6、.env.before-catalog-r7均只留NAS。无schema、生产或重置操作。Web r8正在本机构建，不能提前写已部署。

Web r8更新：本机e636f6→768717退出0；包34d10dba515bc7d8b2755915a58eb82e187de87424aaa1f12a02b0c9f39d098c；NAS d03ace→87f0d4完成，仅Web。PDF28对应/opinions桌面及390×844手机已实际查看，四种范围卡恢复，输入框约65px，未触发检索；账号真实关闭历史保存且空记录。/original手机scrollWidth375、innerWidth390（15px滚动条），无横向溢出，页脚display:none。截图after-opinions-r8-desktop/mobile、after-catalog-r8-mobile均在原tmp目录。r8之后仅说明文字12px与旧无效色值清理待下一包。

## 原文证据组 VISUAL-09（PDF30–32）

A证据：实际/evidence无查询截图before-evidence-r8-desktop显示旧纸色/黑标题、误用208品牌、侧栏摘要位置/标题比例不同；viewpoint-search.module.css与SiteHeader仍是旧视觉。PDF30的概念/理论关联在DiscoveryPassage与EvidenceSummary未投影，现有source_header已从正式快照并由_taxonomy_for排除未发布节点，具备真实来源。

最小修复：仅evidence路由退出旧scope；提取PDF30独立品牌；恢复页头真实馆藏搜索、读者入口、标题与三栏尺寸、手机三项筛选按钮、摘要/上下文/文献状态的颜色字号。通过_public_row从新鲜且已校验theories投影related_concepts/related_theories的id/title/slug；不改变数据存储、检索算法或索引。原摘录校验、权限、引用前重新核对、取消/重试/已获材料保留继续复用。

明确未完成：PDF30中/EN控件尚无已实现的界面语言能力，不能放置假切换按钮或宣称整页闭合；正文原始字体仍未取得。只打开无q路由，未创建检索会话、执行模型、提交表单或业务数据。源码结果/多版本/上下文对应视图的实际有数据状态未验收，保持B。当前正构建r9，不能据源码或构建称已显示。


r9实际更新记录：本机初始5ba28e→7d7115退出0；1674文件包bbe5aed01fa54ef9ca7d8ddc2c81afd931ef31032da0e4ad5f449ca196508581。NAS6feea1→f832f8更新完成，Web06d7a96fc9d1、APIec8f27420854；只读桌面1280与手机390截图after-evidence-r9-desktop/mobile已保存。页面实际显示新品牌/三栏/三项手机筛选，无查询无结果状态。截图又确认旧筛选项挤占主栏；按PDF补六段年份、可读版本，并把语言/责任者/主题/概念折入更多筛选。手机仅图标搜索缺少可访问名称也已补入。

新增availability按真实激活版本与公开译作关系实现，未改变原文/深度排序。语言筛选沿用原Meilisearch language条件，不因_metadata匹配处无该字段就误判遗漏。文献类型中的译著/会议论文尚不能与当前DocumentType七值直接等同，仍A，未把会议论文错误映射为全部章节。语言切换和原字体仍未闭合。

r10：本机27d2cc→0c2578退出0；手机按钮名称补入后6811b7→fd6427退出0。1677文件包995e7c23687b6aa2b8476d2b902a973292aa88aba5b53eac241bf2fe8921a38e，AST/diff6eabbd退出0。未运行测试/检索/模型/业务表单。正在更新隔离预览，备份.env.before-evidence-r10；原账号/批注/数据库保持。
