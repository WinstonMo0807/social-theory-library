# 原文排版与全站组件候选 · 2026-11-13

本轮用户新增：截图 OCR 原文排版清洗，检索右栏不再重复证据摘要，生成三组 imagegen 设计；扩展至全站摘录展示、文字、按钮位置及交互反馈。沿已采纳阅读器的黑金品牌、纸白与控件视觉。最新批注要求本检索页固定布局、恢复书封，覆盖本页此前借用拖动和复位的方案；PDF 阅读器的拖动规则保持。三组新布局尚未选定；本轮仅本机/内网候选，没有生产发布、main 推送、API/数据库变更。

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
