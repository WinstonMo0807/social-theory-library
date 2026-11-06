# STL 架构映像

用于内部汇报的六幕交互式架构展示。沿用 STL 已确认的黑金标识、纸白基底及本地 Noto 字体。直接导入仓库的 `BrandImage`、`Button` 和 `Dialog`，使用现有 React、esbuild 与 Playwright，不新增 npm 依赖。

展示不属于业务网站路由，不请求业务 API，不写数据库、不启动任务、不读取凭据。服务仅监听 `127.0.0.1`，只提供构建后的静态文件。内部路径与架构索引仍属于内部汇报材料，不应放入公网静态目录。

## 启动

从本仓库根目录运行，要求现有 `web/node_modules` 和 Node 可用：

```powershell
node web/architecture-showcase/build.mjs
node web/architecture-showcase/serve.mjs
```

入口为 <http://127.0.0.1:5196/>。如果要先查看完整总览，使用 <http://127.0.0.1:5196/?stage=3>。`serve.mjs` 的可选首参数可以改端口，仍只绑定本机。也可运行本目录 `start.ps1`。停止使用当前终端的 Ctrl+C。

构建目录 `dist` 已忽略，不提交。它包含本地字体、标识、架构快照及存在时的匿名页面截图，可完整复制用于离线汇报；复制后把 `serve.mjs` 放在 `dist` 的同级目录，用 Node 启动。正式演示无需 API、数据库、网络模型或联网字体。

## 场景与操作

1. 全站总览：中央品牌与六个产品领域，点击可聚焦并展开子模块。
2. 页面地图：公开浏览、登录阅读、本人研究、管理工作区；可查看完整路由清单。
3. 研究工作流：问题、原文证据、Reader 定位与共享引用。只表达真实调用关系，不发起检索。
4. 技术与数据：Web、Django、PostgreSQL、Celery/Redis、Meilisearch、模型、OCR 与文件职责。
5. 设计系统：实际品牌、字体与色值、复用控件、页面组合及匿名首页截图。
6. 实现与证据：本轮观察、已有代码待验收、具体未闭环项。

默认手动推进。播放只推进当前场景，最后一阶段停止。点击阶段名称可直接跳到任一阶段；点击模块显示子模块、来源、路径和权限说明。返回全局会显示当前场景的完整结构。

| 操作 | 键盘 |
| --- | --- |
| 上一阶段 / 下一阶段 | ← / → |
| 播放 / 暂停 | 空格；按钮聚焦时保留原生操作 |
| 切换六幕 | 1–6 |
| 重播当前阶段 | R |
| 全屏 | F |
| 关闭详情 / 对话框 | Esc |
| 访问节点与控件 | Tab、Enter |

支持系统 `prefers-reduced-motion`。开启后禁用定时播放和位移动画，仍可手动逐阶段讲解。画布保持 16:9，实际检查了 1920×1080、1440×900、1366×768、1280×720；窄竖屏按比例缩放，优先用于桌面或横屏投影，并未宣称手机上的大字号体验已优化。

## 图片与视频

右上角导出菜单提供：

- PNG：当前画面 3840×2160，适合直接放入 PPT。字体、标识与图片均在本机嵌入，导出会移除工具菜单。
- SVG：内嵌字体与图像的独立静态画面，使用 SVG `foreignObject`，适合浏览器查看。PPT 请用 PNG，以免 Office 对该 SVG 特性的支持差异。
- WebM 录制：选择本展示标签页，再手动讲解和推进；停止后下载。录制只在本机保存，不上传。浏览器需支持 `getDisplayMedia` 和 `MediaRecorder`。

已生成文件位于仓库的 `output/playwright/architecture-showcase/`：六幕 1920 截图、节点详情、全屏、`4k/` 六幕高分辨率 PNG，以及 `video/STL-architecture-1080p.webm`。视频是无旁白的自动操作录屏；不代表现场讲解必须按固定节奏。

同目录的 `STL-architecture-local-20261106.zip` 包含无需安装 npm 依赖的构建成品、独立 Node 静态服务器、六张 PPT 图片及视频，可移到另一台电脑。重新打包使用 `python web/architecture-showcase/package.py`。

重生成成品（本机服务运行时）：

```powershell
node web/architecture-showcase/export-assets.mjs
node web/architecture-showcase/record.mjs
```

这两个脚本使用已安装的 Playwright 和 Microsoft Edge。录制脚本会运行约一分钟；不触发 STL 业务操作。

## 内容维护

内容、证据和表现分开：

| 文件 | 责任 |
| --- | --- |
| `audit.py` | 人工核实的模块、关系与状态解释，以及自动提取逻辑 |
| `architecture.json` | 可读的架构数据快照、全部页面路由与直接导入、源码哈希、有限运行记录 |
| `evidence-index.csv` | 节点到源码文件、行号、类型和 SHA-256 的索引 |
| `runtime-evidence.json` | 本轮匿名页面观察；只保留路径，不保存内部服务器地址 |
| `scenes.ts` | 场景叙事、阶段与空间布局 |
| `app.tsx` / `style.css` | 交互、聚焦、动画和排版 |
| `export.ts` | 本机图片与标签页录制 |

架构变化后先查源码，更新 `audit.py` 中的解释与锚点，再执行：

```powershell
python web/architecture-showcase/audit.py
node web/architecture-showcase/build.mjs
```

提取器会核验所有来源文件与锚点，生成当前行号和整文件哈希，检查连线端点、关系类型与来源引用。锚点丢失会直接失败。它自动更新路由与直接导入，不会根据文件存在自动认定功能可用，也不会自动推断模块所属或升级验收状态。

需要更新真实页面截图时，可对明确授权的预览地址运行 `capture-site.mjs <预览原点>`。脚本创建全新的匿名浏览器上下文，只 GET 七个指定页面，不保存 cookies、服务原点、登录资料或私人内容。随后重新执行提取与构建。不要把未经检查的登录态截图复制进 `site`。

## 验证口径

`node web/architecture-showcase/verify.mjs` 是本展示的定向浏览器检查。报告保存为 `output/playwright/architecture-showcase/verification.json`，覆盖六幕、节点与子节点、来源搜索、暂停与阶段重播、键盘、全屏、四档桌面视口、减少动态效果、4K PNG 和外部请求隔离。

这不替代 STL 的正式全站验收。本轮真实站点只做匿名渲染与 `/explore` 登录跳转观察；没有重新执行登录业务、检索质量、OCR、私人研究、后台提交或生产操作。自动目录的两份样本结果来自本轮读取的最新项目记录，在节点详情中明确标为记录依据；没有将其冒充本轮重新运行。
