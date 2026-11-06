# STL 4.0 架构展映

独立的内部汇报应用。六个场景可逐段讲解、播放、暂停、聚焦节点、返回、全屏和导出。只监听 `127.0.0.1:5274`，不注册到 STL 的 Next/Vinext 路由，不代理业务 API，不连接数据库。

## 打开与启动

本轮入口：<http://127.0.0.1:5274/?scene=overview&phase=2>。

在仓库根目录执行（现有 `web/node_modules` 需可用）：

```powershell
node tools/architecture-report/audit.mjs
node tools/architecture-report/build.mjs
node tools/architecture-report/server.mjs
```

已有构建时只需最后一条。也可双击同目录的 `启动架构展映.cmd`。启动脚本不安装依赖、不终止占用端口的其他进程。需要停止时，在运行服务器的终端按 Ctrl+C。当前端口占用时先核对是否已经运行本应用。

使用仓库已有 React、Vite、TypeScript、Lucide、Playwright；没有增加业务依赖或修改 `web/package.json`。BrandImage、Button、Input 和字体/CSS 直接复用现有代码。构建复制现有品牌和字体资产到本应用的忽略目录，不修改原文件。

## 讲解方法

首次打开显示完整总览。点击“播放”从当前场景的第一段展开；自动推进只发生在当前场景内，末段停下，不自动跳到下一场景。以手动段落按钮或前后箭头控制讲解节奏。

| 操作 | 行为 |
| --- | --- |
| 下方六个场景 | 总览、信息架构、工作流、技术与数据、设计系统、实际状态 |
| 点击模块 | 聚焦其说明、内部模块、路由、权限及源码证据 |
| 返回上一层 / 返回全局 | 保留原场景和阶段 |
| 左右方向键 | 上一阶段 / 下一阶段，边界可跨场景 |
| 空格 | 播放 / 暂停；焦点在按钮时执行该按钮 |
| R | 重播当前阶段，随后暂停，不自动进入下一阶段 |
| F | 全屏 / 退出全屏 |
| 1–6 | 直接切换场景 |
| Esc | 关闭弹层或返回全局；浏览器可优先用于退出全屏 |
| Tab / Enter | 访问工具、节点和内部模块 |
| ? | 查看快捷键 |

系统减少动态效果偏好会关闭移动、流动连线与缩放过渡；段落仍可手动切换。浏览器标签隐藏时自动暂停。

画面使用 1600×900 逻辑尺寸，保持 16:9 等比适配；优先用于桌面和投影。1920×1080、1366×768、1280×720、1024×768 已检查。390 像素屏幕可操作且无横向溢出，但架构文字等比缩小，不作为手机阅读或正式讲解推荐尺寸。

## 导出与离线材料

右上角“导出”提供：

- **4K PNG**：3840×2160，保留当前场景和阶段，不含外部播放器和节点详情。
- **WebM 视频**：1920×1080，无音轨，从当前场景第一段播放到结束。

导出由本机 Edge + Playwright 执行，无页面或截图外传。PNG 和视频均为实际浏览器渲染。视频需要 Playwright 的 FFmpeg 工具，本机已安装；其他机器缺少时运行：

```powershell
node web/node_modules/@playwright/test/cli.js install ffmpeg
```

服务器启动后，可以批量导出：

```powershell
node tools/architecture-report/export.mjs all png
node tools/architecture-report/export.mjs workflow video
node tools/architecture-report/export.mjs all video
```

CLI 结果保存到 `output/playwright/architecture-report/exports/`，网页导出同时返回浏览器下载。当前已经提供六张 4K 静帧和一段研究工作流 WebM。视频导出约需当前场景的播放时长；同一服务器一次接受一个导出任务。

## 数据与证据维护

| 文件 | 用途 |
| --- | --- |
| `data/architecture.source.mjs` | 人工审计后的节点、关系、场景、状态、说明及源码锚点；主要维护入口 |
| `data/architecture.json` | 自动解析的行号、SHA-256、快照信息和展示数据 |
| `data/evidence-index.csv` | 节点与源码/项目记录的对应清单 |
| `data/inventory.json` | 全部页面文件、静态导入边、字面量页面链接及 API 路由声明 |
| `data/runtime.json` | 匿名预览只读检查结果，不保存服务器地址、Cookie 或正文 |
| `src/layouts.ts` | 展示坐标；与业务事实和实现状态分离 |
| `src/App.tsx` / `src/style.css` | 通用播放器、节点详情、场景视图和动效 |

更新架构时先检查真实调用链，修改 `architecture.source.mjs`，然后运行 `audit.mjs` 和 `build.mjs`。锚点消失、路由不存在、节点或边引用缺失会使提取失败，避免悄悄生成无来源内容。新增目录或模块不会自动被认定为可用；业务含义及状态仍需人工核对。

`audit.mjs` 默认只读源码，不连接内网。如确需刷新匿名预览证据，可显式运行：

```powershell
node tools/architecture-report/audit.mjs --probe <已授权的内网预览源地址>
```

该命令固定只读首页、欢迎页、理论页、探索门禁和三个 API 健康/权限入口；不会登录、创建检索、触发 OCR 或修改数据。截图使用全新匿名浏览器上下文，保存在 `output/playwright/architecture-report/source/`。不复用管理员或读者 Cookie。

生成数据和构建、截图、视频属于本地快照/运行产物，已忽略 Git；可维护的事实定义、提取器与播放器代码进入检查点。页面中“来源”可下载生成后的 JSON 和 CSV。

## 已完成的验证及限制

```powershell
node web/node_modules/typescript/bin/tsc -p tools/architecture-report/tsconfig.json
node tools/architecture-report/build.mjs
node tools/architecture-report/verify.mjs
```

`verify.mjs` 使用本机 Edge，检查六个场景、节点和内部模块、返回/焦点、路由筛选、暂停冻结、单阶段重播、键盘、全屏、多个尺寸、减少动态效果、4K 导出及本地服务器访问边界。截图和机器记录在 `output/playwright/architecture-report/verification.json`。另已在 Codex 浏览器实际进入/退出全屏并操作节点。

这验证的是**汇报应用**。没有因此宣称 STL 的登录业务、OCR、模型质量、复杂书种、私人资料隔离、正式部署或全站验收通过。状态页中的项目记录与本轮只读观察分别说明。自动目录使用最新项目记录，已归为实现待扩大验收；中转 API 的真实配置和调用仍未验证。政策研究暂停、RAG/LLMWiki 待定，未混入主架构。

## 技术参考

- [MDN：Fullscreen API](https://developer.mozilla.org/en-US/docs/Web/API/Element/requestFullscreen)
- [MDN：Web Animations 暂停](https://developer.mozilla.org/en-US/docs/Web/API/Animation/pause)
- [Playwright：视频录制与保存](https://playwright.dev/docs/videos)

使用原生 SVG、CSS、Web Animations 和 View Transition；不需要 React Flow 或 GSAP。连线分别标注归属、导航、调用、数据和复用，演示没有实时业务指标。
