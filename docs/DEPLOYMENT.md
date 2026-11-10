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
