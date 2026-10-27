# 2026-10-27 内网候选收尾验证

## 2026-10-27 12:45 切换材料接续点

Web85源码检查点4be4c9f2。公网五层Compose仅只读解析完成（config退出0），未启动服务或改生产；解析输入为生产插值默认与候选镜像/模型，不是最终发布env，worker仍带18084 URL、部分已验证资源限制仅在预览覆盖中，需在既有发布配置材料中明确收口。详CUTOVER_CANDIDATE顶部与public-candidate-config-r5.log，不将工具初轮解析错误登记为新产品故障。用户登录和批注台已恢复，现有1条验证批注保持；390px iframe集合目录空态实看，218–222详情仍B。下一步仅准备既有发布环境/资源差异和新鲜数据恢复安排，不重做已关闭视觉、OCR或深度查询。


## 2026-10-27 12:40 集合与研究回放组

Web85 4b764481c1f7/API53/RapidOCR3，生产保持。BOOKLIST-TAB-01和VISUAL-77具体源码修正关闭D，类型/编译/内网部署退出0。PDF218–222逐张读图；当前本人0书单、全部范围0研究会话，实际空态有证据，有数据详情/手机底栏/业务操作仍B。没有创建私人资料。恢复点collections-r85-recovery（前Web84），详情VISUAL_FIDELITY最新项。后续沿原公网配置与统一验收范围，不重跑索引/OCR/质量评测。

## 10:20 原始笔记选择恢复与读者空态

Web84 19e67126a76e实际打开“从笔记选择”已从page UUID错误恢复到真实空态。MemoryProposal仅修请求分页p，AnnotationViewSet与账户归属未变。PDF205–207/216–217桌面/手机空态与筛选实际读回；206有数据详情/确认/授权及笔记编辑导出仍B，不创建私人数据代替验收。VISUAL-76具体密度/计数修正D，原VISUAL-59/61已完成项从五行陈旧缺口描述中纠正。

类型、构建及仅Web部署退出0，无全量测试/私人写入。非Web容器身份一致，生产未动。证据与恢复见VISUAL_FIDELITY的76及reader-r84-recovery；前次09:09候选DB包保留，不重复声明新恢复证明。

## 09:50 隐私三视图与切换配置读回

VISUAL-75具体差异已修复并运行Web83 8efb3bf8409a；API/四worker r53、RapidOCR3不变，非Web容器ID一致。实际桌面/390px读取PDF223–225对应设置、导出空态及无任务状态；手机概览与分类已显示，未执行私人导出/删除/设置写入。类型/构建退出0；截图和精确范围见VISUAL_FIDELITY最新项。全状态、字体身份及206视图像素验收仍B。

公网配置只读比较发现PUBLIC-CONFIG-01：生产EMAIL_PROVIDER=brevo且容器与源.env均无BREVO_API_KEY；新版邮件入口mail_available明确因此不可用。预览用locmem且DEBUG=false，实际只读登录契约email_delivery_available=false，符合不外发隔离。未发送邮件/取得邮件成功回执，不将缺配置写成新源码缺陷。公网前须补受限环境凭据，详CUTOVER_CANDIDATE最新配置表。生产配置、域名与隧道未改。

当前工作继续至公网切换前。只有本记录明确列出的运行行为经过验证，不能将其推广为206视图全部验收。生产未更改。

## 09:10 深度链真实完成与新候选备份

原会话362d1468第二轮通过正常HTTP retry接续，EG2/BGE/邻文/ConvMemory及QueryLexicon全部completed，ranking_applied=true，40条深度结果全部对应当前校准资产5bc8a288及有效文档修订、PDF页和reader_url，source_changed=false。整体status仍partial，唯一提示passage_facets来自明确的work_ids范围，不是本次深度失败。未放宽归属/来源核验或改业务状态。原基础任务59.694秒；深度任务243.521秒，BGE约220秒、ConvMemory约13秒。DEEP-RUN-02关闭D，真实查询运行通过；模型质量、负载容量及长期稳定仍B。

证据tmp/stl4-rapidocr-20261027/deep-live-query-r2.log、deep-live-query-readback.json、deep-query-worker-r53.log，原失败deep-live-query-attempt1.json保留。API/四worker r53（3f81aeeaec33）、Web80/RapidOCR3，API512MiB、总开关true、beat已恢复。未进行新的质量测评。

新候选备份deep-timeout-r53-recovery/candidate-after-deep-r53.dump于09:09:46生成，16,007,416字节，SHA256 82c782c47d97027288f13d12ce7cb00acd9ba5c5ab284a17d2d9593aac361c8e。pg_restore --list退出0；当前182迁移/3作品/3版本/13资产/4账号，账号摘要与原基线一致。本包只核对归档目录，未重新恢复；之前r80备份已单独恢复验证，不混称同一包。证据deep-candidate-backup.log。生产未变。

## 09:02 真实深度查询的等待预算修正

DEEP-RUN-02（A，运行复核中）：正常样书查询362d1468第一轮基础原文141条、EG2稀疏/向量各40条、邻文读取成功。query worker在08:54:52开始BGE，08:55:22客户端30秒后ValueError降级；08:55:25 ConvMemory返回429，inference仍占用串行模型槽。首轮结果和状态保存在deep-live-query-attempt1.json及deep-live-query.log。后续deep/status显示BGE inference_completed=false，但没有服务错误正文，不能仅由该状态确定原服务端失败原因。

最小范围为config.settings的BGE/ConvMemory HTTP预算与上限（250秒）、.env.example相应值、compose.stl4-deep现有INFERENCE_REQUEST_SECONDS上限240秒；原600秒任务、模型制品、输入截断、20/10候选数和串行CPU不变。r53 3f81aeeaec33已更新API/四worker，原Inference镜像仅重读配置，恢复点deep-timeout-r53-recovery。原正常retry接口进入generation2，尚待结果，不把部署成功记成问题已解决。

本次work_ids限定原文，基础entities/curation按既有passage_facets返回提示，可能使总会话为partial；验收必须分别记录真实总状态与deep状态，不能修改业务代码强行改绿。

## 08:53 完整深度投影与启用

2404条独立投影全部完成，接续段按原hash跳过453条、新写1951条。只读逐条核对当前原文资格和准确文字片段、source_revision、scope_token、input_hash、768维向量有限性与L2归一化，2404条全部通过；既定三模型制品/代次一致。当前三版本原文分别1300/719/385条，样书仍指向e0ec49b2/5bc8a288。证据deep-enable-runtime-r3.log。首次探针没有显式分页limit导致取回数量不足，修正探针后通过，非索引数据缺失；原失败日志保留。

仅内网启用总开关，API/四worker仍r52、Web80保持，API临时768MiB已恢复512MiB。首次部署因已有worker任务未修改环境，等待空闲后成功；beat恢复。deep-enable-r52-recovery保留.env、镜像、补写和OOM历史，未改模型、原件、生产或基础索引。实际匿名查询362d1468在途；其成功/降级状态另记，当前不宣称实际深度检索验证完成。

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
