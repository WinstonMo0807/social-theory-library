# Knowledge Core / Intelligence 内网候选

更新：2026-11-11。代码检查点 `cac1f5cc`，任务分支 `codex/stl-knowledge-intelligence`。本说明只描述独立内网候选；正式数据库、公网、DNS及Cloudflare Tunnel没有由本任务切换。实际执行记录见 [CURRENT_PROGRESS](../../CURRENT_PROGRESS.md)，早期方案、对比资料和逐阶段限制保留在[历史检查点](KNOWLEDGE_INTELLIGENCE_CHECKPOINTS_20261109_11.md)。

## 入口和当前完成范围

|入口|实际业务|
|---|---|
|[原文与检索](http://192.168.5.3:5174/admin/sources)|指定作品/版本/正文修订，分别查看阅读、关键词、语义、策展、发布状态；检查结构与章节上下文、脚注、实际PDF；人工跨页段落校正；原文选取、核验和陈述草稿；检验与登录读者同范围的真实检索。|
|[知识编纂](http://192.168.5.3:5174/admin/knowledge)|知识页/陈述/实体目录；正文区块与实际公开组件预览、类型资料及异名；来源依赖、反向引用、局部待更新与修订；跨页编纂提交同一ChangeSet。|
|[STL Intelligence](http://192.168.5.3:5174/admin/intelligence)|指定修订和范围的任务；八阶段及章节产物；实体区分、陈述、Wiki patch和证据集中审核；决定持久化、依赖闭合保存、预览及候选发布。|
|[模型设置](http://192.168.5.3:5174/admin/intelligence/settings)|复用原Provider配置与能力开关。用户选择自行接入OpenAI-compatible API；当前真实生成模型未启用。|

保持AdminShell、STL书页/人物符号、纸白、炭黑和砂金。编辑预览复用公开组件，窄屏证据抽屉保留编辑状态。公开 `/` 欢迎页、`/home`、作品/学者/理论/主题/学科等URL与视觉保持。

RAG负责来源检索和上下文，Wiki负责有来源的持续编纂，Intelligence负责分析产物与建议。检索本身不写正式知识。私人笔记、问答和连续研究默认不进入全馆Wiki输入。

## 正式数据与唯一业务入口

|模型|职责和迁移方式|
|---|---|
|Work、Edition、Asset、DocumentRevision|沿用书目、出版版本、文件与正文解释身份；发布资产分叉后共享不可变PDF，不覆盖原件。|
|RevisionPage、DocumentStructure、DocumentNode、DocumentNodeSegment|固定修订的原始文字、哈希、逻辑层级及有序页面区间。目录校正重映射结构；人工段落独立保护。历史无快照且当前指纹失配时拒绝重建，不用当前Page冒充旧修订。|
|EvidenceAnchor、EvidenceSegment|一个锚点含多个有序原文范围；精确文字来自不可变快照。KnowledgeLegacyMapping保留EvidenceSpan、Passage、旧检索文档等ID解析及定位缺口。|
|Entity、EntityAlias、EntityIdentifier|统一身份，外键关联Person、KnowledgeNode、Topic、Discipline、Subdiscipline等原资料。组织/事件复用OrganizationAuthority、TheoryTimelineEvent，研究对象使用约束资料表；同名不是唯一身份。|
|Assertion及Participant、Source、Evidence|陈述内容、角色、归属、来源作品/版本/章节、表达身份、条件及证据立场分开。不同作品中的使用、批评和相反解释可共存，无跨来源三元组唯一约束。|
|KnowledgePage、KnowledgeBlockDependency|知识页身份、公开投影与区块依赖。唯一编辑正文仍为EditorialRevision；复用canonical修订、发布快照和outbox。Markdown只作导出。|
|CurationRun、CurationArtifact|固定修订、范围、窗口、阶段、输入指纹、模型配置、用量、错误及恢复产物；复用Celery、task_runtime与远程租约。|
|ChangeSet、ChangeItem、ChangeReceipt|候选、审核与应用回执；候选不提前写正式实体。依赖组事务、基准版本、幂等请求和局部冲突保护人工改动。|

`knowledge_sources.py`统一来源/锚点，`knowledge_core.py`、`knowledge_workspace.py`管理知识和编纂，`intelligence.py`、`intelligence_changes.py`管理分析与变更，`retrieval/search.py`提供共同检索。DRF和MCP直接调用应用服务，权限、版本及撤回校验不只依赖transport。

- `/api/catalog/`：馆藏、责任者、资产、目录、OCR、编目和原发布业务。
- `/api/knowledge/`：Entity、Assertion、知识页、工作区、导出、历史锚点以及指定修订的manifest/page/context。
- `/api/intelligence/`：来源、run创建/状态/取消/恢复、阶段产物、ChangeSet审核/应用/预览。
- `/api/search/`：五类来源的统一查询与上下文，管理端检索检查。观点首屏/深检索、读者研究、Intelligence回查与MCP使用同一服务。

公开学者、理论/概念、主题/学科、作品、阅读路径及策划读取已发布知识投影；旧payload由serializer/投影适配。草稿不通过公开查询读取。

## Locator v1 与正文结构

顶层包含 `source_type=original_text`、work/edition/asset/document_revision/node/anchor ID、章节路径、原文、reader_url、精度及有序segments。Wiki与其他来源类型不会以原文引文样式混入结果。

每段包含1基物理PDF页 `page_number`、独立印刷标签 `printed_label`、Unicode code point起止偏移（开始包含、结束不包含）、exact/prefix/suffix、content_hash、node及有效geometry。原始文字与检索规范化文字分离；前端以Array.from转换code point与UTF-16边界。跨页必须返回多段，无可信几何时返回经核验的text_range和页面，不生成伪坐标。

历史接口读取被引用修订及其发布历史，同时检查当前访问、撤回与文件权限。目录/结构/正文修订不静默改绑历史锚点。脚注保留原页与注号，通过引用关系扩展上下文；长章节有返回范围和预算。

Docling 2.149.0仅在独立计算节点运行，明确开启标题层级，优先复用既有OCR和优质文本。实际缺失或低置信范围才重解析，人工段落不被覆盖。范围、对齐缺口和未映射标题保留；不把局部解析说成全馆结构已校准。节点部署及恢复详见[结构执行器](STRUCTURE_WORKER_20261110.md)。

## 检索、运行状态与恢复

Meilisearch继续负责原文关键词、向量、融合和发布投影；PostgreSQL为来源权威，没有新增向量库或图数据库。书目、实体和知识页的统一对象查询使用已发布投影。

关键词写入不依赖embedding/reranker。当前候选worker显式 `DISCOVERY_INDEX_KEYWORD_ONLY=true`，旧有效向量按原版本保留，新向量完成后再退役旧投影。每批最多20条跨短正文单元提交，Meilisearch确认后才推进断点；失败重放使用稳定ID。重建不先清空活动索引。

运行状态区分真实失败、等待索引、模型未就绪与零命中；未完成覆盖返回coverage_pending。源修订无可验证快照时任务为manual_intervention，停止相同输入的自动重试，管理台提供正文核对和任务入口。当前《逃避统治的艺术》保留此历史缺口；不能直接修改旧checksum或把当前文本补写成历史。

索引协调器仍每5分钟执行，消息有效期3600秒，避免排在单worker的多个切片后失效。来源归属、task_id、发布修订和内容哈希在写入/完成时复核，旧任务不能退役新任务投影。

## Intelligence 与管理员自行接入模型

固定DocETL 0.3.0、LiteLLM 1.108.3、MCP 2.3.0、Docling 2.149.0；计算依赖与API环境分开。DocETL的薄适配委托既有AIClient transport，无独立LiteLLM Proxy、额外密钥或默认外呼。

八阶段为读取、章节分析、顺序全书综合、实体匹配、Assertion候选、Wiki局部编纂、ChangeSet、审核应用。输入超预算明确失败或由上游切窗，不静默截断。实体先由STL检索形成有界候选，不走名称相同即合并的resolve捷径；全书综合按章节顺序fold，不以采样冒充覆盖。

窗口缓存包含实际正文范围/哈希、结构版本、prompt/schema、实际Provider/模型配置和依赖。成功无候选也持久化，拒绝决定保留。恢复只执行缺少或失效产物；头像/排版变化不使章节全部失效。远程CurationRun阶段复用租约、心跳、输入校验、模型回执及完成协议；取消或过期结果不能继续写回。

Provider能力为 `curation_reasoning`，配置档 `curation-reasoning-default`，复用ProviderSecret加密与馆长权限。HTTP候选不录入密钥；在可信NAS SSH终端使用同一配置服务的交互命令：

```sh
sudo docker exec -it stl-intelligence-demo-api python manage.py configure_intelligence_provider   --actor 馆长账号 --base-url https://你的服务/v1 --model 模型名称 --enable
# 仅支持JSON Object的接口加 --json-mode json_object；默认json_schema。
```

密钥由getpass隐藏输入，不写命令参数或聊天。命令只保存配置，不试用、不启动分析、不发布；之后在管理台恢复run。跨进程Provider名额复用Redis容量租约，初始重型执行名额1、DocETL并发1。真实短章、整书推理、模型用量和长章恢复仍待用户接入后实测，不能用transport夹具替代。

## 已执行迁移与旧实现处理

候选库 `stl_intelligence_demo_20261109` 已迁移至catalog0099、ingestion0022；2026-11-11再次检查无待执行migration。正式库未迁移。来源为受限目录中一致性pg_dump的独立恢复，馆藏文件只读挂载；原账号ID和私人数据保持。

49个有效身份、6条已确认历史学术关系、对应6个人工知识区块已有映射。来源回填记录3107条精确定位和17条旧偏移缺口，后续逻辑索引另持续创建锚点。当前Work57、Person22、Entity49、EntityAlias212、Assertion7、KnowledgePage9。旧行/人工决定/历史引用均保留。

```sh
# 仅在明确连接候选库、完成对应备份后执行；这些命令不是正式库切换授权。
python manage.py migrate
python manage.py backfill_knowledge_core --identities --batch-size 100
python manage.py backfill_knowledge_core --claims --batch-size 100
python manage.py backfill_knowledge_core --relations --batch-size 100
python manage.py backfill_knowledge_core --human-pages --batch-size 100
python manage.py backfill_knowledge_core --typed-profiles --batch-size 100
python manage.py backfill_knowledge_core --page-dependencies --batch-size 100
python manage.py backfill_knowledge_core --revision UUID --batch-size 100
python manage.py backfill_knowledge_core --retrieval --generation UUID --batch-size 100
# 每种回填分别处理游标；按输出next_after继续 --after UUID，每批独立事务，不调用模型。
python manage.py retire_legacy_knowledge_tasks
# 核对人工成果已迁移后才用 --apply --batch-size 100；候选已执行，勿重复当作新任务。
```

Field Assistant的书目采用、身份查询、来源和人工锁已提取到CatalogCandidateService；旧名称仅兼容。MetadataReview学术关系、旧关系编辑及Enrichment采用进入统一ChangeSet；结构化书目候选留在编目域。主题分类等合法结构关系保留。

旧claim/library_synthesis生产者、正文回调、调度和晚到远程写回已关闭。候选34926条旧AI任务已受控取消，628条其他任务保留；不清空Redis、历史表或索引。旧DerivedClaim/EvidenceSpan/Passage/SemanticChunk及关系表按人工历史/反馈/引用保留只读用途。Discovery是共同检索的现有实现，不是第二套正式知识写入。Knowledge Studio聚合、发布投影、读者研究及CurationProject/RecommendationIssue等编辑项目保留。

## MCP

官方Python SDK 2.3.0，可信本地stdio运行，11个工具覆盖馆藏、知识、五类搜索、上下文、run与产物、ChangeSet草稿。默认没有审核、发布、Provider凭据或远程计算租约工具。

```sh
python manage.py serve_knowledge_mcp --actor 既有账号
```

使用已安装计算依赖的环境。可信启动者绑定既有账户，每次操作重新检查权限；不把NAS执行权限交给不可信代理。网络MCP端口未开放。实际stdio读取、检索、创建等待配置run、重复草稿及权限校验已执行；草稿在同一管理台待审，发布前公开内容保持。

## 真实操作证据与剩余边界

- 《以利为利》修订ff54d2c0，PDF13/14跨页锚点4a423919及旧d5b0daac均可读；人工段落564字符、独立脚注1条，原文哈希保持。PDF13—16为扫描图加不可见OCR层。新结构索引626b4c17成功，298单元/1370投影。真实远程Docling PDF15—16失败后恢复，44.063秒完成、0生成模型调用。
- 真实跨页选取、区块编辑、审核、重复应用、预览及候选发布已经操作；原公开作品组件读回内容。专题、类型资料及异名流程同一审核服务，局部人工冲突和依赖闭合以隔离回归核验。演示人工草稿标为internal_demo_agent，不冒充模型结论。
- 中文/英文检索及固定版本PDF已实际核验。2026-11-11浏览器“科学技术革命”从22条增长到30条，仍提示未完整覆盖；打开PDF17/印刷7。NAS时延波动，样本含1.22秒预热服务调用、11.01秒浏览器服务计时以及55秒冷启动采样，不承诺稳定吞吐。
- 本批关键词/来源回归31项通过，新增历史快照保护1项通过，TypeScript退出0。更早的真实PostgreSQL事务、权限、局部冲突、远程恢复、唯一写入与数据回退检查见CURRENT_PROGRESS；夹具和真实馆藏证据分开记录。
- 全馆索引继续分批补齐，缺失历史来源保持明确失败；候选当前没有可用于实测的向量。真实模型未配置，因此真实整书覆盖、推理质量、模型用量与语义检索不能宣布验收完成。2026-11-09正式站502缺少对应时段日志，也未认定其根因已修复。

## 运行、隔离与回退

API为NAS18091，Web为Windows5174，正式NAS18084保持。候选API512MiB/768MiB含swap、1worker/2threads；关键词/Intelligence worker512/768、CPU0.5、solo/concurrency1、prefetch1，队列intelligence,discovery_index；Meilisearch384MiB；独立Redis。限定beat256/384、CPU0.15只运行reconcile-discovery-index。API和beat不加载Docling/DocETL。

源目录 `/volume2/library/stl-previews/intelligence-20261109`。候选容器unless-stopped；Windows前端和结构节点用现有启动脚本恢复，尚未设置开机自启。执行器HTTPS18491只绑定内网IP和计算路由，正常验证证书；与MCP知识访问权限分离。

启动命令及证书/计算节点配置见[部署说明](../DEPLOYMENT.md)与[结构执行器](STRUCTURE_WORKER_20261110.md)。原容器、环境、数据库快照和限定表备份保留在受限目录，运行产物与密钥不入Git。回退先停止新任务并保留当前产物，恢复对应旧候选代码/容器；不反向改正式库、不删除历史成果。0099已有同名组织时不能直接恢复旧唯一约束，更不能删除或合并数据强行回退。
