# 2026-10-27 内网候选收尾验证

当前工作继续至公网切换前。只有本记录明确列出的运行行为经过验证，不能将其推广为206视图全部验收。生产未更改。

## 06:47 索引运行中断与恢复

DEEP-RUN-01：原补写PID26在453条后退出137，现有接续器自动按input_hash跳过453条后继续；实际读回890/2404。API容器cgroup记录oom=2/oom_kill=2，容器未重启；当前主进程、请求进程、补写进程RSS约76/187/186MiB，共享512MiB。该限额下额外完整Django诊断进程会再占用同一预算，后续常规统计改为stdlib只读探针。未获得各次OOM精确时刻，不推断每次受害进程或宣称全部根因已证明。

本轮最小处置仅将运行中的预览API热调到768MiB/禁Swap，前后容器ID、主PID、启动时间相同，未重启/重复补写，应用源码及Compose均未修改。恢复参数NAS deep-backfill-memory-recovery/limits.json；补写退出后恢复512MiB。最后读回memory.current=435355648、上限805306368、OOM计数仍2。历史失败保留，生产不变；D关闭本次资源处置，持续运行及完整覆盖仍B。证据tmp/stl4-rapidocr-20261027/deep-heartbeat-0640.log、deep-memory-adjustment.log、deep-heartbeat-0650.log。

## 已确认并修复

- PAGE-LABEL-01：`ingestion/services/extract._explicit_page_labels`把扫描器默认PDF 1…N视为可靠印刷标签。样书Reader在PDF34显示印刷34，而原目录/正文应为21。仅排除默认单段连续物理编号，明确分段/罗马标签保留；人工页码映射优先。12项聚焦检查通过，包括映射历史与发布契约。
- OUTLINE-PREVIEW-01：`DocumentOutlineWorkspace`首选目录节点PDF14但原稿预览保持PDF1。根据当前节点ID和物理页同步预览；手动翻页仍保留。Web类型与构建通过。
- PRIVACY-EDIT-01：`parallel_reading.update_task`额外要求新笔记保存开关，违反现有隐私界面和PRIVACY_OPERATIONS明确的“已有内容仍可编辑”。只移除已有任务编辑的该条件；新建、本人归属、事务锁、版本和回执校验保留。两份早期测试对此互相冲突，按现有产品规则修正旧断言。
- PRIVACY-INPUT-01：`PrivacyRequestStopInput.to_internal_value`在多余owner字段时抛字符串错误，DRF封装errors时ValueError，实际返回500。改为标准non_field_errors，仍拒绝多余字段及他人归属，接口回归返回400。
- PUBLICATION-DISCOVERY-01：实际校准发布事件115d819c在rag/semantic消费者重试8次后dead_letter。读者检索与LibraryRetrievalService已消费Discovery，但`projection_refresh._semantic_projection`仍启动旧SemanticIndexJob，因无旧active SemanticIndexVersion失败。启用Discovery时沿同一任务账本验证当前公开文件、CatalogRevision、source_revision、generation及完整写入记录；等待现有索引调度完成，失败仍保留，未启用Discovery的旧路径保持。延迟完成复用原投影租约和版本检查，不新建索引架构或隐藏失败。
- OUTLINE-EXPORT-MAPPING-01：当前5bc8a288的10项人工目录来源是page_mapping，指纹、正文、reviewed均正确，管理端正常点击导出仍被outline_exports.export_revision的来源枚举拒绝。补合法page_mapping分支，保留人工确认、当前指纹、正文版本和所有节点校验；无需修改历史数据。
- OUTLINE-EXPORT-POSITION-01：已有旋转/裁切合成回归四项均实际失败，PyMuPDF1.26的set_toc坐标转换丢失裁切偏移。只在独立副本中将显示落点反旋转、加CropBox偏移并转换到PDF坐标，使用公共xref_set_key写入GoTo目标；保留全部标题、层级、页数及精确落点读回检查。18项导出/页码回归最终通过，初次失败日志保留。

## 本轮真实样书

《社会学方法的准则》170页，整书cd28e58a成功；目录页7–13定向d23d9390成功。前6页保留旧OCR来源，其余新引擎；另两书未OCR。期间预览PostgreSQL256MiB出现一次OOM，已保存117页；上限调512MiB后沿同一任务恢复至170。不是零中断，也不等同逐字准确率。

v8真实目录任务e5cfece5生成10项。逐项查看原PDF章节起页，人工补引言34，实际管理端保存、采用、书签导出成功。导出资产95d9f651的170页PDF实际读回10书签，落点14/18/34/36/48/79/106/119/151/165。原始资产SHA仍dd72348c885b6f80843891dfe4064071e98c5e5fe5e3431d3b07cd729080eccc。

页码修订49012719（候选2）经过原界面影响预览并采用，0补页，五段：1–3无编号、4–5为1–2、6无编号、7–13为1–7、14–170为1–157。实际原件页眉逐页核对；章节起页数字省略时依据印刷目录和相邻页，不伪称OCR自动确认。新阅读资产5bc8a288、正式快照e0ec49b2，沿用10个已采用目录；Reader实际PDF34显示印刷21。公开阅读已切换，派生消费者此前失败，需以修复后事件状态另记。

管理OCR服务检查按钮成功保存新回执，历史失败未删除。批注台已验证原PDF读取、画线/文字/视口保存和刷新回读。样书内容及原文不提交Git。

## 验证与运行边界

- `precutover-contracts-final-r2.log`：108项读者计划、确认笔记、本人隐私、并读、私人引文及备份回归退出0。初轮失败与修复依据保留。备份测试模拟入口改到已有capture_backup_snapshot，未削弱原件缺失、归档失败和幂等断言。
- `discovery-publication-contracts.log`：16项通过，包括新增7项准确修订/旧来源拒绝/延迟完成/真实失败保留和原9项投影流程。
- `page-label-regression-final.log`：12项通过。`outline-v8-final.log`：26项通过，含实书170页隔离重放。不是检索质量评测。
- Web类型、构建退出0；实际r80策划页读取新品牌和副标题/描述字号。只读PDF73及当前截图，实际内容数量保持1，未填造PDF示例数据或人物肖像。
- API49 d695df3c1ff3/Web80 958185f55582已更新内网；API50 e60e7518c1c0准备应用发布消费者修复。更新仅空闲服务，索引worker仍有任务保留旧镜像；beat在finally恢复。最终版本/重试/恢复演练结果继续补充。

## 05:25 已读回与仍需完成

- API50已部署，Web80保持；原事件已沿现有重试入口恢复，Discovery原作业5371683a继续当前准确source_revision，149个单元、物理页112。rag/semantic仍等待，不冒充完成。API51目录导出修复镜像20d2c9551c97已构建，部署中。
- r80目录初选原稿实际显示PDF14，截图outline-preview-r80.png。当前阅读PDF34显示印刷21。
- 候选备份candidate-after-r80.dump共15,722,229字节，SHA256 4e8f321ecb672a7fd483585bc27e86f85c24f99ddcf1d100c6a9aafa86859c0f。已恢复到独立stl4_verify_20261027_r80数据库，4账号身份/密码哈希/权限摘要与更新前一致；182迁移、3作品、3版本、12资产读回。旧库及生产不变。证据restore-verification.log；不是生产恢复演练。
- DOCX第一次探针误在不挂载socket的API执行，不作为服务故障。实际worker随后返回conversion_timeout，NAS内存PSI some约67%。确认无活动OCR作业后暂时停止空闲RapidOCR，再经同一worker/socket转换两页合成DOCX：14.96秒、两页正文正确、源指纹未变、LibreOffice7.4.7.2；finally已重启RapidOCR。证据docx-isolated-runtime.log。这证明转换链可用，不能单独证明全部超时根因或双栈高负载稳定。
- 原OCR实例曾有OOM=1/kill=1记录，时间未定位；重启前health/ready均200且模型实际验证通过。原PG OOM及恢复过程也保留。不得用重启后清零计数宣称无中断。

05:28:25：API51（20d2c9551c97）更新后原UI提交任务2a186965成功，生成8d4b32db副本。实际打开170页并读回10个正确书签，原件SHA未变（mapped-export-readback.log）。API/普通/入库/查询worker r51、Web80保持，索引worker忙保留r45；beat恢复。首次更新因健康任务忙未改环境，第二次沿同一恢复点核对后更新空闲服务。

05:43最终读回：原5371683a成功230单元/385派生文档，115d819c六个消费者全部completed。EG2/BGE/ConvMemory合成运行成功，deep/status ready；独立索引初始化config_snapshot遗漏修复后API/四worker r52（41f9a5647a89），7项契约通过。2404条公开passages正在原命令中补写，50条261.4秒，总开关false等待完整索引。已安排同线程30分钟自动接续及NAS脱离会话接续器，详情CURRENT_PROGRESS。

OCR重启后冷态/ready503如实返回；原管理界面验证模型后实际health/ready均200，runtime_verified=true、workerPID208。服务页05:43新检查回执成功，设置重新读取显示最近处理成功03:54:29；旧开着的页面未刷新并非接口漏记录，没有据此改代码。证据ocr-restored-ready-verified.log、ocr-restored-service-r52.png。

公网批准仍待用户最终确认。其余206视图的B验收不改记为开发缺项，字体文件身份及全站逐像素一致尚未证明。模型质量和全NAS长期稳定性未由上述检查证明。
