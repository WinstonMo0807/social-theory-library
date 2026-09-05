# 当前问题

更新日期为 2026-09-05。状态依据当前源码、已有测试和可重复的生产检查。`待核实` 表示本轮没有运行对应环境或权限路径，不能改写为通过。

## 3.0.4 当前真实限制

- 15:03 工作台出现共用参数遗漏错误。build_edition_workflow 对 7 个步骤未传 catalog_state，导致已建 Edition 的上架、已发布维护和队列均可 500。ee89588 最小修复已于 15:14:25 上线，未改数据或运行测试。不能将 readiness 成功写成工作台已经逐本验收。
- Cloudflare 隧道在主发布和热修期间均出现 1033 与连接超时，重启原连接后恢复。当前公网就绪，但长期稳定性未核实；后续复现需处理外网连通性，不能通过反复回退业务代码掩盖此问题。
- 非线性保存、统一字段决定、候选编辑修订、发布包、正文保护、统一策展和 Topic 合并已实现并随 3.0.4 上线。当前状态见 [CURRENT_PROGRESS.md](../CURRENT_PROGRESS.md)，不能再把上午恢复时的缺口当作当前全部未完成。
- 2026-09-05 14:59:18 已完成公网切换，生产 catalog 0040–0042 已应用，readiness 为 3.0.4、pending_migrations=0。备份、隔离恢复记录、旧镜像、首次失败与恢复记录保留。
- 最终生产一致性报告仍为 clean=false。5 项历史候选与字段/关系差异，以及 5 项已确认关系指向未发布或归档分类的警告需要管理员判断。公开读取已排除非正式端点，原关系未删，不能把警告归零作为自动发布或合并依据。
- 完全没有 UploadItem 的手工创建作品，外部人物查找结果仍受原候选持久化服务限制。馆内查找、手工填写、新建并关联可以使用；后续应补正式候选契约，不伪造上传项。
- 用户要求本轮最终收口不追加测试运行。较早阶段的定向回归只能证明当时的源码。最终工作树、catalog 0040 的生产 PostgreSQL 行为、真实 Celery 事件重试、管理员浏览器写入和公网边界仍需通过部署检查确认。
- 一致性审计命令是只读工具。它会报告 accepted 候选未写字段、重复实体、发布 revision、搜索、QueryLexicon 和 Semantic 资格问题，但不会自动合并 Person、Topic、KnowledgeNode 或修改历史人工馆藏。任何修复都需要备份和明确规则。
- 正式 QueryLexicon 已重建到 registry v2，47 条旧来源问题已消除。新 generation 为 e1ffe3fc-da50-46cb-a648-bc6b973b6cb0，revision 13；旧 generation 保留。没有直接删除活动词典或自动升级候选别名。
- metadata ready 与 fulltext ready 已分开。没有合格 DocumentRevision 或质量记录的已发布作品只能提供书目与获准阅读的 PDF。真实 PaddleOCR、远程 embedding、Meilisearch 内容和 Reader locator 需要逐项生产核对。
- 知识发布投递依赖现有 ProjectionState 和幂等任务。外部服务故障应显示为智能内容处理异常，并继续服务上一稳定 revision。长期重试、dead-letter 处置和人工重新处理仍需要生产观察，不能用清空失败记录处理。
- 旧 TheorySchool、Concept、WorkKnowledgeRelation、章节决定和多类 Candidate 表仍保留兼容或诊断用途。3.0.4 停止把它们当作普通 Admin 的主要操作语言，但物理删除要等映射一致、旧读取为零和观察期完成。
- 期刊论文和整期期刊已有资源类型基础。三类字段模板、目录与论文列表需要在真实管理员上架样本中继续核对，不能由 model choice 或静态表单断言代替。
- 外部书目、VIAF、联网检索、AI 简介和候选封面的实际可用性会随环境与授权变化。它们失败时不得阻断手工编目，也不得降低证据、身份或正式发布门槛。
- 生产上的普通非 superuser 管理员完整上架、即时新建实体、bundle 发布、修改已发布作者、仅换封面、主题合并和整书撤回场景尚无本轮持久写入证据。部署验收应优先使用可回滚事务或专用测试记录，不修改真实馆藏来制造通过。

## 3.0.3 阶段限制记录

本节是旧版本阶段记录。当前部署与数据状态以上方 3.0.4 和数据库审计报告为准。

- 公开 Scholar 缺失的根因已确认。生产有 4 个 published ScholarProfile，但对应 Person 均为 draft。源码修复和有界收敛命令已完成。正式 apply 只能在 fresh backup、dry-run 数量匹配和新镜像就绪后执行。
- PublicPageContract 当前覆盖 Scholar 9 页、Theory 7 页、Topic 8 页，路由与管理字段审计均为 100%。旧 `/theory-schools` 路由、Topic 的旧 Theory 补充和 Scholar curation 中的旧 Theory ID 仍是明确兼容层。退役需要 normalized mapping 完整并连续观察没有旧读取需求。
- Reader focus 的生产 EvidenceSpan 共有 3,735 条，active 且 bbox 为空的数量为 0。源码与测试已覆盖 passage locator 和拒绝无关同页匹配。部署后仍需用真实 Viewpoint、原文检索和 Ask 结果逐条核对高亮，不能只以 URL 包含参数认定通过。
- Claim Gold 仍为空，21 个 `llm_small` demand 继续等待 capability，且全部不阻断发布。3.0.3 不启用 AI、4070 或 Claim 默认排序。
- OCR 全局暂停仍为 true，6 个 OCR job 为 paused。部署必须保持这些 ID 和状态不变，不得 Resume All。
- NLB、NCPSSD、Z39.50、CNKI、维普和万方的合法凭据或使用规则仍未补齐。Processing Center 应显示降级，不得把缺少 optional Provider 写成核心书库不可用。
- 正常 Administrator 登录下的 protected Preview 和 Processing Center 需要部署后浏览器验收。匿名路径只能证明拒绝访问，不能替代真实管理员会话。

## 3.0.2 当前真实限制

- 3.0.2 已完成 catalog 0039、fresh backup、回退标签、公开 T4 和同源发布。候选树 `f0ffad378928591691df45770ad32d3bbd062a50` 保留为首轮 T4 快照。正式发布的 tracked tree、最终镜像 label 与远端 release branch 保持一致；源码文档不自引用自己的 commit SHA。
- Library Synthesis 的代码路径已经完成，但生产没有可执行的 LLM executor 时只会显示等待。尚无生产采用样本，不能写成摘要或策展候选质量已通过。
- NLB Singapore Catalogue v2 adapter 已有 fixture 与完整 provider gateway 路径，但生产尚未配置合法 credential，也没有真实中文书目的质量抽样。NCPSSD、Z39.50、CNKI、维普和万方继续按既有合法使用边界降级。
- Claim Gold 管理接口不等于已有 Gold。当前 benchmark 尚未 ready，Claim 默认排序不能开启；support、oppose、qualify、locator 与 attribution 仍没有新的生产前后指标。
- 4070 按本轮要求没有部署。生产有 21 个有效 demand 处于 `waiting_for_capability`，publication blocker 为 0。真实 Laptop 在线领取、模型输出质量和断线重领仍待核实。
- 受控 OCR 测试验证了文本进入 EvidenceSpan 和候选，但不等于真实生产 PaddleOCR 已执行。用户已暂停的 6 个 OCR job 在切换前后保持 paused。本轮没有恢复、重排或执行它们；后续只能逐项判断，不能 Resume All。
- SafeWebFetcher 现在会执行响应头和 HTML 页面 robots 指令、SSRF、固定 IP、内容类型、大小、编码与中文正文检查。它没有通用站点授权能力，也不会绕过登录、付费墙或反爬；Provider 使用规则仍需由相应 adapter 与管理员配置保证。
- Knowledge preview 对标量、Person、关系和 ReadingPath 阶段采用只读内存 overlay，不会临时写库。任何仍无法由公开 serializer 完整物化的特殊字段必须明确标记 partial，不得以后台模拟卡片冒充正式页面。
- legacy TheorySchool、legacy Concept、WorkKnowledgeRelation 和旧 route 继续只读或 advanced 兼容。退役仍以 mapping parity、零旧写调用、公开页不再依赖和观察期完成为条件。
- 上架工作流曾把未处理的 Person 候选加入正式 `contributors.items`，并默认创建作者、译者表单行，导致候选很多且空译者也像必填项。该问题已在 3.0.2 生产候选中关闭。实际上架项有 28 个待处理 Person 候选，Workspace 可见 29 个 Person 候选，正式贡献者列表只有 1 项；候选没有进入正式草稿，批量责任者 metadata 也不能直接采用。作者区保留一个尚未落库的空输入，译者按需添加，空行不阻止保存。

## 3.0.1 发布时的真实限制

- 3.0.1 已部署。正式 release commit 为 `fa7444d3524f99f81bc5c0c20fbbc3477e81a76e`，catalog 0035 至 0038 和 ingestion 0014 已应用，pending migration 为 0。Fresh backup、PostgreSQL 16 restore rehearsal、3.0.0 additive-schema compatibility、正式镜像、T4 与回退记录均已完成。
- 作品摘要的 Source Abstract 和 No Reliable Candidate 已实现。只依据馆内 PDF EvidenceSpan 生成并带引用的 Library Synthesis Candidate 尚未实现。系统会明确返回 `source_abstract_not_found_and_library_synthesis_not_completed`，不会用模型常识补写摘要。
- 4070 pull worker 协议和客户端已落地，但当前客户端只执行 `claim_extraction`。claim attribution、claim stance、rerank、curation reasoning 和 ReadingPath generation 尚不能由这个客户端领取。真实 Laptop 尚未连接生产，在线模型质量和断线重领继续标记为待核实。
- Research Source Registry 提供 NCPSSD、Z39.50、CNKI、维普和万方的受控扩展位置，不等于这些 Provider 已在生产可用。NCPSSD 需先核对使用规则。全国联合编目需要有效 endpoint、credential alias 和可选 Z39.50 runtime。CNKI、维普和万方需要合法授权 Provider 或人工 Evidence，源码不包含绕过登录或反爬的 crawler。
- SafeWebFetcher 的生产正向路径已用真实 SearXNG lead 和公开英文 HTML 验证。中文网页正文 Evidence 转换仍需按站点使用规则核对。Baidu CAPTCHA 可能再次让 SearXNG 暂时无结果，Processing Center 必须显示来源降级，不能表现为没有候选。
- Asset access 修复覆盖 Passage、SemanticChunk focus、manifest、Page 和全文搜索。12 个访问矩阵 case 已验证未授权正文不回显，公网 normalized Reader Asset、Range 206 和匿名访问边界也已通过。公开、注册、受限和私有四类 Asset 的完整生产 inventory 仍待核实。
- 唯一 Owner 配置已在切换时脱敏核对，identity match 为 true。应用 API、公开注册和 Django 管理表单继续按大小写无关规则保护 Owner 邮箱和重复邮箱。
- 生产事务验收发现的 CuratedClaim `FOR UPDATE + DISTINCT` PostgreSQL 错误已由 commit `4c30565c` 修复并部署。候选镜像和正式容器均通过采用、单 Editor 发布、公开 Work 显示和真实 PDF locator 的外层事务回滚验收，没有测试数据或任务残留。

## 3.0 当前真实限制

- 3.0.2 已正式部署。catalog 0033 至 0039、ingestion 0014、DocumentRevision/Evidence backfill、registry seed、Claim shadow scheduling、Projection reconciliation 和公网 smoke 已执行。生产 readiness 为 3.0.2，pending migration 为 0。最终 tracked tree、部署镜像 label 与远端 release branch 通过发布记录绑定。
- 真实馆藏没有可用的 Claim gold judgment，也没有当前可消费 Claim demand 的 LLM executor。21 个 Claim shadow demand 正确等待，DerivedClaim 与 CuratedClaim 均为 0。因此默认排序不能切换；Opposing Evidence Recall、Qualification Recall、Attribution Error Rate 和 stance accuracy 仍没有 benchmark 前后数字。公开 T4 已看到 direct 2、oppose 2、qualify 1，但这只是查询结果分组，不能替代人工 Gold 或正式质量指标。
- 生产 inventory 中存在 TheorySchool 到 archived KnowledgeNode 的可疑 legacy mapping。目标未发布且名称身份不匹配，migration 没有复制三条旧理论关系。该映射和关系 parity 需要研究者人工确认，不能自动改成另一个理论身份。
- 真实 RTX 4070 worker 当前不在线。协议、权限、heartbeat、lease 与生产离线等待已验证；真实在线领取、模型输出质量和 reconnect 恢复仍待 Laptop 与专用 credential 可用后核实。
- Processing Center 继续展示 optional Provider 降级和缺失 AI capability。T4 时有 21 个 demand 等待 executor，blocking count 为 0，stale Projection 为 0；汇总同时显示 1 类缺失 capability、6 项 Provider 降级和 9 项 Research Source 降级。NLB 没有生产 credential。外部 Provider 不能阻止上传、编辑和发布，也不能把 snippet 当成正式 Evidence。
- 生产已有 9 个 DocumentRevision 和 3,735 个 EvidenceSpan。DerivedClaim、CuratedClaim 与 Claim Gold 均为 0。现存文档质量问题需要通过有限页 OCR 或馆藏清理处理，不应通过虚构 Evidence 或重建 Page 解决。
- 生产有 6 个 paused OCR job，均在本轮切换前已被用户暂停。它们不计入 open ProcessingJob，也不阻断发布；切换过程没有恢复或执行 OCR。
- 3.0 兼容表暂不删除。TheorySchool、legacy Concept、WorkKnowledgeRelation 和旧 identity adapter 只有在 mapping parity、零旧写调用和观察期完成后才可退役。
- 普通 Editor 的生产权限、Revision、Candidate、Claim 发布和公网页码已通过真实 PostgreSQL 外层事务回滚验收。它不等于已经向正式馆藏保留测试修改，持久业务数据仍只由正常编辑操作产生。
- 有限页 OCR 调度可以在生产事务中验证，但实际 OCR 识别仍需真实上架旅程。Ask 登录后 Answer Composer 和 4070 在线领取也继续标记为待核实。

## 2.9.2 已解决项与剩余限制

- 2.9.2 已部署公网。catalog 0032 的 PostgreSQL 16 rehearsal、正式 migration、统一 API/Worker/Beat、Web、容器内 HTTP readiness、Cloudflare、队列、日志、顺序语义检索、Reader Range、公网页面和稳定性观察均已有生产证据。该发布门槛已关闭。
- Research Orchestrator、ResearchContext、44 个 Field Contract、确定性 Planner、12 类 Universal Entity Discovery、自动研究和功能健康已真实运行。后端全量为 678 passed、32 skipped；前端为 Node 118/118、Auth/Scoped Search 21/21、build、TypeScript 和完整 ESLint 通过。32 个环境型 skipped 仍不能写成已执行。
- draft/ready Public API 与页面继续 404，管理员 page preview 正常。React #482 和 API 404/5xx 语义已修复。公开 queryset 没有放宽，PDF preview 与 published Work 未回归。
- 8 条 orphan ResearchRun 已通过有界 RecoveryAction 安全取消并审计。新任务会在保存时预分配 Celery owner UUID，再用同一 task ID 派发，排队任务不会因 Worker 尚未启动而被误判为 orphan。Research productive probe 当前 healthy，相关 incident 已 resolved。
- 最终 fresh 未保存 Person E2E `e285af7a-4949-4567-b765-60739c44df17` 已证明姓名进入 query、精确 Edition、预分配 task ID、VIAF 与 unresolved 多候选、SearXNG 实际调用、FieldLock 与正式关系不变。部署边界探针确认 external_web/SearXNG 始终为 `lead_only` 且 Evidence 数为 0。本次 fresh SearXNG 为零条一般 Web 结果，因此不能写成 fresh SafeWebFetcher 正向 passage 已验证。
- Processing Center 当前准确显示外部来源降级。SearXNG 与 VIAF 正常；OpenAlex 未配置，Wikidata timeout，SafeWebFetcher 和部分 metadata provider 有可见 incident。这些是外部研究质量限制，不影响本馆候选、编辑、公共搜索、Reader 或发布数据安全，也不得靠降低 identity/Evidence 门槛消除。
- Universal Entity Discovery 后端支持 12 类，共享 Picker 已进入九步 workflow 和当前实际维护页中的学者、学科、子学科、理论节点、主题、关系、时间轴与 Reading Path 输入。部分类型仍没有独立 canonical 创建模型，不能把统一发现控件写成绕过原权限和模型的创建编辑器。
- 共享 Interaction Feedback 已覆盖 workflow、research、preview、Processing Center、health 及本轮关键异步动作。全站其余普通 button、`onClick`、`apiRequest`、`window.location` 和 button-like link 尚未形成逐项生产记录，不能据此声称所有普通导航与同步控件都已统一重写。
- Entity Picker 的首个生产版本在责任者两栏表单中向左裁切。最终 Web 改为按列对齐，并让活动 section 在 Picker 打开时使用 visible overflow。最终生产页的 560px 面板完整位于 1265px 视口内，分组、Arrow Up/Down、Escape 与 ARIA 已验证。390、720、1440px 由同版源码自动化与前序浏览器检查覆盖；浏览器原生 Tab 焦点移动仍没有独立生产证据，源码与 Node 回归覆盖 Tab 不拦截。
- 无状态匿名浏览器会用 `/api/auth/me/` 401 和缺少 refresh cookie 的 400 判定未登录，Chromium 因此记录预期资源状态。没有 pageerror、requestfailed 或公共功能失效。若后续要求匿名页面控制台完全无 4xx，可新增返回 200 的只读会话探测接口，不能用吞错或放宽认证解决。
- 普通 non-superuser 管理员公网上传与发布 E2E 没有正常账户，继续标记为 `待核实`。本轮没有创建账户、提升权限或绕过认证。
- 生产测试没有保存、发布、接受 Candidate、建立 Person 关系、自动 merge、覆盖 FieldLock、切换索引或修改 authority。安全结论来自只读状态、审计与前后 hash；真实正常账户的业务 mutation 仍由既有自动化和后续人工操作承担。

## 2.9.1 馆藏策展续作状态与剩余验证

- 2.9 源码已建立统一候选 DTO、字段策略、来源画像和当前工作流内的 Inspector 交互。没有新增数据库 migration，也没有建立第二套 Candidate 或联网 RAG。
- 本地完整后端与前端回归、production build 和 Workflow Playwright 已通过。2.9.1 API/Worker 与最终 Web session-fix 镜像已经部署，公网与正常 Winston 管理员只读浏览器验收通过。
- 生产 SearXNG 发现器返回 200 和 8 条结果。外部站点的长期结果质量、超时与页面解析仍会随环境变化；失败必须继续显示为来源不可用，不能表现成没有候选。普通 Web snippet 仍只能作为研究线索。
- 普通非 superuser 管理员公网上传与发布 E2E 按用户要求跳过，仍为 `待核实`。2.9 部署不能被用作该账户权限路径的证明。
- 本轮没有在生产创建或修改期刊论文，也没有执行 Candidate accept、Reading Path placement、保存、发布或下架。book 与 journal_article 的字段和工作流写入继续以本地自动化为证。
- 2026-08-21 续作已修复并部署。非 Person 实体消歧候选现在进入正确工作步骤；研究按钮遵守 `can_run_enrichment`；Candidate decision 后旧 pending 行会失效并重新读取；可选研究 query 设定 500 字符门槛。匿名 SaveWorkButton 也只在共享 session 确认 authenticated 后读取私人收藏。

## 2.8.1 R2 入库问题状态

- 2.8.1 已部署并完成 R2 到 NAS ingestion handoff recovery。原异常 UploadItem `92ea5bc2-904b-49cd-848f-67accff9639d` 已恢复为 ready，正式 Asset、Work 和 Edition 均已建立。
- 新 Worker 的 12 个 Beat recovery 周期未再出现空文件、nullable join 锁错误或队列堆积。旧 2.8.0 Worker 切换窗口中的两条 ValueError 仅作历史记录保留。
- 普通非 superuser 公网上传与发布的真实账户 E2E 仍为 `待核实`，原因是用户明确跳过李咏琴账户密码测试。该状态不等同于已证明权限路径完整。
- 研究候选层已作为 v2.9 增量实现，并继续复用现有 Candidate、Evidence、QueryLexicon 和 Field Enrichment 权限，没有放宽服务端 mutation 权限。

## 2.8 生产基线历史边界

- 2.8.0 馆藏与策展工作流已经部署生产。catalog 0031 已在 fresh BackupJob 的 disposable PostgreSQL 恢复副本演练，正式迁移后 pending migration 为 0。
- catalog 0031 新增 EditionWorkflowDecision、ReadingPathStage 和 ReadingPathItem stage/position。生产原有 Reading Path、Stage 和 placement 均为 0，因此没有历史路径阶段需要人工合并。迁移前后核心馆藏 ID 集合哈希一致。
- 单 Work Reading Path 和 RecommendationOverride mutation 已有权限、锁、冲突与审计测试。生产页面已只读验收 contextual editor，但没有对真实 Reading Path、RecommendationOverride 或馆藏执行测试 mutation。真实多管理员并发仍为 `待核实`。
- 登录管理员浏览器已验证 Focus Mode、step rail、Inspector、Work-centric Library、Maintenance Mode、策展跳过语义、发布后管理和旧 URL 兼容。book 与 journal_article 的完整写入流程仍以本地自动化和隔离浏览器测试为证；本轮没有在生产创建测试期刊或改动现有书。
- 2.8 没有开发新的互联网 Research & Curation Discovery。Field Enrichment 仍使用既有 structured/web Candidate 和 Evidence；失败继续显式显示，不会自动写 canonical knowledge。
- 2.8.0 时记录的 R2 正式导入事件已经由 2.8.1 recovery 修复并完成正式 Asset 建立。普通非 superuser 真实账户 E2E 仍按上文标记为 `待核实`。

## 当前 2.7 总览

- 六项 master issue 的源码均已进入 2.7，P0 ingestion locking、session bootstrap 和 PostgreSQL 16 BackupJob 已部署。
- 公共观点检索 V2 当前已启用，但只完成有限真实 smoke，盲化人工 qrels 仍未完成。V1 必须继续保留为回退。
- Field Enrichment 已验证结构化 Provider、内网 SearXNG discovery、SafeWebFetcher 和 pending Candidate。未达到 identity 或 evidence 门槛时返回 0 Candidate 是安全结果。
- Ask Library 对注册读者开放个人模型连接，检索仍使用 stable published-library scope。个人模型不能扩大可见范围。
- 当前发布判断为 `PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。需要继续观察大 PDF、后台标签页、真实读者模型和 Authority 数据质量。
- 当前结论和联动关系以 [GPT-HANDOFF.md](GPT-HANDOFF.md) 为首要入口。下文保留的 V2 disabled、SSH blocked 和 2.6.1 状态属于对应日期的历史证据。

## Six master issues

1. STL-001　中英文跨语言观点检索质量。
2. STL-002　field-aware 联网候选与多源证据。
3. STL-003　Ask Library 模型、权限和社会科学 RAG。
4. STL-004　各板块首页与全站搜索的明确 entity scope。
5. STL-005　PDF metadata review PostgreSQL locking。
6. STL-006　Admin / Reader Center session bootstrap。

STL-007 以后记录的是支撑性产品或运维 follow-up，不替代这六项 master issue。

## STL-001 bilingual viewpoint retrieval

状态为源码实现并已有限启用。Task 2A 结构性接入和 Task 2B-0 评测工具已完成，Task 2B-0.5 的隔离数据面已经在真实馆藏备份上运行。公共 V2 已启用，但人工 benchmark 尚未完成，因此质量结论仍需保守。

默认语义模型为多语种 MiniLM，查询切词同时处理拉丁字符和中文，观点检索也支持语言过滤。现有测试能证明同语种查询的基础行为，但没有发现中文问题检索英文材料、英文问题检索中文材料的专项回归，也没有显式翻译模块。关键词降级不具备可靠的跨语言能力。

QueryLexicon 是本问题与 STL-002 的共享基础能力。2026-08-16 已完成 Task 1 核心源码和 Task 1.5 一次性环境验证，见 [query-lexicon-design.md](query-lexicon-design.md)。Task 2A 增加了只供 V2 使用的 search resolver、有界 bilingual branches、ambiguity 保留、entity/cross-language coverage、passage-level language detector 和 evaluation config snapshot。Task 2B-0 又增加了稳定 benchmark schema、V1/V2/lexical/dense 四路 pooling、盲化人工标注包、固定 diagnostic/dev/test split、分组指标、历史 language 审计和 QueryLexicon 双语覆盖审计。英文 entity coverage 的 substring 误命中已经改为拉丁词边界。Task 2B-0.5 新增 search-only bundle、evaluation namespace guard、QueryLexicon 重建、独立 Meilisearch build、snapshot manifest 和 pilot candidate 工具，详细边界见 [semantic-search-evaluation-environment.md](semantic-search-evaluation-environment.md)。

以下是 Task 2B 隔离评测时的历史快照。当时 V2 feature flag 仍关闭，也没有执行生产 historical semantic reindex。真实 corpus repair 使用 PostgreSQL 16.14 副本，并在隔离 Meilisearch 1.37.0 中建立 3,881 文档的 repaired shadow UID `semantic_passages_eval_real_corpus_repaired_20260817_r63`。目标 QueryLexicon revision 为 1，shadow SemanticIndexVersion 状态为 ready，没有 activate。后续 2.7 发布已经建立新的 clean production UID，并在有限对照后启用公共 V2。

公开 V1 的索引版本元数据存在既有漂移。数据库中的 active SemanticIndexVersion 记录 2,543 个文档，而同 UID 的生产 Meilisearch 实测为 3,005 个文档。历史 job 已证明 2,543 是最初两个 Asset 的建立数，后来第三个 Asset 的 462 个文档通过没有 index version 的 active incremental path 写入同一 UID，旧代码没有更新版本记录。公开索引 record ID 与 3,005 个 current ready chunk 完全对应，missing 与 extra 都是 0。旧文档缺少新的 `document_id` 字段，另有 schema drift。生产版本记录仍未修改。源码已移除继续制造该漂移的模糊写入路径；新的 job/直接写入必须绑定唯一 active version，历史 null-version job 无法安全回填时以 `INDEX_VERSION_REQUIRED` 失败。

已新增只读一致性命令和 active 文档数同步。`SemanticIndexVersion.document_count` 对 active version 表示当前 UID 的实际文档数，对 ready 或 retired version 表示冻结时的实际数。`expected_document_count` 保留建立快照预期。metadata-only repair 只允许非 active 且 corpus 与 schema 完全一致的版本。公开 active version 必须继续人工审批，不能由命令自动修正。

真实 authority 暴露了新的主要缺口。public active lexicon 只有 5 个实体和 23 条 entry，Person 为 0，只有 3 个实体具备确认的中英文 canonical 或 translation。馆藏中的 Person 均为 draft，`Pierre Bourdieu`、`布尔迪厄` 和 `habitus` 因此没有统一实体扩展。Legacy TheorySchool 映射到 archived KnowledgeNode 的异常也没有被自动修正。这个缺口必须由 authority 审核解决，不能靠 ranking weight 或自动补译名掩盖。

真实数据审计发现 876 个 failed chunk 全部来自同一 draft Work 的 embedding DNS 失败。它们已在 disposable clone 中使用既有 pipeline 幂等恢复，repaired shadow 达到数据库 ready 3,881 与 Meilisearch 3,881 一致。另有两个 2026-08-09 后没有更新的 OCR job，分别使《实践与反思》和《弱者的武器》仍存在正文与 chunk 覆盖缺口。Production Task 3 部署时，新 Beat 首轮 recovery 重排了这两条 stale job；系统随即停止 Beat、非强杀 revoke并协作式暂停。两条现均为 paused，《弱者的武器》只完成了页65至68，未进入semantic或Candidate。它们仍需独立业务决定，不能靠 ranking 处理。

原 34 条 diagnostic 候选已在 repair 前完成 V1、baseline_v2a、lexical、dense 四路 top 10 pooling，共 766 个待判断 candidate。该包现标记为 `pre-corpus-repair`，不得作为正式 qrels，也不应继续人工标注。所有 query 仍无 gold，usable benchmark query 为 0。必须先在 3,881 文档 repaired corpus 上重新 pooling，之后才能比较同一 corpus 上的 shadow baseline 和 shadow V2。

下一步先由管理员决定是否恢复两个 paused OCR job，再在 repaired corpus 上重新 pooling 34 条候选。管理员确认约 30 条 pilot 后，先完成 3 至 5 条 query 的全部盲标。Person 状态、结构化译名和真正英文正文的馆藏仍是独立数据任务。只有 pilot 成功、80 至 120 条工作量可估算且 test split 可封存后，Task 2B-1 才能只用 dev 比较 branch budget、profile 和权重。

证据位置包括 `api/config/settings.py`、`api/catalog/services/semantic_indexing.py`、`api/catalog/services/semantic_index_consistency.py`、`api/catalog/management/commands/audit_semantic_index_consistency.py`、`api/catalog/services/semantic_search.py`、`api/catalog/services/semantic_search_v2.py`、`api/catalog/services/semantic_search_benchmark.py`、`api/catalog/services/semantic_search_evaluation_environment.py`、`api/catalog/services/query_lexicon/search.py`、`api/catalog/services/passage_language.py`、`docs/search-evaluation.md`、`docs/semantic-search-evaluation-environment.md` 和 `evals/semantic_search/task2a_cross_language.schema.json`。

## STL-002 field-specific web enrichment

状态为 Task 5 IMPLEMENTED，等待 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。没有 production deployment、production migration 或真实 Provider crawl。

Task 5 已建立统一 FieldEnrichmentRequest、FieldPolicyRegistry、SourceClass、StructuredSourceAdapter、可替换 WebSearchAdapter、安全 fetch、EnrichmentCandidate/Evidence 与 FieldMutationRegistry。请求按已有 target 与 field 执行。来源优先级、identity gate、证据数、冲突、refresh 和 Accept 路由都由 field policy 集中定义，不再散在前端 draft、Provider 与 serializer。

Wikidata、VIAF、LOC、OpenAlex、Crossref、OpenLibrary、Google Books 与 GROBID 都复用现有实现。可配置 SearXNG 只发现 URL，snippet 不会成为 Evidence。实际页面 fetch 保存 supporting span、canonical URL、title、domain、retrieved time、HTTP metadata 与 checksum，并拒绝私网、回环、link-local 和 redirect 后的 private target。Provider error 会按 unavailable、timeout、rate limited、fetch blocked、invalid source 和 parse failed 分类，其他来源结果仍可显示。

候选分 FACTUAL、CLASSIFICATION 与 INTERPRETIVE。Person 同名没有第二身份因素时不会产生字段候选。理论关系只靠共现不会生成；解释性 relation 默认要求两个独立来源。Accept 在单事务重新验证 policy、identity、evidence、staleness、current value 和 FieldLock，再写 PersonNameVariant、ScholarProfile、Work/Edition、KnowledgeNodeAlias、pending classification、pending KnowledgeRelation、timeline 或 ReadingPath source-of-truth。服务不直接写 QueryLexiconEntry，不自动发布、不自动 Accept，也不触发 semantic reindex。

代表字段已打通 Person identifier/affiliation/name variant、Edition publication year/publisher/ISBN、Work first publication date、KnowledgeNode alias/discipline/subdiscipline、KnowledgeRelation、timeline、Topic discipline 与 ReadingPath item。旧 AuthoritySuggestions 已降为显式只读 identity discovery，不再直接填 draft。旧 Metadata Review 继续兼容，最终是否与通用候选 UI 合并留到综合验收。

新增 migration 为 `catalog.0029_field_enrichment`，只创建 schema/index/constraint 并扩充 relation choices。本阶段没有应用 production migration。SearXNG 未部署，真实 Provider 质量、服务条款、真实 rate limit、网页解析覆盖、PostgreSQL migration 和管理员真实流程都属于最终综合验收。

证据位置包括 `api/catalog/services/field_enrichment/`、`api/catalog/enrichment_views.py`、`api/catalog/models.py`、`api/catalog/migrations/0029_field_enrichment.py`、`web/components/field-enrichment-control.tsx`、`api/tests/test_field_enrichment.py` 和 [field-enrichment-inventory.md](field-enrichment-inventory.md)。

## STL-003 library RAG

状态为 Task 6 IMPLEMENTED，等待 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。本阶段没有 production deployment、production migration、真实模型调用或大型 RAG evaluation。

AI runtime 已按 metadata extraction、Library QA 与可选 field enrichment capability 分离。非密钥 profile 使用私有 SiteSetting 与 AuditEvent，secret 和 endpoint 只通过服务器环境 alias 解析。Admin Settings 可以配置模型与受控生成参数并做安全健康检查。Library QA 不再被 metadata model 的必填校验阻塞，所有 provider HTTP 已收敛到共用 AIClient 的 generate、stream 与 health check。

LibraryQuery 已对齐 Task 4 的 plural scope contract，未知、不可公开和空 corpus scope 都不会静默变成全馆查询。公开 query understanding 只使用 QueryLexicon public_active。LibraryRetrievalService 默认强制 stable V1；experimental_v2 只允许管理员显式 debug，不改变公开 feature flag或 ranking 参数。比较问题使用双方独立约束分支；无法可靠解析两个公开实体时保留可查看的 passage，但不进入模型综合。逐字引文使用 keyword literal path，其他 entity anchor 分支数量有硬上限。

回答只依据已持久化 LibraryEvidence。Evidence 可以定位 Work、Edition、Asset、Page、document ID、原始 passage、实际语言和 Reader URL。无有效公开证据、检索错误、比较双方覆盖不完整、原句未找到或模型未给出有效 citation 时，服务明确返回证据不足，不自由回答。历史 assistant answer 不成为 evidence，馆藏文本没有 system 权限。Ask 不联网、不写 EnrichmentCandidate、QueryLexiconCandidate 或 authority。

Explore Ask 已改用 cookie-first session bootstrap。不可恢复的 401、403、429、认证临时错误与 provider failure 分开处理，只有 401 触发认证重验。Reader、Scholar、Theory 与 Topic 页面共享一个 scope-aware Ask 入口。旧 `/api/catalog/library-question/` 已删除；`_scope_filters`、`retrieve_library_sources` 和无语义的 provider compatibility wrapper 也已删除或改为命名服务。AssistMode.OFF 与 singular scope aliases 仍需在最终 reading migration 中规范化。

新增 migration 为 `reading.0005_library_ai_runtime_rag`，只增加 message runtime/query metadata 与 source Page/language/provenance/deep-link字段，没有 AI 调用、数据扫描、索引重建或 authority mutation。本阶段没有应用 production migration。Task 6 核心后端 35 项和较宽相关选择器 89 项通过；前端 Task 6 Node 4 项、Auth session 13 项、TypeScript、targeted ESLint 与 production build 通过。Django 静态门槛也已通过。

证据位置包括 `api/common/ai_runtime.py`、`api/ingestion/services/ai_client.py`、`api/reading/library_query.py`、`api/reading/library_retrieval.py`、`api/reading/library_assistant.py`、`api/reading/runtime_profiles.py`、`api/reading/migrations/0005_library_ai_runtime_rag.py`、`api/tests/test_library_rag_task6.py`、`web/components/explore-ask-client.tsx` 和 [library-ai-rag-inventory.md](library-ai-rag-inventory.md)。

## STL-004 scoped search

状态为 Task 4 IMPLEMENTED，等待最终综合架构验收。

Task 4 已建立统一 SearchContext 和 SearchService。Scholar、Topic、Subdiscipline、Theory、Work、Discipline 与 ReadingPath 都有明确 entity domain；global 必须显式并按组返回。Entity Search、Semantic/Viewpoint Search、Reader文档内搜索和图谱内筛选保持不同职责。

Public Scholar同时要求Person verified和ScholarProfile published，QueryLexicon匹配只用public_active。Theory采用KnowledgeNode canonical identity并抑制mapped legacy重复；Topic保持独立identity；Work按Work去重Edition。主要目录搜索与分页状态写入URL，Subdiscipline和Admin Scholar不再只筛当前页数组。

旧无context global payload、mixed theory-system search、legacy TheorySchool presentation route和旧array loaders暂时兼容。它们的删除/合并决策留到 FINAL INTEGRATED ARCHITECTURE ACCEPTANCE。

Task 6 已让 LibraryConversation scope 复用本节的 plural context contract，并保留有限 legacy singular aliases。最终是否删除兼容 aliases 留到综合验收。

证据位置包括 `api/catalog/services/scoped_search.py`、`api/catalog/views.py`、`api/catalog/knowledge_views.py`、`api/catalog/theory_system_views.py`、`web/lib/search-context.ts`、`web/lib/server-api.ts`、主要目录页面和 `docs/scoped-search-inventory.md`。

## STL-005 PostgreSQL nullable-join FOR UPDATE failure

状态重新打开。原 metadata/entity resolution 锁点已修复并通过 PostgreSQL 验证，但 2.8 上线后的真实 R2 staging recovery 仍触发同类数据库错误。

2026-08-20 的生产只读检查发现，`process_r2_staging_job` 在恢复 UploadItem `92ea5bc2-904b-49cd-848f-67accff9639d` 时反复报 `FOR UPDATE cannot be applied to the nullable side of an outer join`。关联 ProcessingJob 为 `ca68dde3-f1b4-4e0b-872d-45fc1e3ba261`。这证明先前审计没有覆盖 R2 import/recovery 的全部锁查询。当前尚未完成源码定位，也没有修改生产记录。

历史错误为 PostgreSQL 不允许对可空外连接一侧执行 `FOR UPDATE`。2026-08-16 的 P0 修复审计了 `api/ingestion` 中全部锁点。实体消歧、候选持久化、OCR PDF 和后台 backfill 现在都明确限定主表，元数据复核则依次锁 UploadItem、Edition 和 Work。候选持久化还以 UploadItem 父行为并发协调点，能够覆盖当前候选集合为空的情况。没有删除必要锁，也没有捕获后忽略数据库异常。

同一次修复补上 ProcessingJob 的 PostgreSQL 行级 claim、`task_id` 所有权检查和周期恢复。Redis 消息仍只负责唤醒，stalled 或 broker notification 丢失的 OCR、页码和 metadata enrichment 任务会由现有 ingestion recovery task 重新发现。历史 failed UploadItem 可以复用原 PDF、Work、Edition、Asset 和人工锁，从安全预检阶段继续。下架后重新发布的 PublicationEvent 长业务键也会稳定压缩到既有 120 字符字段，不需要 schema migration。

原 69 项 PostgreSQL 回归中的 12 项 ingestion 失败已经通过。第 13 项是 authority provider 线程连接绕过 pytest 主事务所造成的 SourceRecord 测试隔离问题，单独运行通过，不属于本问题。新增 9 项 PostgreSQL integration 全部通过。宽口径 155 项相关回归为 152 项通过，剩余 3 项均是封面测试关闭 FileResponse 后继续使用已关闭测试连接，与 ingestion 修改无关。生产部署、生产历史记录 retry 和真实 Celery worker 被强制终止后的演练仍为 `待核实`。

证据位置包括 `api/ingestion/views.py`、`api/ingestion/tasks.py`、`api/ingestion/services/entity_resolution_decisions.py`、`api/ingestion/services/candidate_store.py`、`api/ingestion/services/ocr_pdf.py`、`api/ingestion/services/processing.py`、`api/tests/test_ingestion_postgres_integration.py` 和 `api/tests/test_ingestion_integration.py`。

## STL-006 auth initialization failure

状态为源码已修复并通过本地真实 Cookie 浏览器验证，生产部署待核实。

根因有两项。第一，前端曾把 `library_session_active` 当作进入受保护页面的前置条件，导致有效 HttpOnly Cookie 在 localStorage 被清理或不可用时无法恢复。第二，Reader Center 曾把 `/auth/me/` 与八类阅读资源放入同一个 `Promise.all`，任一资源的 403、500 或网络错误都会清理会话并跳回登录。

2026-08-16 已建立统一 session bootstrap。Admin、Reader Center 和作品笔记深链接都会先用服务器 Cookie 请求 `/auth/me/`，并区分 loading、authenticated、unauthenticated、forbidden 与 temporary error。只有 refresh 后仍不可恢复的 401 会清 session。403、5xx、429 和网络错误保留会话。Reader Center 使用独立资源状态，一个模块失败时其余模块仍可显示。

同一标签页的 refresh 使用共享 Promise。支持 Web Locks 的浏览器还使用跨标签 refresh lock 与 revision，避免旋转 refresh token 被并发使用。storage、focus 和 pageshow 会触发服务器重验，角色变化和另一标签页 logout 不依赖旧的本地缓存。后端日志现在以无凭据方式区分 `no_cookie`、`expired_session`、`invalid_session`、`user_not_found`、`permission_denied` 和 `refresh_failed`。

本地验证包括 16 项 accounts 测试、13 项前端 session 行为测试和 13 项 Playwright 流程。其中 1 项使用真实 Django API、真实 HttpOnly access/refresh Cookie 与一次性 SQLite 数据库，覆盖读者登录、删除 hint 后刷新、logout 和切换管理员。最终综合阶段又把所有旧 `getStoredAccessToken()` 调用迁移到始终发送 cookie credential 的 `getServerSessionCredential()`，17 项 Auth/Ask 前端回归通过。生产公网与局域网 hostname、HTTPS Secure Cookie、真实 Edge 代理和既有生产 session 仍为 `待核实`。

本任务按边界没有修改 Explore Ask。该 RAG 界面仍有自己的 401/403 合并判断，后续只能在 STL-003 范围内处理，不能据此否定 Admin 与 Reader Center 的本次修复。

证据位置包括 `api/accounts/authentication.py`、`api/accounts/cookies.py`、`api/config/exceptions.py`、`web/lib/api.ts`、`web/lib/session.ts`、`web/lib/use-session-bootstrap.ts`、`web/components/admin-shell.tsx`、`web/components/reader-center.tsx`、`web/tests/auth-session.test.mjs` 和 `web/tests/auth-bootstrap.spec.ts`。

## FINAL INTEGRATED ACCEPTANCE 当前阻塞

本地源码收敛已完成一组安全修复：protected PDF 不再使用 shared public cache，chunk assembly 同步保存 SHA-256，SemanticIndexJob 禁止模糊 active UID 写入并提供 `INDEX_VERSION_REQUIRED`/`MODEL_UNAVAILABLE` 错误码，缺少 active version 时异步 enqueue 不会污染入库状态，旧 Ask 503 route 与未使用 compatibility functions 已删除。2.7 的本地后端、前端、migration drift 和构建门槛通过。

本轮授权使用的临时 RSA 私钥与对应公钥指纹一致，但 2026-08-19 对 `Winston@192.168.5.6:22` 仍返回 `Permission denied (publickey,password)`。本机也没有 Docker 或 PostgreSQL 16 runtime。因此当前生产容器、数据库、NAS、真实模型、真实 Provider、fresh backup、统一 migration rehearsal、clean active index 和浏览器生产联动均不能据称通过。SSH 恢复前不执行 production migration 或公网 cutover。

## STL-007 resumable large PDF upload

状态为 R2 multipart 已部署，但正式导入存在生产阻断项。

2026-08-20 的部署验收发现一个 `staging_status=uploaded` 项仍没有本地 FileField。Beat 每分钟恢复时，旧 `process_upload_item` 路径报 `The 'file' attribute has no file associated with it`，R2 staging job 又遇到 STL-005 的 PostgreSQL 锁错误。Celery active、reserved、scheduled 在抽样时为空，但数据库 pending job 会继续被 Beat 唤醒。本轮按用户要求不修复或重置任务，R2 object 也未删除。

旧公网实现把 2 MiB PDF chunk 逐片发送到 Django，XHR `timeout=0`，current speed 只在 progress event 更新，ETA 优先累计平均速度。连接半开时没有新事件，旧速度不会下降，也没有 stall abort，因此会长期显示正常速度和短 ETA。页面状态又主要位于 React 与 localStorage，切页或刷新后可见进度丢失。

2.7.1 Web 只通过 presigned UploadPart URL 把 PDF 发送到 R2 staging。默认 part 8 MiB、每文件 3 并发、全局 6 连接、18 秒 stall abort、每 part 最多 3 次退避重试。近期 5 秒速度窗口在停顿时归零，ETA 不再使用旧累计平均值。UploadItem 数据库存 owner、part 与 ETag；站内切页由全局 manager 保持 XHR，刷新后页面从服务端恢复任务并明确要求重新选择同一 File。

R2 完成后由 Ingestion Worker 流式导入原有 intake/NAS storage并继续既有 pipeline。R2 不作为永久书库。正式入库失败保留 object，cleanup 失败不撤销 ready，Beat 可恢复。3 天 Lifecycle 和 1 天 incomplete abort 只作兜底。

仍需观察真实慢速网络、浏览器后台节流和 R2 上游错误率。浏览器刷新无法保留 File 对象，这是浏览器安全边界；系统不会伪装为能够无文件继续读取本地磁盘。

证据位置包括 `api/ingestion/services/r2_staging.py`、`api/ingestion/views.py`、`api/ingestion/migrations/0013_uploaditem_staging_backend_and_more.py`、`api/tests/test_r2_staging_upload.py`、`web/lib/r2-multipart-upload.ts`、`web/components/admin-upload.tsx` 和 `web/tests/upload-metrics.test.mjs`。

### 2.7.1 PDF illegal Unicode repair

生产失败项 `9ce0b150-eca4-4872-9baf-d0a09cf08704` 已确认在 text extraction 第 32% 失败。PyMuPDF 从 PDF 字体返回 `封面` 后跟两个孤立 low surrogate，psycopg 无法把该 Python 字符串编码成 UTF-8。2.7.1 在 PDF/OCR extraction boundary 与 persistence defense 两层把孤立 surrogate 替换为 Unicode repair mark。正式重试已越过该阶段并达到 ready 100%，规范 Asset 保存 596 Page。原始 PDF、人工元数据和已保存字段未被改写，也没有自动发布。

## STL-008 BackupJob PostgreSQL client compatibility

状态为 resolved。正式 BackupJob 和同一 artifact 的 disposable restore rehearsal 均已通过。

真实根因是 PostgreSQL server 16.14 与原 API 镜像 pg_dump/pg_restore 15.18 不兼容。生产 Worker 日志明确记录 pg_dump 因 server version mismatch 退出，排除了网络、数据库权限和 NAS 目标路径问题。

API 镜像现已固定 PostgreSQL 16 client。BackupJob 在导出前检查 server、pg_dump 和 pg_restore major，密码只通过子进程环境传入，错误会脱敏。API、Worker、Ingestion Worker 与 Beat 已统一使用 pg_dump/pg_restore 16.15。正式 BackupJob 生成 9,944,031-byte artifact，SHA-256 为 `9376ba2f86bde08675f2ad8d335193daea24c40165bc2bd1d8ab4643365c50b6`。

同一 artifact 已恢复到 disposable PostgreSQL 16.14。关键馆藏、authority、ingestion、BackupJob 和 migration 表的数量与 ID hash 均和 source 一致，Django check 通过。该备份与恢复门槛建立时，source 仍是 catalog 0026、ingestion 0010且不含QueryLexicon/Candidate表。随后Production Task 3已在该门槛保护下应用0027/0028/0011。

证据位置包括 `api/Dockerfile`、`api/distribution/database_backup.py`、`api/distribution/tasks.py`、`api/distribution/management/commands/rehearse_database_restore.py`、`api/tests/test_distribution_backup.py`、BackupJob 运行记录和 `docs/PROGRESS.md`。

## STL-009 PDF to QueryLexicon candidate coverage

状态为 Task 3 DONE。Candidate 机制、PostgreSQL migration、完整 authority resolver 和真实 corpus 已通过最终验收；真实结果为 authority coverage gap。

Task 3 已新增 QueryLexiconCandidate/Evidence、deterministic pair extraction、exact batch resolver linking、Person 身份保护、跨 Work evidence 去重、Admin Accept/Reject 和 ProcessingJob 异步恢复。Accept 只写 PersonNameVariant 或 KnowledgeNodeAlias，再由既有 ChangeEvent 更新 QueryLexicon；pending/rejected 不改变 revision，也不直接写 Entry。

PostgreSQL 16.14 完整 authority 副本包含 6 Person、2 KnowledgeNode 及 Discipline、Subdiscipline、TheorySchool、Topic、LegacyKnowledgeMapping。0028/0011 首次应用、回退和重应用均成功，migration 前后 authority、3,881 SemanticChunk、SemanticIndexVersion、ProcessingJob 和 QueryLexicon state hash 不变。

QueryLexicon active revision 为 1。public_active 是 5 entity/23 entry，admin_resolvable 是 12 entity/61 entry。6 个 Person 全部为 draft，public 为 0，但 candidate extraction 可以通过 admin scope 解析其 authoritative canonical term。公开 search 仍只使用 public scope。

最终 5 Work、1,989 Page、3,881 chunk 扫描得到 1,652 observations、1,473 个有效结构 pair 和 1,387 个 unique pair。funnel 为 no canonical anchor 1,473、invalid/noisy 179，其余六类均为 0。两次 commit 完全幂等，Candidate、Evidence 和 authority 增量均为 0。

该结果正式归类为 `REAL CORPUS / AUTHORITY COVERAGE GAP`。Task 3 不再通过扩展规则追求正数 Candidate。后续 authority 编辑可以自然增加 exact anchor coverage，但不得自动发布 Person、创建 KnowledgeNode 或把 generated alias 提升为 verified translation。本问题不要求 semantic reindex，不改变 Task 2B-1，也不启用公开 V2。

2026-08-17 已完成 Production Task 3 Deployment。catalog 0027/0028 与 ingestion 0011 均 applied；生产 QueryLexicon revision 1、generation `af302b64-1b3f-447d-88ca-5ed505bc87e9`、69 entries，public 5/23、admin 12/61。单个真实 Asset 两次 extraction 复用同一 succeeded job，Candidate/Evidence 仍为 0，revision 与 active semantic UID 未变化。公开 V2继续关闭。

证据位置包括 `api/catalog/services/query_lexicon/candidates.py`、`api/catalog/models.py`、`api/ingestion/services/processing.py`、`api/catalog/management/commands/extract_query_lexicon_candidates.py`、`api/tests/test_query_lexicon_candidates.py`、`docs/query-lexicon-design.md` 和 `docs/PROGRESS.md`。

## STL-010 QueryLexicon Candidate review surface

状态为已部署。Next Admin 已有 Candidate review 页面，Django Admin 继续保留低层维护入口。统一页面已经明确显示这是跨领域审核队列，不是自更新词典。

生产 API 内部使用真实管理员权限渲染 Candidate 与 Evidence changelist 均为 HTTP 200。status、linking、candidate type、term type、language、extraction version filters，Evidence inline，Accept/Reject actions 和 Asset discovery action 都存在。公网 `/admin/catalog/querylexiconcandidate` 由 Next 管理前端接管并返回 404；当前 Nginx 也没有把 Django `/admin/` 暴露到公网或LAN Edge。

这不影响 Candidate extraction、事务、审核模型或历史单Asset smoke。2.7 部署后仍需在真实权限下确认 Next Admin 页面与 API 的一致性。不得为解决入口问题放宽权限或公开无保护的 Django Admin。

证据位置包括 `api/catalog/admin.py`、`api/config/urls.py`、`deploy/nginx/default.conf.template` 和 `web` 当前管理路由。

## Version 2.7 architecture follow-up

状态为已部署并进入人工观察。旧后台入口已整理为统一信息架构，新增 capability contract、Knowledge Workspace、QueryLexicon Workspace、Projection Status 和 System Status Center。Unknown Entity 不再只落入 rejection funnel，而是保留可审计观察并聚合为 NewAuthorityCandidate。Candidate Review 对 field/query lexicon 只允许 accept/reject，对 New Authority 只允许 Match Existing/Create Draft/Reject；统一 envelope 显示标准审核状态并保留领域子状态。Provider 状态页区分 configured、not_configured 与尚未探测的 health unknown。

Projection Refresh 复用现有 `ProcessingJob`、Celery worker 和 recovery，不建立第二套队列。单目标刷新只协调既有 QueryLexicon event、semantic job 和 PDF candidate job，并保持幂等、可重试和非阻断。

后台发布、审核、处理控制和 Ask 实验模式的关键判断已改用同一 capability contract；用户角色字段仍只作为兼容展示和账户治理规则，不作为新后台 API 的唯一授权依据。普通 Admin 可以只读查看 QueryLexicon 与 Semantic Index；reconcile、索引激活和破坏性维护仍受 manage capability 保护。System Status 主导航复用实际 Celery broker/control/heartbeat 证据，旧 System Health route 仅作为兼容诊断入口。

仍需在最终阶段验证真实部署中的容器版本、migration head、队列、NAS、Meilisearch、AI provider 和 web provider。未完成真实环境检查前，不把本地源码状态写成公网已部署。

### 2026-08-19 2.7 门槛刷新

本地源码门槛已再次通过。后端收集 547 项、9 项按环境跳过，前端通用 63 项与 Auth/Scoped Search 17 项通过，Django check、migration drift、compileall、TypeScript、ESLint、Vinext build 和 diff check 通过。目标主机仍拒绝已授权 RSA 公钥，公网 readiness/health 仍报告 2.6.1；因此 FINAL INTEGRATED ACCEPTANCE 与 PUBLIC CUTOVER 继续保持 `BLOCKED`，未执行任何生产 migration、部署、active index 切换、公开 V2、authority publish 或 Candidate accept。

### 2026-08-19 2.7 live deployment update

上述 SSH 阻塞已解除。真实生产已部署 commit `7cd68d30776c0c652e080d147959a3183a92b71b`。catalog 0030、ingestion 0012、reading 0006 已 applied；fresh BackupJob、QueryLexicon reconciliation、clean semantic UID audit 和 active switch 均成功。生产保持 V2 false、Ask stable、AI/Web `NOT_CONFIGURED`，没有自动发布 authority 或 Accept Candidate。

当前总状态为 `PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。尚待用户进行登录后的 Admin、Reader Center、Ask、Candidate Review 人工测试，以及对真实 Provider 配置后的功能验证。

## 2.7 post-cutover usability findings, 2026-08-19

### Reader-owned Ask provider

状态为已部署。读者可以在 Ask 页面配置自己的 OpenAI-compatible、Ollama 或 vLLM 服务。凭据加密保存，不进入浏览器存储、日志或 API response。没有个人连接时，若服务器默认 profile 可用则使用默认服务；两者都不可用时明确显示配置入口和证据边界。`reading.0007_reader_ai_connection` 只创建连接表和索引，不会联网或改馆藏。

### Admin session and upload disappearance

状态为源码已修复，公网人工流程待核实。可见性切换和 pageshow 只做有界后台探测；临时网络/5xx 和单次后台 401 不再把已认证上传工作区卸载。跨标签 logout、明确 403 和后续受保护请求仍会执行服务器权限判断。拖拽上传增加键盘入口、拖拽深度处理、类型提示和现有分片恢复反馈。

匿名浏览器在没有 refresh Cookie 时，SimpleJWT refresh endpoint 会返回 400。客户端过去把它当成认证服务故障；现在只对该 refresh endpoint 将 400/401 统一视为无可恢复会话，正常显示登录提示。其他 API 的 400 不受影响。

Reader 过去使用恒为真的 cookie credential 标记判断登录，导致匿名访客也请求批注、书签、进度与历史接口。它现在复用 session bootstrap，并在 session 确认为 authenticated 后才访问私人记录。退出登录后页面内已加载的私人批注与书签会清除。

### Reader layout

状态为源码已修复。纸本页码是可选工具栏单元，已从隐式网格列中分离并在窄屏隐藏。OCR 状态通知回到文档流，不再覆盖 PDF 页面。尚需在真实生产浏览器以不同缩放、侧栏组合和长标题做人工观察。

### Authority/web enrichment errors

状态为源码已修复。结构化来源和网页来源现在返回部分结果、provider/error 分类和 request id；snippet 仍不被当作证据。没有达到 identity/evidence 门槛时，页面展示拒绝原因和统计，而不是只显示“没有候选”。真实 provider 可用性、条款和内容质量仍需单独核实，不应通过降低身份阈值解决。

生产 smoke 发现 VIAF 会返回 `result: null`。旧解析器对 null 切片导致 TypeError，且并发聚合器让这一家来源的失败清空全部结果。列表字段现先做类型规范化，单个 Provider 的网络或解析失败只形成 warning，本地及其他来源结果继续保留。

Person 字段补全过去只用列表中的第一个中文规范名，VIAF/LOC 经常因此无结果。现在只有首个查询完全没有结构化记录时，才以同一 authority 对象的已确认原文名再查一次。它不会使用生成拼音、unidecode 或低信任 alias，也不会绕过出生年份、标识符、机构和作品等身份条件。

编辑器的身份发现按钮优先使用表单中的原文/外文名称，并显示当前实际检索词。该表单值只帮助管理员发现来源；没有保存和人工审核前，不会成为权威数据或检索词典条目。

VIAF AutoSuggest 同时返回人物和统一题名记录。Person adapter 现只接收 `personal` heading，并仅从 heading 末尾明确的四位年份区间提取生卒年。统一题名不会再伪装成人物证据，日期不合法时仍按缺失处理。

### Candidate Review semantics

状态为源码已修复。All Candidates 已改名为候选审核中心，明确它是跨领域 review queue，不是自更新社会科学词典。Metadata、QueryLexicon、Field Enrichment、New Authority 和 Theory task 继续各自写入 source-of-truth；QueryLexicon 仍是 derived projection。统一列表支持准确总数和截断提示。

### Release gate result

Fresh BackupJob、`reading.0007` migration plan/migration、统一镜像发布、公开 Reader/Ask/Range smoke 和真实 Provider smoke 已完成。布迪厄产生的 1 条真实字段候选保持 pending，未自动接受。没有发布 draft authority、改 ranking 或 semantic reindex。公开 V2 在五条生产对照查询无 fallback 后按用户授权启用，Ask 仍固定 stable retrieval。

General web 的运行缺口已用固定版本、内网专用的 SearXNG service 收敛。它不暴露公网，也不直接写 Candidate；只有后续 SafeWebFetcher 取得真实页面和 supporting passage 后才可能形成 Evidence。真实搜索引擎上游的限流或阻断仍会按 provider partial failure 展示。
