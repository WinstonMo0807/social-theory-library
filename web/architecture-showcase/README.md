# STL 架构演示 v2

用于内部汇报的 6 幕交互式架构展示。使用演示包含检索与引用、入库与发布、私人研究，共 14 步。每步记录操作、输入、输出、接口、字段、权限和失败条件。

动效参考 Elicit 当前首页的同画面连续操作演示。沿用 STL 已确认的黑金标识、纸白基底及本地 Noto 字体。直接导入 `BrandImage`、`Button` 和 `Dialog`，使用现有 React、esbuild 与 Playwright，无新增 npm 依赖。

展示不属于业务网站路由，不请求业务 API，不写数据库、不启动任务、不读取凭据。服务仅监听 `127.0.0.1`，只提供构建后的静态文件。内部路径与架构索引仍属于内部汇报材料，不应放入公网静态目录。

## 启动

从本仓库根目录运行，要求现有 `web/node_modules` 和 Node 可用：

```powershell
node web/architecture-showcase/build.mjs
node web/architecture-showcase/serve.mjs
```

入口为 <http://127.0.0.1:5196/>，默认打开检索演示。完整总览使用 <http://127.0.0.1:5196/?scene=0&stage=3>。入库演示使用 <http://127.0.0.1:5196/?scene=2&journey=1>，私人研究使用 <http://127.0.0.1:5196/?scene=2&journey=2>。

`serve.mjs` 的可选首参数可以改端口，仍只绑定本机。也可运行本目录 `start.ps1`。停止使用当前终端的 Ctrl+C。

构建目录 `dist` 已忽略，不提交。构建结果包含本地字体、标识、架构快照及存在时的匿名页面截图，可完整复制用于离线汇报；复制后把 `serve.mjs` 放在 `dist` 的同级目录，用 Node 启动。正式演示无需 API、数据库、网络模型或联网字体。

## 场景与操作

1. 全站总览：中央品牌与六个产品领域，点击可聚焦并展开子模块。
2. 页面地图：公开浏览、登录阅读、本人研究、管理工作区；可查看完整路由清单。
3. 使用演示：在固定界面中连续呈现 3 条流程。操作内容随时间轴变化，右侧同步说明实际模块和数据交接。
4. 技术与数据：Web、Django、PostgreSQL、Celery/Redis、Meilisearch、模型、OCR 与文件职责。
5. 设计系统：实际品牌、字体与色值、复用控件、页面组合及匿名首页截图。
6. 实现与证据：运行观察、已有代码待验收、待配置或待接入能力。

默认停在当前阶段。点击“播放流程”后，从当前阶段起点播放；暂停后再次播放会继续当前位置。最后一步结束后自动停止。完成后再次播放会从流程起点开始。进度条可拖到任意位置，阶段按钮直接显示该步的完整画面。

点击“查看调用与字段”展开当前步骤的源码依据。架构节点中的“实际使用”可跳到对应演示。技术节点还列出存储记录和服务职责。返回全局会关闭详情，并显示当前场景最后阶段。

| 操作 | 键盘 |
| --- | --- |
| 上一阶段 / 下一阶段 | ← / → |
| 播放 / 暂停 | 空格；按钮聚焦时保留原生操作 |
| 切换六幕 | 1–6 |
| 从当前阶段起点重新播放 | R |
| 全屏 | F |
| 关闭详情 / 对话框 | Esc |
| 访问节点与控件 | Tab、Enter |

支持系统 `prefers-reduced-motion`。开启后禁用定时播放和位移动画，仍可手动逐阶段讲解。画布保持 16:9，实际检查了 1920×1080、1440×900、1366×768、1280×720；窄竖屏按比例缩放，优先用于桌面或横屏投影，并未宣称手机上的大字号体验已优化。

## 图片与视频

右上角导出菜单提供：

- PNG：当前画面 3840×2160，适合直接放入 PPT。字体、标识与图片均在本机嵌入，导出会移除工具菜单。
- SVG：内嵌字体与图像的独立静态画面，使用 SVG `foreignObject`，适合浏览器查看。PPT 请用 PNG，以免 Office 对该 SVG 特性的支持差异。
- WebM 录制：选择本展示标签页，再手动讲解和推进；停止后下载。录制只在本机保存，不上传。浏览器需支持 `getDisplayMedia` 和 `MediaRecorder`。

新版产物位于 `output/playwright/architecture-showcase-v2/`：6 幕截图、3 条流程的关键步骤、节点详情、全屏截图、`4k/` 中的 9 张 3840×2160 PNG，以及 `video/STL-architecture-v2-1080p.webm`。视频约 111 秒，完整录制 3 条流程，再展示调用详情与其余架构场景。现场网页仍可手动控制节奏。

同目录的 `STL-architecture-v2-local-20261106.zip` 包含构建成品、独立 Node 静态服务器、源码、9 张 PPT 图片和视频。解压后运行 `start.cmd`，无需安装 npm 依赖。重新打包使用 `python web/architecture-showcase/package.py`。

## 文案修订后的原版备份

备份目录为 `output/backups/STL-architecture-v1-STC-20261106/`，同级有 ZIP。备份保留原版布局与播放方式，以及第一轮 STC 文案修订。`source/` 保存当时源码，`sha256.json` 记录文件校验值。

双击备份内的 `start.cmd`，打开 <http://127.0.0.1:5197/>。备份与新版可以同时运行。原版先前的截图和视频仍在 `output/playwright/architecture-showcase/`。

重生成成品（本机服务运行时）：

```powershell
node web/architecture-showcase/export-assets.mjs
node web/architecture-showcase/record.mjs
```

这两个脚本使用已安装的 Playwright 和 Microsoft Edge。录制脚本约需 2 分钟，不触发 STL 业务操作。

## 内容维护

内容、证据和表现分开：

| 文件 | 责任 |
| --- | --- |
| `audit.py` | 人工核实的模块、关系与状态解释，以及自动提取逻辑 |
| `architecture.json` | 可读的架构数据快照、全部页面路由与直接导入、源码哈希、有限运行记录 |
| `evidence-index.csv` | 节点到源码文件、行号、类型和 SHA-256 的索引 |
| `runtime-evidence.json` | 本轮匿名页面观察；只保留路径，不保存内部服务器地址 |
| `scenes.ts` | 场景叙事、阶段与空间布局 |
| `journeys.json` | 3 条使用流程的步骤、时长、操作、数据和来源 |
| `module-facts.json` | 技术模块的职责、记录类型和边界 |
| `journey-scene.tsx` / `journey.css` | 同画面操作演示及逐步说明 |
| `app.tsx` / `style.css` | 交互、聚焦、动画和排版 |
| `export.ts` | 本机图片与标签页录制 |

架构变化后先查源码，更新 `audit.py` 中的解释与锚点，再执行：

```powershell
python web/architecture-showcase/audit.py
node web/architecture-showcase/build.mjs
```

提取器会核验来源文件与锚点，生成当前行号和整文件哈希。模块关系、流程步骤和职责说明的来源均纳入检查及 CSV 索引。锚点丢失会失败。提取器自动更新路由与直接导入，不会根据文件存在自动认定功能可用。

动画时长保存在各步骤的 `duration` 中，单位为毫秒。步骤的 `visual` 选择已有画面类型。事实变更只需更新数据文件；增加新的画面类型时再修改渲染组件。

中文按项目此前保存的 STC 规则复核。规则来源为 [STC Simplified Technical Chinese](https://github.com/daimonia-ai/STC-Simplified-Technical-Chinese)，本机副本位于 `tmp/stl4-font-copy-20261029/stc-reference/`。使用 `copy-snapshot.py` 提取 JSON 中的展示文字，避免把 JSON 引号和源码标识当成文案错误。`copy-review.json` 保留机器疑点的语义判断。

需要更新真实页面截图时，可对明确授权的预览地址运行 `capture-site.mjs <预览原点>`。脚本创建全新的匿名浏览器上下文，只 GET 七个指定页面，不保存 cookies、服务原点、登录资料或私人内容。随后重新执行提取与构建。不要把未经检查的登录态截图复制进 `site`。

## 验证口径

定向检查命令：

```powershell
node web/architecture-showcase/verify.mjs
node web/architecture-showcase/verify-journeys.mjs
```

两个脚本共通过 77 项检查。报告保存在 `output/playwright/architecture-showcase-v2/` 的 `verification.json` 和 `journey-verification.json`。覆盖 6 幕布局、14 步流程、节点跳转、来源、播放内容变化、暂停与续播、时间轴定位、全屏、4 档桌面视口、减少动态效果和 4K 导出。第二个脚本同时检查 5197 上的原版备份，运行前须启动备份服务。

这不替代 STL 的正式全站验收。本轮真实站点只做匿名渲染与 `/explore` 登录跳转观察；没有重新执行登录业务、检索质量、OCR、私人研究、后台提交或生产操作。自动目录的两份样本结果来自本轮读取的最新项目记录，在节点详情中明确标为记录依据；没有将其冒充本轮重新运行。
