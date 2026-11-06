# STL 架构演示 v3

用于内部汇报的 5 幕交互式架构展示。使用演示包含检索与引用、入库与发布、私人研究，共 38 步。每步记录操作、输入、输出、接口、字段、权限和失败条件。

动效参考 Elicit 当前首页的同画面连续操作演示。沿用 STL 已确认的黑金标识、纸白基底及本地 Noto 字体。直接导入 `BrandImage`、`Button` 和 `Dialog`，使用现有 React、esbuild 与 Playwright，无新增 npm 依赖。

展示是独立的本机应用，仅提供静态文件，不执行真实业务操作。界面动作依据实际组件重建。文献、页码与成功状态均为示例，原文以线条表示；这些画面不构成业务验收记录。服务只监听 `127.0.0.1`。内容包含内部架构和管理路径，仅供内部汇报。

## 启动

从本仓库根目录运行，要求现有 `web/node_modules` 和 Node 可用：

```powershell
node web/architecture-showcase/build.mjs
node web/architecture-showcase/serve.mjs
```

入口为 <http://127.0.0.1:5196/>，默认打开检索演示。完整总览使用 <http://127.0.0.1:5196/?scene=0&stage=3>。入库演示使用 <http://127.0.0.1:5196/?scene=2&journey=1>，私人研究使用 <http://127.0.0.1:5196/?scene=2&journey=2>。

也可运行本目录的 `start.ps1`。要更换端口，可在 `serve.mjs` 后添加端口号。按终端中的 Ctrl+C 停止服务。

`dist` 包含网页、字体、标识、架构数据和已保存的页面截图。离线使用时，复制整个 `dist` 目录，并将 `serve.mjs` 放在同级目录。启动后无需连接业务 API、数据库或模型服务。`dist` 已加入 Git 忽略清单。

## 场景与操作

1. 全站总览：展示 6 个功能领域，点击模块可查看子模块与来源。
2. 页面地图：按浏览、阅读、私人研究和管理权限组织页面。
3. 使用演示：在固定界面中连续呈现 3 条流程。按 20、10、8 步呈现。输入、指针、勾选、排序、加载与回执随时间轴变化。右侧说明每步操作及界面反馈。
4. 底层架构：Web、Django、PostgreSQL、Celery/Redis、Meilisearch、模型、OCR 与文件职责。
5. 品牌标识：实际品牌、字体与色值、复用控件、页面组合及匿名首页截图。

默认停在当前阶段。点击“播放流程”后开始播放，暂停后可从当前位置继续。最后一步结束后自动停止。完成后再次播放，会从流程起点开始。拖动进度条可定位；使用底部步骤选择器，可直接显示该步的完整画面。流程下方的分段按钮可跳到对应分段。

点击“查看步骤依据”，可查看本步输入、输出、接口、字段、权限和源码。演示内可操作的按钮只切换展示步骤。节点详情中的“实际使用”可跳到对应演示。点击“返回全局”，会关闭详情并显示当前场景的最后阶段。

| 操作 | 键盘 |
| --- | --- |
| 上一阶段 / 下一阶段 | ← / → |
| 播放 / 暂停 | 空格；选中按钮时，空格执行该按钮操作 |
| 切换场景 | 1–5 |
| 从当前阶段起点重新播放 | R |
| 全屏 | F |
| 关闭详情 / 对话框 | Esc |
| 访问节点与控件 | Tab、Enter |

支持系统的“减少动态效果”设置（`prefers-reduced-motion`）。开启后停止自动播放和位移动画，仍可手动切换。画布比例为 16:9，已检查 1920×1080、1440×900、1366×768 和 1280×720。竖屏会缩小画布，正式汇报宜使用桌面横屏。

## 图片与视频

右上角导出菜单提供：

- 导出 PNG：生成当前画面的 3840×2160 图片，适合插入 PPT。图片包含字体和品牌资产，隐藏工具菜单。
- 导出 SVG：生成内嵌字体与图像的文件，适合浏览器查看。文件使用 `foreignObject`，Office 支持情况可能不同，PPT 宜使用 PNG。
- 录制演示：选择本展示标签页，再播放或手动切换。停止后下载 WebM 视频。浏览器须支持 `getDisplayMedia` 和 `MediaRecorder`。

新版产物位于 `output/playwright/architecture-showcase-v3/`：5 幕截图、38 个步骤截图、节点详情、全屏截图、`4k/` 中的 11 张 3840×2160 PNG，以及 `video/STL-architecture-v3-1080p.webm`。视频约 3 分钟，完整录制 3 条流程，再展示步骤依据与其余架构场景。现场网页仍可手动控制节奏。

同目录的 `STL-architecture-v3-local-20261106.zip` 包含构建成品、独立 Node 静态服务器、源码、11 张 PPT 图片和视频。解压后运行 `start.cmd`，无需安装 npm 依赖。重新打包使用 `python web/architecture-showcase/package.py`。

## 备份

本轮修改前的完整 v2 已保存为 `output/backups/STL-architecture-v2-final-STC-20261106.zip`，保留当时源码、成品、服务器和说明。上一轮 v2 离线包仍在 `output/playwright/architecture-showcase-v2/`。

### 文案修订后的原版

备份目录为 `output/backups/STL-architecture-v1-STC-20261106/`，同级有 ZIP。备份保留原版布局与播放方式，以及第一轮 STC 文案修订。`source/` 保存当时源码，`sha256.json` 记录文件校验值。

双击备份内的 `start.cmd`，打开 <http://127.0.0.1:5197/>。备份与新版可以同时运行。原版先前的截图和视频仍在 `output/playwright/architecture-showcase/`。

重生成成品（本机服务运行时）：

```powershell
node web/architecture-showcase/export-assets.mjs
node web/architecture-showcase/record.mjs
```

这两个脚本使用已安装的 Playwright 和 Microsoft Edge。录制脚本约需 3 分钟，不触发 STL 业务操作。

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

提取器按源码中的定位文本查找行号，并保存文件校验值。找不到定位文本时，提取失败。模块、流程和职责说明的来源都写入 CSV 索引。页面路由和组件导入会自动更新，功能是否可用仍须单独验证。

动画时长保存在各步骤的 `duration` 中，单位为毫秒。步骤的 `visual` 通过 `visualStates` 选择已有画面，调整步骤顺序不改变画面含义。`chapter` 指定分段，`feedback` 说明界面反馈，`target` 指定演示指针的目标。事实变更只需更新数据文件；增加新的画面类型时再修改渲染组件。

中文按项目此前保存的 STC 规则复核。规则来源为 [STC Simplified Technical Chinese](https://github.com/daimonia-ai/STC-Simplified-Technical-Chinese)，本机副本位于 `tmp/stl4-font-copy-20261029/stc-reference/`。使用 `copy-snapshot.py` 提取 JSON 中的展示文字，避免把 JSON 引号和源码标识当成文案错误。`copy-review.json` 保留机器疑点的语义判断。

更新网站截图时，对已授权的预览地址运行 `capture-site.mjs <预览原点>`。脚本在未登录的浏览器中读取 7 个指定页面，不保存登录信息或私人内容。随后重新提取并构建。放入 `site` 的截图须先检查是否含私人信息。

展示术语统一如下：

| 用语 | 含义 |
| --- | --- |
| 作品 / 出版版本 / 文件 | 分别对应 `Work`、`Edition` 和 `Asset` |
| 文档修订 | 同一文件的正文解释版本，对应 `DocumentRevision` |
| 原文位置 | 原文所在的文档版本、PDF 页码与选区 |
| PDF 副本 | 保留原件后另行生成的文件，如带目录书签的 PDF |
| 生效的发布修订 | 当前用于确定公开内容的修订 |
| 已实现 · 待验收 | 已有源码，仍须验证业务运行结果 |

## 验证口径

定向检查命令：

```powershell
node web/architecture-showcase/verify.mjs
node web/architecture-showcase/verify-journeys.mjs
```

两个脚本共通过 279 项检查。报告保存在 `output/playwright/architecture-showcase-v3/` 的 `verification.json` 和 `journey-verification.json`。

检查覆盖：

- 5 幕布局、38 步流程，以及节点跳转和来源详情。
- 播放内容变化、暂停续播和进度条定位。
- 全屏、4 档桌面视口、减少动态效果和 4K 导出。


这些检查只验证展示应用。已保存的网站观察覆盖未登录时的页面显示和 `/explore` 登录跳转。STL 全站业务仍按项目记录验收。自动目录的 2 份样本结果来自已有项目记录，本展示未重跑样本。
