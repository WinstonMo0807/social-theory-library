# NAS 资源修复与策展 OCR 交接

本记录接续 `NAS_RESOURCE_AUDIT_20261108.md`，覆盖其“尚未修复”和“需手工恢复服务”的旧状态。用户明确授权修复重复投递、积压、资源调度并部署公网；最新要求是本对话停止本机 OCR，由书库策展对话接续。没有修改前端视觉或发布 readable-r9。

## 修复范围与运行方式

- OCR pending 恢复先读取 Redis 队列和 unacked 中的 task ID。已有投递不重复入队；读不到 broker 时保守等待。未更改业务任务的幂等和权限规则。
- 高频恢复、心跳、巡检设置短于下一周期的过期时间，防止过时巡检排长队。巡检批次在完成探测之间按 8 秒预算让出；已不存在对象的投影保留失败历史，不再阻塞其他对象。
- OCR 改走 ingestion 队列。ingestion 与 discovery_index 共用 concurrency=1、prefetch=1 的处理 Worker；读者查询保留独立按需 Worker。旧 index Worker 不再常驻。
- NAS 上 root 管理的 `stl-on-demand.service` 仅管理固定容器名单。队列和 unacked 保护工作中的 Worker；模型、DOCX、SearXNG、NAS OCR 按实际请求唤起并在闲置后退出。应用容器不取得 Docker 权限。只发送 TERM，绝不定时强杀活动任务。
- 本批策展临时使用 `192.168.5.3:18091`，仅显式 job/upload 白名单适用；已有管理员绑定优先。电脑失联保留页级检查点等待重试，不偷偷转回 NAS 批量 OCR。其他文件仍使用原服务配置。
- 两份超长中文题名原先超过 Linux 文件名的字节上限。磁盘文件名现用既有 Asset UUID，完整书名继续保存在 original_filename；原文件和字节内容保留。
- 1800 页《经济与社会》的原生提取触发过处理容器 768 MiB 内存限制。逐页 store_shrink 不足以释放文档资源；现每 32 页关闭并重新打开同一 PDF，保留纯文本和坐标结果。没有加大处理容器内存上限。
- 后续自动目录识别也实际触发过普通 Worker 的 512 MiB 限制。相同的文档资源生命周期修复已用于 `document_outline.extract_outline`；目录识别/派生 PDF 任务转入同一单并发 ingestion 队列，避免与 OCR/导入重处理叠加。

PyMuPDF 官方说明支持分段关闭文件来释放大文档资源，见 [大文件与内存处理](https://pymupdf.readthedocs.io/en/latest/faq/index.html)。本次是否有效以实际文件复测为准。

## 镜像与部署

API、普通 Worker、Beat、ingestion/query/index 三个处理角色共用一个 API 镜像；数据库、缓存、搜索、前端仍按原有职责保留。镜像数量不等于运行内存，不为减少列表数字混合数据库和应用生命周期。

本机使用 `scripts/pack_runtime_image.py` 从未启动、未挂业务卷的干净旧镜像导出包制作单层运行镜像。r3 替换已核对基线的 13 个后端文件，r4 为 14 个。NAS 只接收并 docker load，不做 Docker build。后续发布继续在本机打包；不要重新执行旧 r9 NAS 叠层构建脚本。

- r2 已部署，SHA `c782e3a9a2555ed6520daaeec01bb423757fe361d9b3f7568c23e4092da1bac8`。
- r3 加入大文件内存修复，镜像 `social-theory-library-api:4.0.0-20261108-resource-r3`，SHA `cbad02913804d5403353fb54a1c1f410c781dc959f8694efcba1a0a7b9f4ea60`，单层、528522046 字节。归档 SHA `c282fbcf0c3da12408b2c838ca3ead90e7c897d5525c0933e67d20b99c3f5a46`。
- r4 补齐目录内存修复及重任务路由，镜像 `social-theory-library-api:4.0.0-20261108-resource-r4`，SHA `2270f190400af0378e99a0a9ac79386e97aae928ba94b72fc233c964572354bc`，单层、528522542 字节。归档 SHA `c9f5a7f721b19381b6d2bdbdcb424ae757e13706686b2422e259297d4f9d5878`。最终运行版本以本文件末尾实测为准。
- 活动完整 Compose 入口仍为 `/volume2/library/stl-releases/20261107-r1/public/compose-command.json`。资源配置位于 `/volume2/library/stl-releases/20261108-resource-r1/resource.compose.json`，r3 镜像覆盖层为同目录 `resource-r3.compose.json`。
- 部署只更新上述 6 个角色并平滑 reload edge。Web、PostgreSQL、Redis、Meilisearch、edge、Cloudflared 的容器身份和启动时间均需保持，部署脚本有前后断言。
- 本次无 schema 迁移、索引重建、原件清理、DNS/隧道变更。闲置旧预览和旧推理副本继续退出。不要完整 compose up 全部服务。

## 已上传文件的实际核对

策展清单为 58 份 PDF、57 部作品，不能与后台含历史重复的 61 条上传记录混为同一口径。最初仅 56/58 个原件哈希匹配正式存储；修复两份超长文件名失败后，已 58/58 匹配，无需重新上传。

《甜与权力》《社会运行论及其发展》通过原管理员重试接口恢复；三条 OCR 失败任务沿既有页级检查点恢复；《社会运行导论》《成为三文鱼》的中断解析已恢复。《经济与社会》的最后一次解析和最终统计见本文件末尾运行验收记录。

不是所有文件或所有页面都需 OCR。例如《国家的视角》436 页、《科学革命的结构》253 页可直接利用文字层；《经济与社会》1800 页，本机文字提取复测判定 6 页、NAS 真实入库最终登记 7 页，接续须以后台实际页级目标为准。已有逐页目标和处理结果必须保留，不强制全书 OCR。策展工作区已有 1172 页本地阅读 OCR 不等于已经回写网站。

## 真实观测与验证

| 时间/条件（北京时间 2026-11-08） | MemAvailable | 1/5/15 分钟负载 | 说明 |
| --- | ---: | --- | --- |
| 原事故记录 11-07 23:40 | 约 193 MiB | 42.40/37.95/33.28 | 原记录含构建和系统压力，不能当同工况压测 |
| 02:51，本机 OCR 在工作 | 2.31 GiB | 1.61/1.35/1.32 | NAS OCR 处于退出宽限期 |
| 02:54，本机 OCR 与上传恢复在工作 | 2.99 GiB | 1.36/1.28/1.29 | NAS OCR 已自动退出 |
| 03:02，按用户要求暂停 OCR 后 | 3.30 GiB | 0.70/1.00/1.22 | 内存 PSI avg10=0；不能将暂停后的低负载当满负荷数据 |

队列整理时 1630 条降至 192 条，删除 696 条相同投递和 742 条被更新周期消息取代的旧巡检。独立业务消息、未知消息与 unacked 保留；写入前完整备份并 WATCH 校验。运行期间 OCR 队列曾连续观察到 44/44、46/46 条投递/唯一 ID，未再次出现同 ID 大量堆积。用户暂停后 OCR 排队消息为 0。

DOCX 按需启动经真实 UNIX socket `/health` 验证，约 5.26 秒就绪，清理该次探测需求后自动退出。推理、查询与联网研究共享受测调度规则，但本轮未执行模型基准或完整研究任务。

《经济与社会》本机原生提取：修复前峰值 1788.9 MiB，修复后 201.2 MiB；1800 页、1671979 字符、15035 文本块、6 个 OCR 目标页均一致。全部 ExtractedPage 字段序列的 SHA256 同为 `3c01bf0b1ac688b45bf7c6f9919acfaef81f31d0320cac339220138a0d1efaee`。这项测量未启动 OCR。Linux 真实入库结果另记，不能用本机峰值代替 NAS 峰值。

定向回归 51 项通过；最后工具/路由子集 13 项通过；新增文档分段复核与相关恢复测试 10 项通过。r3 隔离 Linux 镜像 `manage.py check` 通过。扩大检查有 2 项旧选择性 OCR 预期失败，在干净已发布源码上同样复现；另 5 项 DOCX converter 检查受 Windows 缺少 ThreadingUnixStreamServer 限制。本次没有删除断言或宣称这些检查通过，也没有运行完整视觉/E2E 验收。

目录追加验证：32 项运行中 26 项通过、6 项旧预期失败；将同一旧目录测试放在干净已发布源码上运行，18 项中完全相同的 6 项失败（主要是旧访客权限和旧目录自动生效约定）。新增重任务路由检查通过，r4 Linux 隔离 check 通过。命令分别为 `python -m pytest tests/test_automatic_outline_20261106.py tests/test_document_outline_20261013.py tests/test_nas_queue_recovery_20261108.py -q -p no:cacheprovider`，以及在 `tmp/nas-optimize-20261108/baseline-api` 对 `test_document_outline_20261013.py` 运行同一检查；失败未被隐藏。

同一 1800 页 PDF 的目录原生阶段（空数据库查询夹具，仅比较 PDF 读取和原生候选）峰值 584.9→191.1 MiB，671 个节点及诊断 SHA 同为 `c64b3d0d493de660e3453d1a86011cde9945e56c19f07a64688760c42bea69dd`。时间 7.31→64.41 秒，是释放缓存换取低峰值的实际代价；生产完整目录处理还包含数据库观察和自动匹配，不能把这项夹具结果当完整目录验收。

## OCR 暂停与接续

用户要求移交后，使用既有管理员暂停入口设置 OCR 全局暂停，等待在途页面存盘、全部任务停止，再仅关闭本轮拥有的本机 Python 进程。没有强杀正在识别的页。端口 18091 当前应无监听，NAS OCR 服务闲置退出。

接续脚本与完整步骤见 `CURATION_OCR_HANDOFF_20261108.md`。当前网站保留真实“暂停/待处理”状态，后续结果须经原 OCR 管道回写派生数据后才显示完成；不增加“本机 OCR”前端功能，不直接伪造完成标志。

## 回退与证据

恢复目录 `/volume2/library/stl-releases/20261108-resource-r1/recovery` 保存原 Compose、环境、容器配置和镜像引用，均仅 NAS root 可读。数据库包 55959253 字节、SHA `8040f75be391ec2b552fce8969241ed911bf3650764c993b1daf251725a14e66` 已成功恢复到独立数据库 `stl_resource_verify_20261108`，144 个 Asset、372 个处理任务、61 条上传记录回读成功。该验证库没有覆盖正式库。

r3 前新增 `recovery-r3` 保存 r2 Compose、6 角色配置和 60083121 字节数据库包（SHA `aedb52cf6c21a1e48aafe0ac78f283005f6dc34837d6422cd84fb65513a57cbd`），pg_restore 目录检查通过。r3 包未再次完整恢复，前一包的完整恢复证据不能冒充此包的完整恢复。

r4 前新增 `recovery-r4` 保存 r3 Compose、6 角色配置和 71899854 字节数据库包（SHA `48c54b9d04a7c4a6c73525bb87670a620d625fe16d9c18e08fe90c1ce4354ede`），pg_restore 目录检查通过。回退 r4 使用此目录的 Compose，只回退角色代码，不覆盖当前数据。

队列备份在 `/volume2/library/stl4/storage/backups/nas-resource-20261108/celery-before-f77f217436684f77b113b5c9c0b3bfec.json`，SHA `bef46be4294e255c87cbff0c4016e326df57bc3308e3034db9b5e8538eb0e677`。当前队列已有新任务，不整包回灌旧消息。

回退先停按需管理器，温和排空相关 Worker，再按 `recovery-r3/compose-command.json` 只回退代码角色到 r2，恢复入口和平滑 reload edge，随后恢复管理器。需回到最初资源设计则使用 `recovery/compose-command.json` 并单独核对服务启动范围。任何回退均不把旧数据库覆盖现有策展数据，不执行 down -v。

运行证据均在未提交目录 `tmp/nas-optimize-20261108/`，包括 deploy、deploy-r3、observations、uploaded-actual、native-baseline-digest、native-bounded、tests-final、tests-final-r2、tests-native-r3 等记录。运行归档、PDF、模型、数据与凭据不提交。

## 最后运行验收

《经济与社会》实际上传任务在 NAS 用 r3 成功结束，用时 168.37 秒；处理容器 cgroup memory.peak 552640512 字节（约 527 MiB），该容器 oom/oom_kill=0。61 条后台 UploadItem 全部 ready，58/58 原件哈希匹配。按这 58 份文件汇总：48 个 OCR 暂停、8 个 OCR 成功、2 个不需要 OCR 的文件没有 OCR 任务；暂停任务实际剩余 14590 页，均有显式逐页目标。不得把它写为 58 本 OCR 全部完成。

原生解析后目录任务出现的单独 OOM 已定位并由 r4 修复。03:33:59 实际回读目录任务 succeeded、progress=100、95 个节点，当前目录的独立 PDF 导出任务 succeeded。处理 Worker cgroup 峰值 547426304 字节（约522 MiB）、普通 Worker 峰值301768704字节（约288 MiB），两者 memory.events 的 oom/oom_kill 均为0。原件、现有正文和笔记没有覆盖；自动目录不冒充人工审核。

r4 六角色已实际部署，14 个运行文件哈希与发布清单一致；公网 HTTPS `/api/ready/`、`/home` 最终回读均200。Web/数据库/缓存/搜索/edge/隧道容器身份及启动时间前后断言通过。本机 OCR 继续关闭、全局暂停保持。03:33 同时有按实际需求启动的正式推理服务和目录处理时，MemAvailable 2499604 KiB（2.38 GiB）、load 2.19/3.01/2.43；服务闲置按既定宽限期退出，不把此值写成所有服务已退出后的结果。
