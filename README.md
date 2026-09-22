# Social Theory Library

Social Theory Library 是面向社会科学研究者的 PDF 数字书库。项目包含公开知识网站、原文与观点检索、PDF Reader、账户中心、批量入库、元数据复核、知识组织、书库问答和管理后台。

**3.0.8与OCR/检索界面修复已提交推送并部署公网。** 当前API/Web应用源码为`486af131405cc1100f5093747f33cf807063c481`，初始检索索引15/15来源、4483条文档全部激活，真实查询、原文定位和阅读已通过。观点检索恢复3.0.6三栏布局；处理中心增加直接OCR重试、暂停/继续及每2秒更新的已保存页数进度。索引由书库自身增量维护。源码、镜像、备份与实际部署结果见[交付记录](docs/V3.0.8_COMPLETION_RELEASE.md)、[当前状态](docs/CURRENT_STATE.md)和[部署记录](docs/DEPLOYMENT.md)。

3.0.7已先行完成开发、测试、提交和部署，包括34张参考图对应页面、十三项直接展开的管理入口、推荐期、固定版式编辑、原文策展及学者共享关系。用户已明确豁免受本地运行策略阻断的真实浏览器验收，该项没有标记通过。历史证据见[3.0.7交付记录](docs/V3.0.7_COMPLETION_RELEASE.md)。

## 给准备审计或重设计管理端的 AI

先读[实际架构与应用场景](docs/GPT_ARCHITECTURE_CONTEXT.md)、[管理端架构与功能画像](docs/ADMIN_ARCHITECTURE_PROFILE.md)，再读[上架与发布流程](docs/INGESTION_AND_PUBLICATION.md)和[重设计要求](docs/REDESIGN_BRIEF.md)。它们解释当前六组菜单、43入口、管理员填写什么、各种保存范围、是否跳转、哪些页面实际读取、权限和失败恢复，不依赖原聊天。当前实现不是必须照搬的未来设计。

上述架构画像是3.0.6历史基线；3.0.7的入口与数据增量见交付记录和最新源码，不再沿用六组折叠菜单作为当前界面要求。继续保留原有服务、权限和唯一数据来源，不更换技术栈、删除原件或建立第二套书库。

阅读顺序为 `AGENTS.md`、以上说明、`CURRENT_STATE.md`，然后按[43入口历史能力清单](docs/V3.0.6_ADMIN_CAPABILITY_INVENTORY.md)及[编辑—公开读取历史对照](docs/V3.0.6_PUBLIC_CONTROL_MATRIX.md)进入源码。`CURRENT_PROGRESS.md`、`PROGRESS.md`和旧文档保留历史，旧状态不等于当前状态。原[GPT-HANDOFF](docs/GPT-HANDOFF.md)为2.9.2快照。最新验证及未实测范围见[3.0.8交付](docs/V3.0.8_COMPLETION_RELEASE.md)，不把历史测试数累加成最终全量通过。

## 主要能力

- 公开访客可以检索、在线阅读、下载、复制和生成引用。
- 登录读者可以保存进度、收藏、书单、书签、高亮、划线、私人笔记和阅读历史。
- PDF Reader 支持连续阅读、缩略图、目录、文档内搜索、页码映射、命中定位和 Range 请求。
- 入库支持批次、文件级幂等、分片上传、失败重试、PDF 校验、原生文本提取、OCR、元数据候选、人工锁、实体关系、索引和发布预检。
- 原文、知识入口和策展检索使用实际可公开来源；异步查询支持分页、一次扩展、取消及准确原文上下文，本地编码与重排不依赖付费 API。书库问答实现位于 `api/reading`，仍依赖登录、既有语义检索和可选 AI 服务。
- 管理后台覆盖上传、处理中心、元数据复核、发布、馆藏、知识对象、推荐、检索评估、用户、配置和备份。
- 手工编目可不依赖上传记录。纯书目、带PDF的馆藏和已发布维护使用真实编目会话与现有发布服务。
- 当前工作页整页显式保存，字段建议先填入、可改写/撤销并保留来源；发布前草稿不泄漏。理论时间线在理论管理之下，填写具体文件和页码出处。
- 封面在文件安全校验后优先准备候选，可任选PDF页、上传图片或维持默认。补/换PDF和重新OCR从当前Edition发起，识别进度来自实际已保存页数，并有暂停/继续/取消。
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
