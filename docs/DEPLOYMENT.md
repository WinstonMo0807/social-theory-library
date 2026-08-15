# 部署说明

更新日期为 2026-08-16。本文件记录源码中的部署入口和安全要求，不是当前生产环境的实时状态证明。

## 部署文件

| 文件 | 用途 |
| --- | --- |
| `compose.yaml` | 本地或单机验证，包含数据库、队列、搜索、API、Worker、Web、Edge 和可选 OCR/GROBID |
| `compose.public.yaml` | 加固的完整服务，包含 PostgreSQL、Redis、Meilisearch、API、两个 Worker、Beat、Web、Nginx 和可选 Caddy/OCR/GROBID |
| `compose.cloudflare.yaml` | 在完整服务上增加 Cloudflare Tunnel，并绑定局域网管理入口 |
| `compose.nas.yaml` | 拆分式部署中的 NAS Worker、Ingestion Worker 和 PaddleOCR |
| `deploy/nginx/default.conf.template` | 同源 API、上传并发、限流、X-Accel 和 PDF Range |
| `deploy/caddy/Caddyfile` | 可选的直接 HTTPS 入口 |

已有交接记录称生产使用 `compose.public.yaml` 与 `compose.cloudflare.yaml`。该信息可能变化，部署前必须在目标主机重新确认，不得直接沿用历史容器、IP、任务状态或临时访问凭据。

## 环境文件

仓库只提交 `.env.example`。复制后生成的 `.env`、`.env.nas` 和任何环境专用文件均被 Git 忽略。

示例中的所有 Secret 都是明显占位值或空值。生产部署前至少需要重新生成：

- `DJANGO_SECRET_KEY`
- `PRIVATE_DATA_ENCRYPTION_KEY`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `MEILISEARCH_MASTER_KEY`
- `INTERNAL_API_TOKEN`
- `LAN_PROXY_TOKEN`
- Cloudflare、S3、邮件、AI、OCR 或外部 Provider 所需凭据

不得把真实值写入 Compose、源码、README、Issue、截图、终端记录或 Git 历史。不要在聊天中发送 GitHub Token、生产密码或 2FA code。

## 本地验证

准备本地配置：

```powershell
Copy-Item .env.example .env
```

首次启动前应替换示例数据库密码和 Django Secret。当前 `compose.yaml` 的 Redis 默认不启用密码，因此本地示例使用无密码的容器内 Redis 地址。生产栈要求 Redis 密码，不应直接复用本地值。

启动完整单机服务：

```powershell
docker compose --profile ocr up -d --build
```

只做源码开发时，也可以分别运行 Django 和 Web。具体命令见根目录 [README.md](../README.md)。

## Git 仓库不包含的构建依赖

`ocr_service/Dockerfile` 需要一个为 Intel N5105 编译的无 AVX PaddlePaddle wheel。该文件大小为 120,997,886 字节，超过 GitHub 普通 Git 单文件限制，因此不会提交。文件名、来源提交、构建参数和 SHA-256 记录在 `ocr_service/vendor/README.md`。

构建 OCR 镜像前，必须从授权的私有制品存储把 wheel 放到 `ocr_service/vendor`，并核对 SHA-256。不得从聊天记录、未知网盘或同名未校验文件恢复。

`offline/web-runtime-node-modules-2.5.0-linux-x64.tar.gz`、离线 wheel、模型缓存和历史发布包也不会提交。需要离线部署时，应从独立制品存储恢复，并使用发布清单校验。仅克隆 GitHub 仓库不能证明 OCR 或离线镜像可直接构建。

## 生产部署前检查

1. 确认目标 NAS 型号、CPU、可用内存、真实挂载路径和剩余空间。
2. 确认 Compose project、实际使用的 Compose 文件和当前镜像标签。
3. 备份 PostgreSQL、当前源码、环境文件、Compose 配置和活动索引记录，并验证数据库备份可读取。
4. 检查数据库 migration 状态、Redis 队列、Celery active/reserved/scheduled、OCR 任务和语义索引任务。
5. 确认 `NAS_HOST_ROOT` 下的 archive、public、incoming、backups 和 models 均指向预期目录。
6. 确认 Meilisearch、PostgreSQL、Redis 和对象存储管理端口不暴露公网。
7. 确认生产模式关闭 demo fallback，启用安全 Cookie，并正确设置 Host、CORS、CSRF 和代理头。
8. 先校验镜像和迁移，再替换服务。任何失败都应停止继续切换。

## 数据库迁移

所有 schema 修改必须通过 Django migration。禁止直接在生产 PostgreSQL 执行临时结构修改。

部署前运行：

```powershell
Set-Location api
..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
..\.venv\Scripts\python.exe manage.py showmigrations
```

生产迁移前需要数据库备份和明确回退方案。大表回填、唯一约束和锁等待必须先在代表性 PostgreSQL 数据上演练。SQLite 测试不能替代 PostgreSQL 并发与锁验证。

## 文件与索引安全

- 不运行 `docker compose down -v`。
- 不删除或重建生产 PostgreSQL、Redis、Meilisearch、模型和馆藏 volume。
- 不覆盖、重编码或删除 ORIGINAL PDF。
- 不为修复计数差异先删除活动索引。新索引使用新版本，验证后再切换。
- 不强杀正在保存 OCR 页批次、合并上传文件或提交索引的 Worker。
- 不让公网和局域网管理使用两套独立数据库或馆藏目录。

## 上线后验收

上线后至少检查：

- API readiness、数据库、Redis、Celery Worker、OCR、Meilisearch 和模型健康
- pending migration、任务队列和失败任务
- 登录、权限、账户初始化和私人数据隔离
- 首页、搜索、观点检索、Reader、引用、下载和 PDF Range 206
- 上传分片、恢复、元数据复核、发布预检和下架
- 原文结果与 Reader 页码回链
- 活动语义索引 UID、PostgreSQL ready 记录和 Meilisearch 文档计数
- Cloudflare 或 Caddy 入口、Nginx 日志和浏览器控制台

测试结果应记录命令、时间、退出码和环境。历史验收、本地包检查或页面能渲染都不能代替当前生产检查。

## 回退

每次发布应保留旧源码、旧镜像标签、环境配置和数据库备份。无 migration 的应用回退可以恢复旧源码与镜像。包含 migration 的回退必须依据迁移影响单独决定，不能默认反向迁移安全。

回退后仍要复核 readiness、队列、活动索引、Range、登录和公开页面。生产备份、馆藏、模型与索引不进入 GitHub，它们继续保存在服务器或授权制品存储。
