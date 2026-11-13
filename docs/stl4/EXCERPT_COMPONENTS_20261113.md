## 当前轮：S4 定稿、两种筛选与连续研究停靠区（2026-11-14）

最新用户决定：维持原S4大卡片，放大原文/观点切换；原文保留对应公网筛选的左侧布局，观点保留横向下拉；右侧同一引用/笔记/研究区。只把继续追问做成可移动组件，不能盖住原文和引用。具体选书、选段、沿用上一轮，并保留各轮问题/选材/范围。本节覆盖下方六组未选定、所有组件固定以及预览刷新全清空等历史说明。

### 已实现的内网演示

- 默认S4，原六方案比较移至 `?compare=1&scheme=S1`。保留纸卡叠层与聚焦动效，没有改成紧凑单行搜索。在1600测试视口实测输入卡片约1073×321px，桌面切换标签19px/52px，390手机17px/48px。
- 原文左栏按 `CatalogFilterFields` 保留匹配范围、年份、语言、主题、流派、可获取性、高级五字段及材料类型/作者/标签；类型和年份在2段样例上可筛选，区间及空字段校验保留。公网当前返回登录页，未重新验证生产筛选接口。只在预览重排，不替换实际Catalog API。
- 追问正常位于原文结果下方专用停靠区。开启时桌面结果区独立滚动；右引用保持sticky。复用ReaderGrip与既有拖动控制器，仅增加可选bounds；其他阅读器调用不传bounds，保留其原行为。标题整片可拖，区域内移动、不跨入正文/引用，方向键移动/Home及按钮复位。收起保留约60px标题和草稿，手机回到普通文档流。
- 范围支持沿用所承接轮次、所选段落、指定书籍、当前筛选、研究选材、全部可访问馆藏。书目按书名/作者/年份搜索多选；原文按文字搜索，可查看片段与书页316/PDF330。书目来自用户截图：社会运行论及其发展、西太平洋上的航海者；后者只提供选书示例，不伪造它的原文。
- 每轮保存独立问题、parent、context、scope（段落、书目或筛选快照），回看不改稿；“从这一轮继续”明确改变承接轮次。当前草稿修改不影响已记录轮次。sessionStorage仅保存当前页签的预览轮次/草稿，localStorage只保留组件位置；没有账号研究写入或真实模型调用。
- 默认舒服排版、边界页眉/页码清洗及真实馆藏封面继续保留。主检索与研究提交有明确预览反馈，不把样例当作真实结果。

### 连续研究的产品分析与正式接入边界

读者需要围绕眼前段落理解用语、回到本书继续读、保留引用；研究者还需要限定材料集合、跨作品比较、保留反例/条件和分支。操作必须区分：本轮参考哪些材料帮助解释问题，以及从哪里找下一批材料。例如参考A书一段，同时到A/B两书查找，不能把“参考A”自动解释为“只检索A”。

| 需求 | 当前源码证据 | 接入时的要求 |
| --- | --- | --- |
| 具体选书/选段 | `QueryScope` 与 `research.scope_snapshot` 已支持library/works/passages/filtered，works要求work_ids，passages要求非空且allow_neighbors强制false | 复用现有对象身份、版本/页码锚点及权限；不能空范围回退全库，不能把书页号当PDF页 |
| 本轮参考独立于项目选材 | `start_turn` 当前把项目selections整体写入selected_refs，尚无显式本轮参考输入 | 本次demo单独选择是候选交互；真实接入需增加有所有权校验的context refs契约及请求指纹，不能声称已支持 |
| 较多材料和长研究链 | `collect_research_turn` 的追问规划只取最近3个问题、前5条选材 | 保留读者钉选的问题/材料并提示实际纳入范围；不能界面显示全选、后台静默只取前5条。超限需明确处理，不能编造覆盖百分比 |
| 限定原文后的研究 | `tasks.py` 的passages分支直接使用所给refs，普通search未生成新的对读回答 | “继续研究”当前demo只记录轮次。解释、比较和检验判断应复用既有分析/比较能力并另作接入验证，不把回传选段当作完成分析 |
| 继承与分支 | 已有parent_id、scope快照、请求幂等、revision；原界面比较/历史通过新路由打开 | 同页展示轮次快照、选材与比较；新范围只影响新轮次。历史不能被后续选择覆写 |
| 条件、年份及版本 | 原文Catalog有match fields，研究Discovery有单独filter协议；反证查询明确区分研究时空与出版筛选 | 继承可映射的馆藏筛选；题名/作者匹配字段不能直接冒充研究范围，讨论“20世纪”不自动限定出版于20世纪；跨译本须显式标识 |
| 私人边界与恢复 | 现有owner校验、source_status、请求查询/恢复、笔记授权 | 不自动纳入私人笔记或其他项目；来源失效保留身份/读者笔记并提示，不能替换版本。用户可取消/重试，保留已到材料 |

该表是基于代码的设计分析。本轮不改后台、数据结构、模型路由、公开内容或生产环境。正式接入范围与执行能力尚未在此demo实现。

### 产物与验证

- 内网 `http://192.168.5.3:18895/?mode=viewpoint`；原文 `?mode=original`；直接打开追问 `?mode=viewpoint&research=1`。本机使用localhost相同端口。
- 实际截图 `output/excerpt-ui-20261114/`：S4-original-desktop.png、S4-viewpoint-desktop.png、S4-original-mobile.png、followup-mobile.png、followup-docked-desktop.png。最终以实际停靠区交互为准。
- 内置image_gen输出三张修正版保存在 `output/imagegen/s4-research-20261114/`：s4-original-large.png、s4-viewpoint-followup.png、research-scope-expanded.png；完整提示词 prompts-revised.json。此前5张方案图在工具默认生成目录保留为历史；其中紧凑搜索框已被用户否定，不作为实现依据。生成图中的书封字样/辅助文字只是构图示意，真实书封沿用馆藏资源。
- `tsc --project web/tsconfig.json --noEmit --pretty false` 退出0。`vite build --config web/design-previews/excerpt-directions-20261113/vite.config.ts` 退出0。`node --test web/tests/reader-floating-layout.test.mjs` 退出0，包括原viewport行为和新增滚动停靠边界。
- CUA：真实拖动170×20px后contained/clearOfSource/clearOfCitation均true；收起59.6px、输入隐藏但草稿保留；复位不清问题。具体选书搜索“航海”多选2部，第2轮保存1段参考；第3轮沿用2部书且新增第2段；草稿改成1书1段并刷新，第2轮仍2书1段、第3轮仍2书2段。空选材阻止提交。原文年份倒置报错、2021—2024筛至0段、清除恢复2段。1600、1280、390下无页面横向溢出，390范围选择宽度受控。未进行正式全站E2E或公网业务实测。

状态B：用户确定的S4/筛选/停靠式追问已做成可操作内网设计候选，已做上述有限检查，待用户继续试用。正式研究API接入是后续单独范围。本轮无公网/main推送；只形成独立本地Git检查点，保留共享HEAD/index及其他未提交修改。

## 当前轮：六组专属检索框与结果跳转（2026-11-13）

用户要求更有表现力的原文/观点检索框，六组设计继续作为候选；B正文已确定。未改变全站搜索、阅读器、真实API和部署。演示顶部S1–S6可切换，每组可切换原文/观点并重播入场；选择方案保存在当前URL，输入/筛选切换方案时保留。

| 方案 | 构图与动效 | 快速跳转 |
| --- | --- | --- |
| S1 打开一本书 | 双页构图，右侧书页从书脊展开，焦点强化品牌符号 | 左侧常驻 |
| S2 悬浮检索舱 | 居中品牌、宽圆角输入舱，聚焦抬升，模式胶囊滑移 | 下拉展开 |
| S3 黑金扉页 | 炭黑扉页与纸白输入并列，砂金幕收起；原品牌置于白色底片 | 左侧常驻 |
| S4 问题卡叠层 | 两层纸卡入场归位，输入时略微错开，正文位置稳定 | 横向索引 |
| S5 原文长卷 | 大字号输入与长金线，聚焦时线条展开，无输入卡片外框 | 下拉展开 |
| S6 从问题到原文 | 问题输入与阅读目的双栏，右侧路径随焦点延展 | 横向索引 |

所有方案统一固定布局，不使用可拖动组件。保留真实馆藏封面、舒适原文、默认清洗已知页眉页码及右侧GB/T格式。过滤条提供文献类型、责任者、理论流派、主题、概念、出版年份、语言、可读版本。下拉内可搜索并多选，选中数量可见；当前截图示例没有的元数据明确空态，不编造选项。各项AND、同项OR；两段来源同一书目，选已有责任者不会凭空减少原文。

快速跳转三种容器共享同一实现，结果内搜索匹配可见书目/原文文字（忽略OCR空白），支持仅看已选用。点击定位相应article、更新当前行并转移键盘焦点。页面原文列表与快速跳转同步筛选。数量只有实际两段示例，不沿用截图326。笔记/选材演示仅页内内存，主检索提交明确提示没有发起真实搜索。

动效不延迟输入/导航，不做虚构进度。入场约0.65–1秒，常用控件约0.16–0.4秒；提供重播和prefers-reduced-motion静态降级。S4伪元素入场改backwards，避免forwards覆盖聚焦展开；实际DOM读取确认默认-3°变为聚焦-4°并平移。预览沿用React/CSS及原按键辅助，不新增Swift运行时或动画依赖。

参考：Apple HIG Searching（https://developer.apple.com/design/human-interface-guidelines/searching），采用专属主要入口、清楚的搜索范围、建议词和结果过滤；Anthropic设计团队的公开原型方法（https://claude.com/resources/articles/how-the-product-designer-who-built-claude-design-uses-it-to-explore-ideas-before-building-them）与品牌设计机构Geist案例（https://geist.co/work/anthropic），参考既有资产、字体与功能组件的结合。六组是STL原创探索，不声称为Apple或Anthropic官方组件。

验证：TypeScript --noEmit退出0；Vite demo build退出0。CUA完成1440×1080六组实际截图，390×844逐组宽度检查无横向溢出；长问题221px完整显示；责任者搜索“洪”并选中、Escape关闭；结果搜索“政治”2→1，点击后焦点/selected均为excerpt-1；已选用0的空态可清除；原文模式回车出现明确演示反馈。桌面/手机均保持封面与既有引用显示，未重新验证生产全文检索或私人写入。减少动态效果分支已写入但未切换系统偏好实测。

入口 http://localhost:18895/?scheme=S1；局域网 http://192.168.5.3:18895/?scheme=S1，scheme支持S1–S6。截图output/excerpt-ui-20261113/search-S1.png至search-S6.png，search-mobile-S1.png、search-mobile-S4.png、search-S4-focus.png。源码新增motion-search.tsx/css、改main.tsx；旧Q1–Q3文件保留历史不作为当前入口。

状态B：六组已实现且预览核对，待设计选择。正式API接入、生产发布和main推送均未执行。本轮只形成独立本地Git检查点，保留共享HEAD/index与其他未提交改动。

# 原文排版与全站组件候选 · 2026-11-13

本轮用户新增：截图 OCR 原文排版清洗，检索右栏不再重复证据摘要，生成三组 imagegen 设计；扩展至全站摘录展示、文字、按钮位置及交互反馈。沿已采纳阅读器的黑金品牌、纸白与控件视觉。最新批注要求本检索页固定布局、恢复书封，覆盖本页此前借用拖动和复位的方案；PDF 阅读器的拖动规则保持。三组新布局尚未选定；本轮仅本机/内网候选，没有生产发布、main 推送、API/数据库变更。

## 采纳 B 后的当前版本

- 用户已选择B固定阅读布局。18895不再让读者选择A/B/C，顶部Q1/Q2/Q3只比较检索入口；文案下拉可独立选择原文寻证、问题出发、比较解释。旧三布局和图片仅留历史，不代表仍待选B。
- 实际源码：DiscoverySearchWorkspace删除结果页相关知识、策展推荐和完整覆盖统计面板；不改变后台通道、数据、公开条目或权限，覆盖不足改成一行提示，实际失败/来源变化/重试保留。OpinionSearchEntry移除已失效的知识/策展范围说明。
- 理论流派、责任者、主题、概念与语言复用SearchableFacet多选和搜索；受控选择同步当前filters，选中后保留搜索词。文献类型、出版年与可读版本保持。移动端沿原筛选Dialog。
- EvidenceResultCard采用B版书封/整宽原文，普通卡片区域点击可更新出处栏；选中文字和内部按钮不误触。黑色在线阅读列在同组操作首位并携带return_to，原按钮和键盘入口仍可用。CSS只更新现有组件，不新增检索后台。
- SourceExcerpt去除原始换行/对照模式，唯一舒适阅读；合并空行和隐藏已知边注默认开启，可在格式清洗中关闭。只匹配提供的书名/书页且位于原文边界的整行，不推断未知页码、不改正文或PDF。引用与研究仍提交item.excerpt原文；来源核对失败不复制。
- 三组文案：原文寻证「从一个问题，读到原文。」；问题出发「带着问题，重读经典。」；比较解释「同一个问题，有哪些解释？」。入口样式只在demo等待用户选择，正式入口未代选新形态。
- 验证：tsc退出0；source-text与discovery-read-recovery共6项通过；Vite demo build退出0；独立候选Vinext最终构建退出0（tmp/excerpt-ui-20261113/build-B-final.log）。未运行正式E2E或生产检索。本机CUA核对1440/390三组入口、封面、筛选搜索、默认清洗、无模式开关、长问题显示与回车反馈；手机Q2发现单行裁切，已增高并复测height=scrollHeight=72、无横向溢出。
- 实际截图output/excerpt-ui-20261113/B-query-Q1.png、B-query-Q2.png、B-query-Q3.png、B-query-mobile.png。入口http://localhost:18895/、http://192.168.5.3:18895/。仅本机候选，未推送/部署。

## 最新批注：固定分栏与真实封面

- A/B/C 预览均移除 ReaderGrip、useReaderFloatingLayout、位置记忆及组件复位入口，标题恢复普通标题；选段工具条保留固定位置。右栏桌面 sticky，窄屏恢复正常文档流。未改阅读器。
- 缺封面发生在新 demo，正式检索 EvidenceBook 已有封面。三版结果卡片和右侧出处均补入馆藏真实封面，object-fit:contain 保持完整；加载失败复用 DefaultCover。未生成或改写真实书封。
- 公开馆藏回读确认《社会运行论及其发展》版本 7051527d-6aba-42b8-a268-276c643991ae，李强、洪大用为主编；郑杭生为研究对象。预览书目信息及引用采用馆藏元数据，书页316/PDF330继续明确为用户截图示例。
- 本次 tsc --project web/tsconfig.json --noEmit --pretty false 退出0；Vite demo build 退出0。CUA检查三版1440桌面和390手机，真实封面加载成功，拖动标记为0，无横向溢出。实际截图为 output/excerpt-ui-20261113/fixed-cover-A.png、fixed-cover-B.png、fixed-cover-C.png、fixed-cover-mobile.png。旧生成图含拖动把手，仅留历史；以更新后的demo为当前候选。
- 状态B：已实现、演示检查通过，设计待用户选择；未推送公网或main。

## 产物

- imagegen A 核对与引用、B 连续精读、C 材料比较：`output/imagegen/excerpt-ui-20261113/`，含原始提示词。图中辅助书目、数量及状态是设计示意，不能作为真实馆藏或引文依据；实际 demo 只用用户截图两段原文，页码始终分开标为书页 316 / PDF 330。
- 可操作预览：`http://localhost:18895/`，内网 `http://192.168.5.3:18895/`。源码 `web/design-previews/excerpt-directions-20261113/`。复用真实 SourceExcerpt、SourceText、ReaderContextMenu、DefaultCover、L5/L6/L7 LoadingState。
- 可操作范围：三方案切换、列表/网格、排序、筛选展开与搜索输入、原始/整理/对照、已知页眉页码显示、复制、笔记与选材演示、STL 右键菜单、加载及操作状态。检索提交与在线阅读入口会明确提示设计演示，不伪装真实搜索或 PDF；笔记/选材仅本页内存，不写私人研究。本页不再读取或保存组件位置。
- 实际浏览器截图：`output/excerpt-ui-20261113/desktop-A.png`、`desktop-B.png`、`desktop-C.png`、`mobile-A.png`。

## 排查边界与根因

启动时 AST 扫描 `web/app`、`web/components` 共 592 个 TSX 文件；CSS 扫描 `web/styles`、`web/components`、`web/app` 共 204 文件。脚本产生 312 条固定小字号/小控件线索，涉及 63 文件。它们不是 312 个已证实缺陷：不少是被后续令牌/断点覆盖的旧规则，需看最终级联。清单保存于 `EXCERPT_TYPE_CONTROL_CANDIDATES_20261113.csv`，未据此批量提高所有 CSS 的优先级。

| 分类 | 已核实位置/触发 | 最小处理与边界 |
| --- | --- | --- |
| B 已实现待设计验收 | `formatSourceText` 把 OCR 每行之间的空行全部当自然段，截图形成断词和巨大段距 | 合并长中文未完句之间的 OCR 空行；保留句末、章节标题、列表、表格、数值独行和缩进边界。保留原始换行模式。不会推断文字的学术含义 |
| B | 55 个已有调用组件中的 76 处原文直接渲染，跨检索/阅读批注/研究/公共人物理论主题/后台原文审核 | 接入 SourceText 统一 16px 起、1.85 行高、正文墨色、正常中文换行；短列表继承紧凑字号。另为来源预览和检索详情接入共用控件。私人手写笔记、人工正文对照、引用格式、PDF text layer、offset/anchor 未改 |
| B | `EvidenceSummary` 在右栏重复主区全文 | 改名出处与引用，调用既有 citation-preview 默认显示 GB/T 7714—2025；保留页码、归属核对、关联概念、上下文、其他格式和研究选材。未增加自动摘要或新研究系统 |
| B | 新增清洗文本复制入口可能沿用过期结果 | 生产检索的复制入口先调用原来源核对 API，失败显示错误，不走手动复制降级；仅剪贴板权限失败提供手动文本。引文复制也重新核对来源 |
| B | 来源预览工具栏 27×28px，页码输入宽 37px，控件不换行 | 点击区域 36px 起、窄屏 40px、页码 4.5em、工具栏自然换行；正文提升可读字号与行距 |
| B | `.book-actions` space-between 把操作散到整行且不换行；`.book-summary` 正文沿用 metadata 尺寸及 1.45 行高 | 操作按用途靠左成组、固定 gap、换行、36px 起；简介使用正文令牌和 1.75 行高 |
| B | 共用 `.button` 缺少本层禁用/忙碌样式，长标签和图标容易受挤压 | flex 图标不收缩、自然行高/换行、禁用和忙碌光标、悬停轮廓，触屏主按钮 44px 起；沿用已有焦点/按压和减少动态效果规则 |
| B | 检索 inspector 使用 -132px 顶部负外边距 | 去掉对前方标题固定高度的假设，回到所在列正常起点 |
| D 开发关闭，演示检查通过 | 手机预览标题被右侧工具压出两字孤行；清洗弹层切模式后遮文；开发热刷新重复 createRoot | 标题占整行、工具与眉题同排；点击外部/模式切换/Escape 收起清洗；Vite 热刷新复用 root |

格式清洗仅作用于派生显示。`omitSourceMarginalia` 默认关闭，仅用户勾选时按明确书名/页码、首尾位置、整行精确匹配隐藏；不能识别全部页眉或保证 OCR 正确。源码保留原文 prop，所有 citation-preview/selected_text、研究引用和 PDF 锚点继续传原始文字。测试检查非空白字符不变与二次格式化幂等性。

## 设计借鉴

- USWDS Typography：正文可读尺寸、稳定左对齐、适当行长与段落间距。中文候选使用约 30–42 字的正文宽度，不把英文字符数直接照搬。https://designsystem.digital.gov/components/typography/
- Apple HIG Buttons：按钮留出可点击空间、同组一致尺寸、优先级靠样式表达、必要按压反馈。https://developer.apple.com/design/human-interface-guidelines/buttons
- Adobe Spectrum States：常态、悬停、按下、键盘焦点、禁用、选中与拖动分别表达。https://spectrum.adobe.com/foundations/behavior/states

## 验证

- `node --import tsx --test tests/source-text.test.mjs tests/citation-text-20261112.test.mjs tests/reader-floating-layout.test.mjs`：6 项通过。覆盖 OCR 空行、段落/章节/列表/表格/页码边界、显示字符保留、显式边注过滤、引用 HTML 转义及既有拖动边界/跨书位置记忆/复位。首次漏 `--import tsx` 导致 TSX 无法加载，修正运行命令后通过；不是产品测试失败被忽略。
- `tsc --noEmit --pretty false` 退出 0；demo Vite build 退出 0。
- 独立源码快照（2034 个源码/资源文件，不包含真实 env、依赖、运行数据）Vinext build 退出 0，保留共享工作区原构建；最终补丁后的构建回执见后补记。
- CUA 真实预览检查：A/B/C、原始/清洗对照、页眉页码开关、复制成功反馈、侧栏笔记保存、右键加入选材、GB/T 持续显示、键盘移动/复位、失败状态/重试/忙碌状态；1280 与 1440 桌面及 390 手机检查，无页面横向溢出。截图已保存。
- 这里的笔记/选材验证是明确标记的 demo 状态；未写真实私人资料。没有将全站静态扫描写成所有路由运行通过；尚未登录生产逐页检查本轮新排版，也未进行真实馆藏引用端到端重测。

## 下一步

三方案可共存为普通检索 A、精读 B、比较 C；尚未把该组合记为用户采纳。共享格式修复和组件已写入当前源码；全局三种布局只存在设计预览。选择后沿现有检索、研究、引用接口整合，继续保持来源权限和同一书库；不创建另一套数据。

## 最终本地回执

最终 6 项定向检查、类型检查及独立 Vinext 构建均退出 0。源码/预览/审计清单共 73 文件保存在本地 `codex/excerpt-components-20261113`，功能检查点 `5b61f2c1fb511ea8d81d5ae38ca4cdd452de2f11`。为明确区分接入前已有修改，先保存本地基线 `be4e3ad2a7683a169945b46b9161b366c8f83bc6`；该基线并非本轮新增功能或可直接上线的批准。未 checkout、reset、清理或改动共享 index，两份原暂存 blob 回读相同。未推送远端或生产。
