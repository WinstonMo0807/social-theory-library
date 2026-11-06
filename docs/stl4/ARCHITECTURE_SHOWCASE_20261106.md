# STL 架构映像：内部动态汇报

2026-11-06。独立展示交付，不改正式网站路由、核心组件、API、数据库或生产环境。实现目录 `web/architecture-showcase/`，本机入口 `http://127.0.0.1:5196/`。整体展开入口可加 `?stage=3`。

## 本轮范围与证据

先读取当前工作区与继承修改，应用 Ponytail full、开发规则、既定品牌与前端设计/动效规则。全量提取 `web/app/**/page.tsx` 的 151 个路由文件及直接导入；定向追踪导航、观点检索、原文证据、Reader/引用、私人记录、入库/发布、OCR/索引、权限与设计组件。未声称通读所有业务文件或完成全站验收。

形成 43 个展示节点、44 条分类关系、61 个来源锚点。来源含源码和明确标记的项目记录，各自保存相对文件、行号、锚点和整文件 SHA-256。六领域分组是基于现有导航与职责作出的汇报组织，不是新增业务架构。`architecture.json` 保留所有路由，包括开发预览和暂停政策模块；这些不进入主要产品叙事。

已核实的关键链路：

- `SiteHeader` 的公共导航与读者导航；欢迎页和首页独立。
- 观点页将查询转到证据页；`DiscoverySearchWorkspace` 经客户端向 `DiscoverySearchView` 创建会话；会话事务提交后投递 Celery；结果通过来源资格校验并提供 Reader 位置。
- Reader 复用同一路由的并读模式，调用共享引用服务。作品、版本、文档修订和证据位置分别存在。
- 私人研究查询集按 `user` 或 `project__user` 过滤，私人记录独立保存；公开内容与私人研究不合并为一套公开档案。
- 入库任务调用既有 pipeline，处理结果做非公开索引准备，发布命令通过 `activate_revision` 进入原发布服务。
- 当前 OCR 是 RapidOCR/ONNX 主链，不能继续画成旧 Paddle 运行版本；前端是 React/Next 路由约定与 Vinext，后端是现有 Django REST 服务。
- `CanReadLibrary` 要求登录，前端 `requireReaderSession` 同时拦截；管理端按 capability 控制。
- 直接复用 `BrandImage`、`Button`、`Dialog`，本地字体与 2026-10-27 黑金符号，品牌金从实际 SVG 的 `#cc9847` 读取。

真实站点本轮只新开匿名浏览器 GET 首页、欢迎页、理论、学者、主题、策划和探索入口。前六页 200 并渲染；探索跳到 `/login`（最终登录页 200）。没有发起检索、登录、提交表单、读取私人资料或调用外部模型。记录不保存内部服务器原点。

审计期间项目记录更新了自动目录：最新 `AUTOMATIC_OUTLINE_20261106.md` 给出两份公开扫描件 1/38 项全自动书签结果。展示已同步为已实现、更多书种待验收，并明确是项目记录依据，不冒充本轮重跑。私人研究中转未配置/调用和第三方登录禁用仍分别标记。

## 成品

六幕包括全站总览、页面地图、研究工作流、技术与数据、设计系统、实现与证据。支持模块聚焦、子模块、来源与路由检索、手动阶段、播放/暂停、当前阶段重播、返回全局、键盘、原生全屏、减少动态效果与固定 16:9 画布。

源码与维护说明在 `web/architecture-showcase/README.md`。架构解释在 `audit.py`，数据在 `architecture.json`，证据平表在 `evidence-index.csv`，叙事与布局在 `scenes.ts`，动画与交互独立在 `app.tsx` / `style.css`。

提供 3840×2160 PNG、内嵌字体与图片的浏览器 SVG，以及标签页 WebM 录制入口。六张 4K PNG 和 1080p 无旁白 WebM 另行生成到 `output/playwright/architecture-showcase/`，运行产物不提交 Git。SVG 使用 foreignObject，PPT 使用 PNG。

## 已执行检查

| 命令 / 检查 | 结果与界限 |
| --- | --- |
| `python web/architecture-showcase/audit.py` | 退出 0，来源锚点、端点与类型检查，生成 43/44/61/151 快照 |
| `node web/architecture-showcase/build.mjs` | 退出 0，复用现有依赖构建独立静态目录 |
| `node web/architecture-showcase/capture-site.mjs <授权预览原点>` | 退出 0，七个匿名页面的有限观察 |
| `node web/architecture-showcase/verify.mjs` | 31 项展示检查通过；无页面 JS 错误，无外站或业务 API 请求 |
| `node web/architecture-showcase/export-assets.mjs` | 六幕 PNG 的真实文件头均为 3840×2160；独立 SVG 下载成功 |
| `node web/architecture-showcase/record.mjs` | 1080p WebM 录屏已生成；手动录制按钮的原生屏幕选择需由演示者操作 |

浏览器使用本机 Microsoft Edge 与仓库现有 Playwright。覆盖 1920×1080、1440×900、1366×768、1280×720，实际进入/退出全屏，并切换系统减少动态效果模拟。代码检查和本展示运行不等于 STL 业务全链、NAS 高负载、真实模型质量或 206 个视图的正式验收。

修正记录：

| 调整前 | 调整后 | 直接证据 |
| --- | --- | --- |
| 主画布说明与底部播放栏重叠 | 缩小场景可用高度、重排节点与说明 | 六幕截图和 DOM 边界检查 |
| 聚焦画布越出底部，详情内容超出面板 | 画布裁切，详情滚动区使用实际剩余高度 | 节点详情截图和面板边界检查 |
| 减少动态效果检查未等待媒体事件 | 等待实际响应状态后断言；禁用定时播放并保留手动操作 | 浏览器切换与阶段推进 |
| blob SVG 转 PNG 时画布被标记 tainted | 完整内嵌资源的 data URL 转换 | 实际 PNG 下载、文件头和图像复核 |

## 状态与后续

- D：独立展示实现及本轮定向检查完成，属于新交付；不改变原 STL 模块的 B 状态。
- B：正式汇报用语/节奏的主观选择，实体投影及浏览器原生录屏选择框的现场操作。没有发现因此必须扩大的业务开发项。
- 排除：公网部署、业务写入、正式全站验收、模型/OCR 重跑、政策研究、新 RAG/LLMWiki 决策。

服务器只监听 loopback，只读静态构建目录，并校验 Host、方法与路径。不代理源文件或业务接口。工作区继承修改与并行更新保留。共享进度文档按追加段落记录，不将其他线程修改一起提交。
