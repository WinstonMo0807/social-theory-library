## 2026-11-13 候选批任务暂停，目标迁至 Mac mini

因宿主实际内存/IO等待，已温和停止 `stl-intelligence-demo-index-beat` 和 `stl-intelligence-demo-worker`，均ExitCode0，无OOM；不清队列/索引/数据库。最后任务write_timeout，断点133保留，不能记录为成功。API、候选搜索、Windows5174保留。正式API、worker、数据库、MCP和隧道未修改。不要按下面历史步骤自动重启候选批任务，先完成资源与迁移核验。

用户已选Mac mini承担大部分服务、NAS主要存储。目标把活动数据库/Redis/Meilisearch放在Mac本地，保留NAS文件路径与唯一正式写入。新机器尚未到货，未执行迁移或生成用于正式切换的最终配置。测量、备份与迁移门槛见 [组合方案](stl4/RAG_WIKI_MACMINI_COMBINATION_20261113.md)。本轮两项编纂修复仅本机验证，未上传/重启NAS。

## 2026-11-13 内网持续 Wiki 候选

候选API、worker及限定beat已温和重载成功。前端发现node_modules junction共用默认Vite缓存导致pdfjs-dist返回504，现候选`cacheDir=../tmp/intelligence-web/node_modules/.vite`并显式预处理pdfjs-dist，重启后实见同版PDF。该目录在本工作区忽略的tmp中，不清理原工作区依赖/缓存；配置含node_modules路径以兼容当前Vinext/Vite的依赖转换。选项语义核对 [Vite cacheDir](https://vite.dev/config/shared-options#cachedir)。仍为内网Vite候选，无开机自启或正式发行部署变更。

仅候选`stl_intelligence_demo_20261109`执行catalog0100；正式18084及公网无变更。API/worker仍挂载`/volume2/library/stl-previews/intelligence-20261109/source/api`。迁移命令为候选容器内`python manage.py migrate --noinput`，不是正式环境命令。

候选API/worker保持现有凭据配置，生成和向量模型仍关闭。worker solo/concurrency=1，队列intelligence,discovery_index，DISCOVERY_INDEX_KEYWORD_ONLY=true。限定beat现在仅启用reconcile-discovery-index,refresh-knowledge-compilations；旧beat停止保留为stl-intelligence-demo-index-beat-before-wiki-20261113。接续每300秒读取持久化标记，不重新全馆编纂。代理结果仍需要本次交互执行，不是无人值守模型服务。

迁移前备份路径`backup-rag-wiki-20261113/candidate.dump`，301131483字节，SHA256 `2aa7718e928a0e560083b91cbb4aea7b7fa67134305a62a00b4be20b908d92f7`。`pg_restore --list`确认2813行且来源为候选库，尚未实际恢复；运行文件、环境、源码前版均在同一受保护目录，不入Git。不能把不完整dumpdata当备份。回退时先停候选执行器并保留本次新产物；源码可回前检查点，破坏性回迁须明确处理新增订阅/执行字段及数据，不能直接在已有新数据上反向migration。公网切换仍须用户授权。

## 2026-11-11 候选索引恢复

候选API、单worker和限定beat已完成温和重载；正式环境未变。reconcile-discovery-index仍每5分钟派发，有效期从240秒改为3600秒，避免排在最多8个约4分钟切片之后被当作过期丢弃。跨单元关键词批次最多20条，未确认写入不推进断点。不清空Redis或活动索引，不启动额外并行重型worker。Windows5174和Docling节点本轮已恢复；开机自启尚未设置。

## 2026-11-10 内网关键词协调器

候选 stl-intelligence-demo-index-beat 使用原worker镜像、独立候选Redis及数据库，无宿主端口。CELERY_BEAT_ENTRIES=reconcile-discovery-index，仅运行现有5分钟索引协调任务；单worker消费intelligence,discovery_index，DISCOVERY_INDEX_KEYWORD_ONLY=true。beat限制256MiB/384MiB swap、CPU0.15，restart unless-stopped；调度文件在容器/tmp，不与正式beat共用。恢复时停止此候选beat即可；正式beat配置未改。该变量未设置时原调度表保持，未知任务名启动失败，不静默忽略。

2026-11-10 候选新增Windows常驻Docling节点与仅内网HTTPS执行器入口18491。启动、证书信任、固定依赖、实际解析、容器/环境备份及恢复安排见[STRUCTURE_WORKER_20261110.md](stl4/STRUCTURE_WORKER_20261110.md)。标准证书与主机名校验保留，凭据/私钥不入Git。Windows尚无开机自启；候选API、Nginx和队列worker为unless-stopped，前一容器和环境文件仍在。正式环境、公网/DNS/隧道未变。

2026-11-10 候选worker已消费`intelligence,discovery_index`，solo/concurrency=1、prefetch=1，512MiB内存/768MiB含swap上限、CPU0.5。显式`DISCOVERY_INDEX_KEYWORD_ONLY=true`使此worker只补关键词；已存在向量不作为外呼许可，语义补齐需要正常模型执行器。来源结构更新默认请求关键词任务。Dockerfile.intelligence的默认队列同步更新，API不加载重模型。新候选worker为unless-stopped；原容器以`stl-intelligence-demo-worker-before-index-20261110`停止保留。回退需先等当前任务完成或受控停机，将新worker改名保留，再恢复旧容器名和启动；不删除队列、索引或数据库。正式服务未变。原文校正备份与真实样本见CURRENT_PROGRESS。

2026-11-10 候选Web可用`powershell -File scripts/start_intelligence_demo.ps1 -NodePath <node.exe绝对路径>`启动独立隐藏进程，日志/PID写入忽略的tmp/intelligence-web。限定5174→18091；占用端口时拒绝启动，不自动杀其他进程。进程不随工具会话退出，但机器重启后需重新启动；仍为Vite开发候选，不是公网发行部署。0098迁移及受影响表备份见知识核心记录。

# STL 部署与运行入口

2026-11-10 新增[Knowledge Core / Intelligence 内网候选](stl4/KNOWLEDGE_INTELLIGENCE_20261109.md)，记录新模型、服务、locator、配置、隔离部署和未完成项。以下仍描述正式环境，不能将候选能力误作已上线。

当前运行说明在[架构文档第13章](architecture/13_DEPLOYMENT_AND_OPERATIONS.md)，当前镜像与版本证据在[审计基线](architecture/AUDIT_BASELINE.md)。本页保持既有文档链接有效，不再复制第二份会漂移的部署手册。

- [本地运行：环境、Compose、依赖与启动边界](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#本地开发入口)
- [生产拓扑：Cloudflare、Nginx、NAS与同一业务环境](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#生产部署拓扑)
- [运行架构：网络、容器角色、按需重任务与存储](architecture/02_RUNTIME_ARCHITECTURE.md)
- [OCR与派生索引](architecture/10_ASYNC_TASKS_AND_OCR.md)
- [发布、备份和恢复所需事实](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#发布与恢复必须记录的事实)
- [实际完成的检查与未覆盖范围](architecture/VALIDATION.md)

基础Compose是本地环境入口，不是当前NAS的完整部署清单。生产观察到累计27层配置覆盖；旧tag、目录名或单个文件不能代表实际运行版本。Web、API、worker、OCR、模型与索引必须分别核对。

本轮只提交代码整合和文档。生产切换、数据迁移、密钥配置与恢复操作不在本轮范围，不能直接把README示例命令用于已有生产库。

早期Paddle离线依赖、旧部署形态及历史操作说明仍可在 [Git 历史快照](https://github.com/WinstonMo0807/social-theory-library/blob/315a3c48442afc9cafc79718c152e5e70352b13f/docs/DEPLOYMENT.md) 中查看。使用前须按当前源码和实际环境复核。
