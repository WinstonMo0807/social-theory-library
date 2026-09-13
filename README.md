# Social Theory Library

Social Theory Library 是面向社会科学研究者的 PDF 数字书库。项目包含公开知识网站、原文与观点检索、PDF Reader、账户中心、批量入库、元数据复核、知识组织、书库问答和管理后台。

当前源码版本为 **3.0.5**，已于2026-09-13完成公网部署。仓库默认分支 `main` 用作当前版本与后续整体重设计的基线。源码提交与运行镜像不必具有相同的文档提交号，具体上线依据见[当前状态](docs/CURRENT_STATE.md)和[部署记录](docs/DEPLOYMENT.md)。部署记录是有日期的快照，不代表任何未来时刻的服务保证。

## 给准备重设计书库的 GPT

先读[实际架构与应用场景](docs/GPT_ARCHITECTURE_CONTEXT.md)，再读[上架与发布流程](docs/INGESTION_AND_PUBLICATION.md)和[重设计任务说明](docs/REDESIGN_BRIEF.md)。这些资料描述正在使用的系统，包括普通读者、馆员、Owner的操作，真实数据职责，旧入口与新入口的关系，以及已知限制。当前实现不是必须照搬的未来设计。

用户下一步需要重新思考整体架构，尤其后台和上架过程。本次提交只准备可靠基线和上下文，并未替用户决定新技术栈、重写后台或迁移生产数据。提出方案时先说明用户操作和数据变化，再给代码和迁移设计。

阅读顺序为 `AGENTS.md`、以上三份说明、`CURRENT_STATE.md`，然后按问题进入实际源码。`CURRENT_PROGRESS.md`、`PROGRESS.md`和旧版文档保留历史过程，不能把其中的旧“未上线”文字当作当前状态。原[GPT-HANDOFF](docs/GPT-HANDOFF.md)已经标记为2.9.2历史快照。

## 主要能力

- 公开访客可以检索、在线阅读、下载、复制和生成引用。
- 登录读者可以保存进度、收藏、书单、书签、高亮、划线、私人笔记和阅读历史。
- PDF Reader 支持连续阅读、缩略图、目录、文档内搜索、页码映射、命中定位和 Range 请求。
- 入库支持批次、文件级幂等、分片上传、失败重试、PDF 校验、原生文本提取、OCR、元数据候选、人工锁、实体关系、索引和发布预检。
- 原文检索与版本化观点检索使用真实馆藏文本。书库问答的新实现位于 `api/reading`，依赖登录、语义检索和可选 AI 服务。
- 管理后台覆盖上传、处理中心、元数据复核、发布、馆藏、知识对象、推荐、检索评估、用户、配置和备份。
- 手工编目可不依赖上传记录。纯书目、带PDF的馆藏和已发布维护使用真实编目会话与现有发布服务。
- 书目可公开、PDF可阅读和正文智能检索就绪是不同条件。后台保存不会直接改变正式页面，人工发布也不能只靠一个 `published` 标志判断完成。
- 人物整理支持有预览和回滚的非冲突人工合并。统一媒体覆盖封面、推荐图、肖像、知识节点及阅读路径，保留草稿和历史文件。

## 技术栈

- Django 5.2、Django REST Framework 3.16
- React 19、Next.js 16、Vinext、Vite
- PostgreSQL 16
- Redis、Celery Worker、Ingestion Worker、Celery Beat
- Meilisearch 全文与语义索引
- FastAPI、PaddleOCR、可选 PP-StructureV3
- Nginx、可选 Caddy 与 Cloudflare Tunnel

完整结构见 [架构文档](docs/ARCHITECTURE.md)。

生产是NAS上的模块化单体，Web和API分容器运行但共用一套后台服务。公网Cloudflare Tunnel与局域网入口最终访问相同的API、PostgreSQL、任务和NAS。R2可作上传临时中转，不是第二个永久书库。仓库中的Sites/Worker/Drizzle适配文件不代表当前生产已经改用D1或在Cloudflare Workers运行。

## 目录

| 路径 | 内容 |
| --- | --- |
| `api` | Django API、迁移、任务、入库、检索、阅读数据与测试 |
| `web` | 公开站、Explore、Reader、账户中心和管理后台 |
| `ocr_service` | PaddleOCR FastAPI 服务与目标 NAS 构建说明 |
| `deploy` | Nginx 和 Caddy 配置 |
| `offline` | 离线镜像定义。大型离线依赖不进入 Git |
| `scripts` | 验收、模型准备和历史部署辅助脚本 |
| `tests`、`evals` | 检索评估工具与种子问题 |
| `docs` | 架构、进度、问题、部署、数据模型和历史设计记录 |

## 本地开发

Compose使用根目录`.env`。只复制安全示例并填写自己的本地配置，不要复用生产凭据：

```powershell
Copy-Item .env.example .env
```

在宿主机直接启动Django前，需要将本地配置提供为进程环境变量。直接运行`manage.py`不会自动加载根目录`.env`；未设置`DATABASE_URL`时会使用开发SQLite。`postgres`和`api`等Compose服务名不能直接用作普通宿主机地址。已有虚拟环境时：

```powershell
Set-Location api
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py runserver
```

前端使用 Node.js 22.13 或更高版本：

```powershell
Set-Location web
npm.cmd ci
npm.cmd run dev
```

也可以使用 Compose 进行单机验证：

```powershell
docker compose --profile ocr up -d --build
```

OCR 镜像需要一个超过 GitHub 普通 Git 单文件限制的 NAS 专用 PaddlePaddle wheel。该文件不会提交。准备方法与校验要求见 [部署说明](docs/DEPLOYMENT.md) 和 `ocr_service/vendor/README.md`。

## 验证命令

后端：

```powershell
Set-Location api
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe manage.py check
..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

前端：

```powershell
Set-Location web
npm.cmd run lint
npm.cmd run build
npm.cmd test
```

这些命令只有在当前环境实际执行并取得退出码 0 后才能记录为通过。

## 开发文档

- [GPT_ARCHITECTURE_CONTEXT.md](docs/GPT_ARCHITECTURE_CONTEXT.md) 是当前GPT入口，描述实际产品场景、运行结构、数据与代码定位。
- [INGESTION_AND_PUBLICATION.md](docs/INGESTION_AND_PUBLICATION.md) 说明上传、手工编目、复核、发布、撤回和正文处理的真实变化。
- [REDESIGN_BRIEF.md](docs/REDESIGN_BRIEF.md) 记录这次用户提出的整体重设计目的、待决策问题和交付要求，不伪装为已经实现的方案。
- [CURRENT_STATE.md](docs/CURRENT_STATE.md) 给出最近部署结果、已验证项目与能力边界。
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) 记录真实模块、数据职责和部署模式。
- [PROGRESS.md](docs/PROGRESS.md) 记录已实现内容、近期验证和下一阶段。
- [ISSUES.md](docs/ISSUES.md) 记录已知问题及历史修复，当前判断优先看最新摘要。
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) 记录环境、构建依赖、迁移、上线与回退要求。
- [AGENTS.md](AGENTS.md) 约束后续 Codex agent 的修改与验证方式。
- [UI_3.0.5.md](docs/UI_3.0.5.md) 记录共享组件和CSS分层。它不表示后台工作流程已重新设计。

GitHub只保存源码、示例与文档。一次`git push`不会自动重新部署NAS，也不能让全新clone获得真实馆藏、数据库或Provider授权。

## 数据安全

Git 仓库不包含真实 `.env`、凭据、馆藏 PDF、用户上传、OCR 数据、数据库、备份、私人阅读数据、模型、embedding、搜索索引、日志、缓存、依赖目录、构建结果或发布包。

原始 PDF、人工锁定元数据、人工确认关系和私人笔记不得被自动处理覆盖。生产数据库不得直接修改，schema 变化必须使用 migration。任何部署操作都要先保留可验证的备份与回退入口。
