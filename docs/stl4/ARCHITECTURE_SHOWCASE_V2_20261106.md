# STL 架构演示 v2 交付记录

本轮完成 STC 中文修订、原版独立备份，以及参考 Elicit 同画面动效的 3 条使用演示。主入口为 `http://127.0.0.1:5196/`。备份入口为 `http://127.0.0.1:5197/`。

## 范围与恢复

- 修改范围为 `web/architecture-showcase/` 及本项记录。
- `tools/architecture-report/` 的另一版展示保持独立。
- 正式网站路由、业务组件、数据库和生产部署保持原状。
- 保留全部继承的未提交修改。
- 文案修订后的原版先保存，再开始改造动效。

备份在 `output/backups/STL-architecture-v1-STC-20261106/`，同级 ZIP 约 21.4 MiB。包含原版源码、可独立运行的构建结果和 SHA-256 清单。运行 `start.cmd` 使用 5197 端口。

## 成品变化

使用演示仍在原有第 3 幕。默认入口先展示该幕，其余 5 幕保留。

| 流程 | 步骤 | 说明 |
| --- | --- | --- |
| 检索与引用 | 提交问题、异步检索、查看证据、定位原文、生成引用 | 查询和筛选创建会话，证据位置传到阅读器，再用于引用预览 |
| 入库与发布 | 上传文件、处理正文、自动目录、发布修订、阅读下载 | 处理状态、公开状态和全文就绪分别说明 |
| 私人研究 | 新建研究、保存材料、授权笔记、继续追问 | 项目归属、材料引用和笔记授权分别检查；模型保留待配置状态 |

每一步包含用户操作、系统职责、输入、输出、调用关系、字段、权限、失败条件和来源。技术模块新增 8 组职责说明。架构节点中的实际使用入口可跳到对应流程。

时间轴控制实际画面内容。输入逐字出现，任务逐步接续，证据卡片展开上下文，阅读器定位选文，引用面板进入前景。暂停保留当前进度，再次播放从暂停位置继续。拖动进度条可直接定位，重播从当前阶段起点开始。最后一步结束后停止。

减少动态效果时显示完整画面，保留手动阶段切换。全屏模式支持调用详情对话框。输入框、流程标签和键盘操作保持可访问。

## 设计与文案依据

2026-11-06 实际访问 [Elicit 首页](https://elicit.com/)，浏览器观察到首页视频长 41.884 秒。查看了输入、结构化结果及来源展开画面。仅借鉴同画面演示和焦点变化方式，未复制视频、文案或品牌资产。

STL 继续使用现有 `BrandImage`、2026-10-27 标识、本地字体、纸白底色和金色重点。按钮与对话框继续复用仓库组件。没有新增 npm 依赖。

STC 来自项目此前保存的 `tmp/stl4-font-copy-20261029/stc-reference/SKILL.md`。规则来源为 [STC Simplified Technical Chinese](https://github.com/daimonia-ai/STC-Simplified-Technical-Chinese)。已读取通用、界面、文档、对话规则及词表，使用 `for-web-dev` 和 `--anti-echo` 检查展示文字。

修订重点是删除口号式标题，明确操作和数据对象，保留权限与尚未验证的状态。JSON 展示字段由 `copy-snapshot.py` 提取后检查，避免 JSON 语法触发误报。最终展示文案机器检查为 0 个错误、13 个警告；语义复核后保留软件“实现”状态用语及“流程示意”标记。后者用于区分演示与真实业务执行。决定保存在 `copy-review.json`，完整输出在 `output/playwright/architecture-showcase-v2/stc-reviewed.json`。

## 新增核实内容

源码索引包含 43 个节点、44 条已分类关系、68 个来源锚点和 151 个页面文件。流程与模块职责的来源一并写入 `architecture.json` 和 `evidence-index.csv`。

| 判断 | 核实位置 |
| --- | --- |
| 保存检索会话后，事务提交时投递任务 | `api/catalog/services/discovery_sessions.py` 的 `_create_session` |
| 会话归属与当前来源资格分别检查 | `get_session`、`session_access`、`discovery_projection.py` |
| 原文结果保留文件、版本、证据位置和阅读地址 | `discovery_views.py`、`discovery-evidence-detail.tsx`、阅读器路由 |
| 引用预览允许匿名，但只读公开快照 | `api/reading/shared_citation_views.py` 的 `PublicCitationPreviewView` |
| 选文须唯一对应来源，活动版本变化时拒绝旧预览 | 同上，`selection_range` 与 `post` |
| 入库先准备非公开索引，OCR 按内容和批次策略投递 | `api/ingestion/services/pipeline.py` |
| 自动目录保留人工修订，书签写入派生 PDF | `document_outline.py`、`outline_automatic.py`、`outline_exports.py` |
| 公开状态取决于有效活动修订 | `publication_commands.py` 的 `catalog_publication_state` |
| 私人记录按本人过滤，管理身份不扩大范围 | `api/reading/research_views.py` 的 `PrivateRecordViewSet` |
| 笔记检索须有明确授权范围 | `api/reading/research.py` 的 `search_memories`、`plan_memory_rows` |

这些是源码核实。动画中的问题是示例，原文用线条表示，不含编造引文或私人资料。动画不执行真实检索、OCR、发布、模型调用或私人写入。原版的匿名页面观察与既有项目样本记录继续保留各自验证范围。

## 检查与产物

| 命令 | 结果 |
| --- | --- |
| `python web/architecture-showcase/audit.py` | 退出 0；锚点、节点、关系和步骤来源通过检查 |
| `node web/architecture-showcase/build.mjs` | 退出 0；独立构建完成 |
| `node web/architecture-showcase/verify.mjs` | 退出 0；31 项通过 |
| `node web/architecture-showcase/verify-journeys.mjs` | 退出 0；46 项通过 |
| `node web/architecture-showcase/export-assets.mjs` | 退出 0；9 张 PNG 均为 3840×2160，另有 SVG |
| `node web/architecture-showcase/record.mjs` | 退出 0；WebM 实际解码为 1920×1080，110.72 秒 |
| `python web/architecture-showcase/package.py` | 退出 0；压缩包完整性检查通过 |

77 项浏览器检查覆盖 14 步布局与来源、播放内容变化、暂停与续播、进度条定位、重播、结束停止、键盘、全屏、4 档桌面视口、减少动态效果、节点跳到使用流程、4K 导出与独立备份。浏览器没有脚本错误，也没有业务或外部请求。

检查中修复了进度条与讲解文字重叠，以及原文卡片的底部裁切。流程动作文字缩短后仍保留原意。截图和导出均使用真实浏览器。

交付目录为 `output/playwright/architecture-showcase-v2/`：

- `STL-architecture-v2-local-20261106.zip`：离线启动包，含源码、9 张 PPT 图片和视频。
- `4k/`：6 幕及 3 条流程关键画面的高分辨率图片。
- `video/STL-architecture-v2-1080p.webm`：完整流程录屏。
- `verification.json`、`journey-verification.json`：浏览器结果。
- `stc-reviewed.json`：文案检查结果。

本项开发与展示定向检查为 D。STL 正式全站验收仍按原 B 类记录。私人研究中转的配置和调用未在本轮执行，生产未部署。
