# Social Theory Library 3.0.5 当前进度

最近核对时间为 2026-09-10，香港时间。

## 3.0.5 当前动作

2026-09-10 18:11 核对。Reader 切片已本地提交 0a43ac5。OCR 分批、暂停恢复、选择性识别和文档智能回归已收口，四文件合计28 passed，退出0，49.22秒。移除不再存在的同步索引 mock，改为检查实际 DocumentRevision、未发布版本不产生正式发布事件、人工页码与原件字节保留。这部分只改测试，未修改 OCR 实现，以独立本地提交保存。

首组22项通过后，文档智能用例补上指定 OCR 文档修订的实际活动快照。合并复核确认激活前命题不可见，旧 stale/superseded 命题仍不可见。没有恢复旧同步写入口，也没有改动真正的证据公开资格或质量门槛。

2026-09-10 18:05 核对。Reader 页码/正文状态切片已收口，扩大回归 70 passed，退出 0，148.07 秒。可读 PDF 在正式全文未就绪时仍提供页码和尺寸，书签与私人笔记可保存，未激活文字/章节/文本块不返回。访问接口不再仅凭 OCR 任务成功报告文字可用。文件权限、文内搜索和 PDF 下载选择规则保持原样。

封面选择、必填字段与发布故障测试已按真实编辑修订和持久事件检查。首次发布处理失败不提前公开，撤回先停止公开再等待外部清理，失败/重试记录与原文件保留。Django check、migration drift、verified API 漂移和 diff 检查均退出 0。本切片以独立本地提交保存，没有推送、生产连接或部署。

下一项从 `test_claim_curation_v300.py`、`test_claim_pipeline_viewpoint_v300.py`、`test_field_enrichment.py` 和 `test_task2a_query_lexicon_search.py` 的已记录失败继续，逐项检查人工作者、活动全文修订、别名候选与持久事件，不默认全部是旧测试。最新完整后端仍为 checkpoint3 的1063通过/38失败/32跳过，不据专项成绩推算全量。Person 合并、其他实体媒体、完整 API/Reader/界面/legacy 收敛、真实 PostgreSQL/索引/Provider 和生产恢复验收仍未完成。未推送、连接或部署生产。

### 本轮及此前过程记录

以下保留各次运行及当时动作，以本页顶部为最新状态。

2026-09-10 接续 Reader 与文件发布测试，上一轮 20 passed、4 failed，退出 1。页码新测试先红为 3 failed、2 passed，退出 1，41.29 秒。其中两项复现 metadata-only PDF 页码被全文门槛拒绝，另一项是测试重复建立活动修订，已修正夹具。页码接口开始区分可用页码元数据与正式全文，仍要求本版本活动修订及原文件访问权限，未就绪文字和文本块不返回。正在验证，尚未提交，不连接生产。

页码修复专项已验证 11 passed，退出 0，41.62 秒，包含实际 PDF 第 73 页对应印刷页 50 的旧回归。私有/受限文件、非活动文件、无修订/外版本指针均拒绝；正文与文内搜索门槛未放宽。当前继续封面手工选择的编辑修订和发布/撤回失败事件测试，尚未收口。

随后完整 Reader/文件发布组 34 passed，退出 0，45.62 秒。封面按真实维护发布 HTTP 与消费者确认验证；发布失败保留未完成事件，撤回不等外部清理。继续核对发现 access.ocr_text_available 仍仅看 OCR 任务成功，会在正文未激活时报告可用；正在补该一致性测试及无 OCR 私人书签/笔记端到端 API 用例。

访问状态不一致已以 1 failed、2 passed 复现，退出 1，43.15 秒；私人书签/笔记保存及其他账号拒绝通过。已将 ocr_text_available 加上同一正式正文条件，保留真实 OCR 任务状态，原文件选择和下载规则未变。正在扩大 Reader、范围检索、公开修订及完整入库回归。

最新核对为 2026-09-10 17:30。应用代码提交 4120c66。全后端 checkpoint3 报告于 10:55:52 完成，1133 tests、1063 passed、38 failed、32 skipped、0 errors，583.194 秒。续接后进程句柄失效，退出码未知。当前继续投影事件、公开 Reader 和 OCR 旧测试入口，不重跑最初审计；仍禁止生产发布。

checkpoint3 后第一组投影/语义版本/类型/年份范围测试 39 passed，退出 0，44.24 秒。只更新了旧 mock 参数、标题影响的明确六类处理集合、UUID JSON 形状和数据库访问标记，原失败/重试/事务租约断言保留。知识实体发布/工作室/编辑修订组 30 passed，退出 0，47.10 秒；通过 KnowledgePublicationEvent.domain_event 核对实际领域事件、原修订 provenance 与版本推进。该测试切片已收口，未改应用逻辑。下一组继续 Reader 与文件发布旧夹具，不据专项成绩推算新的全量失败数。

事件测试切片已本地提交 6030451。当前继续 Reader/文件发布旧夹具，笔记与正文 focus 先建立明确活动修订，必填作者和语言使用实际人工字段决定，机器置信分数不再当作发布授权。正在跑 reader_cover_semantic 与 resilient_publication 两组，尚未收口；剩余同步 index mocks 会按持久事件检查处理，不恢复已退役的写入口。

本轮接续于 86fde7c，工作区起始干净。推荐图例已接入既有 MediaAsset/Rendition、Work 编辑修订和发布引用保护。旧接口保留，保存草稿后返回真实预览，移除图例只清除选择而不物理删除历史文件。公开页只读活动快照，书封与推荐图例独立。0050 为新增可空 FK，没有生产迁移或外部写入。

推荐图例的旧接口删除历史文件已以 2 failed 复现。0050 增加 Work.recommendation_rendition，推荐图例与书封复用媒体选择、资料快照、验证和 CatalogPublicationMedia；移除只清选择，发布及回滚保持精确文件引用。第一组 36 passed，退出 0，70.48 秒。第一次运行未保存完成报告，未计通过。当前已接共享图例编辑器、媒体库推荐用途、生成类型与公开推荐适配器，正在跑扩大后端与前端全量。未提交、未部署。

扩大后端 53 passed/1 failed，定位为推荐图仍触发正文索引，已在原依赖注册表补图片字段及 FK 的 Public-only 规则，随后 56 passed，退出 0，110.37 秒。TypeScript、lint、API 漂移检查通过。前端构建/原 184 项通过，新增推荐/书封适配 4 项通过。6 项真实浏览器流程通过且包含推荐图选择/预览/清除，但后台 FieldAssistant 一次 SQLite 锁冲突仍需处理。隔离 fixture 已验证本机 Django 支持并配置 IMMEDIATE 写事务及超时，并给编目 E2E 增加 500 响应断言，正在复核。生产 PostgreSQL 设置未变。

本地 fixture 修正后 6 项真实 E2E 通过，退出 0，2.0 分钟，新增的 500 响应断言通过，输出未再出现 database is locked。仍不证明 PostgreSQL 并发。兼容图例旧回归已更新为实际发布修订与旧文件保留；首轮 56 passed/1 failed，失败是报告 fixture 缺少必填发布机构，已补测试数据后最后重跑中。没有放宽必填规则。

兼容图例补齐测试数据后 57 passed。新增精确 edition_id 路由、请求越界拒绝和待发布文献类型的 PDF 图例生成后，最后后端 59 passed，退出 0，98.98 秒。最新 Web 重新构建和完整 188 项通过，退出 0。最后 10:35 的 E2E .last-run.json 为 passed，续接后句柄失效，最终退出码未知。最新 lint 与 API 漂移复核退出 0，Django check 与 migration drift 退出 0。工作台、旧复核页和媒体库均已接共享图例编辑，API 写入和预览保持当前版本上下文。推荐图例切片已本地提交 4120c66，checkpoint3 完整结果见本页顶部。未推送或部署。

当前 Reader/公开证据回归切片已完成。旧夹具补明确活动 Catalog/Document 快照，生产 selector 和证据过滤未放宽。原始分支接续于 cc1335f，尚未连接生产。

公开证据首组 23 passed/2 failed，90.81 秒。测试 helper 未将指定 reader_asset 传给 catalog_snapshot，混用了同一 Edition 的较新受限文件；另一个 RAG fixture 只有 metadata_ready 却期待可查询正文。已修正测试并新增无正式全文不能作 RAG 来源的断言。审计还发现 PDF 封面归属检查在比较前覆写 edition.work，可能让旧 Work 候选通过。新增复现正在执行，尚未计修复完成。

封面归属风险已复现为 1 failed，其余公开 Reader/证据 26 passed，66.49 秒。已将真实 Edition.work_id 比较移到赋值前，再锁定确认归属的 Work；无 schema 或数据清理操作。新增合法封面仍可保存的用例后，扩大 Reader/媒体/范围检索组 62 passed，退出 0，70.69 秒。明确覆盖多文件快照、草稿/失效/受限证据、无正式全文 RAG 拒绝、阅读历史与登录文件。

新核对的发布门槛：AdminWorkRecommendationImageView 旧图例接口直接改 Work.recommendation_image，替换/删除时物理删除旧文件；尚未统一进入 EditorialRevision 和媒体引用保护。该问题为源码确认，未检查生产是否存在受影响历史图例。接下来处理此入口与剩余投影/OCR回归，不把媒体系统判为完成。

当前分支为 `codex/v3.0.5-architecture-convergence`，媒体切片已本地提交 `b39ddce`，首页权限切片为 `fe89007`，规范关系修复为 `44e79df`，语义投递保护为 `8405d9f`。未推送、未连接或部署生产。

旧 MetadataReviewView 未同步统一字段确认的遗漏已修复。显式语言、书目字段和关联选择通过原 CatalogFieldDecision、人工锁与发布包记录；未传语言保留现值、不确认默认值。复用同一 DRF 字段契约，校验 ISBN/DOI/年份/出版日期一致性；已声明的 publication_date 现在实际保存。已归档作者拒绝并原子回滚，不自动恢复。

最终复核/旧 backfill/全部完整入库集成 34 passed，退出 0，180.31 秒。覆盖中文图书/期刊文章、搜索过滤、引用、PDF Range、受信代理、文件替换、原 Annotation 的 asset/page/quote 保留、撤回和重新上架。处理完成前的新书/重新上架不可见，替换处理中旧公开版本保持可读。发布消费者采用明确的 test-only 确认，未证明实际模型、Worker 或索引可用。

Reader 替换集成发现语义任务投递失败会把活动 SemanticIndexVersion 标为 failed。8405d9f 已修复，仅让未完成候选受失败影响，active/retired 完整保留，旧 task_id 的迟到错误不能覆盖已执行或重新派发的任务。任务失败与重试记录保留，没有重建或重置活动索引。该专项先红后绿，最终 12 passed，退出 0，87.57 秒。

当前 Django check、migration drift、API 契约漂移和 diff 检查均退出 0，无 schema 或前端代码变更。元数据复核切片已本地提交 92c16f8；不将这些结果推算为新的全量后端成绩。

工作台旧回归首组 29 passed/1 failed，50.42 秒。整步历史确认不能替代实际字段确认；未采用机器候选继续可查，不阻止已确认字段；策展 N/A 按字段状态显示完成；关联同名 Work 后仍需确认字段。

同名 Work 关联后重跑可被 OCR 覆盖的风险已先红复现并修复。新增只读 effective_catalog_reconciliation 从当前已审核、目标与 Edition.work 一致的候选推导有效状态。流水线与后台复用此读取，保留原始 preflight_summary，撤销后自然恢复待判断状态。原本已复用整个 Edition 的更强保护不能被降级。首组 39 项通过；最后加入智能编目和发布命令组，59 passed，退出 0，94.71 秒。Django check、migration drift、API 契约与 diff 检查退出 0。没有新增 schema 或改写历史报告。本切片实现和验证已完成，按独立本地提交保存，未推送或部署。

续接从剩余全量回归和未完功能继续。最近一次完整后端仍是 wave2 的 1002 passed/61 failed/32 skipped，之后这些专项不当作新的全量结果。下一批优先处理 Reader/公开修订旧夹具、投影事件契约与 OCR 测试旧入口，再完成 Person 合并、剩余媒体/API/界面和生产验收。

中间失败与修正原因已记录在 docs/V3.0.5_VERIFICATION.md。未放宽数据库保护约束或公开访问过滤。

已修复媒体导航断言和草稿封面预览。预览从待发布 EditorialRevision 读取选图，使用受保护的私有 URL，不写 canonical Work。新增 Model/QuerySet 媒体内容保护。该组后端 33 项、导航 23 项通过，TypeScript、lint 和 API 漂移检查退出 0。

随后补齐只改 alt/许可时的发布边界。MediaRendition 的 0049 保存不可变资料快照，资料改变会生成新的选择版本；发布前 diff 显示来源、许可和说明，另一个管理员后来修改媒体源资料不会改变已核对的版本。扩大回归 47 passed/1 failed，最后失败为测试给 Edition 而非实际 Work 发布事件设置投影状态，已按事件对象修正。最终 48 passed，退出 0，48.91 秒。媒体切片的 `npm test` 重新构建并完成 181 项，退出 0；当次 3 项真实 E2E 通过，退出 0，56.7 秒。

后续仍有其他实体媒体、人物查重合并、完整工作台/Reader/API/CSS 收敛、legacy 写入冻结、剩余全量后端失败和生产恢复演练。v3.0.5 全部完成与上线门槛均未达到。

Editor 首页 403 已修复。原因为前端无条件请求管理员统计并忽略失败。AdminShell 现在向子页面提供已验证会话；首页与统计页按当前能力读取，复用可取消、按账号隔离的资源 hook，失败显示重试且不假装队列为空。后端权限未改。TypeScript、lint、首组 26 项和最新完整构建/184 项通过。最新真实 Playwright 6 项通过，退出 0，1.1 分钟，包含 Editor 无统计请求、管理员真实统计、队列断网与重试、手工编目、Reader 拒绝及媒体操作。日志中的统计 403 来自明确的越权 API 拒绝测试。

前端一次全量运行曾集中 SSR 失败，原因待核实；同一首页、无改动完整重跑及最后重新构建后均通过，未删除失败记录。后端 wave2 报告已完成，1095 项中 1002 passed、61 failed、32 skipped，396.086 秒，进程句柄失效，退出码未知。

字段助手的最后一个静态可识别旧关系创建点已修复。TheorySchool 输入只经现有人工确认 LegacyKnowledgeMapping 解析成 KnowledgeNode；草稿写 WorkNodeRelation，已发布作品进入原 EditorialRevision。缺失、错类型、未发布或身份不匹配的映射会拒绝。历史 WorkKnowledgeRelation 保留不覆盖，已存在规范关联时字段显示去重。新增 8 项及原规范身份/候选集成共 37 passed，退出 0；补映射/目标事务锁后核心 23 passed，退出 0，49.00 秒。Django check 与 migration drift 退出 0，无 schema 变更。PostgreSQL 并发锁与生产行为仍待核实。

下一项从 wave2 的具体失败继续处理字段人工确认、公开测试夹具和旧同步索引假设，再完成 Person 合并等未完功能。不要重跑最初全仓审计，也不要把局部修复后的剩余失败数量估算为全量实测。

### 此前开发记录

下列按发生顺序保留。某一记录中的“当前”只代表当时，最新状态以上方摘要为准。

用户要求的全栈系统升级已开始。完整任务位于本机附件 `bc6af443-82db-4f9a-8e88-e03744b12693/pasted-text.txt`，共 119 节。已核对干净基线 `codex/v3.0.4-cataloging-intelligence`、提交 `340b94f`，并建立 `codex/v3.0.5-architecture-convergence`。原分支未修改。

已完成主要依赖审计与完整本地基线，记录在 `docs/V3.0.5_ARCHITECTURE_AUDIT.md` 和 `docs/V3.0.5_VERIFICATION.md`。已实现第一个发布安全修复，公开 selector 和新发布入口拒绝指向其他 Edition 的 revision。9 个新不变量用例先出现 3 个预期失败，修复后与原发布/一致性检查合计 22 项通过。没有修改历史数据或 schema，尚未上线。

发布归属修复已本地提交 `1ba12c9`。CatalogingSession、catalog 0043、ingestion 0015、无上传实体候选服务/API、Web 新建与会话入口已实现。会话从 Edition 推导 Work；候选采用/拒绝/撤销复用原服务，按会话与贡献角色隔离。旧候选和真实上传记录保留，无 fake UploadItem。

验证已完成 12 项会话基础、24 项候选首组。扩大集成 110 passed/1 failed，唯一旧公开预览 fixture 补显式活动快照后其参数组 3 passed。TypeScript、新文件 lint、Django check、migration drift、build 均退出 0。两项真实本地 Playwright 已分别通过，覆盖非 superuser Editor 创建/保存/重开与 Reader 拒绝。首次命令路径和标题选择器失败均保留记录，业务 API 没有 mock。

会话与候选已保存为第二个本地提交 `c7b2cb6`。当前字段契约已接入 SECTION_FIELDS、REQUIRED_FIELDS、FIELD_DEPENDENCIES、字段标签、可写字段、工作流序列化验证和发布检查。ISBN/DOI 的格式校验不代表外部标识符存在性。catalog 0044 新增 publication_mode，旧数据保持 document，手工新建使用 bibliographic。

纯书目沿用原 CatalogPublicationRevision/outbox，成功后返回公开详情且 reader_asset=null。有任何附带 Asset 时仍检查真实文档，不用纯书目模式掩盖坏文件。50 项首轮契约/会话/发布测试通过，增加会话 publishing/published 关联后 44 项通过。TypeScript 和当前新文件 lint 通过。该切片仍未提交、未生产部署，正进行剩余联动与构建。

19:28 完成当前构建与两项真实 Playwright，均退出 0，新增覆盖无上传新建作者并关联。字段助手标量采用也已使用契约校验，相关 20 项通过。基线 8 个 lint 错误已修复，全仓 lint 和 TypeScript 均退出 0。按上下文隔离的临时状态拒绝旧异步结果，Knowledge Studio 复用可取消的 API hook，3 个状态隔离单元测试通过。完整 Node 基线的旧断言和后端失败仍未全部处理。

字段契约/纯书目提交为 `11e9f6f`，前端状态修复提交为 `36db404`。当前 MetadataCandidate 的 session FK、ingestion 0016、来源导入/API、字段助手采用拒绝、工作台读取和一致性审计已接入，正在跑相关测试，尚不计完成。完整 Workbench、OpenAPI、媒体、legacy 与最终全回归仍未完成。本机 E2E 临时 SQLite 只含测试账号与记录，不是生产或恢复副本。

元数据首组 39 passed/2 failed，定位为统一年份校验未先转换候选字符串；已补 integer normalizer，保持 1000–2100 范围并拒绝布尔/小数，正在重跑元数据与旧 backfill 集成。人工导入的来源标签和 URL 保留为导入证据，不再误标成书内 PDF 证据。没有自动改正式题名或采用导入值。

元数据/字段/旧 backfill 集成随后 26 passed，退出 0，43.01 秒。仍无生产数据操作。接下来配置 OpenAPI 生成工具，并逐领域替换手写 TS；不能只生成 schema 文件就宣称所有端点已覆盖。

已固定新增 drf-spectacular 0.30.0 与 openapi-typescript 7.13.0。JSON 错误统一包装保留旧 error/detail 字段，新 schema 入口受原后台权限保护，正在首次生成和回归。npm audit 当前 14 项（6 high/8 moderate），主要涉及现有 Vinext/构建工具及传递依赖，未执行 audit fix 或强制升级。须在安全阶段逐项确定实际影响，不能忽略。

OpenAPI 全量探测报告 170 类端点无法推导及 162 类警告，退出 0 不能证明通过。已建立明确的 verified 编目契约范围，不发布工具猜测的旧类型。该范围 `--validate --fail-on-warn` 退出 0，TypeScript 已自动生成，编目客户端改用生成类型，`npm run api:check` 检测 serializer/schema/TS 漂移。全量 API 覆盖仍未完成。

23:57 收口结果为 API 契约专项 6 passed、生成漂移检查与 TypeScript 退出 0、当前构建与真实编目 E2E 2 passed。此前 30 pass/1 fail 是查询计数测试缺少 django_db 标记，已修复后仅重跑该文件。metadata/candidate 相关 31 项也已通过。下一项为统一发布命令、预发布字段 diff、合法回滚与过期消费者防护。

元数据/契约基础已本地提交 `d8fde9a`。当前 publication_commands 已开始接管旧 publish/withdraw 入口，包含只读准备差异、校验指纹、revision 归属与文档一致性检查。回滚只接受已合法激活过的修订，以原不可变快照创建单调递增的恢复发布，不改写旧快照；旧活动内容继续服务到恢复处理完成。正在跑专项，API/UI 尚未接完，不计交付完成。

发布命令首组 37 passed。API、生成类型和前端字段 diff 已接入，旧直接“确认发布更新”按钮现先进入差异核对；上传/维护的实际发布均带 prepared_fingerprint。扩大旧修订集成 26 passed/2 failed，正在将旧任意幂等键的合并测试改为真实维护发布 HTTP 行为，并对齐已有扁平 changed_fields 契约，不放宽业务检查。最近 Playwright 的 .last-run.json 保存 passed；原进程句柄在用户续接后失效，不假设进程退出码。

旧修订两项已定向通过。新增正式快照 Model/QuerySet 不可变保护后，原 Reader 夹具因为在创建后改写 reader_asset 被拒绝，已改为创建时设置正式内容。发布差异/历史/回滚和三类健康状态均已接前端，当前重新运行发布与真实编目 E2E。回滚只恢复公开内容，不覆盖后来人工编辑字段，保留的不同草稿显示为待发布修改。

00:55 最后结果为发布/不变量/旧编目/编辑修订 38 passed，三类健康独立性新增用例 1 passed。TypeScript、lint、生成漂移、migration drift、构建均退出 0。真实编目 Playwright 2 passed，51.8 秒，包含新建、保存、重开、人工作者、发布前 diff 和读者拒绝。当前准备保存该逻辑提交，再做新的全回归盘点。全部生产门槛仍未达到，不能部署。

发布切片已提交 `a15b0f4`。00:59 全量后端 XML 记录 1074 tests、86 failures、32 skipped，即 956 passed；耗时 371.484 秒。前端全量 XML 为 181 tests、17 failures，即 164 passed。原进程句柄已失效，以报告记录结果，不重跑获取退出码。正在按真实公开 revision 修正旧 Reader/Scoped Search 的 published 夹具，后续逐域处理，绝不恢复仅 state=published 即公开的旧捷径。

Reader/收藏进度/Scoped Search/公开 Range 夹具更新后 27 passed，退出 0。前端旧位置、文案和控件断言已对齐当前字段助手与系统诊断分工，完整 181 tests/0 failures，退出 0。还补回了被旧界面重构遗漏的学者 external_identifier 字段助手，仍由人工采用。TypeScript 与 lint 退出 0。npm test 已改为自动发现所有 .test.mjs，当前继续语义检索相关夹具和剩余后端失败。

当前 `npm test` 已实际完成重新构建和自动发现的 181 项，全通过，退出 0。Semantic/Opinion 组在显式活动修订 fixture 下 28 passed/1 failed；最后一项只因旧断言要求移除所有过滤，而当前 fallback 正确保留 active Asset 空范围约束，已对齐断言并定向复核。未放宽任何 Meilisearch 访问过滤。

最后 fallback 用例定向 1 passed，退出 0。语义与 Reader 回归切片已收口，剩余后端 failure 不估算为已通过。下一项优先补 L1/L2/L3 功能健康，把 workbench 实际构造、活动 revision 与公开目录检查接到既有探针，避免 /ready 绿色掩盖工作台故障。Person 合并已实读 9 类 Person 引用和 5 类 ScholarProfile 引用，事务实现仍待完成。

回归切片已提交 `6206b16`。分层健康已接入原 HealthCheckRegistry 和 Processing Center，包括 migration、真实 workbench 只读构造、活动 revision/公开 serializer，以及独立公网探测。/ready 明确只证明 database/schema，L2/L3 未执行；历史陈旧健康结果在层摘要标为 unknown。新增只读 check_functional_readiness 命令，缺真实样本不能通过门槛；正在跑相关回归和构建。

分层健康/原调度/权限组 34 passed，空样本门槛 1 passed。TypeScript、lint、构建及完整 npm test 181 项通过。公网 API 验证已要求有效 readiness JSON，不能用 WAF/HTML 200 冒充成功；最后探针专项正在收口。没有实际请求生产或自动执行恢复。

最后分层健康专项 8 passed、migration drift 退出 0。该项可本地交接，生产检查尚未执行。下一步继续剩余回归、MediaAsset/Rendition 与人物合并，不把当前部分实现冒充 v3.0.5 全部完成。

分层健康已提交 `cd7eaba`。MediaAsset/Rendition、0045/0046、受保护上传/元数据/预览接口与媒体管理页已实现，首组 8 项通过。曾因主任务在测试运行中改源码导致旧模块常量导入失败，已在稳定源码重跑，不把中间失败当通过。媒体保存增加并发校验，正在运行 9 项媒体专项与包括真实图片上传的新 E2E。公开 Work/Portrait 尚未接入媒体字段，上传不会自行公开。

媒体后端最终 9 passed，退出 0。浏览器前两项仍通过，新媒体用例发现 select 标签定位与 Vinext Image 拒绝 localhost API 图片，真实网络 trace 证明原图/缩略图已保存。已改角色定位和原生 picture/img，保留私网 SSRF 防护，重新构建与 E2E 正在运行。公开封面接入仍待后续完成。

媒体 E2E 又定位到保存后刷新列表会暂时清空 data 并卸载编辑器，导致成功提示和新预览丢失。已保留当前选择对象，刷新不卸载表单；编辑版本号只在本人成功保存后推进，避免隐藏其他管理员的并发修改。正定向重跑媒体浏览器旅程，不用延长等待时间掩盖该问题。

最新媒体定向 E2E 的 .last-run.json 已保存 passed，原句柄续接后失效。当前 Work.cover_rendition 和 rendition group_key 的 0047 已生成。媒体封面可先进入现有 Work EditorialRevision，公开 serializer/图片端点只读取活动快照的精确衍生图；新增响应式 srcset 与媒体库选封面入口，正验证发布隔离。尚未接入 Person/Knowledge/ReadingPath 媒体，不计完整媒体系统完成。

16:53 当前构建和 3 项真实 E2E 通过，包含媒体上传、署名许可、焦点、横幅预览及封面关联。作品媒体发布/契约/编辑修订 35 项通过；0048 新增 CatalogPublicationMedia 真实 FK，保护每个公开衍生图不被删除。正在复核引用保护和小图 srcset 去重；公开图仅允许活动快照中的 ID，不公开媒体原件。

19:00 的 E2E 观察到 Vinext 导航取消时 ERR_STREAM_UNABLE_TO_PIPE、Editor 首页统计请求 403，列为待排查问题。没有覆盖正文/外部 Provider/PostgreSQL/生产 Cloudflare。未推送、未连接生产。

完整基线随后完成。后端 888 通过、90 失败、32 跳过；前端 161 通过、17 失败。TypeScript 与 build 通过，lint 8 个错误、3 个警告。生产发布明确阻断。失败按旧公开快照夹具、字段确认规则、异步 outbox 接口与真实回归分类，不放宽公开权限或把机器确认视为人工决定。

本轮授权包含全部安全门槛通过后的生产发布；不延续旧任务的停止测试要求。计划见 `task_plan.md` 顶部。先解决数据正确性、发布安全和编目可用性，再处理媒体与界面。每个交接小项在本页分别记录实现、验证和上线状态。

生产当前版本、镜像、迁移与公网状态均待本轮实测。最后历史记录为 2026-09-05 15:52 Cloudflare 1033，不能推断今天仍故障或已经恢复。备份恢复、关键 E2E、Workbench、Reader 和发布不变量通过前禁止切换。

## 3.0.4 历史交接记录

最近核对时间为 2026-09-05 15:52，香港时间。本页是额度恢复、中断续接的第一入口。源码、构建、功能验证和上线分别记录。

## 当前状态

15:37 用户再次报告公网 1033。当前公网尚未恢复，书库 API/Edge 内网仍返回 3.0.4 和迁移待执行 0。已捕获隧道假存活证据：ready 报 3 条连接，但 TCP 已 13 分钟未收到回应、持续重传。仅将 cloudflared 独立网络命名空间的 tcp_retries2 从 15 调至 8，并持久化到 compose.cloudflare.yaml，固定使用现有 image digest。宿主仍为 15，其他书库服务、数据库、TLS/防火墙/域名权限未改。

失效连接已被释放，但 NAS 主机和容器向多组官方 Cloudflare TCP 7844 端点的新连接仍超时，Cloudflare API 443 亦超时。尚不能确定是路由器、ISP 还是其他上游设备丢包。需要取得路由器/出站网络的安全管理入口再继续；不得称公网已修复，也不要继续以反复重启书库代码来处理此问题。配置备份在 NAS `storage/backups/cloudflared-stall-20260905-1546`。详见 `docs/CLOUDFLARE_TUNNEL_RECOVERY.md`。

15:03 用户反馈工作台无法打开。生产错误 d277ae6118dc 已定位为 build_edition_workflow 未向 7 个步骤传 catalog_state，影响所有已建立 Edition 的上架、已发布维护、工作队列和字段研究。未建立 Edition 的初始上传分支不受这一个错误影响。最小修复 `ee89588` 已推送，并于 15:14:25 完成 API 热修，只改一个后端文件，没有改馆藏数据或运行测试。此前 readiness 只能证明服务启动，不能代表工作台功能通过。

当前 API/Worker/Beat image 为 `social-theory-library-api:3.0.4-workbench-ee89588`，ID 为 `sha256:859330ad798a4a2edac1d25d5bacb9f9658b32d71eac0875cd7780ceca1062a4`。Web 保留主发布版本。热修记录位于 `storage/backups/pre-v304-workbench-hotfix-ee89588/deploy-record`。再次发生的 Cloudflare 1033 在原隧道重新连接后恢复；持续稳定性未证明，不能把重启恢复写成网络根因已根治。

3.0.4 已于 2026-09-05 14:59:18 正式上线。公网 readiness 返回版本 3.0.4、database=true、pending_migrations=0。API、Web、两个 Worker、Edge 和 Beat 已完成切换及恢复，6 个暂停的 OCR 任务保持原状态。

代码分支为 `codex/v3.0.4-cataloging-intelligence`，上线代码提交为 `18f4106`，此前实现提交为 `0d479ff`，均已推送。最终 tree 为 `d38f23ba0b8b77a3df376b08d68abaaa85da7670`，855 个文件，归档 SHA-256 为 `6860dbfe2d0c105dc9382b0958b56f94a6db831e5d6ff1590b8a87a66c37080c`。当前仅在补充最终交接文档，后续文档提交不改变已部署应用代码。

主发布 API image 为 `sha256:dbd0db1d1599531aa83199e4834ab2c8b5c348c05a8fd4df845dae3b1c8c259e`，Web image 为 `sha256:1e1433ca18a26ae8f1c32b0f9e04382587edda5f0be1202a083c9b65694eb127`，主发布标签为 `3.0.4-d38f23ba0b`，API 已由上方热修替换。初次 npm 下载超时后复用了锁文件完全相同的既有构建依赖。中断前已完成的基础镜像和恢复演练没有重复执行。临时恢复数据库及独立网络已清理，正式备份、原始文件和回退镜像保留。

生产 0040、0041、0042 已应用。正式词典已切换到 registry v2，generation 为 `e1ffe3fc-da50-46cb-a648-bc6b973b6cb0`，revision 为 13。旧词典的 47 项来源规则问题已经清除。最终生产报告剩余 5 项历史候选/关系决定错误、5 项关系端点警告，均需人工判断，不是全库无错误。13 类核心对象 ID 摘要及 9 个原始 PDF 记录摘要与升级前一致。

最终镜像包含公开分类端点过滤、撤回后旧快照裁剪、字段级异步查找和本地拒绝反馈。旧全局候选路由转到字段工作台，原能力保留系统诊断。探索页及全部次级页面的暖灰背景修复已经随版本部署。按用户要求未追加功能测试或浏览器视觉验收。

本次历史显示再次缺失的原因已经定位并修复。上次只映射了字节偏移，没有映射原始记录序号，导致历史游标期待 4735 而对应记录为 4729。新备份后在隔离副本原生重建，将位置和序号一并映射回不变的原文件，只合并本任务 29 个回合、1,918 个显示项。备份位于本机 `.codex/tmp/history-recovery-20260905-1428`。修复后未测试、未启动新模型请求、未重启 Codex。界面端是否刷新不宣称已经验收。

部署访问可用，不需要密码。首次切换因词典命令漏传 normalization-version 参数退出 1，已恢复旧应用且保留新增 schema，记录在 deploy-record/attempt-1。修正参数后第二次切换成功。期间 Cloudflare 返回 1033，原隧道重启并恢复连接后公网就绪。没有恢复覆盖生产数据库、删除活动索引或重跑全馆 OCR。

## 已落盘的实现

- 架构审计、保留/封装/替换/废弃/迁移清单，以及 35 项要求和 18 项交付矩阵。
- 逐字段状态、依赖失效、事务采用、旧值/新值及依据审计。候选采用、普通保存和正式发布分开。人工确认不会被后台建议覆盖。
- 作者、译者、出版社、年份、简介、主题和理论的字段助手。后端聚合默认 3 个结果，馆内正式对象优先，其他草稿限当前编目上下文。本地人物也支持拒绝反馈，不写入正式事实。
- 非线性工作台，任意顺序编辑保存，按正式字段计算发布门槛。手工确认现有草稿实体自动登记发布包。重复预检、轻量新建并关联已接入。
- 学者、主题、理论、学科、子学科、阅读路径及 Knowledge Studio 共用字段助手。普通 Studio 已有字段操作、草稿关联显示及重新处理，技术视图保留到系统诊断。
- 作品观点候选复用原审核服务，采用只写独立草稿；公开观点受活动馆藏快照名单约束。
- 已发布内容修改进入 EditorialRevision。后台列表、详情、保存响应和预览统一材料化待发布修订，公开读取仍使用活动正式快照。
- PublicationBundle、CatalogPublicationRevision、知识发布 outbox 和幂等消费者。处理失败保留旧活动版本，显式重新处理复用原事件。并发更新继承尚未完成的正式修改；共享 Work 字段更新传播到其他已发布版本。
- QueryLexicon 正式来源 registry v2。全文、语义和观点使用独立发布命名空间。正文修改才重做相应内容，元数据更新复用向量，纯封面不重做 embedding。
- OCR/重新抽取先建立独立文本解释 Asset，保留原 PDF、旧页码、已发布片段和人工页码映射。完成后只通过发布事件激活，低质量结果不能替换合格正文。
- 诊断重建入口也走正式事件或草稿 staging。清理保护全部发布修订和运行任务引用，不删除旧稳定正文。
- 图书、论文、整期期刊差异模板。0042 建立唯一的期刊目录/论文关联，工作台可增删排序关联，正式快照和共用 WorkDetailView 显示；草稿论文不生成公开链接。
- 字段稳定后 900ms 防抖预取，60 秒共享缓存、并发合并、请求取消和上下文失效。外部失败不阻断手工编辑。
- 紧凑/完整草稿预览复用公开 WorkDetailView，完整模式不保留 Admin 侧栏。探索首页及次级页面已改用与全站一致的暖灰纸面背景。
- Topic 合并、正式关系迁移及精确更新事件，冲突阻断。全库只读一致性命令覆盖 schema、模型数量、外键、字段、身份、别名、发布包、修订和事件状态。
- Django 迁移 0040、0041、0042 已应用到生产，旧应用回退时保留新增 schema。

## 当前真实数据库情况

2026-09-05 13:17 通过生产容器执行 PostgreSQL READ ONLY 盘点，并读取真实全文和语义索引。

- 9 Work、9 Edition、18 Asset、9 ORIGINAL、3,679 Page，6 本已发布、3 本草稿。
- 未发现规范化同名身份重复、重复贡献关系或多个当前同类文件。两个实际索引中草稿且公开的文档数均为 0。
- 《社会学的基本概念》没有已确认作者，旧两条作者关系未确认，正文质量为 0。不得猜测角色后自动提升。
- 《质的研究方法与社会科学研究》的陈向明作者关系实际存在且已人工确认，Person 仍是草稿。0040 会保守回填编目发布包，保存草稿不公开。
- 《弱者的武器》的旧正文低于质量门槛。新资格过滤应排除其不合格正文，PDF 保持可读。
- 6 个 OCR 任务由用户暂停。升级不会擅自恢复。历史 accepted 候选与正式字段不一致、混杂人名等保留人工核查。
- 完整结论见 `docs/V3.0.4_DATABASE_AUDIT.md`。本轮没有自动合并、删除或批量确认历史馆藏。

## 构建及备份记录

用户要求不新增功能测试，本轮未运行单元、集成或 E2E。A–J 最终验收保持待核实，不能把构建成功写成场景通过。

- `python -m compileall -q api/catalog api/ingestion api/reading`、`api/manage.py check`、`api/manage.py makemigrations --check --dry-run` 最新退出码均为 0。
- `web/npm run build` 已完成；`npx tsc --noEmit --pretty false` 修复递归返回类型及期刊类型映射后退出码 0。最后源码以远端候选镜像构建为准。
- 编译期间发现的本地语法及类型问题均已修复，没有把首次失败写成通过。
- Fresh BackupJob 为 `6d17bfc8-7a58-4dc0-a7eb-b6231806dcff`。
- 备份 SHA-256 为 `443c774374f4b496b2c4b32352ac10f8beeb854c426b975bdd57a2006d445066`。
- database dump SHA-256 为 `5dcc4f932d5fa6e5b0c40a344c86c07e12abba0df76c39513c0dcc7ee9670b23`。
- 已恢复到隔离 PostgreSQL 16，旧 schema 和核心馆藏身份核对一致。新增 0040–0042 亦已完成；此结果来自中断前已启动的部署步骤，本轮只读取已有记录。
- 回退镜像标签为 `pre-v304-20260905-134000`。记录目录为生产 `storage/backups/pre-v304-cutover-20260905-134000/deploy-record`。

## 仍需人工处理或后续核实

1. 5 条历史候选与确认关系差异、5 条关系端点警告仍需管理员判断，详见数据库报告。不得自动把顾忠华、马克斯·韦伯等未确认角色提升，也不自动恢复归档理论对象。
2. 用户暂停的 OCR、质量不足的正文和外部来源可用性维持原有边界。没有运行 A–J 完整功能或权限验收，不能声称全部场景通过。
3. 完全没有 UploadItem 的手工创建作品，外部人物查找的候选持久化仍受原服务限制。馆内查找、手工填写和新建关联可继续使用，未伪造上传记录。
4. 历史索引修复已写入，按用户要求没有修复后测试。后续若用户仍报告界面问题，先核对游标与原序号，不能再只映射字节偏移。

## 续接方法

先读本页，再看 Git 和最后修改点。只核对上一项的实际结果，不重跑全量审计。每完成可交接小项更新本页。历史显示于 14:31 再次修复，不能沿用上午的用户确认来证明本次显示结果。完整要求回溯见 `docs/V3.0.4_USER_REQUESTS.md`。

详细文档为 `docs/V3.0.4_ARCHITECTURE.md`、`docs/V3.0.4_REQUIREMENTS_MATRIX.md`、`docs/V3.0.4_UPGRADE.md` 和数据库报告。较早测试记录只对应当时源码，不能用于证明最终版本。
