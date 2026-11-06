# STL 架构演示 v3 交付记录

2026-11-06。入口为 `http://127.0.0.1:5196/`，源码在 `web/architecture-showcase/`。

## 本轮结果

- 场景收为 5 项。原“技术与数据”改为“底层架构”，原“设计系统”改为“品牌标识”，删除“实现与证据”场景。
- 使用演示由 14 步改为 38 步。检索与引用 20 步、入库与发布 10 步、私人研究 8 步。
- 依照真实组件重建界面状态。问题输入、范围选择、加载、结果排序、上下文、原页定位、选文、引用复制和导出均有可见反馈。
- 改为固定窗口内的连续操作。保留暂停、续播、重播、进度定位、键盘和全屏，增加分段导航和操作步骤选择器。
- 调整简介、流程标签、窗口、右侧说明与底部控制之间的间距。修正上下文弹窗、引用浮层和私人研究末步的裁切。

动效参考 [Elicit 当前首页](https://elicit.com/) 的同画面操作与局部展开。本轮在浏览器中观察视频，并保存第 5、17、29 秒参考帧。没有复制 Elicit 的素材、品牌或宣传数据。STL 标识、配色与字体沿用当前批准资产。

## 步骤及源码依据

| 流程 | 演示内容 | 主要组件 |
| --- | --- | --- |
| 检索与引用 | 输入问题、选择范围、检索进度、结果、排序、摘要、上下文、同书段落、阅读器、页码、选文、格式、复制、导出 | `opinion-search-entry.tsx`、`discovery-search-workspace.tsx`、`discovery-evidence-detail.tsx`、`reader-shell.tsx`、`shared-citation-overlay.tsx` |
| 入库与发布 | 选文件、批次策略、上传、处理、目录、纠错、保存、发布检查、修订生效、下载 | `admin-upload.tsx`、`upload-batch-view.tsx`、`document-outline-workspace.tsx`、`publication-review.tsx` |
| 私人研究 | 打开选材、新建项目、备注、加入、查看选材、下轮范围、追问、服务配置边界 | `shared-citation-overlay.tsx`、`research-session-detail.tsx` |

`journeys.json` 保存各步的操作、反馈、输入、输出、调用、字段、权限、失败条件和来源。`visual` 选择具名画面，步骤排序与画面类型分开。`duration` 控制时长，`target` 指定指针目标，`chapter` 指定分段。

提取结果为 43 个节点、44 条关系、77 个来源锚点、152 个路由文件。CSV 索引包含全部步骤对应的源码位置与文件校验值。源码锚点失效时提取失败，本轮已按实际函数和当前登录表单修正锚点。首发账号与第三方登录状态采用最新项目记录，Google 记为后续项。

演示文献、页码、处理进度和成功回执均为示例。原文用线条表示，不编造真实引文。页面明确说明示例性质。界面依据源码重建，不等同于录制正式业务操作。

自动目录与人工纠错按当前代码分别展示。保存修正后目录生效，下载副本仍需后台生成。生成期间可返回原件或已有副本。私人研究保留配置边界，没有呈现尚未接通的模型答案。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `python web/architecture-showcase/audit.py` | 退出 0，来源锚点和节点关联有效 |
| `node web/architecture-showcase/build.mjs` | 退出 0，独立构建完成 |
| `node web/architecture-showcase/verify.mjs` | 退出 0，29 项检查通过 |
| `node web/architecture-showcase/verify-journeys.mjs` | 退出 0，250 项检查通过 |
| STC `for-web-dev` 检查，含 Anti-Echo 语义复核 | 退出 0，0 个错误、4 个警告 |
| STC `for-document` 检查 README | 退出 0，0 个错误、1 个警告 |
| `node web/architecture-showcase/export-assets.mjs` | 退出 0，11 张 3840×2160 PNG 与总览 SVG |
| `node web/architecture-showcase/record.mjs` | 退出 0，视频已录制并由浏览器解码 |

检查覆盖 38 步的最终画面及每步 3 个中间时刻，逐步反馈与来源，实际输入变化、暂停、续播、排序、加载、复制回执、末步停止、节点跳转、全屏、键盘、减少动态效果及 4 档桌面视口。浏览器未发现 JavaScript 异常，未发出业务或外部请求。

首轮检查发现了简介间距、上下文弹窗高度、下载页及研究末步溢出。均已修正并复测。验证脚本也修正了范围控件值须符合 50 毫秒步长，以及演示内外同名“导出”按钮的选择范围。没有删除失败断言。

STC 警告逐项保留理由：2 处“相关性排序”是实际排序选项；“已实现 · 待验收”是状态名称；示例说明防止观众将模拟成功状态当作业务运行证据。`copy-review.json` 保存 Anti-Echo 复核决定。

这些检查仅针对独立展示。既有匿名网站观察继续保留。全站业务验收、真实私人中转、OCR、数据库与生产部署的结论均未扩大。

## 产物与备份

- 成品和报告位于 `output/playwright/architecture-showcase-v3/`。
- `4k/` 包含 11 张 PPT 图片，含 5 个场景及 6 个使用步骤。
- `video/STL-architecture-v3-1080p.webm` 为 1920×1080，时长 186.28 秒。完整呈现 3 条流程与架构场景，无旁白。
- `STL-architecture-v3-local-20261106.zip` 包含成品、源码、静态服务器、说明、图片和视频。运行 `start.cmd` 即可本机使用，不需要安装 npm 依赖。
- 修改前的 v2 完整备份为 `output/backups/STL-architecture-v2-final-STC-20261106.zip`，ZIP 内容已校验。
- 原 v1 STC 备份、原 v2 交付包继续保留。5274 的独立竞争版本未修改。

本轮只修改 5196 独立展示及本项交付记录。没有新增依赖，没有业务写入，没有修改数据库、正式路由、品牌组件或生产服务。Git 检查点仅纳入本项源码和新增记录，不推送。
