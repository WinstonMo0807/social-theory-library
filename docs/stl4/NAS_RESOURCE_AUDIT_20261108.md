# NAS Docker 负载调查与临时退出记录

调查时间：2026-11-08 01:57—02:08，Asia/Shanghai。依据实际 SSH 只读采样、容器 inspect/cgroup、Redis 队列、PostgreSQL 只读事务、两个相关对话及对应源码。未执行构建、压测、OCR、索引重建、数据清理或新版本发布。

用户最初要求调查；随后明确不需要旧推理模型，并要求目前不工作或相关对话不需要的服务全部退出。按此追加授权，仅对下表明确闲置服务执行退出及取消自动重启。没有删除容器、镜像、模型、卷、数据库或原始 PDF。

## 结论

存在实际负载设计问题，但不是把所有进程装进两三个容器就能解决。首要问题是普通队列拥堵与重复投递、周期任务堆积、整机预算缺失，以及在承载业务的 NAS 上继续叠层构建镜像。重复旧推理副本也有明确浪费。

NAS 为 Intel N5105、4 核，内核可见内存 7.63 GiB。调查开始有 22 个运行容器，其中正式书库 16 个；另有一份旧预览推理服务。镜像列表有 651 行标签、444 个不同镜像 ID，不能把这些数字当作运行容器数或内存占用。

历史故障证据来自 tmp/stl4-workspace-type-20261107/read-r9-after-cancel.log：load 42.40 / 37.95 / 33.28，MemAvailable 197648 KiB（约 193 MiB），Docker inspect 超时、页面访问失败。read-r9-pressure.log 同时出现 D 状态进程。符合严重内存和 I/O 压力，但不足以证明每次都发生内核 OOM kill。

本次采集发生在宿主机重启之后，journal 只保留上一启动周期自 11-07 23:47 起和本次周期的记录，未覆盖上述 23:40 故障。所查 kernel journal 没有匹配 OOM 条目，本次 cgroup OOM 计数为 0，不能据此否定重启之前的问题，也不能把容器 exit 137 单独解释为 OOM。

## 已观察的资源与镜像

| 对象 | 调查开始的近似工作集 | 说明 |
| --- | ---: | --- |
| 正式 Web | 112 MiB | 768 MiB 上限 |
| API | 221 MiB | 512 MiB 上限 |
| 四个 Celery Worker | 合计约 951 MiB | 各自 concurrency=1，总共仍有四个执行槽 |
| Beat | 186 MiB | 实际未设置内存上限 |
| RapidOCR | 568 MiB | 1536 MiB 上限；这批书仍有未完成 OCR |
| 正式推理 | 286 MiB | 1600 MiB 上限；取样时没有模型处于 loaded 状态 |
| 旧预览推理 | 271 MiB | 同一镜像的重复进程，无调用方 |
| SearXNG | 118 MiB | 本轮无相关在途研究任务 |
| DOCX 转换 | 20 MiB | 小占用，非主要原因 |
| PostgreSQL / Redis / Meilisearch | 约 80 / 16 / 34 MiB | 当前低占用不能代表索引时峰值 |
| NAS Firefox 容器 | 约 440 MiB | 非本轮书库范围，未操作 |

以上为不同秒的 Docker stats 工作集快照，不能与 RSS、共享页或宿主 MemAvailable 直接逐项等同。正式配置中有限额的服务，其内存上限相加约 8640 MiB，已经大于物理内存；还未包括未限额的 PostgreSQL、Beat、入口、NAS 自带服务。上限不是预留量，此总和证明缺少可同时运行的整机预算，不表示这些服务实际始终占用这么多。

运行 PostgreSQL 的 Memory=0，与仓库 compose.stl4-cutover.yaml 的 512m 不一致。配置文本存在不等于既有容器已经采用；不能为了对齐文本直接重建数据库。

镜像检查：

- 正式 Web readable-r4：2234.4 MiB，53 层。
- 正式 API scholar-slug-r3：520.3 MiB，117 层。
- Worker upload-r5：519.1 MiB，103 层。
- 推理镜像：429.0 MiB，9 层。
- r9 候选脚本以运行中的 Web 镜像 digest 为 FROM，随后删除并 COPY dist。旧内容仍留在下层，连续补丁会累积层和体积。此脚本没有构建前的宿主内存/压力门槛或跨对话互斥。应用已经在本机编译，NAS 上卡住的是镜像打包/叠层，不应误写成 NAS 正在编译整个前端。

## A：有直接证据的修复项

### NAS-A01 OCR 重复投递和周期消息积压

02:01:36 实际读取 broker DB 2 的 celery 列表，共 2277 条，低于读取预算 3000，因而该次覆盖了整条普通队列。此前 02:00 左右为 2242 条；ingestion、discovery_query、discovery_index 当时均为 0。

- OCR：890 条消息，仅 79 个不同 task ID，至少 811 条是相同任务 ID 的额外副本。
- 两类执行器心跳：231 + 230 条。
- run_scheduled_health_probes：116 条。
- recover_ingestion_queue：116 条。
- recover_projection_queue：116 条。
- 其余包括发布事件、术语恢复、备份调度等。部分任务已有 expires，其他多类周期任务没有 expires。
- 数据库实际有 40 个 pending OCR job、40 个当前 task ID；记录目标 14707 页、已处理 2567 页、剩余 12140 页。这是持久任务进度，不代表已重新核验每页都必须 OCR。

根因代码 api/ingestion/services/processing.py:345 的 recover_stalled_processing_jobs：pending 超过 INGESTION_QUEUE_STALLED_SECONDS（缺省 180 秒）后直接再次投递同一 task ID，未确认旧消息是否仍在 broker 等待。拥堵会触发更多重复消息。旧身份检查可防部分重复业务写入，但不能消除排队、反序列化、数据库查询和恢复开销。

api/config/settings.py 的任务路由没有把 process_ocr_job 指定给 ingestion 队列，dispatch_ocr_job 也未指定 queue，因此它进入默认 celery，与轻任务和周期检查共用单 Worker。不能看到 ingestion-worker 空闲就认为 OCR 没在工作。

最小修复应保留持久 job、页级检查点、当前 task ID 和人工修订：针对每次投递建立可续期的排队/执行凭据，限制恢复重复入队；周期任务按用途设置过期与合并；OCR 转入串行批处理队列。不能直接 purge Redis 或把所有等待任务重做。

### NAS-A02 巡检占用业务执行槽和失效目标循环

最近所取日志中，11 次 run_scheduled_health_probes 均用时约 20 秒；源码 soft_time_limit=20，捕获异常返回 time_budget。这里的 Celery succeeded 只代表函数返回，不代表所有服务健康。它与 OCR 共用一个执行槽，周期消息积压时影响更明显。

同时有 10 次 recover_projection_queue 报 ValueError：投影目标不存在。已定位调用链：tasks.recover_projection_queue → reconcile_projection_runtime:1611 → schedule_domain_change_projections:478 → queue_projection_refresh:361 → _target:103。协调循环没有把缺失对象作为单独终态处理，异常中断本次后续处理，下个周期重来。

最小范围：周期巡检分预算、限制过时任务、保留真实失败；失效投影目标明确关闭或标记待处理并继续其他对象，保留历史。不要通过吞掉异常或显示绿色解决。

### NAS-A03 整机预算与构建争用

单容器上限没有覆盖所有实际服务，总峰值也未限制。r9 构建与现有 OCR、任务、模型/索引和 NAS 自带服务争用同一 4 核机器。停止构建后历史记录仍有高负载，不能把全部原因归给 r9。

最小范围：构建/打包移到本机，NAS 只加载成品和滚动替换；同一 NAS 同时只允许一个部署/构建动作；重任务按实时 MemAvailable、压力和已占用执行槽决定是否接纳，暂停新增任务而非杀正在保存的任务。总预算先以给系统留约 2 GiB 及突发余量为设计起点，数值须经代表工作负载实测，不直接压低已经出现过 OOM 的 Meilisearch 上限。

### NAS-A04 镜像连续叠层与有效配置难追踪

保留现有技术栈，改为从固定、可复现的干净运行基础重新产出版本镜像。共用 API 镜像可继续被 API/Worker/Beat 使用，不把多个进程合到一个容器冒充资源节省。临时候选版本设置数量上限和明确退出流程。镜像清理要先核对活动引用和回退保留清单；本轮没有清理 651 个标签。

## D：按追加授权已退出的服务

| 容器 | ID 前缀 | 退出依据与影响 |
| --- | --- | --- |
| stl4-preview-20261026-r1-discovery-inference-1 | bf8c73ee48b9 | 旧推理副本，网络仅自身，无公开端口、无 8091 在途连接；与正式服务共用模型目录，文件保留 |
| social-science-library-ingestion-worker-1 | f8acc4b7d66d | 活动/预取/延迟任务均 0，队列 0；新上传的后续处理暂缓 |
| social-science-library-discovery-query-worker-1 | 98bab7eb40f4 | 活动/预取/延迟任务均 0，队列 0；语义/深度查询执行暂缓 |
| social-science-library-discovery-index-worker-1 | cb0dda545143 | 活动/预取/延迟任务均 0，队列 0；新的索引更新暂缓 |
| social-science-library-discovery-inference-1 | 3748e82a014f | 未加载推理模型；模型推理暂不可用 |
| social-science-library-docx-preview-1 | ffa62b52014d | 本轮没有 DOCX 转换工作；DOCX 预览暂不可用 |
| social-science-library-searxng-1 | c437c11392a5 | 当前相关任务不做联网研究；依赖它的联网研究暂不可用 |
| stl-workspace-proposals-20261107 | 138a915e1abb | 旧独立 A/B 工作区演示，正式 UI 已另行发布；18088 演示暂停 |

全部 RestartPolicy=no。后三份 Worker 返回 exit 0；只发送 TERM，没有超时升级为 SIGKILL。其余终止码 143 是本轮主动 TERM 的结果，不记为 OOM。第二批操作对所有其他运行容器检查身份、启动时间和运行状态，变化列表为空。

02:06:15 MemAvailable=3085056 KiB（2.94 GiB）；02:06:49 为 2918556 KiB（2.78 GiB）。此前约 1.9 GiB；运行负载会变，不能把差值全部当成精确释放量或长期稳定性承诺。

退出后全 NAS 14 个运行容器，其中正式书库 10 个：Web、API、普通 Worker、Beat、RapidOCR、PostgreSQL、Redis、Meilisearch、edge、Cloudflared。另四个为独立架构展示、NAS Firefox、mihomo、kspeeder，没有改变这些其他应用。

01:57—02:06 的当前负载已远低于历史故障峰值，但经历过宿主重启，不能将其改善全部归因于本轮。

## 临时模式、恢复与下一阶段

这是主动暂停闲置能力，不是已经实现自动按需启停。相关界面仍可能显示服务未就绪；不能说所有功能都正常。Beat 可能继续产生定时索引消息；恢复能力时须先看队列，勿一次启动整套历史 Compose。

需要新上传处理：只启动 ingestion-worker。需要语义检索/索引：先启动正式 discovery-inference 并确认模型准备状态，再按需要启动 discovery-query-worker、discovery-index-worker。需要 DOCX 或联网研究：分别启动 docx-preview、searxng。旧预览推理和旧方案预览保持退出。

恢复单个已核对服务的方式是 docker start <准确容器名>；当前 restart=no 会让它在 NAS 重启后保持不自动运行。确定恢复长期服务时再对该服务恢复原 unless-stopped。重新创建容器或完整 compose up 会重新使用 YAML 的 restart 策略，本轮没有把所有配置文件改成永久停用。

正式推理包含旧 E5/mMARCO 和 EG2/BGE/ConvMemory 新链，当前整个进程已退出，模型权重不驻留。不要仅凭目录名带 stl-previews 就删除权重，正式服务也挂这些目录。今后清除旧兼容模型需要核对活动索引/调用链，属于代码与模型依赖精简，不影响本轮已经释放的进程内存。

建议长期分为三类职责，但保持必要的独立进程和资源边界：

1. 页面、API、数据库、缓存、搜索索引和入口常驻。
2. 轻任务、交互查询、串行批处理采用约三组 Worker；先修路由和重复投递，再由原四组收敛。保留查询与重批处理隔离。
3. OCR 尽可能复用本机既有服务，仅对确需 OCR 的页处理，结果经原流程保存；推理、DOCX、联网研究按能力需要运行。不能给 Web 暴露 Docker socket 来实现任意启动权限。

两三个“大容器”仍会运行同样的 Python、Node、数据库和模型进程，节省不了其主体内存，并扩大重启影响。可整理成两三个部署分组，容器数不宜成为硬指标。当前 10 个常驻书库容器是临时关闭多项能力后的结果，不是完整功能只需 10 个的验证结论。

## B：验证边界

- 已核实相关两个对话及 CURRENT_PROGRESS，保留所有原有未提交/已暂存修改。
- 四个关键源码文件与运行 Worker 的 SHA256 一致：settings.py、processing.py、projection_refresh.py、system_health.py。
- PostgreSQL 查询使用 BEGIN READ ONLY 和 5 秒 statement_timeout，仅返回聚合计数/状态；Redis 只读长度和消息头统计，未输出业务消息体。
- 退出后 LAN /home 返回 200（6.508 秒），/api/ready/ 返回 200（0.048 秒）；API、edge 健康。首次探针错误使用 127.0.0.1，而实际端口只绑定 192.168.5.6，已按 inspect 的真实绑定更正。没有把首次失败或最终 200 当作全站功能验收。
- 未修复队列与源码，未验证满载稳定性、全站交互或公网浏览器，没有重新运行两份会话的构建/策展工作。
- 原始诊断工具输出有一项 Redis 启动凭据被意外带出。后续采集改为白名单，不在本报告保存值；.env/.env.nas 已确认受忽略保护。未擅自轮换凭据，轮换应另作同步客户端的维护操作。

## 官方依据

- [Docker 资源限制](https://docs.docker.com/engine/containers/resource_constraints/)：无显式限制的容器可以消耗宿主可用资源，限制需与真实工作负载匹配。
- [Celery 优化](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)：队列增长、长短任务路由与进程内存需要分别控制，增加容器或只改预取不等于解决拥堵。
- [Docker 构建建议](https://docs.docker.com/build/building/best-practices/)：使用可复现的基础、多阶段产物和职责明确的容器。运行镜像不是内存占用量。

以上通用资料用于解释设计取舍；本报告的具体数字和缺陷来自本机及 NAS 实际采样。
