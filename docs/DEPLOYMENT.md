# 部署说明

更新日期为 2026-08-19。本文件记录源码中的部署入口和安全要求，不是当前生产环境的实时状态证明。

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

### BackupJob PostgreSQL runtime

正式 BackupJob 由 `api/distribution/tasks.py` 执行。API 镜像明确安装 PostgreSQL 16 client，不能改回 Debian 未锁 major 的 `postgresql-client`，也不能使用 `postgres:latest` 作为正式工具来源。API、默认 Worker、Ingestion Worker 与 Beat 必须使用同一 API 镜像。当前没有独立的定时 BackupJob，管理员请求由默认 Worker 消费。

任务开始导出前会读取 PostgreSQL server、pg_dump 与 pg_restore 版本。pg_dump 或 pg_restore 的 major 小于 server major 时，任务立即失败并写入明确的无凭据错误。数据库密码只通过子进程环境传入，不出现在 argv、manifest 或错误文本。

成功归档继续采用现有 tar.gz 格式。内部包含 custom-format `database.dump`、asset inventory 与 manifest。BackupJob 记录 artifact 名称、创建时间、大小、SHA-256、server/client 版本和 applied migration heads。生成归档以后仍必须完成 restore rehearsal，不能只以文件存在作为迁移门槛。

恢复演练使用空白、隔离、名称含 `restore`、`rehearsal`、`evaluation`、`disposable` 或 `test` 的 PostgreSQL 数据库。连接信息通过环境变量提供，不写进命令行示例。命令还要求目标数据库名二次确认：

```powershell
Set-Location api
..\.venv\Scripts\python.exe manage.py rehearse_database_restore `
  C:\path\to\library-backup.tar.gz `
  --confirm-disposable-database library_restore_rehearsal
```

命令会拒绝非 PostgreSQL、名称不符合 disposable 约束、确认值不一致或已经存在业务表的目标。它校验归档内 database.dump 的 SHA-256，并在 pg_restore 前再次检查 client、目标 server 和 dump client major。

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

### Production Task 3 回退记录

2026-08-17 部署镜像为 `social-theory-library-api:2.6.1-task3-prod-20260817-181038-a611debdf616`，source revision 为 `a611debdf6167cbf3b4448718922b8cf62a375d593e16973f1041634456a9327`。部署前环境回退副本为 `/volume2/library/docker/social-theory-library/.env.pre-production-task3-20260817-182353`。原 STL-008 hotfix image 与更早 r60 image继续保留。

catalog 0027/0028 与 ingestion 0011 都是 additive schema。正式 artifact 的 disposable rehearsal 已证明旧 STL-008 hotfix image 能在保留这三份 schema 的数据库上通过 Django check、migrate plan 与核心 ORM 读取。因此应用故障时优先恢复环境文件并切回旧 image，不自动 down migration，不删除 QueryLexicon/Candidate tables，也不重写 authority。

生产切换后 QueryLexicon revision 为 1，generation 为 `af302b64-1b3f-447d-88ca-5ed505bc87e9`。公开 V2 仍关闭，active semantic UID 仍为 `semantic_passages_20260809143729_4cf87bc9`。回退前后都要复核这三个值。

## Version 2.7 release gate

2.7 的统一 release 必须让 API、Worker、Ingestion Worker、Beat 和 Web 使用同一源码 revision。生产前最低检查为 fresh BackupJob、artifact checksum、`migrate --plan`、`manage.py check`、后端 migration drift、前端 TypeScript/build 和基础设施可访问性。迁移前暂停不兼容旧 worker，迁移后再启动统一镜像。

上线顺序固定为备份、计划检查、暂停不兼容 worker、使用一次性 API 容器执行显式 migration、统一应用发布、QueryLexicon dry-run/reconciliation、必要的 clean semantic projection、健康检查和恢复处理队列。`compose.public.yaml` 的 API 启动命令只执行 collectstatic 和 Gunicorn，不会自行 migrate；生产迁移必须由发布操作者在核对 `migrate --plan` 后执行。不得自动发布 draft authority、自动 Accept Candidate、自动全库 web/AI enrichment 或切换公开 V2。若生产基础设施或备份门槛不能证明，状态必须保持 `DEPLOYMENT BLOCKED`。

受控迁移示例（目标主机上执行，不把真实环境值写入命令记录）：

```text
docker compose -f compose.public.yaml -f compose.cloudflare.yaml run --rm --no-deps api python manage.py migrate --plan
docker compose -f compose.public.yaml -f compose.cloudflare.yaml run --rm --no-deps api python manage.py check
docker compose -f compose.public.yaml -f compose.cloudflare.yaml run --rm --no-deps api python manage.py migrate --noinput
```

2026-08-19 本地 2.7 门槛已通过：后端全量回归、Django check、migration drift、compileall、前端 Node 回归、TypeScript、ESLint、Vinext build 和 diff check 均退出成功。早先 SSH 公钥拒绝已由用户修复，后续真实部署已完成。

### 2026-08-19 实际 production cutover

- release commit：`7cd68d30776c0c652e080d147959a3183a92b71b`
- API、Worker、Ingestion Worker、Beat 和 Web 使用统一 2.7 image family。当前 Compose 的 API 启动命令不执行 migration。
- fresh BackupJob、6 个 production migration、QueryLexicon dry-run/reconciliation 和 clean semantic projection audit 已完成。
- active UID 已切换到 `semantic_passages_20260818210650_4cf87bc9`，旧 UID 保留为 retired rollback target。未启用 V2，未修改 ranking、authority 或 Candidate Accept。
- 公网 ready、health、首页、V1 semantic、Range 206 和 Edge refresh 已通过。当前状态为 `PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。
- 回退副本保留在生产目录：`.env.pre-2.7-255cc30-20260819`、`.env.pre-2.7-7cd68d3-20260819` 和 `compose.*.pre-2.7-255cc30-20260819`。包含 migration 的回退仍只允许应用/镜像回退，不自动 down migration。

### 2.7 reader-owned Ask connection follow-up

`reading.0007_reader_ai_connection` is an additive migration for the authenticated reader-owned Ask connection. It creates only the encrypted connection record, status fields and lookup index. It does not call a provider, scan a PDF, create a Candidate, change authority, or touch a semantic index. Apply it only after a fresh BackupJob and a reviewed `migrate --plan`; deploy the same API, Worker, Ingestion Worker, Beat and Web revision afterward. A server-side AI profile remains optional. Do not put reader API keys in `.env`, manifests, logs, browser storage or screenshots.

### 2026-08-19 post-cutover usability release

- Fresh BackupJob `14a78648-8b26-44c0-a450-24acc3d594f7` completed and its artifact checksum was recomputed before migration.
- `reading.0007_reader_ai_connection` was the only planned operation and applied in 6 seconds. Final application image family is `2.7-7294225`; the pre-release `.env` backup is `.env.pre-usability-6d9848a-20260819-124834`.
- Public viewpoint V2 is enabled after bounded production comparison. Rollback is an environment change to `SEMANTIC_SEARCH_V2_ENABLED=false` plus API/Edge refresh; it does not change the active UID. Ask Library continues to use stable retrieval.

### Internal SearXNG source discovery

`compose.public.yaml` pins the official GHCR mirror `ghcr.io/searxng/searxng:2026.8.4-c63835bd2` and mounts `deploy/searxng/settings.yml`. Set a random `SEARXNG_SECRET`, `FIELD_ENRICHMENT_SEARXNG_URL=http://searxng:8080`, and `FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS=searxng` in the private production environment. The service has no host port and must remain on the backend network. Its JSON result is discovery metadata, not evidence; do not bypass `SafeWebFetcher` or the field policy registry.

The production adapter timeout is 20 seconds and SearXNG gives upstream engines 10 seconds with a 20-second hard maximum. Provider timeout remains a partial-result error and must not be hidden as an empty candidate set.

The NAS egress smoke showed Baidu returning JSON results while the default Western engines timed out without a configured container proxy. Production therefore keeps only the verified Baidu engine. Re-test engine reachability before changing this list; do not enable an engine merely because its adapter exists.
