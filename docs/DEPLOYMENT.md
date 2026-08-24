# 部署说明

更新日期为 2026-08-25。本文件记录源码中的部署入口、安全要求和最近一次 3.0.0 生产发布快照。任何后续部署仍需重新检查实时状态。

## Version 3.0.1 pre-cutover status

当前判断为 `SOURCE CANDIDATE / LOCAL GATES COMPLETE / NOT DEPLOYED`。3.0.0 部署源码已固定为 commit `35b5cce` 和 tag `v3.0.0-baseline`。3.0.1 工作树从该提交开始。公网 `/api/ready/` 仍返回 3.0.0，生产 API/Web image、`storage/backups/pre-v300-cutover-20260824-142628/deploy-record`、fresh database backup 和现有回退入口都保持不变。

3.0.1 目标 migration 为 catalog 0035、0036、0037、0038 和 ingestion 0014，reading 仍为 0007。

- catalog 0035 增加 Edition publication date，并为 ResearchRun 增加 canonical revision、draft session/hash、trigger input、current 和 superseded 状态。
- catalog 0036 增加 ReadingPath learning goal、ReadingPathItem prerequisite，并允许 Subdiscipline EditorialRevision。catalog 0037 增加 Discipline EditorialRevision。
- catalog 0038 设置 `atomic = False`。它按 ReadingPath 聚合已采用 Candidate，并在每条路径自己的事务中回填空的 learning goal 与 prerequisite。每条实际变化同步增加 CanonicalObjectRevision，并创建带稳定 idempotency key 的 DomainChangeEvent。migration 只前向运行，reverse 为 noop。
- ingestion 0014 只扩展 EntityResolutionCandidate status choices，增加 `stale`。它不删除 Candidate 或 Evidence。

本地 T3 已完成。初轮后端完整回归发现 3 个本轮影响面内的旧契约失败，契约更新后受影响 4 case 通过。发布安全审查关闭 Owner identity、迟到 Research candidate 和兼容 Global Search 正文权限三项高风险问题；所有编辑停止后，稳定最终代码完整回归为 897 passed、32 个环境型 skip。前端 production build 与 142 项完整 Node 测试发现 1 个旧选择器失败，修改后受影响文件 7 项通过。TypeScript、完整 lint、Django check、migration drift 和 `git diff --check` 通过。Workbench Playwright 首次因没有启动本地 API 而得到 3 个 `Internal Server Error`。启动 3.0.1 候选 API 后，同一套件 3 项通过。

正式切换前仍需完成以下门槛。

1. 从当前 3.0.0 生产生成 fresh BackupJob，复算归档 checksum，并恢复到 disposable PostgreSQL 16。
   切换前还要确认生产邮箱在大小写无关比较下没有重复，并把唯一 Winston 管理员的有效邮箱写入受保护的 `LIBRARY_OWNER_EMAIL`，输出只保留脱敏布尔和数量。
2. 在恢复副本顺序应用 catalog 0035 至 0038 和 ingestion 0014。核对 Work、Edition、Asset、Page、TextBlock、Passage、SemanticChunk、Person、KnowledgeNode、ReadingPath、ORIGINAL Asset 和活动索引的数量与 identity hash。
3. 核对 0038 的候选输入、实际更新路径、Canonical revision 和 DomainChangeEvent 数量。重复执行等价逻辑应无重复写入。因为 0038 没有反向数据迁移，应用回退必须保留 additive schema。
4. 使用保留新增 schema 的恢复副本验证 3.0.0 API 核心只读兼容性。失败时停止发布，不在生产执行 down migration 或 restore 覆盖。
5. 从最终 release commit 构建明确 tag 的 API/Web image。API、默认 Worker、Ingestion Worker 与 Beat 使用同一 API image revision。
6. 保存 pre-v301 Compose、环境文件校验、镜像 ID、源码 archive、活动索引、队列与核心 inventory。暂停 Beat 和 Worker 后应用 migration，再按 API、Worker、Beat、Web、Edge 顺序切换。
7. 完成容器内 HTTP readiness、普通 Editor 关键旅程、Candidate 核实、有限页 OCR、CuratedClaim、Projection、公开页、Reader Range、Ask Evidence、Provider degradation、missing capability 和日志观察后，才可标记 3.0.1 已部署。

4070 客户端当前只执行 `claim_extraction`。其他 capability 不能因 heartbeat 声明而写成已经有执行路径。Laptop 离线时需求保持 waiting，publication 不受阻。Library Synthesis Candidate 也尚未实现，不能在生产 smoke 中把 Source Abstract 或模型常识冒充为该能力。

Research Source 扩展必须遵守源码中的边界。NCPSSD 只允许规则核对后的公开 metadata。全国联合编目必须使用配置的 Z39.50 endpoint 和 credential alias。CNKI、维普、万方只允许合法授权 Provider 或人工 Evidence 导入。Provider 缺失形成可见降级，不放宽 Candidate 与 Evidence 门槛。

## Version 3.0 Wave 4 cutover

3.0 从 `4b97a3484db0c3918f5b0fef8bfc75c35bd0dcee` 增量构建。它继续使用现有 `social-science-library` Compose project、PostgreSQL、Redis、Meilisearch、NAS、PaddleOCR、SearXNG 与 Cloudflare 入口。不得建立第二套数据库或搜索基础设施。

目标 migration 为 catalog 0033 和 0034。二者先在 fresh BackupJob 恢复出的 disposable PostgreSQL 16 上应用。演练必须确认迁移前后 Work、Edition、Asset、Page、TextBlock、Passage、SemanticChunk、Person、KnowledgeNode 与活动 SemanticIndexVersion 没有意外删除，并确认 2.9.2 image 能在保留新增表的 schema 上完成核心只读操作。应用回退默认保留 additive schema，不自动反向 migration。

正式顺序如下。

1. 冻结源码并记录 archive SHA、镜像 tag、当前 Compose、env 文件校验、活动索引和核心对象 inventory。
2. 生成 fresh BackupJob，复算归档 checksum，并完成 PostgreSQL 16 restore、migration 和 rollback compatibility rehearsal。
3. 等待任务稳定，暂停 Beat 和相关 Worker。旧 API/Web 继续服务。
4. 使用候选 API image 执行 migration plan、0033、0034 和 no pending migration 检查。
5. 依次切换 API、默认 Worker、Ingestion Worker、Beat、Web 和 Edge。不得使用 `docker compose down -v`。
6. 有界执行 DocumentRevision/Evidence backfill、registry seed 和 projection reconciliation。Claim 只进入 shadow；AI 不可用不阻断发布。
7. 完成 T4 smoke 和观察后才更新本节为 `PUBLIC DEPLOYED / PRODUCTION ACCEPTED`。

切换时保持 `VIEWPOINT_CLAIM_BENCHMARK_GATE_PASSED=false`。只有真实人工 benchmark run 达到门槛，且 Superadmin 显式激活后，才能在后续发布中改为 true。4070 worker 使用主动 pull，不要求 NAS 保存笔记本公网地址或依赖其在线。

回退入口必须包括旧 API/Web image、旧 Compose/env 副本、fresh database backup、源码 archive 和活动 index UID。若新应用异常，暂停 3.0 Beat/Worker，切回完整 2.9.2 image family，并重新检查 ready、public routes、Reader Range、队列和日志。除非确认发生数据损坏且用户授权，不用 restore 覆盖生产数据库。

### 2026-08-24 实际 3.0 cutover

当前状态为 `PUBLIC DEPLOYED / PRODUCTION ACCEPTED WITH EXPLICIT DEGRADED ITEMS`。公网 `/api/ready/` 返回 3.0.0、database true、pending migrations 0。Compose project、PostgreSQL、Redis、Meilisearch、NAS、PaddleOCR、SearXNG、Cloudflare 和活动语义索引均沿用 2.9.2，没有新增平行数据面。

- 正式 BackupJob 为 `3a8a2633-dc3d-4566-8bed-28d0b1bc29aa`。归档 `/data/backups/pre-v300-database-20260824-142628/library-backup-20260824-062810-3a8a2633.tar.gz` 的 SHA-256 为 `afff698b1c4d8de1bac887fdb572f858a8a9191d195aca642abcc3b45163ee52`，已复算并通过 `pg_restore --list`。
- deploy record 位于 `storage/backups/pre-v300-cutover-20260824-142628/deploy-record`。其中保存旧 `.env`、Compose、2.9.2 API 源码、旧与新镜像 ID、迁移演练、馆藏 identity hash、backfill、benchmark、Projection reconciliation 和 API hotfix 记录。生产 Secret 没有写入 Git 或输出日志。
- catalog 0033、0034 先在 PostgreSQL 16 disposable clone 应用。迁移前后 Work 8、Edition 8、Asset 16、Page 3,135、WorkNodeRelation 1 和 Page identity hash 一致。旧 2.9.2 API 在保留新增 schema 的 clone 上仍返回 ready，因此应用回退不要求反向 migration。
- 正式回填建立 8 个 active DocumentRevision 和 3,735 个 EvidenceSpan。Work、Edition、Asset、Page、TextBlock、Passage、SemanticChunk 与 8 个 ORIGINAL Asset 的 count 和 identity hash 和切换前一致。没有全馆 OCR、Page 重建、PDF 覆盖或活动索引切换。
- Claim shadow 有界调度 21 条 demand。当前没有 LLM executor，全部为 `waiting_for_capability`，publication blocking 为 0。Claim benchmark 没有 gold，gate false，默认 Viewpoint 继续使用 Semantic V2。
- 最终 API、Worker、Ingestion Worker 和 Beat 使用 `social-theory-library-api:3.0.0-final-ae0f4614-20260824-150032`，image ID `sha256:069c9c1aedf7b31e24c2ddfa4602e9130d1338e033b701007202a36e7afcbdd1`。API archive SHA-256 为 `ae0f461428b8abb16e05b32ad70373dfbf699c924c83c74b8409062e59ac0bc6`。
- Web 使用 `social-theory-library-web:3.0.0-candidate-4022b77b-20260824-140003`，image ID `sha256:05b8dc9fd0c04e8c394234c97173995216bc6102a3f3a033a43c8851dfaef6d4`。Web archive SHA-256 为 `4022b77b565770d4ce839c683864e3271d1aaf60bcf25ada27e65be710baf0eb`。该标签对应已校验并实际部署的不可变发布包。
- 正式切换暴露出 PostgreSQL 对 nullable join 执行无范围 `FOR UPDATE` 的限制。Capability runtime 与远程 Worker 的 CapabilityDemand 查询改为 `select_for_update(of=("self",))`。专项 25 项、生产 `reconcile_v3_projections --limit 100` 以及一次不留数据的 4070 lease/context/completion 事务回滚 smoke 均通过；stale Projection 和 waiting Projection demand 均为 0。
- 严格公网 Playwright 6 项通过。首页、当前入库、固定与动态路由、Explore assets、Ask 权限、Reader Range 206、中文 CMap 和 596 页真实 PDF canvas 均已覆盖。顺序 Semantic 与 Viewpoint 查询为 `v2_hybrid`、fallback false，原文、作品、页码和 Reader URL 可用。
- 末次记录 `final-observation-20260824-150715` 中，两个 Worker 的 active、reserved、scheduled 均为 0；Redis 的 celery、ingestion、query_lexicon、unacked、unacked_index 均为 0。活动语义索引仍为 `semantic_passages_20260818210650_4cf87bc9|3005|3005`。API、Worker、Ingestion Worker、Beat、Web 与 Edge 的近 8 分钟 fatal pattern 均为 0，应用容器 RestartCount 为 0。
- 最终 API/Web 归档已复制到 deploy-record 的 `release-artifacts`，复制后 SHA-256 再次匹配。四个仅用于构建和演练的 `/tmp/social-theory-library-v300-*` staging 目录及临时脚本已按精确白名单删除，共释放 85,180,945 bytes；生产镜像、BackupJob、回退环境、部署记录和 SSH 权限保留。

应用回退先恢复 `deploy-record/environment-before.env`，再切回记录中的 2.9.2 API/Web image 并重建 API、Worker、Ingestion Worker、Beat 与 Web。0033、0034 保留；该路径已在迁移 clone 上验证。只有确认数据损坏并取得明确授权时，才使用上述 fresh BackupJob 覆盖数据库。不得执行 `down -v`，不得删除 DocumentRevision、EvidenceSpan、等待中的 Claim demand、原 PDF 或活动索引。

## Version 2.9.2 production deployment, 2026-08-24

当前判断为 `PUBLIC DEPLOYED / PRODUCTION ACCEPTED`。公网 [https://books.winstonmo.com](https://books.winstonmo.com) 的 `/api/ready/` 返回 2.9.2、database true、pending migrations 0。生产仍使用 `social-science-library` Compose project、`compose.public.yaml` 与 `compose.cloudflare.yaml`，没有建立第二套部署体系。

### 最终应用镜像与服务

- API、默认 Worker、Ingestion Worker 与 Beat 使用 `social-theory-library-api:2.9.2-final-3a4733aa-20260824-014228`，image ID 为 `sha256:235d990637ba6e9e5bf3c18011110caa436eb24e47aa4e39b8ab57baf4f2c662`。API 发布归档 SHA-256 为 `3a4733aa550cf04af09b9d55a4ec4ed678a480df1d1c8fcd034febd6a8ebb92a`。
- 最终 Web 使用 `social-theory-library-web:2.9.2-final-34e8e016-20260824-014512`，image ID 为 `sha256:bcc0f0c7f89f76358f08a491094b5a965f72aa9d06faad3698a5e952f3080fac`。Web 发布归档 SHA-256 为 `34e8e01616183a390600a583d420b9b729cd51edf888f17352db8b6518a27d64`。
- 这次最终统一切换包含 ResearchRun owner、Evidence 边界、健康权限、管理员 PDF preview、Picker 降级保留、活动 section overflow 和全部实际维护输入接入。没有重建数据库、PDF、模型或活动索引。
- 最终检查中 API、两个 Worker、Beat、Web 与 Edge 均 running，应用 RestartCount 为 0。PostgreSQL、Redis、Meilisearch、PaddleOCR、SearXNG 与 Cloudflared 保持原状态服务；Cloudflared 使用 HTTP/2 并注册四条连接。

### Migration、备份和回退

- catalog 0032 是 additive migration，只新增 `ResearchRun`、`HealthCheckRun`、`HealthIncident`、`RecoveryAction` 及索引。它没有数据回填、外部请求、PDF 操作、authority mutation 或索引切换。
- 同一切换前 BackupJob 已恢复到 disposable PostgreSQL 16.14。`pg_dump` 与 `pg_restore` 为 16.15，恢复状态、0031 到 0032 migration、Django check、新表、空 migration plan，以及保留 0032 schema 时 2.9.1 核心读取均有 deploy-record 证据。
- 正式 migration head 为 catalog 0032、ingestion 0013、reading 0007，pending count 为 0。
- 最终切换前 fresh BackupJob 为 `965c6431-5d45-4ba2-b4a1-e7f7b263ddde`。归档位于 `/data/backups/pre-v292-followup-20260824-013956/library-backup-20260823-174701-965c6431.tar.gz`，SHA-256 为 `b126ace3aadb66374b79a975360cace81236dae92ca68afefd3d4bceddd6d75e`，已复算并通过 `pg_restore --list`。此前同版本备份的 PostgreSQL 16 restore、0032 migration 和保留 schema 的 2.9.1 compatibility rehearsal 仍保存在 deploy-record。
- API 回退标签为 `social-theory-library-api:pre-v292-final-20260824-014723`。最终 Web 回退标签为 `social-theory-library-web:pre-v292-final-20260824-015006`。应用回退不反向 migration、不恢复覆盖数据库、不修改活动索引。
- API 切换记录位于 `storage/backups/pre-v292-cutover-20260821-174610/deploy-record/final-api-20260824-014723`。Web 记录为同一根目录下的 `final-web-20260824-015006`，最终备份记录为 `final-followup-20260824-013956`，末次稳定性验收记录为 `final-verification-20260824-021518`。
- 验收成功后，两个旧 staging 和三个本轮 staging 已按显式 `/tmp` 白名单删除，清理记录位于末次 verification 目录的 `staging-cleanup.env`。发布镜像、回退标签、backup、deploy-record 与 SSH 权限均保留。

### 生产验收结果

- 12 个 Compose 服务均 running。两个 Celery Worker 可 ping，active、reserved、scheduled 均为 0；Redis 的 celery、ingestion、query_lexicon、unacked 与 unacked_index 均为 0。Beat 持续调度健康、ingestion、semantic 与 QueryLexicon recovery。
- 活动语义索引保持 `semantic_passages_20260818210650_4cf87bc9|3005|3005`。国家、实践、社会学三条公网请求均返回 `v2_hybrid`、`fallback_used=false` 和非空结果。
- 已发布 normalized Reader Asset 的 Range 请求返回 206、`Content-Range: bytes 0-1023/7426650`、`application/pdf` 和 `%PDF-`。
- 首页、Explore、已发布 Work、Reader 和公共原文检索正常。完整动态路由矩阵在 1440、1920、2560、3840px 的 136 个 route-width 组合通过，移动端和平板组也没有破图或横向溢出。核心首屏布局断言全部通过；匿名会话探测产生预期的 `/api/auth/me/` 401 和无 refresh cookie 的 400 控制台资源消息，单独记录为非功能性限制。draft `/works/work-aaf54876` 与对应 Public API 均为 404。
- 管理员 draft 页面预览真实渲染，Reader、保存、下载和引用动作保持关闭。匿名打开管理员预览会转到登录页，受保护 PDF endpoint 匿名返回 401；登录管理员可打开 preview 与 PDF。React #482 不再复现。
- 最终镜像上的 ResearchRun `e285af7a-4949-4567-b765-60739c44df17` 使用未保存的“马克斯·韦伯”，精确绑定 Edition `aaf54876-f563-402f-b244-b14af54614fa`，预分配 task ID，query 同名，实际调用 SearXNG，并返回 VIAF 与 unresolved 两个候选。未保存表单随后被丢弃，没有建立关系、接受候选或覆盖 FieldLock。部署代码探针确认 SearXNG external_web 候选保持 `research_lead`、`lead_only` 且不包含 Evidence。
- 8 条 orphan ResearchRun 由 RecoveryAction `119e7f98-f74b-4a35-9b80-2c05ad3d36a5` 安全转为 canceled，并分别写入审计。最新 Research productive probe `7747b1c9-d0f0-4662-85e7-252b28ada86f` 为 healthy，configured、reachable、functional、productive 均为 true，相关 incident 已 resolved。
- 最终 Entity Picker 在生产页测得 left 343.39、right 903.39、width 560、viewport 1265、document scrollWidth 1265，活动 section overflow 为 visible。VIAF 与未解析分组、降级提示、Arrow Up/Down、Escape、ARIA expanded/controls/active descendant 均在最终生产浏览器核对；390、720、1440px 规则有同版源码的自动化与前序生产浏览器证据。
- 切换后二十分钟以上的两轮完整验证没有应用容器重启、队列积压、持续 HTTP 500、Traceback、CRITICAL 或 unhandled exception。OpenAlex 未配置、Wikidata timeout、SafeWebFetcher 与部分 metadata provider 故障由 Processing Center 如实显示为外部来源降级，不阻断 SearXNG、VIAF、本馆候选、编辑或公共书库。
- Work 8、Edition 8、Asset 16、Page 3135、SemanticChunk 3881、Person 7 与 KnowledgeNode 2 的 ID hash 同切换记录一致。没有删除或重建馆藏、PDF、volume、模型或活动索引。

### 已知但不阻止 2.9.2 的限制

- 普通 non-superuser 管理员上传和发布 E2E 没有正常账户，继续标记为 `待核实`。本轮没有通过绕过登录或提升权限取得该证据。
- 最终 fresh SearXNG 查询实际发出但返回零条一般 Web 结果；VIAF structured provider 已返回真实候选。当前运行不能写成 fresh SafeWebFetcher 正向 passage 已通过。
- 外部功能健康当前有六个待处理事件。SearXNG、VIAF、Crossref 正常；OpenAlex 未配置，Wikidata 握手超时，LOC 零候选，SafeWebFetcher 与部分 metadata provider 没有产出。Research Orchestrator、核心服务、OCR、公开目录、Reader、任务与站内检索均 healthy。
- 新的无状态浏览器访问公共页面时，PublicSessionProvider 会用 401/400 判断没有可恢复登录，会在 Chromium 控制台留下预期资源状态；没有 pageerror、requestfailed 或功能失效。后续可以增加 200 响应的专用匿名会话探测接口，但它不阻止 2.9.2 运行。
- 共享 Interaction Feedback 已覆盖本轮关键 workflow、research、preview、Processing Center 和 health 动作；这不等于已经逐一重写全站所有普通按钮和文本导航。

GitHub repository 的 Public visibility 是 owner 的当前决定。最终 Git 交接只能包含安全源码、测试和文档。真实 `.env`、Secret、Token、SSH key、PDF、OCR 数据、数据库、备份、用户数据、日志、模型、embedding、Meilisearch 数据和其他活动索引不得进入 commit 或远端树。SSH 部署权限按用户要求继续保留。

## Version 2.9.2 pre-cutover plan, 2026-08-21, historical

以下内容是部署前计划，只用于解释当时的保护门槛。当前状态以上一节 2026-08-24 的生产快照为准。当时的判断为 `SOURCE CANDIDATE / LOCAL GATES IN PROGRESS / NOT DEPLOYED`，不再代表当前公网。

部署身份、TCP 22、BatchMode SSH、`sudo -n`、Docker Compose 与生产目录已经重新验证可用。私钥目录继续由 `.gitignore` 排除。部署权限可用不等于发布门槛已经通过，也不得把私钥、sudo 配置或任何生产凭据写入发布包、文档或 Git。

### 当前源码与本地门槛

2.9.2 候选源码已包含独立 Research Orchestrator、未保存 draft context、Research Field Contract、Universal Entity Discovery、ResearchRun 诊断、功能健康与事故恢复、管理员页面预览、统一操作反馈，以及自动研究和宽版 Entity Picker。已有兼容 API 继续复用 Candidate、Evidence、QueryLexicon、FieldLock、ProcessingJob、AuditEvent、公开 queryset 和原有决定服务，没有建立第二套馆藏或 authority。

截至本节写入时，完整后端 pytest 为 610 passed、32 skipped，退出码 0。后端 Research、Entity Decision 与 Health 定向测试 31 项通过；前端定向 Node 测试 29 项、完整 Node 108 项、Auth 与 Scoped Search 19 项、TypeScript、完整 ESLint、production build、Python compileall 和 `git diff --check` 已通过。migration drift、`sqlmigrate` 审查、PostgreSQL 16 恢复演练、Celery/Redis 环境检查和生产 smoke 仍是硬门槛。任一项未完成时不得标记 `READY FOR CUTOVER`。

### 目标 migration

2.9.2 的目标 migration 是 `catalog.0032_healthcheckrun_healthincident_recoveryaction_and_more`。它依赖 catalog 0031 和当前用户模型，新增 `ResearchRun`、`HealthCheckRun`、`HealthIncident`、`RecoveryAction` 及其索引。源码中没有数据回填、外部请求、PDF 操作、authority mutation 或索引切换。这个判断来自 migration 源码审查，仍需在生产备份恢复出的 disposable PostgreSQL 16 上证明。

目标生产 head 为 catalog 0032、ingestion 0013、reading 0007。迁移必须由待发布的统一 API 镜像显式执行。新 Beat 或 Worker 不能在 0032 应用前启动，因为 2.9.2 的研究运行与健康任务会读取新增表。正式窗口至少执行并保存以下无 Secret 证据：

```text
python manage.py showmigrations catalog ingestion reading
python manage.py sqlmigrate catalog 0032
python manage.py migrate --plan
python manage.py check
python manage.py migrate --noinput
python manage.py showmigrations catalog ingestion reading
```

生产应用 0032 前必须完成 fresh BackupJob，复算归档与 `database.dump` checksum，并把同一 artifact 恢复到 disposable PostgreSQL 16。演练需要覆盖 0031 到 0032、Django check、空 migration plan、2.9.2 核心 ORM 读取，以及保留 0032 schema 时 2.9.1 应用的回退兼容性。

### 切换顺序与保护边界

1. 固定候选源码清单和 SHA，完成 API、Web 统一 2.9.2 镜像构建及镜像内检查。API、默认 Worker、Ingestion Worker 与 Beat 必须使用同一 API image revision。
2. 重新读取生产 Compose 拓扑、磁盘、容器、RestartCount、migration、队列、ProcessingJob、活动语义 UID、核心对象数量与 ID 集合。不得沿用 2.9.1 历史快照代替实时值。
3. 生成 fresh BackupJob，校验归档并完成恢复演练。保存当前环境和 Compose 副本，为正在运行的 2.9.1 API 与 Web 建立不可变 `pre-v292` 回退标签。
4. 等待业务队列为空，暂停 Beat、默认 Worker 与 Ingestion Worker。保持旧 API/Web 提供服务，使用新 API 镜像先检查 migration plan，再显式应用 catalog 0032。
5. 依次切换 API、默认 Worker、Ingestion Worker、Beat 与 Web。刷新 Edge，使其指向新的 API/Web 容器。`running` 不是 readiness，必须取得容器内真实 HTTP 响应。
6. 完成下节生产验收和稳定性观察后，才可标记 2.9.2 已部署。随后才能做 Git 安全扫描、commit 和 push。

整个过程不得运行 `docker compose down -v`，不得删除或重建 PostgreSQL、Redis、Meilisearch、馆藏、模型、备份或活动索引 volume。不得覆盖 ORIGINAL PDF、人工锁、人工确认关系、authority 或读者数据。不得自动 merge Person、自动发布 draft authority、自动 Accept Candidate，也不得把 SearXNG snippet 提升为 Evidence。不得放宽 public Work queryset，管理员预览只能使用受保护的 preview API。

### 2.9.2 回退

发布前要在当前 2.9.1 镜像上创建新的 `pre-v292` API/Web 标签，并保存环境、Compose、源码清单、镜像 ID、migration plan、核心对象快照和活动索引 UID。此前 `pre-v291` 标签是历史回退点，不能替代本轮发布前快照。

catalog 0032 从源码看是 additive schema。只有 disposable PostgreSQL 演练证明 2.9.1 能在保留 0032 四张表的数据库上启动和读取核心对象后，应用故障时才可以暂停 2.9.2 Beat/Worker，切回完整的 2.9.1 API/Worker/Beat/Web 镜像族并刷新 Edge。回退时不自动 down migration，不 DROP 新表，不恢复覆盖生产数据库，也不修改活动索引。若 migration 中途失败或 schema 状态不明确，应维持旧应用、停止继续切换并人工审查，不能用自动 restore 掩盖问题。

回退后重新检查 ready/health、pending migration、队列、公开目录、登录后台、Research 入口的兼容降级、PDF Range 206、活动索引和日志。只有这些检查通过，才可把回退记为成功。

### 2.9.2 生产验收清单

- 公网与容器内 `/api/ready/` 均报告 2.9.2、database true、pending migrations 0；catalog 0032、ingestion 0013、reading 0007 已应用。
- API、两个 Worker、Beat 与 Web 使用记录一致的 2.9.2 revision。Web 容器内真实 HTTP、Edge、Cloudflare 入口和主要静态 bundle 正常，应用容器没有重启增长。
- 首页、Explore、作品页、理论、主题、学者、登录、账户与后台主要路由正常。顺序执行观点检索，避免触发 Edge 的同 IP 并发限制。
- 真实公开 PDF 返回 206、`Content-Range`、`application/pdf` 和正确字节；Reader 能渲染，复制、引用和下载保持原权限。
- draft 与 ready Edition 不产生 `public_url`，匿名公共接口和 `/works/<slug>` 继续 404。授权管理员页面预览可读，published 作品页仍正常。
- 正常管理员会话打开 Intake 与 Maintenance workflow。页面加载自动研究，未保存 Person 文本进入 context 和 query；800ms debounce 只重规划受影响字段，手动刷新不会形成请求风暴。
- Universal Entity Discovery 返回 local、local_draft、authority、external_web 和 unresolved 分组，保留多个候选及评分、原因、冲突和 provenance。外部失败时本地结果仍可用。
- 真实 SearXNG、SafeWebFetcher 与至少一个适用 structured/authority provider 产生可区分的诊断。snippet 只作 lead，只有受支持的结构化记录或实际抓取 passage 可以成为 Evidence。
- 实体动作继续由显式决定服务处理。生产 smoke 不自动 merge 或覆盖 authority；create draft 只在经确认的测试对象和授权下执行。FieldLock 与人工确认结果保持优先。
- Processing Center 先显示功能健康，再显示依赖。持久化 probe 能区分 configured、reachable、functional、productive，页面 GET 不临时访问全部 Provider。
- Beat 健康探测租约能阻止重叠批次。Incident 与 RecoveryAction 持久化、幂等、次数限制、退避和 AuditEvent 可核验，恢复动作不直接改数据库、主机或防火墙。
- 保存、刷新、文件 retry/resume、发布/下架、健康恢复、页面/PDF 预览均显示 pending、success、error 与 disabled 状态。桌面和窄屏 Entity Picker 无横向溢出，键盘和 ARIA 状态可用。
- Redis 与 Celery active/reserved/scheduled、ProcessingJob、ResearchRun、HealthCheckRun、Incident、失败任务和日志无持续异常。OCR、Provider 或索引单项失败只能形成可解释降级，不能回滚已确认馆藏。
- 切换前后 Work、Edition、Asset、Page、SemanticChunk、Person、KnowledgeNode 的数量和 ID 集合无意外变化，活动语义 UID 与 Meilisearch 文档计数保持一致，除 catalog 0032 新表外没有未授权的数据变化。
- 在稳定观察窗口结束后重新执行 ready、主要路由、真实联网 research、Processing Center、队列、日志、Range 和容器重启检查，并保存时间、命令、退出码与脱敏证据。

GitHub repository 的 Public visibility 是 owner 的当前决定，不得根据旧文档改回 Private。生产验收完成后的 Git 交接只能包含安全源码、测试和文档。真实 `.env`、Secret、Token、SSH key、PDF、OCR 数据、数据库、备份、用户数据、日志、模型、embedding、Meilisearch 数据和其他活动索引不得进入 commit 或远端树。

## Version 2.9.1 workflow follow-up, 2026-08-21

- release identity 为 base HEAD `1053ff1`、API archive SHA-256 `2ce32c44bce7dbe78ed927309e06b7725c202b08409771ad4b217e1f4eb657c9` 和最终 Web archive SHA-256 `6e7fe2c94338b6f87605b4ee63081020657220452dae340f11d8c768eb673dae`。本轮没有 commit 或 push。
- API、默认 Worker、Ingestion Worker 与 Beat 使用 `social-theory-library-api:2.9.1-wfpatch-2ce32c4-20260821-013518`，image ID `sha256:889d3eeb08e3480993189a223cc3a37522892ac1cb5f3e5d4d2fafe9ec688988`。Web 使用 `social-theory-library-web:2.9.1-sessionfix-6e7fe2c-20260821-020442`，image ID `sha256:6456ab938c52b163de03d5ada1bfbe616100cff14c18ce60e6c3cf4d18c9fce6`。
- Fresh BackupJob `7b3d4d6b-3c6d-402b-a2d1-a28ae40a99b3` completed。artifact 为 `/data/backups/pre-v291-cutover-20260821-013826/library-backup-20260820-173909-7b3d4d6b.tar.gz`，14,823,744 bytes，SHA-256 `3ab91485f375bd2e7760bb60071151f82b3b83791d024ec3e2f85cf5729d9aff`。database dump SHA-256 为 `460d6cf5802953f568022b49d5c648c4387018e57325826e0538d71b41064003`。
- 同一 backup 已在 isolated PostgreSQL 16.14 完整恢复。pg_dump/pg_restore 为 16.15，restore 后 Django check 通过。disposable container 使用 tmpfs、没有 host port，验收后已精确删除。
- production migration plan 为空。catalog 0031、ingestion 0013、reading 0007 不变。Work、Edition、Asset、Page、SemanticChunk 等核心 ID 集合和活动语义索引在切换前后不变；active UID 继续为 `semantic_passages_20260818210650_4cf87bc9|3005|3005`。
- 公网 ready/health、主要路由、三条顺序 v2_hybrid、PDF Range 206、真实 Reader canvas、1440px/390px 响应式和 Web bundle markers 通过。匿名页面不再请求私人 saved API。
- 正常 Winston 管理员会话只读验证 Dashboard、2.9.1 标签、Intake Focus Mode、九步 workflow、Inspector、研究候选面板与 capability 按钮。没有执行联网研究、保存、Candidate decision、Reading Path、发布或下架 mutation。
- 核心回退标签为 `social-theory-library-api:pre-v291-20260821-013826` 与 `social-theory-library-web:pre-v291-20260821-013826`。最终 Web 回退标签为 `social-theory-library-web:pre-v291-sessionfix-20260821-020442`。部署记录位于 `/volume2/library/docker/social-theory-library/storage/backups/pre-v291-cutover-20260821-013826/deploy-record`。
- Meilisearch、PostgreSQL、Redis、PaddleOCR、PDF、模型和活动索引均未替换或重建。普通非 superuser 管理员公网上传与发布 E2E 仍因没有正常账户凭据而标记为 `待核实`。

## Version 2.9.0 production deployment, 2026-08-20

- release commit 为 `e318ec8268e7ff4321b7474cba184b92d3a92ad5`。源码归档 SHA-256 为 `c6ad9494bdd1ad6fbc7c34dd1b300c9d0a3f82fc93755ad37ec7403a91f67e67`，Web dist 归档为 `082f525c802414c4f431267b4c37d55d317e06ffed33d00c2c215c07523d32f2`。本地与 NAS 上传副本一致。
- API、默认 Worker、Ingestion Worker 与 Beat 使用 `social-theory-library-api:2.9.0-e318ec8-20260820-225905`，镜像 ID 为 `sha256:063a3fcaa715cef3380b928cebf82821b6741612accf794e8216b8951b1d7d78`。Web 使用 `social-theory-library-web:2.9.0-e318ec8-20260820-225905`，镜像 ID 为 `sha256:8e0b6ac3f131d49de9707ae23445c1725c1de9c414e97220c6016cad05728551`。
- 本次没有数据库 migration。production migrate plan 为空，catalog 保持 0031、ingestion 保持 0013、reading 保持 0007。PostgreSQL、Redis、Meilisearch、PDF、模型和 PaddleOCR 镜像没有替换或重建。
- Fresh BackupJob 为 `cde45824-844a-45d9-94ac-db0eaae750be`。归档位于 `/data/backups/pre-v290-cutover-20260820-230321/library-backup-20260820-150405-cde45824.tar.gz`，SHA-256 为 `68ff2e685c25afd1bbc5a467b1d416746d0e285947741e1ab37fa9b55a3666f4`。内部 database.dump 已通过 `pg_restore --list`。
- 切换记录与环境、Compose、核心对象和活动索引快照位于 `/volume2/library/docker/social-theory-library/storage/backups/pre-v290-cutover-20260820-230321/deploy-record`。2.8.1 回退标签为 `social-theory-library-api:pre-v290-20260820-230321` 与 `social-theory-library-web:pre-v290-20260820-230321`。应用回退只恢复环境和镜像，不反向迁移、不恢复数据库、不修改索引。
- Work、Edition、Asset、Page、SemanticChunk、Person、KnowledgeNode、ReadingPath、UploadItem 与 ProcessingJob 的 ID 集合哈希在切换前后相同。活动索引保持 `semantic_passages_20260818210650_4cf87bc9|3005|3005`。
- 公网 ready、health、主要公开路由、三条顺序 `v2_hybrid` 查询、真实 PDF Range 206、公开版本 bundle 和新容器日志均通过。两个 Worker 与 Redis 队列为空，应用容器 RestartCount 均为 0。SearXNG 返回 200 和 8 条真实发现结果。
- Winston 管理员会话只读检查了 Intake Focus Mode、step rail、候选 Inspector、classification、knowledge、curation、publication、Maintenance Mode 和旧 review/publication URL。没有执行保存、联网研究、Candidate decision、Reading Path、发布或下架 mutation。
- 普通非 superuser 管理员公网上传与发布 E2E 按用户要求跳过，继续标记为 `待核实`。SSH 部署授权按用户要求保留，不能在后续任务完成前撤销。
- `/tmp/social-theory-library-v290-e318ec8-20260820-225044` 发布暂存已经精确删除。部署脚本与 SHA 清单已复制到上述 deploy-record；成功镜像、fresh backup、回退标签和 SSH 授权均保留。

## Version 2.8.1 R2 ingestion hotfix, 2026-08-20

- API、默认 Worker、Ingestion Worker、Beat 与 Web 使用 `2.8.1-hotfix-20e448a-20260820-055953` 镜像族。`/api/ready/` 返回 2.8.1，pending migrations 为 0。
- 活动语义索引保持 `semantic_passages_20260818210650_4cf87bc9`，数据库和 Meilisearch 均为 3,005。
- UploadItem `92ea5bc2-904b-49cd-848f-67accff9639d` 已完成 R2 import、正式 pipeline、Asset 建立和 staging cleanup。连续 12 个 Beat recovery 周期没有新增 handoff 错误或队列堆积。
- 切换前 BackupJob 为 `a34b13a2-8c79-4bfd-bbd4-b1902c60d367`，回退目录为 `/volume2/library/docker/social-theory-library/storage/backups/pre-v281-cutover-20260820-060904`，归档 SHA-256 为 `03823151e83670f5d5747a0883c46e445ffe55b907b3f866a9a28f3399334451`。回退镜像标签为 `social-theory-library-api:pre-v281-hotfix-20260820-060904` 和 `social-theory-library-web:pre-v281-hotfix-20260820-060904`。
- 普通非 superuser 管理员公网上传 E2E 按用户要求跳过。SSH 部署授权按用户要求继续保留。

## Version 2.8.0 production deployment, 2026-08-20

- release commit 为 `2b1f91ef759b5642b299a5bc504f1f18d417c65e`。源码包 SHA-256 为 `8863b9e28a10ed7762e4e897831c20ee882d605f552915c19f8edb8e98eb9d48`，Web dist 包为 `e7b03d53c239db4b4af1490f36646e980325ad0d2208f9a2fac9b7960cfb309d`。本地与 NAS 暂存副本一致。
- API、Worker、Ingestion Worker 与 Beat 使用 `social-theory-library-api:2.8.0-2b1f91e-20260820-035701`。Web 使用 `social-theory-library-web:2.8.0-2b1f91e-20260820-035701`。
- Fresh BackupJob 为 `1bb75e2d-a411-448f-9553-25f605c5e0cd`。归档位于 `/data/backups/pre-v280-20260820-035701/library-backup-20260819-195838-1bb75e2d.tar.gz`，SHA-256 为 `824f455fc340bfa69ab70f82c68a8f37dbfbc3d423c0233222e1182b4bf21e05`。同一归档已在 disposable PostgreSQL 完成恢复和 catalog 0031 演练。
- 正式 migration 只把 catalog 从 0030 推进到 `0031_admin_workflow_v280`。ingestion 保持 0013，reading 保持 0007。Work、Edition、Asset、Page、SemanticChunk 的迁移前后 ID 集合哈希一致，生产没有 Reading Path、Stage 或 placement 记录需要转换。
- 第一次切换因 Web 尚未监听而自动恢复 2.7.1。第二次切换因 readiness 错把登录后版本文字当成匿名 HTML 门槛而自动恢复。两次回退都没有删除 volume 或反向迁移。第三次使用真实 Web HTTP 与 bundle 标记分别验收后成功。
- 成功切换记录位于 `/volume2/library/docker/social-theory-library/storage/backups/pre-v280-cutover-20260820-041502`。旧 2.7.1 应用镜像和 additive 0031 schema 可作为应用级回退入口；不得自行 down migration 或删除新表。
- 公网 ready/health、公开路由、登录 Admin、Intake Focus Mode、Work-centric Library、Maintenance Mode、旧 review/publication redirect、顺序观点检索和真实 PDF Range 206 已通过。活动语义 UID 保持 `semantic_passages_20260818210650_4cf87bc9`，没有重建索引。
- 已发现但未在本次发布中修复的入库事件：UploadItem `92ea5bc2-904b-49cd-848f-67accff9639d` 为 R2 uploaded 且本地 file 为空；关联 pending R2 job 每分钟恢复时遇到 nullable outer join `FOR UPDATE` 错误。不得把 2.8 发布成功写成 R2 入库问题已解决。
- 发布暂存目录 `/tmp/social-theory-library-v280-2b1f91e-20260820-1945`、专用 sudoers 和两条本轮公钥记录已删除，本地临时私钥与公钥也已删除。使用该身份的新 SSH 连接返回 `Permission denied`。撤权后的 ready、health、Maintenance Mode、V2 semantic 和 PDF Range 206 仍通过。

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
- `reading.0007_reader_ai_connection` was the only planned operation and applied in 6 seconds. Final application image family is `2.7-87251cb`; the pre-release `.env` backup is `.env.pre-usability-6d9848a-20260819-124834`.
- Public viewpoint V2 is enabled after bounded production comparison. Rollback is an environment change to `SEMANTIC_SEARCH_V2_ENABLED=false` plus API/Edge refresh; it does not change the active UID. Ask Library continues to use stable retrieval.

### Internal SearXNG source discovery

`compose.public.yaml` pins the official GHCR mirror `ghcr.io/searxng/searxng:2026.8.4-c63835bd2` and mounts `deploy/searxng/settings.yml`. Set a random `SEARXNG_SECRET`, `FIELD_ENRICHMENT_SEARXNG_URL=http://searxng:8080`, and `FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS=searxng` in the private production environment. The service has no host port and must remain on the backend network. Its JSON result is discovery metadata, not evidence; do not bypass `SafeWebFetcher` or the field policy registry.

The production adapter timeout is 20 seconds and SearXNG gives upstream engines 10 seconds with a 20-second hard maximum. Provider timeout remains a partial-result error and must not be hidden as an empty candidate set.

The NAS egress smoke showed Baidu returning JSON results while the default Western engines timed out without a configured container proxy. Production therefore keeps only the verified Baidu engine. Re-test engine reachability before changing this list; do not enable an engine merely because its adapter exists.

## Version 2.7.1 R2 upload staging

R2 只承接浏览器到正式入库之间的临时 PDF。`INTAKE_STORAGE_BACKEND`、NAS archive/public/incoming、Asset FileField、Reader Range 和公开下载继续使用原有实现。不得把 `R2_BUCKET` 设置成公开馆藏 bucket，也不得把 staging object URL 保存为 Asset URL。

生产 API、Worker、Ingestion Worker 和 Beat 需要同一组服务端变量：

```text
R2_UPLOAD_STAGING_ENABLED=true
R2_ACCOUNT_ID=<server secret environment>
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET=library-upload-staging
R2_ACCESS_KEY_ID=<server secret environment>
R2_SECRET_ACCESS_KEY=<server secret environment>
R2_REGION=auto
R2_UPLOAD_PART_SIZE=8388608
R2_PRESIGNED_URL_TTL_SECONDS=900
R2_MAX_ACTIVE_UPLOADS_PER_USER=5
R2_SIGN_PART_BATCH_SIZE=12
R2_IMPORT_CHUNK_BYTES=8388608
R2_CLEANUP_MAX_ATTEMPTS=12
R2_UPLOAD_CORS_ALLOWED_ORIGINS=https://books.winstonmo.com,http://localhost:3000,http://127.0.0.1:3000,http://192.168.5.6:3000,http://192.168.5.6:18080,http://192.168.5.6:18082
```

Access Key、Secret 与 Cloudflare Token 不进入 Compose、数据库、浏览器、manifest、日志或 Git。S3 multipart 数据面不需要 Cloudflare API Token。若 Token 曾出现在聊天或截图，发布后应轮换并撤销。

本地 Vinext 与 Compose Web 的实际端口是 3000，本地完整 Edge 默认 8080。生产 LAN Edge 当前使用 3000、18080 和 18082。R2 bucket CORS 必须按实际浏览器 Origin 配置，至少允许 PUT 与 Content-Type，并 expose ETag。应用提供以下无 Secret dry-run。只有临时运维 credential 具备 bucket CORS 管理权限时，第二条命令才会成功；正式 object-scoped runtime credential 应保持最小权限，生产 CORS 通常由 Cloudflare Dashboard 或独立运维 Token 写入。

```text
python manage.py configure_r2_upload_cors --dry-run
python manage.py configure_r2_upload_cors
```

本次生产 object-scoped credential 对 `PutBucketCors` 正确返回 AccessDenied。管理员已在 Bucket Settings 保存同一最小策略，随后通过真实 OPTIONS、PUT 与 ETag response 验证。应用运行不需要 Cloudflare API Token。

`ingestion.0013_uploaditem_staging_backend_and_more` 只增加 UploadItem staging 字段、索引、namespace constraint 与 ProcessingJob choice。它不连接 R2、不扫描 PDF、不搬移 NAS 文件、不生成任务。发布前仍需 fresh BackupJob、`migrate --plan`、空队列窗口、统一 2.7.1 image 和 additive PostgreSQL rehearsal。

应用回退优先切回 2.7 image。0013 字段可以保留，旧代码会忽略；不要反向删除含未完成 upload session 的字段。回退后新浏览器上传入口不可用，但已经进入 NAS 的 PDF、已有馆藏和活动索引不受影响。R2 Lifecycle 会处理遗留 incomplete multipart 和 staging object。
