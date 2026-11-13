## 2026-11-14 OCR页面预取更新内网

653012a4的discovery_sources.py已更新候选并逐文件核对SHA256，回退包backup-ocr-page-prefetch-653012a4-20261114002026/source-before.tar.gz。API于2026-11-13T16:21:08.479817725Z重启，重型worker/beat仍停止，无schema变化。首次候选ready200/23.979秒，随后再次检查正式/候选均200/0.136秒才开始有限接续。宿主内存/IO full PSI avg60约26.19%/32.96%，不将探针成功解释为NAS承载已验证。公网、正式库、MCP保持。

## 2026-11-13 有界身份查询部署

- 794e50ae已推送并更新候选knowledge_core.py，回退包backup-bounded-identity-ids-794e50ae-20261113235631/source-before.tar.gz；仅API重启，worker/beat继续停止。源代码无schema变化。API启动后ready200/9.311秒，随后200/0.057秒才继续。
- 相同实际代理输入仍逐字段匹配；规训接续至14/126产物。新批次18.974秒、SQL15.172秒，候选身份查询126次6.348秒，其余查询出现冷读波动。此前同类身份查询14.007秒，但未控制负载，不能声称总体耗时已稳定改善。
- 以利单次关键词接续9→12单位，49.683秒，20个新锚点实际保存；Meili调用2.886秒、SQL合计约19.1秒、锚点10.599秒，正在进一步区分事务提交开销。仍waiting_index，旧有效投影保留，未宣布新索引已完成。
- 已请求用户恢复过期浏览器登录，仅UI核验等待；后台继续，不改公网、正式库或MCP。

## 2026-11-13 身份比较已更新候选

- 0404550d已推送，候选knowledge_core/intelligence_queries两文件哈希核对后更新，回退包backup-surname-comparison-0404550d-20261113232524/source-before.tar.gz。前端读取真实匹配依据，TypeScript退出0。无schema变化。
- API于15:25:57 UTC重启；首次ready30秒超时，前端随后200/16.470秒。检查未见本次worker超时或OOM，内存峰值255,078,400字节、CPU限额未节流；宿主内存/IO仍有压力，尚无具体阻塞调用栈。随后ready200/0.138秒，未登录me401/0.072秒，才继续有限批次。worker/beat保持停止。
- 治理76/106Wiki产物；未把当前暂时恢复等同NAS全负荷稳定或公网切换准备完成。Intelligence独立页、MCP、正式库和公网保持。

## 2026-11-13 确定性回执更新

09d07a20已更新候选intelligence.py并核对SHA256，回退包backup-resume-receipts-09d07a20-20261113224757/source-before.tar.gz；仅API重启，worker/beat仍停止。治理36个Wiki产物已保存，后续按2个产物一批、批次前后检查正式与候选ready。新窗口恢复分支尚未部署。现有SSH禁止端口转发，本轮没有改动SSH策略或发布数据库端口。公网、正式库、MCP未变更。

## 2026-11-13 部章目录修复部署

4cc5a57e的document_outline、outline_automatic、knowledge_sources三份运行文件已部署并核对哈希，仅候选API于14:00:49 UTC重启。源码回退包backup-outline-fragments-4cc5a57e-20261113220005/source-before.tar.gz；数据包backup-foucault-outline-v11-20261113/source-and-compilation-before.dump为58,670,914字节，SHA256 8fdda903a57de83cabc350b8cf47b161a4f23ccb7815f7666784df0efb2263e5，pg_restore清单224行，未实际恢复。

指定规训文献通过原服务生成16条自动目录及新结构，383快照与两份旧结构保持。无schema变化，不运行全馆重建，不复写治理当前分析采用的v4结构。重启后有一次候选/前端30秒超时，随后均200；宿主内存/IO等待仍高。worker/beat保持停止，公网、正式库、MCP不变。

## 2026-11-13 新馆藏自动维护候选更新

f6728245已更新5份API源码并核对哈希，源码回退包位于候选根目录backup-knowledge-automation-f6728245-20261113212303/source-before.tar.gz。仅候选API于13:23:55.921 UTC重启，无迁移；worker/beat保持停止。前端来自当前工作区，实际登录界面成功读取策略并显示模型未启用的等待路径，未保存策略或启动全馆任务。正式/候选/前端分别HTTP200，宿主内存和IO等待仍存在。公网、正式数据库和MCP没有变更。

## 2026-11-13 目录候选备份与关键词回执运行

b5ae5fdc已上传候选discovery_indexing.py并核对哈希，备份backup-index-receipts-b5ae5fdc-20261113193247/source-before.tar.gz，API于11:33:34.611 UTC重启。指定书目3次有限执行已确认实际迟到回执，最近47.540秒完成单元6→9并保留下一批任务。worker/beat仍停止，未运行全馆索引。

本次目录源码尚待本检查点上传。候选数据备份backup-governance-outline-b5ae5fdc-20261113/source-and-compilation-before.dump，54,669,073字节，SHA256 d3c6e31639e2b3b50a6d9991f8af5079c1bff4272fa77ab379b4e029d744c6a9；pg_restore清单224行，未实际恢复。更新仅针对未人工校准的治理自动目录，保留原修订和全文；不改正式库、公网、MCP，无schema变化。

## 2026-11-13 关键词索引持久回执

- 已据真实任务37063修复慢写入接续：发送后保存任务编号和本批来源哈希，等待时保留回执，后续先确认原任务，不重复提交已知批次；只有当前租约、来源及原文哈希一致才标记关键词就绪。等待不消耗失败重试次数，失败回执仍可诊断。
- 原有47项定向回归通过；新增3项调整测试前置索引设置后单独复跑通过，覆盖迟到成功、来源变化、旧租约及不重复发送。没有schema变更；源码尚待本检查点部署，未据测试声称NAS索引完成。
- 所有重型worker/beat保持停止，仅计划指定书目的有限接续；公网、正式库与MCP保持。

## 2026-11-13 索引分批与局部审核运行更新

b9316cf9已更新settings.py/discovery_indexing.py，备份backup-index-slice-b9316cf9-20261113191006。a97655a6已更新intelligence_changes.py/knowledge_core.py，备份backup-local-conflicts-a97655a6-20261113192028。均逐文件哈希核对，仅重启候选API，无schema变化，worker/beat停止。真实回滚应用157项成功、1人工区块受保护；未发布或保留审核确认。

20秒协作索引不限制单次服务等待。一次候选20条写入耗时119.121秒才完成，应用回执超时，旧1902条可用记录保留，新结构ready0。持久任务回执接续补丁尚在实现，不继续全馆负载，不修改正式Meilisearch数据或配置。

## 2026-11-13 索引时间片与综合编纂部署

- 候选已运行525bbcf0的intelligence.py，备份于候选根目录backup-wiki-synthesis-525bbcf0-20261113183058/source-before.tar.gz。仅重启候选API，10:31:52 UTC恢复；无schema变化，无正式库/MCP/公网变更。
- 新增DISCOVERY_INDEX_SLICE_SECONDS（默认240，最小1秒）控制单来源索引协作执行窗口。受限NAS可用20秒做单来源接续；计时包含准备，等待数据库或Meilisearch确认仍可超出预算，不是请求超时。不得先删旧有效索引；当前单元可幂等重放。
- 本段新增配置尚未上传。定向回归36项通过；候选worker/beat仍停止，只允许本轮指定样本有限批次。完整模型运行仍待管理员启用Provider，不新增隐式外呼。

## 2026-11-13 结构补丁运行与定向数据保存

68b4e231仅更新候选knowledge_sources.py、document_structure.py，两份哈希一致；API于09:52:30 UTC重启完成。源码备份位于候选根目录backup-structure-68b4e231-20261113174949/source-before.tar.gz。定向结构/编纂数据备份backup-structure-data-68b4e231-20261113/source-and-compilation-before.dump为50,276,492字节，SHA256 b94bf8e7403c0de02c68253c056a024c9cd278e2d540d5f8e2af57967d6b4e3a，pg_restore清单202行；尚未做恢复演练。

新结构及接续run通过原服务保存，原结构/历史锚点不删除。源码回退不删除新增数据；当前结构回退须精确选定保留结构并重新协调接续任务，不能直接恢复整库覆盖此后审核。无schema变更，未运行全馆索引。来源定向更新成功，关键词任务仍queued，worker/beat保持停止。最后正式ready200/0.171秒、候选200/2.856秒、5174入口200/0.252秒；宿主mem/io full PSI avg60为13.82%/18.77%，不宣称无风险。

## 2026-11-13 长书恢复补丁部署

83f7b332仅更新候选intelligence.py，逐文件哈希一致。备份backup-resume-83f7b332-20261113172532/source-before.tar.gz；候选API于09:26:16.990096243 UTC启动。正式ready200/0.161秒、候选200/0.616秒、5174入口200/0.319秒；此前一次请求超时不解释为零命中。worker/beat保持停止，mem/io full PSI avg60为9.70%/12.58%，仍有等待。无新增迁移或全馆索引重建。

## 2026-11-13 自动维护补丁运行更新

隔离候选现为f766829f相关API运行源码。仅更新source_schedule.py、discovery_indexing.py、knowledge_publication.py，哈希逐项一致；备份位于候选根目录backup-maintenance-f766829f-20261113164348/source-before.tar.gz，无新增数据库迁移。只重启候选API，08:45:23 UTC正常启动，退出码0、无OOM。候选worker/beat保持停止，未恢复后台负载或启动全馆重建。

在候选PostgreSQL上只读核验来源并集与游标窗口，以进程内小预算读取3身份，1.875秒、0写入，数据库配置/检查点保持。随后真实检索4次、34条原文固定修订核验通过，范围与局限见联动记录。正式库、公网、MCP无变更。当前开发不等待Mac，后续硬件迁移另行处理。

## 2026-11-13 大馆藏状态候选已迁移

本轮仅隔离候选更新到b054f9c2；36份API运行文件核对一致，未复制MCP文件。备份目录为候选根目录下backup-collection-b054f9c2-20261113162358，candidate-tables.dump包含DiscoverySourceState、Person、django_migrations，29812字节，SHA256 102c6cebcc787b21eb0b6a130c05945586f2a6aea7fdcd2714bd2855db998686；pg_restore --list为39行，未实际恢复。source-before.tar.gz保留被替换源码。

限定数据库stl_intelligence_demo_20261109，lock_timeout=5s、statement_timeout=50s，执行manage.py migrate，实际0091_person_citation_name、0101、0102共5.678秒。无剩余迁移。回退保留新增列和数据，源码可以退回，不直接反向删除迁移数据；正式数据库没有迁移。

refresh_retrieval_coverage的预览/应用/统计实际共31.778秒，11来源中5有效回执、6缺口；关键词完整5、向量0。仅SQL状态核验，没有Meilisearch写入。候选API重启完成于08:26:40 UTC；worker/beat仍停止，勿自动恢复。内网入口保持192.168.5.3:5174，API18091。最新宿主内存/IO full PSI avg60为14.72%/19.81%，本轮不启动全馆重建或重任务。

## 2026-11-13 联动版内网运行

e955992d已更新隔离候选API；源码备份位于候选目录`backup-rag-linkage-e955992d-20261113154829/source-before.tar.gz`。重启客户端45秒超时后实际容器已正常恢复，07:49:21 UTC启动；随后候选ready200、前端5174/admin/sources200。30份运行文件逐一哈希匹配。候选worker/beat保持停止，正式、公网、MCP未修改。新0101迁移仍待部署，不能提前运行引用新字段的候选命令。当前开发继续，Mac迁移后置。

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

## 2026-11-13 最终公网与 main 回读

本轮阅读器与加载修复已于13:59:59 +0800上线。同期检索追加读取预算后，14:11:21 +0800最终Web为viewpoint-web-r4（sha256:8810070bb92af9e6dcf0b97e5960c8b1d91fc42bc8f88fe10f8e031dfcfdf73c），以本轮reader-b-loading-r1为底层，保留本轮全部13份源码。独立回读1866个构建文件哈希一致，runtime-config由启动入口生成；五入口200、106其他容器保持。API未被本轮改写。main已推送bfb55957并核对远端相同SHA，本条为其最终回执补记。原两项暂存、共享HEAD及其他未提交内容保持。Mac架构迁移未开始。详docs/stl4/READER_B_LOADING_20261113.md。

## 2026-11-13 B 版阅读控件与等比随机加载已上线

B 版短把手、整块标题拖动、双页码同排、上方复位及账户本机位置记忆已实现；L5/L6/L7每次加载随机，首屏HTML即带动效，Logo与双线/书签使用同一SVG按容器等比缩放。定向检查、类型与构建、本机真实PDF、刷新/返回记忆和复位、1280/390px布局均通过。13:59:59 +0800发布reader-b-loading-r1，1867运行文件一致，106其他容器保持；外网首页/账户/检索200。公网阅读会话已退出，未声称本轮登录后的公网操作复测。main合并树类型检查通过，Git推送收尾中。详docs/stl4/READER_B_LOADING_20261113.md。

## 2026-11-13 brand-annotations-r1 当前公网Web

NAS回执 2026-11-13T03:57:17Z 完成Web-only更新，镜像 sha256:015d463fd71bfe4e681d66d217c88777178effa3082020968eaf330ed79b2626。API继续使用reader-unified-r3，未迁移数据库或重启任务服务。1866运行文件哈希一致，runtime-config原样保留；ready/home/admin/explore/original/account均200，106其他容器身份、配置和启动时间不变。

发布目录/volume2/library/stl-releases/20261113-brand-annotations-r1；活动compose-command追加web.compose.json。恢复脚本recovery/rollback-web.py只切回先前Web，带活动版本保护，不回灌数据库。沿用reader-unified-r1已完整读验的252637363字节数据库备份并重新核对SHA256。详stl4/BRAND_LOADING_ANNOTATIONS_20261113.md。

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
