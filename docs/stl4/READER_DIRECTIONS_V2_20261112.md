# 阅读器业务核对与六组新设计候选

日期：2026-11-12。范围：源码只读审计、官方设计参考、6 张 Image Gen 图、独立内网交互 demo。没有修改正式 reader/API，没有部署公网。

## 最新决定与交付

用户要求阅读器与 Logo 加载各增加 3 版，除既有品牌标识外，允许大幅改变组件。随后强调加载场景很多，不可全部用一种，认可当前呈现方向；此认可不是最终方案选择。

入口 `http://192.168.5.3:18885/`，本机 `http://127.0.0.1:18885/`。

| 候选 | 组织方式 | 适合的工作 |
| --- | --- | --- |
| R1 研读工作台 | 左导航、中原文、右原文/笔记/研究，稳定结构 | 边读边记录，频繁核对引用 |
| R2 静读书桌 | 原文为主，目录浮层，笔记抽屉，横向研究资料区 | 长时间连续阅读，按需整理 |
| R3 对读长桌 | 双版本页、独立/同步翻页、下方对齐/术语/研究台 | 原文与译文比较、人工对齐 |
| L5 页序展开 | 原 SVG 书页层依次显现 | 首次进入阅读器或文献 |
| L6 墨金汇读 | Logo 不动，标识外两条短线相向汇合 | 小型来源区、短时核对 |
| L7 书签循行 | Logo 不动，纸页边缘的书签运动 | 单页 PDF 容器等待 |

三组 Logo 可以按用途共存。原 SVG 几何和颜色不变；生成图只用于构想，图中的词句不是产品文案定稿或功能证据。

## 参考证据与取舍

- Zotero 官方 PDF reader 文档和官方截图：标注可进入笔记并保留原文页与引用回跳。借鉴“原文、摘录、笔记关联清楚”，不照搬客户端颜色。https://www.zotero.org/support/pdf_reader
- Readwise 官方 PDF 文档及工具演示：文献信息、Notebook、PDF 选区与阅读工具相对集中。文档区分原 PDF 与 Enhanced text 的能力。这里只借工具组织，不宣称本项目已有 PDF 重排或图片框选。https://docs.readwise.io/reader/docs/faqs/pdfs
- JSTOR 官方 Presenting Research 文档：资料集进入、页缩放、缩略图、内容并排比较与返回。借鉴同一任务的比较和回程，不引入第二套馆藏。https://support.jstor.org/hc/en-us/articles/5377264237079-Workspace-Presenting-Research

本站保留纸白 #F7F4EE、炭黑 #242424、白内容层、暖灰与少量砂金；标题/正文宋体，工具系统无衬线。使用 React/Next/Vinext/Django 既有业务；本 demo 无依赖静态 HTML/CSS/JS，只为选择布局，不是第二个产品栈。

## 不能称为完全覆盖的具体依据

| 分类 | 证据位置 | 触发与影响 | 最小后续范围 |
| --- | --- | --- | --- |
| A：候选入口回归 | `web/components/reader-workspace.module.css:71–74`；`reader-shell.tsx` 的 bookHeading 与 More | 1200px 以下隐藏唯一版本选择器，More 没有替代版本入口；需要退出阅读才能换版本 | 保留紧凑版本入口或在更多中提供同一个选择组件 |
| A：布局行为不一致 | `web/components/reader/use-reader-records.ts:108–115` | URL focus 定位笔记仍执行 setSidebarTab(notes)+setLeftPanel(true)，新候选日常笔记入口在右边；同一笔记出现两套方向 | 定位笔记时复用右侧笔记面板；高亮导航保持对应职责 |
| A：返回上下文遗漏 | `web/components/reader-shell.tsx:496`；`web/app/reader/[assetId]/page.tsx:27–30` | 从研究进入后再切并读，只带 mode/page；ParallelReader 也未接研究上下文与 return_to | 安全携带并读所需的项目及返回路径，避免误用跨版本 reference |
| C：流程优化，非写入错误 | `reader-shell.tsx:285–290`；`shared-citation-overlay.tsx:55` | 引用/选材浮层只接来源与选文，projectId 初始化为空；即使从当前研究进入也要再选目标 | 可传入并重新鉴权的默认项目，保留显式目标确认 |
| B：已有能力需设计验收 | `reader-shell.tsx:412,419` | embedded 分支不使用新的 workspace 样式，策划嵌入场景不能按独立 reader 的图宣称完成 | 选型后验证嵌入宽高和工具访问，不重复实现业务 |
| B：已有并读独立组件 | `web/components/reader/parallel-reader.tsx` | 私人对齐、术语差异、候选判断与公共校准均已存在，之前参考图未展示完整流程 | R3 展开相关组件；正式整合仍待设计选择 |
| C：能力边界 | `web/components/reader/use-reader-selection.ts:72` | 新选段限同一 PDF 页的文字层；跨页拒绝，图片/表格没有矩形选取入口 | 如需要跨页/区域选取须单独确定功能与锚点，不伪装现成功能 |

本表依据本轮实际阅读的源码；没有将其等同公网复现。候选改动是否已在线上运行仍须部署核验，不能称线上已经修复。

## 逐项业务覆盖

| 场景 | 代码核对 | 新方案 / 仍需验证 |
| --- | --- | --- |
| 身份与文献权限 | route requireReaderSession，owner/session 变化清理状态 | demo 不接登录；正式接入沿用权限，不恢复访客 PDF |
| 目录折叠/搜索/页码 | ReaderShell outline 与 use-reader-pages | 三版保留；缺目录时按页阅读，不制造目录 |
| 文内检索 | use-reader-search，原文字层/获准 OCR | demo 可筛示例文字；真实全文查询保留原接口 |
| PDF 页面控制 | 页序、印刷标记、缩放、旋转、全屏、深浅阅读 | demo 展示页码/缩放/专注，旋转与深浅主题仍为现有正式能力，未重做完 |
| 版本与修订 | access/manifest、revision 校验与版本选择 | 窄屏可搜索版本，草稿未存时阻止换版；真实资产切换另验 |
| 六项选段工具 | 复制、引用、高亮、划线、笔记、原文选取 | 三版共享工具；无文字层收起选段操作 |
| 当前页/选段引用 | use-reader-citation 清理旧请求；shared preview 核对来源 | 默认 GB/T 直接文字，其他格式弹层；不加下载引用 |
| 书目/选段区别 | edition 与 revision/quote 分开 | 图中示例引用不作为格式通过；真实模板复用已审计服务 |
| 书签、笔记、高亮 | use-reader-records 完整分页、定位、删除与标签 | demo 笔记保存/回跳与草稿保护；未模拟所有删除/分页逻辑 |
| 私人与公开边界 | 现有研究、书单、公共校准分别授权 | R3 独立校准预览；不将私人材料自动提交公开 |
| 我的研究 | use-reader-research 解析项目/轮次/reference、同版本锚点 | R1 右栏、R2 下方资料区、R3 研究台；模型分析仍在既有研究页 |
| 目标研究/书单 | shared-citation-overlay 查询、去重、原请求恢复 | demo 可搜索选目标；真实保存和幂等不由静态 demo 证明 |
| 研究来源回跳 | research-navigation 安全 return_to 与 evidence refs | demo 保存来源后可回到页码；正式并读返回缺口上表列明 |
| 原文/译文并读 | ParallelReader 双侧版本与私人判断 | R3 展示双页、同步/独立翻页、人工确认/存疑/无对应/增补 |
| 术语差异 | ParallelReader 术语、译文与两侧锚点 | R3 保留私人术语编辑；不称自动对齐已核对 |
| OCR/处理状态 | ReaderOcrStatus、权限、原文件/派生文件 | 保留可阅读扫描页；任务进度使用真实值，未识别页不伪造可选文字 |
| 下载 | 原 PDF/可搜索副本/目录派生副本状态 | demo 保留选项展示，无真实 PDF 下载 |
| 异常恢复 | access、来源变化、未知保存、记录读取、断线 | 阅读器 8 种状态，草稿原位；未把模拟恢复写成真实服务通过 |
| 关联研究 | 已确认学者/理论/主题，AskLibraryLink 的整本文献范围 | 不将整本提问伪装成仅所选段落提问 |
| 嵌入阅读 | embedded ReaderShell 用于策划 | 尚未形成专门嵌入 demo；不宣称独立三版已覆盖所有容器 |
| 窄屏/无障碍 | 移动抽屉、可关闭、版本/研究入口、降低动效 | 本轮专门检查 390px，弹窗原生焦点约束 |

## 多场景加载体系

上一轮静态清单在 `output/design/reader-loading-system-20261112/loading-source-inventory.csv` 与 `loading-style-inventory.csv`：267 个源文件候选、22 个样式文件候选，不是 289 个缺陷。调用点详细映射沿用 `READER_LOADING_DESIGN_20261112.md`，避免重复扫描或扩大范围。

| 场景族 | 呈现方式 | 状态原则 |
| --- | --- | --- |
| 欢迎进入/路由首次打开 | 合适尺寸的品牌动效 + 真实文案 | 不加人为等待，不同时显示第二个转圈 |
| 图书/学者/后台列表首次加载 | 贴合最终行列的骨架 | 维持布局尺寸，不用三个不相关矩形 |
| 检索/筛选/排序刷新 | 原内容保留 + 区域顶端细线 | 不能把旧结果写成新查询已完成 |
| 来源/引文/页码核对 | 小范围骨架/等待 | 切页后清除旧引用，未核准不可复制上一页 |
| 笔记/收藏/表单保存 | 原按钮状态 + 就近成功/失败 | 保留输入，未知结果核对原请求，防重复提交 |
| OCR/导入/索引/派生 PDF/下载 | 数量、阶段与真进度/队列 | 未知时不编百分比；已保存不等于派生文件已生成 |
| 单页 PDF 渲染 | 当前页容器占位，邻页保持 | 不用全屏动画打断连续阅读 |
| 研究流式回答 | 保留已到内容，尾部状态与停止入口 | 不以假打字计时冒充模型或网络状态 |
| 失败/断线/来源失效 | 具体原因、重试与恢复 | 失败不是持续加载，保留草稿 |
| 分页/加载更多 | 列表末尾局部反馈 | 原结果及滚动位置保持 |
| 封面/肖像/图片延迟 | 固定比例、占位与替代信息 | 不为每张图重复播放大 Logo |
| 真空数据/无搜索结果 | 空态与明确下一步 | 请求结束就结束加载，不永久骨架 |

内网提供以上 12 类组件。相同组件可覆盖不同路由，但每个调用点仍须对接其真实状态、权限和恢复逻辑。用户选型之前未进行全站替换。

## 资产及验证记录

- Image Gen 内置工具实际生成 6 图，全部保存并复制到 preview；完整提示词/原始路径见 `output/design/reader-directions-v2-20261112/generation-manifest.json`。
- 源码 `design-previews/reader-directions-v2-20261112/`；无运行依赖或新业务 API。
- 品牌原 SVG 的 SHA256 应为 `415f849fb95bfc00e0e4508d8bbe3b99de9f4867bd614f5b5dc2801dcc0e6b57`，最终核对记录在交付时追加。
- 本轮验证只针对静态 demo，不属于生产端到端验收。最后的检查与截图见本文件下方追加记录。
- 此前引文修复、规范姓名、真实 PDF 流程与已接受 C 检索的发布仍独立收尾；本轮没有以新图替代这些工作，也未称已上线。

### 本轮实际检查结果

- `node --check design-previews/reader-directions-v2-20261112/preview.js` 退出 0；`git diff --check` 针对新候选路径退出 0。
- 6 张 PNG 从内网 HTTP HEAD 均返回 200，文件约 1.7–2.1 MB；品牌源文件与 demo 的 SHA256 完全相同。
- Edge 实际打开内网地址，查看 R1/R2/R3、Logo 和六图页面，浏览器未记录脚本错误。
- 390×844 检查三版 document.scrollWidth 均 390；版本按钮与目录/笔记/引用/研究/更多入口可见。临时 viewport 已复位。
- 实际操作：笔记填写与保存、R2→R3 草稿保留、版本关键词筛选、草稿未保存时的换版阻止、研究/书单搜索、加入示例书单并回跳 PDF138。
- 来源变化状态下右侧显示重新核对，复制引用按钮数为 0，恢复正常状态后引用返回。
- R2 研究资料区及 R3 对齐台的主要保存按钮完整可见；调整了原本过短的底部容器。
- 三组动画暂停后，实际伪元素 animationPlayState 均为 paused；减少动态效果开启后 animationName 均为 none。12 类加载场景均在页面中。
- 保存按钮等待/成功、手动示例任务 42→120 页已操作。进度不是后端实际任务，不将其记为 OCR 验收。
- 截图：`demo-r1-desktop.png`、`demo-r2-desktop.png`、`demo-r3-desktop.png`、`demo-mobile-390.png`、`demo-loading-system.png`，均在 `output/design/reader-directions-v2-20261112/`。
- 当前机器以 LAN 地址访问正常；未用第二台实体设备验证 LAN 防火墙/跨设备连通。HTTP 下剪贴板权限可能不可用，demo 提供直接选中文字的退路。
- 新设计未发布。原有暂存对象 CURRENT_PROGRESS `77ec6fa…`、WORKSPACE_TYPE_REVIEW `947ea56…` 保持。
