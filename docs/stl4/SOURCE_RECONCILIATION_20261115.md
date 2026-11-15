# 2026-11-15 已发布修复的源码归档

本轮按用户要求核对移交包、Git 分支和 Mac 当前容器，补齐主分支遗漏；没有部署、重启应用、运行生产写入或修改数据库结构。主分支基线为 `a1d7aca4`，与核对时 GitHub origin/main 一致。

## 已核实的业务修复

| 修复 | 主分支补入内容 | 证据 |
| --- | --- | --- |
| 已登录读者的准确原文 | 作品书目、策展编排、理论/学者关系、阅读路径按实际访问者读取 registered 原文；SSR 传递现有会话，响应不共享缓存 | 作品会话、策展/编排/关系访问发布记录；24 份后端源码逐一对照运行文件 |
| 主编型图书 | 整书主编/编者可满足相应责任字段，引用仍写 editor，不伪造 author | EDITED_BOOK_RESPONSIBILITY_20261110 |
| 检索状态 | Discovery 活动索引及模型就绪状态、真实覆盖情况与后台标签 | SEMANTIC_STATUS_FIX_20261109 |
| 索引与发布恢复 | 同一索引任务有界等待、408/读超时重读；委托协调任务恢复；全文失败不阻断其他投影；人工重试预算 | BOOK_INDEX_WAIT、INDEX_STATUS_HTTP408、DELEGATED_PROJECTION_RECOVERY、FULLTEXT_FAILURE_ISOLATION、PUBLICATION_MANUAL_RETRY |
| 公开展示 | 学者简介标签、自由文本来源栏清理、理论问题序号、关系 source_material、阅读难度标签 | PUBLIC_CURATION_CLEANUP、THEORY_QUESTION_MARKERS、RELATION_READER_ACCESS |

API 镜像 `17204310147b` 的 21 份差异与包内源码一致；普通 worker `d1711e519d36` 另有 3 份索引/协调修复与包内一致。合计恢复 24 份后端源码。其他 worker 的旧版本差异没有用于覆盖主分支。路径、运行镜像及 SHA256 见同名 JSON。

## 当前 Web 已发生的回退

当前 Web 镜像为 `8b89e98a2cfe`。读取实际 `/app/dist/server/index.js` 确认，作品 loadWork、理论 loadKnowledgeNode、阅读路径和 PublishedPlacements 又未传递会话；与 11 月 9—12 日已发布修复记录不一致。此次恢复这些已发布过的源码并增加可执行回归检查。源码恢复不等于当前运行网页已修复：**尚未重新部署**。

共恢复 17 份前端源码；没有引入旧 C 原型、A–E 比较页或新检索算法。API schema 的两个 ASCII-only slug 差异是旧生成结果，没有覆盖主分支现有 Unicode 契约。

## MCP 分支接回

`codex/stl-mcp-security-20261112` 的安全和上传接入已提交过，但 main 尚缺失。当前 stl-mcp 的 bridge.py、domain.py、server.py、public_server.py 与该分支/移交副本逐字一致。按文件接回 tools/stl_mcp、相应回归测试和发布记录，避免合入其旧应用基线。

`deploy/mcp` 的 NAS 发布脚本作为该既有功能的历史部署材料保留，本轮没有执行。当前服务已迁至 Mac，它们不是新的 Mac 部署入口；私有配置、令牌、状态库和模型不纳入提交。

## 本轮验证

- 隔离 API 镜像：17 个测试文件、157 项通过；SQLite 合成数据、memory broker、断网、无生产挂载。
- 隔离 Web 镜像：6 项执行实际加载器的回归检查通过，覆盖登录传递、401 匿名书目回退、503 不被吞掉。
- MCP 标准库测试：9 项通过，覆盖鉴权、来源/Host、到期轮换、限流、计划重放。
- 53 份 Python 文件语法检查及 Git diff 空白检查通过。
- 未执行完整前端构建、全站 E2E、真实上传或生产验收。本轮没有改变依赖锁文件。

## 实验与原现场

原始 ZIP 已按 SHA256 复制至工作区 `archives/stl-source-20261115/`，包含原暂存补丁、工作副本和全部 refs 的 bundle；364 份额外 ignored 素材仍由原包完整保留。

其余实验和历史差异保存到独立 `archive/stl-experiments-20261115` 分支中的 `archives/stl-20261115/`，不混入应用路径。分类清单说明实验、历史记录、既有独立设计提交及构建产物。dist 构建产物只保留在原 ZIP，不加入源码提交。独立 Knowledge Intelligence 分支保持不变。

恢复归档时按清单选择文件和原始基线；不要将整个历史快照覆盖当前 main。归档分支和离线 bundle 均为本地资料，本轮不推送或发布。

## RAG / 持续 Wiki 独立架构线

用户本轮另行确认要找整套 RAG / LLMWiki 架构。该组代码完整保留在 `codex/stl-knowledge-intelligence`，最新 `b3019d16fcc874041ac7044830331f5a023a08fc`，本机独立源码目录为 `source/social-theory-library-knowledge`。它不是一批未提交零散实验。

其范围包括不可变 RevisionPage、逻辑 DocumentNode、跨页 EvidenceAnchor/Segment、统一原文/上下文检索、关键词与向量解耦、整书分章分析/顺序综合/覆盖账本、Entity/Assertion、持续 Wiki 局部 patch/ChangeSet/人工保护、来源订阅和自动维护接续；0103/0104 及 plan_version=2 的验证与部署边界沿该分支最新记录，不据本轮归档扩大完成声明。

交接记录的三书合计 245 个分析窗口、884947 个纳入范围字符、589 项待审建议是既有产物记录；源码包本身不含候选数据库里的实际建议。该线当前代码、历史及恢复入口独立保存，本轮没有迁移候选库、调用生成模型或恢复自动任务。
