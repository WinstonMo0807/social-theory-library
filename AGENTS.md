# Codex repository rules

## 修改前

- 先阅读 `docs/ARCHITECTURE.md`、`docs/PROGRESS.md` 和 `docs/ISSUES.md`。
- 涉及部署时再阅读 `docs/DEPLOYMENT.md`，并确认当前任务是否允许连接生产环境。
- 先检查工作区状态和现有改动。不要覆盖用户未提交的修改，不要根据旧交接记录虚构 branch、commit 或线上状态。

## 数据与凭据

- 不得提交 Secret、真实 `.env`、API Key、Token、密码、JWT/Session Secret、SSH Key、证书私钥或云端凭据。
- 不得提交馆藏 PDF、用户上传、OCR 原始数据、OCR 派生结果、数据库、备份、用户数据、私人笔记、模型、embedding、向量库、Meilisearch 数据或其他索引文件。
- 不得提交 logs、cache、temp、依赖目录、构建结果、发布归档和本地预览数据。
- 发现疑似 Secret 时不要回显值，也不要删除原文件。先确保路径被忽略，报告文件、行号、变量名和风险类型。
- 不得直接修改生产数据库。不得删除或重建生产 volume、馆藏目录、模型目录和活动索引。

## 架构与产品边界

- 保留现有 Django、Next/Vinext、PostgreSQL、Redis、Celery、Meilisearch 和 PaddleOCR 架构，除非用户明确授权技术栈变化。
- 公网和局域网管理入口使用同一 API、数据库、任务系统、搜索索引和 NAS 存储，不建立需要同步的第二套书库。
- 公开访客继续拥有搜索、在线阅读、下载、复制和引用权限。登录读者的私人数据只按既定权限访问。
- 复用现有 PDF Reader、OCR 服务、入库流程和搜索服务，不建立职责重复的实现。
- 不覆盖 ORIGINAL PDF、人工锁定元数据、人工确认关系、读者笔记和历史文件版本。
- 保持黑、白、暖灰的编辑型界面和响应式行为。不得用静态 mock 掩盖真实 API 故障。

## 修改方式

- 保持范围紧凑，不借修复部署、入库或检索问题重构无关模块。
- 优先修复根因。不得通过隐藏异常、吞掉错误、取消鉴权、删除必要事务锁、放宽访问过滤或删除失败记录处理问题。
- 数据库 schema 修改必须通过 Django migration。禁止手工修改生产表结构。
- 外部元数据、OCR、AI 和检索结果默认是候选或派生数据。人工锁定和人工确认结果具有更高优先级。
- 生产变更前保留数据库、源码、环境和镜像回退入口。不得运行 `docker compose down -v`。

## 测试与记录

- 每次重要修改都需要与风险相称的测试。记录准确命令、退出码和环境限制。
- 不得把未运行、被阻断或依赖真实环境的检查写成通过。统一标记为 `待核实`。
- 本地测试和包检查不能证明 DX4600、Cloudflare、公网、真实 OCR、真实 Provider 或生产索引可用。
- 完成重要功能、修复或迁移后同步更新 `docs/PROGRESS.md`。问题状态变化时同步更新 `docs/ISSUES.md`。
- 架构、部署模式、数据职责或安全边界变化时同步更新 `docs/ARCHITECTURE.md` 或 `docs/DEPLOYMENT.md`。
