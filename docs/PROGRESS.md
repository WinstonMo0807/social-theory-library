# 开发进度

更新日期为 2026-08-16。当前源码版本为 2.6.1。本文只保留后续开发所需的简明状态，历史生产记录不等于本轮实时验收。

## 已实现

- Django/DRF API、Next/Vinext Web、PostgreSQL、Redis/Celery、Meilisearch 和独立 PaddleOCR 服务已经形成完整源码结构。
- 公开站、Explore、PDF Reader、账户中心和管理后台使用同一 API 与数据模型。
- 馆藏模型覆盖作品、版本、资产、逐页文本、全文段落、语义片段、学者、主题、理论节点和知识关系。
- 入库支持批次、文件级幂等、分片上传、失败重试、处理尝试、元数据候选、人工锁、OCR、页码、索引和发布预检。
- 访客可搜索、阅读、下载、复制和生成引用。登录读者可保存进度、收藏、书单、书签、批注和私人笔记。
- 原文检索、混合观点检索、版本化语义索引、馆藏评估工具和受控降级已经接入源码。
- 新书库问答实现位于 `api/reading`，具有私人会话、加密消息、来源校验、流式输出和 Reader 回链。
- 非 Explore 页面已采用黑、白、暖灰的出版型界面。Explore 保持独立冻结范围。
- 当前迁移保存在各 Django app 的 `migrations` 目录，schema 修改继续通过 migration 管理。

## 最近记录的验证

已有本地记录称后端 293 项测试、Django check 和迁移漂移检查通过，前端 lint、TypeScript、45 项 Node 回归和生产构建通过。已有生产交接记录称 API 为 r60、Web 为 r59，并完成主题筛选热修复。

这些结果来自此前记录。本轮 Git 安全审计没有重新运行完整测试，没有连接生产 NAS、Cloudflare、PostgreSQL、Meilisearch、真实 OCR 或登录后台。它们在再次执行前均不能视为当前实时证明。

## 当前版本管理状态

- 2026-08-16 已在 GitHub 账号 `WinstonMo0807` 下创建 `social-theory-library` 私有仓库，并将安全源码快照推送到 `main`。
- 本地 `main` 正在跟踪 `origin/main`。首次 commit 为 `2c0bcb8b2f568dcbc17ef86d3c3197e1198f6560`。
- 首次快照包含 486 个源码、测试、配置、文档和前端素材文件，总大小约 5.82 MiB。馆藏与运行数据继续只保留在服务器或本地受控目录。
- 七项产品问题的状态、证据和验收要求集中记录在 [ISSUES.md](ISSUES.md)。

## 本轮验证

- 首次提交前的主审计和独立复核均为 0 个阻断项，高置信 Secret 与常见个人邮箱扫描均为 0 项。
- 提交树没有真实 `.env`、PDF、数据库、OCR 数据、日志、归档、wheel、模型、embedding、索引或大于 10 MiB 的 Blob。
- `git diff --cached --check` 退出码为 0；首次 push 后本地 `HEAD` 与 `origin/main` 一致，GitHub API 返回 `PRIVATE`，默认分支为 `main`。
- 后端定向测试 20 项通过，只有两条 pypinyin 第三方弃用警告。
- 前端定向 Node 回归 18 项通过。
- 四份 Compose YAML 均能由 PyYAML 解析。当前环境没有 Docker CLI，`docker compose config` 仍为 `待核实`。

## 当前问题摘要

- bilingual viewpoint retrieval 具备多语种模型基础，跨语言检索质量待验证。
- field-specific web enrichment 已有字段级候选，但没有单字段定向触发和来源配置。
- library RAG 已接入新 reading API，登录后的真实生产流程待验证。
- scoped search 在书库问答中存在单数与复数参数键不一致，前端也没有提交 scope。
- PDF metadata / FOR UPDATE failure 已有源码修复，真实 PostgreSQL 回归待重跑。
- auth initialization failure 存在 Cookie 有效而 localStorage 标记缺失时的误判风险。
- resumable large PDF upload 已支持同浏览器续传，跨设备恢复和逐分片哈希仍缺失。

## 下一阶段

1. 为 Codex 或 ChatGPT 连接该私有仓库时使用 GitHub 授权，并只授予所需仓库权限，不在聊天中发送 Token、密码或 2FA code。
2. 后续提交继续执行 Secret、大文件和禁入路径检查，保持仓库为 Private。
3. 产品开发优先处理 STL-004 和 STL-006，再进行书库 RAG 与双语观点检索的真实评估。
