# Social Theory Library

Social Theory Library 是面向社会科学研究者的 PDF 数字书库。项目包含公开知识网站、原文与观点检索、PDF Reader、账户中心、批量入库、元数据复核、知识组织、书库问答和管理后台。

当前源码版本为 2.7.1。新 GPT 或 Codex 会话应先阅读 [GPT 项目交接与联动审计](docs/GPT-HANDOFF.md)，再读取架构、进度和问题文档。生产部署与历史验收可能随时间变化，仍需重新执行环境检查。

## 主要能力

- 公开访客可以检索、在线阅读、下载、复制和生成引用。
- 登录读者可以保存进度、收藏、书单、书签、高亮、划线、私人笔记和阅读历史。
- PDF Reader 支持连续阅读、缩略图、目录、文档内搜索、页码映射、命中定位和 Range 请求。
- 入库支持批次、文件级幂等、分片上传、失败重试、PDF 校验、原生文本提取、OCR、元数据候选、人工锁、实体关系、索引和发布预检。
- 原文检索与版本化观点检索使用真实馆藏文本。书库问答的新实现位于 `api/reading`，依赖登录、语义检索和可选 AI 服务。
- 管理后台覆盖上传、处理中心、元数据复核、发布、馆藏、知识对象、推荐、检索评估、用户、配置和备份。

## 技术栈

- Django 5.2、Django REST Framework 3.16
- React 19、Next.js 16、Vinext、Vite
- PostgreSQL 16
- Redis、Celery Worker、Ingestion Worker、Celery Beat
- Meilisearch 全文与语义索引
- FastAPI、PaddleOCR、可选 PP-StructureV3
- Nginx、可选 Caddy 与 Cloudflare Tunnel

完整结构见 [架构文档](docs/ARCHITECTURE.md)。

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

复制安全示例并设置本地 Secret：

```powershell
Copy-Item .env.example .env
```

后端使用项目虚拟环境：

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

- [GPT-HANDOFF.md](docs/GPT-HANDOFF.md) 是新会话的首要入口，记录当前生产快照、功能联动、剩余风险和继续工作的边界。
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) 记录真实模块、数据职责和部署模式。
- [PROGRESS.md](docs/PROGRESS.md) 记录已实现内容、近期验证和下一阶段。
- [ISSUES.md](docs/ISSUES.md) 记录当前七项产品问题及证据。
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) 记录环境、构建依赖、迁移、上线与回退要求。
- [AGENTS.md](AGENTS.md) 约束后续 Codex agent 的修改与验证方式。

## 数据安全

Git 仓库不包含真实 `.env`、凭据、馆藏 PDF、用户上传、OCR 数据、数据库、备份、私人阅读数据、模型、embedding、搜索索引、日志、缓存、依赖目录、构建结果或发布包。

原始 PDF、人工锁定元数据、人工确认关系和私人笔记不得被自动处理覆盖。生产数据库不得直接修改，schema 变化必须使用 migration。任何部署操作都要先保留可验证的备份与回退入口。
