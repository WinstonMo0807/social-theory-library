# Knowledge Core / Intelligence 内网候选

更新至 2026-11-10。用户授权先运行内网 demo，公网、DNS、隧道及正式数据库切换仍待最终授权。这是首个真实数据闭环候选，完整六阶段尚未完成。

## 基线、隔离与入口

- 最新 main 基线 `2f151a8617b33886f046a7ccc3325d7a2deca3ae`，与审计相同。任务分支 `codex/stl-knowledge-intelligence`，已有检查点 `d52c9f94`、`e7175ee7`。原 F: 工作区的暂存和未暂存修改保持。
- Web `http://192.168.5.3:5174`，本机 Vite/Vinext 开发进程。配置文件强制 API 目标为隔离候选 `192.168.5.6:18091`，不落回正式接口。Web 进程停止后入口不可用，尚非持久发行部署。
- `/admin/intelligence` 为任务和审核入口；`/admin/intelligence/settings` 配置模型；`/admin/intelligence?changeset=5a0e2544-50bc-4635-9d2f-04c4a77d0fed` 为已保存样本；`/works/work-da2580bc` 的研究资料显示知识导读。
- NAS 正式 18084 与公网共用实例，本轮没有在那里执行 migration、索引或知识写入。其他聊天同期改变正式 API/Web 镜像，因此不能声称整个操作期间正式服务身份始终不变；本任务没有切换这些服务。
- 一致性 pg_dump 快照 210,170,684 bytes，独立恢复到 `stl_intelligence_demo_20261109`，独立数据库角色、Redis、Meilisearch和登录 Cookie。快照、环境文件及验证记录留在 NAS 受限目录 `/volume2/library/stl-previews/intelligence-20261109`，不入 Git。馆藏挂载只读。私人数据没有用作模型输入。
- 原报告的 502 未取得对应时段日志。最初最近15分钟日志未见502，不能认定原故障已修复。候选验证中确有慢请求/超时；NAS 采样交换空间约5.36GiB已用，I/O wait 23%（更早采样73%）。这只能证明资源压力，不能代替原502根因。

## 正式模型与入口

|模型/服务|职责和兼容方式|
|---|---|
|RevisionPage、DocumentStructure、DocumentNode/Segment|固定 DocumentRevision 的原始文字、哈希、结构及有序页面范围。快照前核对正文校验和，失配明确失败，不以当前同文冒充历史。现有 Page/Asset/Edition/Work 保持。|
|EvidenceAnchor、EvidenceSegment|多页原文范围；EvidenceSpan/Passage 经映射解析，复用历史标识，不删历史行。精确文字只取不可变快照。|
|Entity、EntityAlias、EntityIdentifier|统一身份并外键连接 Person、KnowledgeNode、Topic、Discipline 等现有类型资料。同名只产生候选，不自动合并。组织、事件等类型专属约束仍待补齐。|
|Assertion、Participant、Source、Evidence|陈述文本、参与角色、来源归属与证据立场分开，不使用三元组跨来源唯一约束。历史来源不足保持缺口。|
|KnowledgePage|页面身份和已发布投影；唯一编辑正文沿用 EditorialRevision。页面草稿、发布快照和 outbox 复用原系统，不建第二套 Markdown 权威。|
|CurationRun、CurationArtifact|范围、真实阶段、窗口产物、失败和模型用量；复用 task_runtime/租约与 Celery。|
|ChangeSet、ChangeItem、ChangeReceipt|候选不预写正式知识表；审核持久化、依赖组原子应用、乐观版本及幂等回执。|

核心服务位于 `catalog/services/knowledge_sources.py`、`knowledge_core.py`、`knowledge_public.py`、`intelligence.py`、`intelligence_changes.py`。DRF 和 MCP 直接调用同一服务。

- `/api/catalog/` 保留馆藏、目录、OCR、文件和既有发布。
- `/api/knowledge/` 提供身份、陈述、知识页、导出、锚点及指定修订 manifest/page/context。
- `/api/intelligence/` 提供 sources、runs、changesets、review、apply。工作台同处显示外部草稿。
- `/api/search/` 与既有 Discovery、读者研究共享 `retrieval/search.py` 的过滤、召回和 locator。`UnifiedRetrievalPipeline` 已从 SemanticSearchV2 适配改为该服务。
- 已接作品页研究资料、工作区作品启动入口、阅读器固定修订及跨页片段。学者/理论/主题/学科/策划等全部公开消费者尚未迁完。

## Locator v1

协议版本见 `knowledge_sources.LOCATOR_VERSION`。顶层包含 source_type=original_text、work_id、edition_id、asset_id、document_revision_id、anchor_id、node_id、章节路径、原文、reader_url、精度和有序 segments。

每个片段保存 PDF 物理 page_number（1基）、独立 printed_label、Unicode code point 的 start/end（前闭后开）、exact/prefix/suffix、content_hash、node_id 和可验证的 geometry。原始文本与检索规范化文本分离。没有可信几何时 precision=text_range，阅读器显示已核对文字并跳转页面，不编造高亮框。前端按 Array.from 做 code point/UTF-16 边界转换。

历史接口核对被引用修订及其发布历史，同时检查当前版本撤回和文件权限；不能用旧修订 URL 绕过登录。manifest 使用该修订对应目录，真实样本返回16个目录节点。当前快照必须先存在，缺少且校验和不符时失败。目录低置信匹配和脚注关联仍需后续结构工作。

## Intelligence 与模型接入

用户选择自行配置 OpenAI-compatible API。本轮没有启用模型、录入真实密钥或调用外部模型。

- 配置复用原 `/reading/admin/ai-runtime-profiles/`、ProviderSecret 加密及馆长权限，能力为 curation_reasoning，配置档 `curation-reasoning-default`。凭据和地址不回显。
- HTTP 候选禁止在表单录入密钥。可信 SSH 交互控制台提供同一配置服务入口，密钥由 getpass 隐藏输入，不接受管道或命令行密钥，不写环境第二份密钥。

```sh
# 在 NAS 上，仅进入本轮候选。actor 填原馆长账号。
sudo docker exec -it stl-intelligence-demo-api python manage.py configure_intelligence_provider \
  --actor 馆长账号 --base-url https://你的服务/v1 --model 模型名称 --enable
# 接口仅支持 JSON Object 时加 --json-mode json_object；默认 json_schema。
```

命令只保存配置，不测试、不启动分析、不发布；随后管理员在工作台恢复任务。省略 --enable 则保持关闭。若 endpoint/权限/配置版本无效，整份修改回滚。

DocETL 0.3.0、LiteLLM 1.108.3、MCP 2.3.0 已固定并安装于本机独立 worker 环境，Docling 2.149.0 仅固定依赖，尚未安装和真实解析。版本元数据/许可证均已核对 MIT。当前 DocETL MapOperation 使用薄 STLMapAPI 适配，直接委托现有 AIClient transport；没有 LiteLLM Proxy。DocETL 自身截断、默认 embedding、优化器、工具、gleaning、额外重试路径不进入。

章节窗口保留范围，严格入口超预算失败，不静默切字符。逐窗口分析后按来源顺序 fold 综合；实体候选先由 STL 有界检索，再结构化比较，不走 resolve 同名 blocking-key 快捷合并。失败产物和空结果可保存。缓存含正文范围/哈希、prompt/schema、实际配置与上游输入；真实长章节覆盖、中断恢复、配置变更失效仍需模型实测。八阶段代码存在不等于八阶段真实分析通过。

## 已执行的真实业务

样本《以利为利》，2012年上海三联书店版。Work `b8923e67-effb-4c84-a12c-1d0d758e05d0`，Edition `da2580bc-09e2-4306-ba0f-7be09852afc4`，Asset `d6d15d59-eba3-4a85-89eb-e31469f7ffee`，DocumentRevision `ff54d2c0-3cf2-4a3b-8057-d284a72ef412`。

|操作|实际结果与限制|
|---|---|
|Celery 执行真实范围|Run `7c285985-7d9a-4ef9-a01c-0bac064079eb` 保存259页原始快照，选PDF13–14范围70个段落节点；章节分析 waiting_configuration；0次模型调用。不是整书分析。|
|跨页引用|Anchor `d5b0daac-30f4-4478-8d2d-76bfc9e41d81` 两段，对应PDF13/14、书页9/10。逐页查看真实PDF，排除页13脚注和页14页眉；文字范围有效，未伪造坐标。原OCR仍有25o/o等误识别。|
|来源 API|已登录锚点/manifest/快照/文件访问200，匿名锚点401。此前4请求组合24.24秒；后续含检索组合84.65秒，不能当单次查询时延。|
|阅读器|用户登录后实际显示PDF13、点击第二片段显示PDF14；从作品知识“查看原文”进入PDF13。固定版本目录16项。旧加载任务 AbortError、缺PDF.js静态资源和重试权限刷新时序已处理。|
|关键词离线模型|独立样本索引14个 keyword_ready、0 vector_ready；查询“分税制”7条、“地方政府”10条，每条返回anchor。明确返回dense/reranker不可用警告。样本generation未设为全馆活动索引，不宣称整个观点检索已就绪。|
|审核、应用、发布|2项流程验证稿确认并保存；重复apply返回同一回执；候选知识发布、Markdown导出和公开读取200，12.46秒，0模型调用。访客不获得原文locator。作品页研究资料实际展示新导读和依据。|
|来源标记|导读由开发代理依据实际PDF准备，用于流程验证，区块origin=internal_demo_agent。它不是模型章节产物，也不是既有人工学术成果。保留历史修订。|
|历史关系回填|2条已确认人物关系、4条已确认作品关系迁入Assertion；原2+5条关系全部保留（1条作品关系未确认）。重复回填新增0条，2.69秒。CuratedClaim=0，故不宣称验证了真实人工正文迁移。|
|历史失配保护|《组织社会学十讲》指定修订的当前Page文本与保存校验和不符，stage1明确失败，不生成伪历史快照。没有为让demo成功放宽校验。|

知识页 `fb6891bd-b872-487f-9179-a76be0950037`；已发布陈述 `2159f8cf-1bb1-461f-b1ae-86cbc2a9a257`。一次新草稿隐藏/再发布脚本在客户端120秒超时后完成，最终发布状态已读回，但中间断言输出未保留，因此不将该次“发布前隐藏”记为独立真实验证通过；已有隔离服务契约覆盖。

## 检查、部署及恢复

- schema migration 0091、0092、0093 已在克隆库执行。命令 `python manage.py migrate`；正式库未迁移。源代码可退回本分支前检查点，候选数据库和容器独立，停止候选即可退出预览，不对正式库反向迁移。
- 回填 `python manage.py backfill_knowledge_core --revision UUID --batch-size 100 --identities --claims --relations`。批次/旧ID映射可重复执行，未跑全馆模型，未删除任何旧行。
- 10项核心/审核定向测试通过，12.18秒；加密控制台新增测试通过1.73秒。早前含完整迁移初始化的4项来源测试153.29秒。DocETL测试使用确定性transport夹具，只证明输入完整和委托次数，不冒充真实推理。Django check、makemigrations --check --dry-run、TypeScript通过。
- API为1 worker/2 threads；候选Redis64MiB、Meili192MiB；无候选beat。计算worker队列仅 intelligence，solo/concurrency=1，DocETL内部并发1，共用Provider的Redis容量租约继续生效。API/beat/OCR不加载DocETL。
- API为测试中额外Django进程临时设置768MiB，实际采样192MiB；旧轻worker采样114MiB。新计算镜像构建与MCP协议核验另记更新，不把内存上限当实际用量。
- 计算镜像先因NAS下载停滞而停止本任务的build容器；官方PyPI匹配Linux/Python3.12依赖改在本机下载后传入隔离build。193,597,440 bytes wheel包不入Git；原镜像保留。
- Web只使用候选独立cookie。正式数据库、活动Meili索引、Redis及Cloudflare配置未清空、未切换。候选源文件通过临时目录加散列比较、单文件原子替换更新。

## 尚未完成的六阶段事项

|阶段|已有可运行部分|仍须完成|
|---|---|---|
|1 Knowledge Core|快照、节点、跨页锚点、身份、陈述、知识页、迁移命令和真实样本|Docling按需解析、可靠章节/同页节/跨页段落和脚注结构、人工目录校正失效、完整类型资料与人工内容迁移|
|2 统一检索|真实消费者共享召回、locator、关键词与embedding解耦；模型离线两页样本通过|全馆关键词generation构建切换、向量后补生命周期、完整逻辑上下文替换旧相邻span、英文/扫描样本业务验证|
|3 Intelligence|八阶段服务、顺序综合、产物缓存、审核和依赖事务|真实短章Provider及长章覆盖/恢复、Docling、远程worker CurationRun完成协议；本轮模型依用户决定等待配置|
|4 管理端|启动/恢复、实体比较、陈述证据、Wiki局部diff、保存、预览发布入口，窄屏实看|集中批量决定的完整操作、桌面及更多冲突状态验证、实体关联作品资料展示补全|
|5 公开消费者及退役|作品页知识导读和原文、历史映射、6条关系迁移|其他公开对象/策划消费者、旧写入口统一、旧AI触发/beat/remote结果关闭及无消费者代码清理|
|6 MCP|官方SDK固定版本10工具注册，同一应用服务，无发布/审核/凭据/租约工具|真实stdio草稿与权限验证随后记录；远程暴露服务未启用|

旧FieldAssistant、DerivedClaim、Discovery上下文及旧正式知识写入仍保留，未隐瞒为“全部退役”。它们仍有业务消费者，不能为了demo直接删除。私人笔记、问答与连续研究不进入全馆Wiki输入。当前版本不符合全部六阶段最终完成标志。
