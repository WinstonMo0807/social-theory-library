# Social Theory Library 3.0 Verification Ledger

更新时间：2026-08-28

本记录只登记实际执行的检查。环境依赖、生产验证和真实馆藏质量评估在完成前均标为待核实。工程严格按四个 Wave 推进，不再拆分子 Phase。

## 3.0.3 Public Knowledge Control

| 改动 | 风险 | 已执行验证 | 为什么足够 | 生产综合验收 |
| --- | --- | --- | --- | --- |
| Scholar 公开资格与发布传播 | 高 | 公开资格、直接发布、EditorialRevision、收敛 dry-run、DomainChange、旧时间线与推荐消费者定向测试通过；生产只读盘点为 published 4、eligible 0、Person draft 4 | 覆盖单一资格规则、阻止 rejected 或 merged 恢复，以及 Person 变化的依赖传播 | fresh backup 后有界 apply，公开 API、页面和 Projection 反向核对 |
| PublicPageContract 与受保护 Preview | 高 | 后端 13 项定向通过；管理审计返回 status ok、Scholar 9、Theory 7、Topic 8，路由和字段均 100%；前端公共页面与 Preview 测试通过 | 同一 serializer、同一公开组件、草稿状态、no-store 和匿名拒绝均有契约 | 正常 Administrator 会话预览与匿名拒绝 |
| Reader Evidence 定位 | 高 | EvidenceSpan locator、Passage focus、Viewpoint 无关同页拒绝、Ask 与 CuratedClaim Reader URL 定向测试通过；生产 active EvidenceSpan 3,735，空 bbox 0 | 覆盖页面、访问权限、active revision、stale 与文字匹配边界 | 原文、观点、Ask 各取真实结果，核对 focus text、bbox、Range 206 与可见高亮 |
| 检索页面与 Explore 视觉收敛 | 中 | 观点检索和公共页面 Node 测试通过；TypeScript 与完整 lint 退出 0；production build 成功 | 共用模式切换与筛选外壳，同时保留观点立场分组；暖纸色来自现有 token | 公网路由、窄屏和模式切换 smoke |
| Processing Center 七工作面 | 中 | Processing Center、Provider 设置与功能健康改动面通过；首次完整 Node suite 仅旧组件调用断言失败，更新后受影响文件 7/7 通过 | URL 状态、功能影响、OCR 健康、焦点样式、Provider 删除确认均覆盖 | 正常 Administrator 会话核对七分区、Provider 降级和 Worker 状态 |
| 综合代码门槛 | 高 | 后端完整 `api/tests` 回归退出 0；Django check、migration drift、PublicPageContract audit、TypeScript、完整 ESLint、前端 production build 与 `git diff --check` 通过 | 只对首次完整前端执行暴露的过期断言重跑受影响文件，符合风险驱动规则 | 同源 tree、镜像 label、部署记录和最终 Git tree 一致 |
| 备份与回退 | 高 | BackupJob `a6ec015b-ef36-46c7-9cc2-735920120461` 完成；archive SHA-256 `e2171e337c34bee1d727389abc8438e101728204c3038dfc6543cb3a83487532`；database SHA-256 `7a0d09a005a6cd87bb6ccdf0030f940854ecc13b7f9e6db675ff40ab1c3ba46d`；隔离 PostgreSQL 16 实际恢复、Django check、空 migration plan、馆藏及 identity hash 匹配 | 证明数据库备份可读且旧 3.0.2 image 可直接作为应用回退，无需反向 migration | 切换后验证回退脚本、旧标签和 readiness；不执行破坏性 restore |

生产源码冻结前确认 OCR 全局暂停，6 个 OCR job 为 paused；21 个 `llm_small` demand 等待 capability，publication blocking 为 0；14 个 ProjectionState 全部 current；活动语义索引为 3,005/3,005。3.0.3 不改变这些策略。

## 3.0.2 Product Convergence

| 改动 | 风险 | 已执行验证 | 为什么足够 | 最终综合验收 |
| --- | --- | --- | --- | --- |
| 生产源码 reconciliation | 高 | Git ancestry、远端 `88ded54`、生产 source revision 与 image ID 只读核对；803 个 tracked file 冻结为候选树 `f0ffad378928591691df45770ad32d3bbd062a50`，归档 SHA-256 为 `06d4a5f8024456ccd5fd1832f22e6071e17995de92a401b9e0703a8094598959`，archive 与 tree membership 差异为 0 | 证明 `fa7444d` 与 `4c30565c` 已包含在开发基线，且首轮生产镜像来自严格 tracked tree | 正式发布重新冻结包含生产记录的完整 tree，并核对同源镜像 label、部署记录与最终 Git commit tree |
| CandidateDecisionProtocol 与 Field Producer Matrix | 高 | Candidate、Provider、OCR 与 remote worker 组合 78 项通过；Research、Viewpoint、Dependency 与 publication 组合 82 项通过；改动面前端 77 项通过；生产 Workbench bundle 与实际候选 payload 已核对 | 覆盖多类候选动作、local-first、producer 状态、discovery lead 转换及三个管理工作面的同一动作契约 | 已完成首轮生产只读 smoke；真实业务采用质量继续由正常编辑操作积累 |
| KnowledgeObjectEditorAdapter、Completeness 与 Knowledge Growth | 高 | Knowledge Studio 与 Growth 后端 6 项通过；前端 Knowledge Studio 9 项通过，并验证六类公开详情页与受保护预览共用组件 | 覆盖公开 serializer、EditorialRevision、Dependency metadata、有界派生读模型、Canonical 不变和 private/no-store | 对象发布与公网反向验证 |
| SafeWebFetcher 分类与持久化 | 高 | SafeWebFetcher 所在 Candidate/Provider 组合通过，含 DNS、TLS、redirect、HTML robots、GB18030、流式大小、失败 SourceRecord 与 URL query 脱敏 | 覆盖中文正文可读、页面使用指令、无 Content-Length 大响应和可操作诊断 | 生产合法公开来源正向与失败 smoke |
| Library Synthesis | 高 | Evidence-only synthesis、task profile、远程 worker 服务端与客户端均包含在 78 项组合中并通过 | 只接受馆内 EvidencePack，没有 executor 时保留 waiting | 生产 waiting 解释；若有 executor 再验证采用与 Evidence refs |
| ProviderCredentialSecret 与 NLB adapter | 高 | Research Source 与 NLB 20 项通过；密文、Owner 权限、不回显、更新时间、测试结果、search/detail/normalize/Evidence/Candidate 均覆盖；migration drift 通过 | 证明 secret 与普通配置分层，测试状态可见且不改变凭据更新时间；NLB fixture 不替代 live 凭据 | 无生产凭据时验证明确降级，不伪造 productive |
| Claim Gold workflow | 中 | Claim Gold 管理 API 包含在 78 项组合中并通过；active revision、stale Evidence、locator 与空 gold gate 均覆盖；生产 inventory 为 Claim Gold 0、DerivedClaim 0、CuratedClaim 0、benchmark ready false | 只允许人工引用当前 EvidenceSpan，不自动创建 Gold，也不改变默认 ranking | 已确认 Viewpoint 继续使用 `semantic_v2_baseline`；正式 benchmark 指标仍待人工 Gold |
| selective OCR consumption | 高 | selective OCR、paused inventory 与单任务处置包含在 78 项组合中并通过；生产切换前后 paused OCR job 均为 6 | 受控 OCR 输出已进入 DocumentRevision、EvidenceSpan 和字段候选，同时保持 stable Page 与 ORIGINAL bytes；生产部署没有恢复 OCR | 真实生产 PaddleOCR 识别仍待管理员逐项恢复，禁止 Resume All |
| 责任者草稿与候选分离 | 高 | 后端定向 2 项、前端 Node 18/18、TypeScript、定向 ESLint、`compileall` 与 `git diff --check` 通过；生产上架项有 28 个待处理 Person 候选、Workspace 可见 29 个 Person 候选、正式贡献者 1 项 | 大量候选仍在 Candidate workspace，但不进入正式责任者列表；批量 metadata 没有采用动作，空译者不阻止保存；ResearchContext 正确区分作者、译者和其他责任者 | 首轮生产核对完成，单项实际采用仍由正常编辑操作验证 |
| 版本、Django 与前端综合门槛 | 中 | `manage.py check`、migration drift、`compileall`、TypeScript、完整 lint、production build 与 `git diff --check` 通过；后端完整 suite 执行一次，唯一失败是旧 exact-dict 断言，修正后只重跑该项并通过，保留 32 项环境依赖 skip；前端完整 Node suite 执行一次，5 条旧源码位置断言随公开组件抽取而失效，修正后受影响 4 个文件 24/24 通过，Auth 21/21 通过 | 真实记录完整门槛暴露的问题及受影响重跑，没有把初次执行写成全绿，也没有为小范围断言修正重复执行全量 suite | 已复核候选与最终 tracked tree、归档和镜像身份 |
| 关键 Playwright | 高 | Workbench 3/3 通过，覆盖保存并前进、dirty canonical 离开提示、期刊与可选策展和带警告发布；受保护 Knowledge Preview 浏览器 smoke 通过，EditorialRevision 成功渲染 Discipline 公开组件，控制台 0 error；部署后公开核心路由、Reader 与静态 bundle 通过 | 验证管理员实际操作、Preview 的公开组件复用和生产 bundle，不以 API 200 代替全部页面行为 | 最终同源镜像替换后已复核受影响公网路径 |
| Production cutover | 高 | 候选树 `f0ffad37` 首轮切换完成；fresh backup、PostgreSQL 16 restore、catalog 0039、旧 3.0.1 additive-schema readiness、候选镜像、readiness、公开 T4、馆藏 identity、回退标签和脚本均已核对；最终 tracked tree 完成无 migration 同源镜像替换与定向复核 | 证明 NAS、Cloudflare、PostgreSQL、Reader、Semantic、Viewpoint、Projection 与降级状态在真实生产可用；首次首页 502 定位为 Edge 缓存旧 Web 容器 IP，强制刷新 Edge 后恢复且脚本已纠正 | 已核对最终镜像 label、部署记录、公网状态与 Git commit tree |

### 3.0.2 首轮生产切换记录

- 候选 API 为 `social-theory-library-api:3.0.2-f0ffad37-20260826-201433`，image ID `sha256:28b1e33d613581cbfe927e9a16ddf91edb44e84a7a2a0049c032c6f77bfaadfd`。候选 Web 为 `social-theory-library-web:3.0.2-f0ffad37-20260826-201433`，image ID `sha256:60cc9c9358e980a0183265b78fa37987ce91091abe1b270cd29b2bd2462651d1`。
- Fresh BackupJob 为 `aedfeac2-b56c-4ba1-ab66-f38dec131e13`。归档 SHA-256 为 `d15ed054b9a40f6a6a2e8a1c3c83e29afa7a9e1ed5fedd0f0bd11fae5c8f9820`，database dump SHA-256 为 `2385cf3c965fae592957ab7029832f547840ce0ab9f07dc183b0c21cfe8d1eee`。部署记录位于 `storage/backups/pre-v302-cutover-20260826-201433/deploy-record`。API/Web 回退标签分别为 `social-theory-library-api:pre-v302-20260826-201433` 与 `social-theory-library-web:pre-v302-20260826-201433`。
- catalog 0039 已应用，catalog、ingestion 与 reading 的 migration plan 为空。PostgreSQL 16 恢复演练、0039 migration、Django check、馆藏 identity hash 和旧 3.0.1 image readiness 均通过。0039 只建立空的加密 Provider secret 表，没有 backfill、外部访问或 Canonical 变更。
- 第二次 T4 中公开首页、Explore、观点检索、Theory、Scholar、Topic、真实 Work、Reader 和登录页均返回 200。Semantic 为 hybrid、`fallback_used=false` 且结果非空。Viewpoint 返回 direct 2、oppose 2、qualify 1，真实 Reader locator 可用。Reader Range 为 206。匿名 Ask 为预期 401。
- 生产有 Work 9、Edition 9、Asset 18、ORIGINAL 9、Page 3,679、DocumentRevision 9 和 EvidenceSpan 3,735。ORIGINAL 总字节为 199,016,197。Page 与 ORIGINAL identity hash、活动语义 UID 以及 3,005 条实际索引记录在切换前后保持一致。open ProcessingJob、open ResearchRun、publication blocker 和 stale Projection 均为 0。
- Claim Gold、DerivedClaim 和 CuratedClaim 均为 0。21 个有效 demand 保持 `waiting_for_capability`。Processing Center 为 blocking 0、missing capability 1、Provider degradation 6、Research Source degradation 9、stale Projection 0。4070 未部署，NLB 没有 credential。用户暂停的 6 个 OCR job 未恢复，发布不受影响。
- 首次 smoke 的首页 502 来自 Edge 持有 Web 重建前的容器 IP，Web 自身已在 3000 端口正常监听。强制重建 Edge 后公网恢复。cutover 和 rollback 脚本已补上 Web 重建后的 Edge 强制刷新。未执行数据库回退或破坏性 restore。
- Beat 恢复后的观察中，两个 queued heartbeat 与一个 unacked health probe 都属于已登记维护任务。active、reserved 和 scheduled 没有 OCR、上传或 Research 任务。6 个 OCR job 的 inventory 未改变，open business task、publication blocker 和 stale Projection 均为 0。

## Wave 1  Knowledge and Data Foundation

| 改动 | 风险 | 已执行验证 | 为什么足够 | 最终综合验收 |
| --- | --- | --- | --- | --- |
| Canonical identity 收敛及 legacy 兼容写入 | 高 | canonical identity、foundation migration、Work editor、theory system 定向测试。Wave 1 相关集成共 77 项通过 | 覆盖 normalized 写入、legacy 映射、禁止新增 TheorySchool 与 legacy Concept、人工确认优先级 | 生产 inventory、迁移演练、迁移后映射核对 |
| DocumentRevision、质量评估、EvidenceSpan | 高 | Document Intelligence 定向测试通过。包含 Page identity、ORIGINAL 保护、选择性 OCR 失效 | 验证新增对象附着于现有 Asset、Page，不重建 Page，也不覆盖原文件 | 真实馆藏 backfill、两页 OCR 增量失效 smoke |
| DerivedClaim、ClaimEvidence、CuratedClaim | 高 | Claim pipeline、策展和公开 Evidence 定向测试通过 | 覆盖 Derived 与 Canonical 边界、人工采用、过期 Evidence 不公开 | 真实 PDF locator、批量 Claim 后工作台 3 至 5 项上限 |
| EditorialRevision | 高 | 草稿、预览、冲突和单 Editor 发布定向测试通过 | 覆盖已发布对象不会因保存立即污染公网，发布事务内提交 Canonical change | 已发布 Theory 真实旅程及回滚演练 |
| Dependency、Projection、Capability foundation | 高 | dependency runtime、QueryLexicon queue 和 Processing diagnostics 定向测试通过 | 覆盖 revision、lease、retry、missing capability 与无消费者队列 | 自动调度集成、生产 reconciliation 和 lag 观察 |

## Wave 2  Intelligence and Retrieval

| 改动 | 风险 | 已执行验证 | 为什么足够 | 最终综合验收 |
| --- | --- | --- | --- | --- |
| Claim shadow extraction、attribution、qualifier、stance | 高 | Claim 与 stance 定向测试通过 | 覆盖否定命题不能仅按 embedding 相似度判定立场，且结果保留 prompt、provider、revision provenance | 真实馆藏 shadow batch 与人工抽样 |
| Unified Retrieval 与 Viewpoint Search 3.0 | 高 | Semantic V2 兼容、七类关系、公开 endpoint 和前端组件测试通过 | baseline 保留。Claim 仅在 gate 后才可改变默认排序 | 真实 gold benchmark、顺序请求、Wrong-work 和 locator 核查 |
| ResearchTaskProfile、EvidencePack、Prompt Registry | 中 | task profile、EvidencePack、candidate adoption 和 benchmark command 定向测试通过 | 覆盖 14 个任务契约、受约束 Evidence、Debate 草稿和完整 ReadingPath 草稿 | 生产 seed、Provider degraded smoke、反馈统计 |
| 4070 pull worker | 高 | `test_remote_capability_worker_v300.py` 7 项通过。2026-08-24 与公开 Claim、Research 组合共 17 项通过 | 覆盖专用 token、限流、payload 上限、heartbeat、租约、幂等完成、过期拒绝、离线非阻断 | 生产 secret 配置。真实 Laptop 在线领取待核实 |
| Ask Library 共用 Evidence | 高 | 新增 Evidence-first 测试 4 项及既有相关测试 29 项通过 | 覆盖无 Evidence 不调用 Answer Composer，DerivedClaim 只作为召回信号 | 公网不足证据回答和 PDF 定位 smoke |

## Wave 3  Editorial and Public Experience

| 改动 | 风险 | 已执行验证 | 为什么足够 | 最终综合验收 |
| --- | --- | --- | --- | --- |
| Workbench A 与 Research Inspector | 中 | Workflow、Claim curation、Revision 组件和后端定向测试通过 | 覆盖当前值、候选、Evidence、采用或拒绝、可选策展及单人发布 | Editor 全流程 Playwright 与生产账户 smoke |
| Knowledge Studio B | 中 | 后端 read model、权限和前端组件测试通过 | 已展示正式内容、关系、Evidence、Claims、候选、Revision、Frontend impact 和 Preview，并复用专业编辑器 | 关键后台旅程 |
| Processing Center C | 中 | 后端 diagnostics 4 项及相关集成 7 项通过。前端新增 11 项及既有 9 项通过 | 覆盖 stale projection、missing capability、Provider degradation 和受限恢复动作 | 生产故障解释、恢复按钮和 lag smoke |
| 公开 Work、Theory、Scholar、Topic、Debate、Viewpoint | 高 | 公共 CuratedClaim、Viewpoint 页面、TypeScript 和定向组件检查通过 | 空模块不显示。公开 Evidence 必须来自当前可读的 active DocumentRevision | 公网路由、响应式、Reader Range 和真实页码 |
| AI capability 与 Prompt 管理 | 中 | `npx tsc --noEmit` 通过。Processing/Settings 相关 Node 26 项通过 | 前端覆盖全部 3.0 AI capability、active/fallback/alias；Prompt 只建立不可变草稿并需 Superadmin 明确启用 | 生产权限和脱敏配置 smoke |
| Wave 3 子系统验收 | 高 | 前端 72 项通过。后端相关集合除一条旧 ReadingPath 直写断言外均通过；该断言改为 EditorialRevision 契约后单项通过 | 失败来自 2.8 测试仍期待 201 直接写已发布路径。新契约验证 Canonical 保持不变、Editor 发布后原子提交 | T3 full regression 和关键 Playwright |

## Wave 4  Migration and Production Cutover

| 项目 | 状态 | 实际验证 |
| --- | --- | --- |
| Legacy 和 DocumentRevision inventory | 完成 | 不安全 TheorySchool 映射被拒绝 backfill。8 个 active DocumentRevision、3,735 个 EvidenceSpan；Page 和 ORIGINAL identity hash 不变 |
| Migration rehearsal | 完成 | PostgreSQL 16 clone 应用 0033、0034。核心计数、Page hash、WorkNodeRelation 均保持；旧 2.9.2 API 在 additive schema 上 ready |
| Claim shadow backfill | 有界完成 | 7 个有 Evidence 的 revision 各调度 3 条，共 21 条；均 waiting_for_capability、publication blocking 0 |
| Projection reconciliation | 完成 | 首次生产执行发现 PostgreSQL nullable join lock 错误。Capability runtime 和远程 Worker 修复后专项 25 项、生产 reconciliation 与远程 lease/completion 事务回滚 smoke 通过，stale 与 waiting Projection 均为 0 |
| T3 backend full regression | 完成一次全量执行及受影响重跑 | 全量只暴露 3 条旧 2.x contract 断言；测试改为 3.0 Revision/retirement contract 后受影响集合通过。随后 PostgreSQL lock 修复只重跑 dependency/projection/remote worker 25 项并做生产 PostgreSQL 命令验证，没有机械重跑全部 suite |
| T3 frontend full unit、TypeScript、lint、build | 完成 | build 成功；主 Node 131 项中唯一旧 credential 正则更新后受影响项通过，Auth 21/21；TypeScript 与完整 lint 退出 0 |
| 关键 Playwright | 完成 | Workbench 3/3；严格公网 6/6，覆盖路由、当前入库、Ask 权限、Reader Range、CMap 和真实 PDF canvas |
| Claim benchmark | gate 保持 false | 生产 0 gold query。baseline 与 shadow 都明确 not ready，default ranking changed 为 false |
| Production backup、cutover、T4 smoke | 完成 | BackupJob、migrations、backfill、镜像切换、ready、Semantic、Viewpoint、Reader、任务/权限状态和馆藏 hash 已核对 |
| Observation 和 rollback | 应用回退已演练，数据库恢复保留 | deploy-record 保存旧 image、Compose/env、源码、fresh backup 和活动状态。旧 API 对 additive schema 的 ready rehearsal 通过；未对生产数据库执行破坏性 restore |

生产记录目录为 `storage/backups/pre-v300-cutover-20260824-142628/deploy-record`。Fresh BackupJob 是 `3a8a2633-dc3d-4566-8bed-28d0b1bc29aa`，归档 SHA-256 为 `afff698b1c4d8de1bac887fdb572f858a8a9191d195aca642abcc3b45163ee52`。最终 API image ID 为 `sha256:069c9c1aedf7b31e24c2ddfa4602e9130d1338e033b701007202a36e7afcbdd1`，Web image ID 为 `sha256:05b8dc9fd0c04e8c394234c97173995216bc6102a3f3a033a43c8851dfaef6d4`。

末次观察记录为 `final-observation-20260824-150715`。两个 Worker 的 active、reserved、scheduled 与五个 Redis/Celery queue 均为 0；活动语义 UID 记录值和实际值都是 3,005；近 8 分钟 API、Worker、Web、Edge fatal pattern 为 0，应用容器 RestartCount 为 0。

最终 API/Web archive 已复制到 deploy-record 的 `release-artifacts` 并复算 SHA-256。四个远端 `/tmp` staging 目录按精确路径删除，共释放 85,180,945 bytes。镜像、数据库备份、环境回退和部署证据保留。

## 已知环境项

- `pypinyin` 发出历史弃用警告。本次没有扩大范围处理。
- 当前生产没有 Claim Benchmark 人工判断集。因此 Claim 排序继续保持 shadow，默认仍为 Semantic Search V2。
- 真实 RTX 4070 Worker 尚未连接生产。生产事务回滚 smoke 证明零 llm_large executor 时任务等待、无派发、非阻断；在线真实领取仍待核实。
- 当前 Processing Center 如实显示 optional Provider 降级和缺失 AI capability。T4 有 21 个等待任务，blocking 0，stale Projection 0。
- 普通 Editor 的关键写入路径已在生产 PostgreSQL 外层事务内完成，并验证 CuratedClaim 发布和公网页码；测试数据随后全部回滚。正式馆藏没有保留测试修改。实际两页 OCR 识别、登录后的 Ask Answer Composer 和 4070 在线领取继续标记为待核实。
- 生产有 3 个历史 paused OCR job，task id 为空，均早于本轮 smoke，不计入 open ProcessingJob 或 publication blocker。是否恢复仍需按原文质量由管理员决定。
- 一次前端命令曾在仓库根目录误执行并因缺少根级 `package.json` 退出。改在 `web` 目录执行后通过。这是命令目录错误，不是产品失败。
- 一次 Django 检查从 `api` 目录误用 `\.venv` 相对路径，三条命令均未运行。改为 `..\.venv` 后 `check`、migration drift 和 migration inventory 通过。
- 一次 pytest 包装调用只取得了后台 session，未收集测试输出。随后用同一目标命令正确轮询，测试通过；该空输出不计入通过数。

## 3.0.1 Product Integration Pass 发布与生产验收记录

| 改动 | 风险 | 已执行验证 | 为什么足够 | 最终综合验收 |
| --- | --- | --- | --- | --- |
| 3.0.0 Git baseline | 高 | 开发起点为 `35b5cce`，tag `v3.0.0-baseline` 指向同一提交；3.0.1 release commit 为 `fa7444d`，archive SHA-256 为 `16a6d39e76ab743466406e6b8e1617e7bc129f84931c47bacf8949fd00d9db06` | 为 3.0.1 提供明确源码起点和不可变发布身份 | 已完成。pre-v301 deploy-record、旧 image 和 baseline source archive 均已保留 |
| Draft-aware Research 与字段契约 | 高 | `pytest --collect-only` 确认 draft-aware 文件为 9 项；相关子系统测试按改动面运行，失败后只重跑受影响 case | 覆盖 canonical revision、draft hash、trigger snapshot、迟到结果隔离、跨步骤增量依赖和直接实体决定幂等 | 最终完整后端回归与真实改题名旅程 |
| FrontMatterIntelligence 与本地优先书目证据 | 高 | Front Matter 定向测试、3 条 ingestion reconciliation/证据测试、2 条完整 ingestion 旅程通过 | 验证 native extraction、EvidenceSpan、有限页 OCR 与后续外部 corroboration 顺序；现有正式 Work/Edition 不被派生结果覆盖 | 两页 OCR、真实 PDF 作者/译者/ISBN 候选 smoke |
| Candidate 核实与 SafeWebFetcher 分类 | 高 | `pytest --collect-only` 确认 Candidate Verification 文件为 14 项；它与 Field Enrichment 的实际执行合计 36 项通过 | 覆盖 local-first、无 Evidence 禁止采用、Web 核实转换、错误分类和刷新不抹证据 | SearXNG 恢复后 adapter 8 条、直接诊断 10 条；真实 lead 转为 120,000 字符 Evidence。中文网页 Evidence 仍待核实 |
| SafeWebFetcher rebinding 与代理边界 | 高 | Candidate Verification 与 Field Enrichment 合计 36 项通过，包含 DNS 重绑、redirect 和环境代理案例 | 每一跳重新校验公开地址，请求固定到已验证 IP，并保留 Host 与 TLS SNI。`trust_env=false` 阻止未审计代理改变目标 | 生产公开英文 HTTPS 正向路径已通过；OpenLibrary 正确分类为 `fetch_blocked`，中文页面仍待核实 |
| 作者、译者与 Publisher 决定 | 高 | Entity Resolution 10 项、Front Matter 5 项、候选前端文件 9 项通过；TypeScript 通过 | 覆盖 role-aware contributor、已有 Person、新学者主页、仅责任者，以及已发布 Edition 的 Publisher 先进入 EditorialRevision | 普通 Editor 使用真实候选的完整决定旅程 |
| Asset 正文访问控制 | 高 | 最终 access matrix 12 项通过，并覆盖兼容 Global Search | Passage、SemanticChunk focus、manifest、Page、文档内搜索和兼容 Global Search 统一使用 Distribution access policy；拒绝响应不包含原文 | 公网 normalized Reader Range 和匿名边界已通过；四类 access status 完整 inventory 仍待核实 |
| 显式 OCR skip | 高 | SKIP policy 的 Front Matter 和 ingestion batch 2 项通过 | 确认显式跳过 OCR 时不会被高价值前置页分析重新排队 | 生产有限页 selective OCR 与 skip 对照 |
| Workbench 保存草稿语义 | 中 | `test_save_draft_does_not_confirm_lock_or_accept_candidates` 通过 | 同时断言 Work 暂存成功，且没有 WorkflowDecision、FieldLock 或 Candidate acceptance | 核心 Workbench Playwright 与 Editor 真实旅程 |
| 角色与唯一 Owner | 高 | Accounts 与角色集合 26 项通过，增强的 Django 管理表单 case 再跑 1 项通过 | 覆盖三角色、Reviewer 兼容、Editor 发布、Owner-only 敏感操作，并确认个人资料、管理 API、公开注册和 Django 管理表单不能变更或占用 Owner 邮箱 | 生产 Owner 配置和大小写重复邮箱已脱敏核对，identity match 为 true；Editor 写入使用事务回滚验收 |
| Research Source Registry | 中 | registry 定向测试通过，标准 metadata parser 与 Provider 配置边界进入 Processing Center | NCPSSD、Z39.50、CNKI、维普、万方只建立受控扩展，不引入万能 crawler。Secret 不返回前端 | 生产配置、健康、用途、最近成功和受影响功能 smoke |
| 4070 远程客户端 | 高 | client 与服务端相关集合 16 项通过，覆盖 WAN 失败持续运行、轮询下限、heartbeat 节流和稳定 completion id | 当前只领取 `claim_extraction`，没有把已声明的其他 capability 误写成可执行 | 真实 Laptop claim extraction、离线恢复和模型输出抽样 |
| catalog 0035 至 0038、ingestion 0014 | 高 | Django check、migration drift 和 migration inventory 通过；0038 定向数据迁移测试通过 | 0038 non-atomic、按路径事务、稳定 event key、仅填空值，并记录 revision 和 DomainChangeEvent。reverse 为 noop | PostgreSQL 16 rehearsal 与正式 migration 均完成，post-plan 为空，旧 3.0.0 image 在 additive schema 上 ready |
| T3 后端完整回归 | 高 | 初轮发现 3 个旧契约失败并定向关闭。安全审查后的三项高风险修复分别完成定向验证。一次并行编辑期间的运行遇到 Candidate decision 临时语法状态，不计为稳定验收；语法修正后影响面 49 项通过。所有编辑停止后，最终完整回归 897 passed、32 skipped，退出码 0 | 最终完整回归来自稳定 worktree。32 项均为既有环境型 skip，未把它们写成通过 | 生产前 migration rehearsal 与 T4 旅程继续覆盖 PostgreSQL、Provider、Worker 和公网环境 |
| T3 前端完整门槛 | 高 | production build 成功；142 项完整 Node 测试有 1 个旧选择器失败，更新后受影响文件 7 项通过；TypeScript 与完整 lint 通过 | 失败是 UI 信息架构变化后的旧选择器，不是运行时功能失败。受影响文件覆盖新选择器契约 | 生产候选 image 与公网静态 bundle smoke |
| Workbench Playwright | 高 | 首次因本地 API 未启动而 3 项均为 `Internal Server Error`；启动候选 API 后同套件 3 项通过 | 相同浏览器旅程在真实本地候选 API 上通过，首次结果明确记为环境前置缺失 | 生产事务回滚验收不等于普通 Editor 的持久正式馆藏写入 |

### 3.0.1 生产验收

| 项目 | 状态 | 实际证据 |
| --- | --- | --- |
| Release identity | 完成 | 主发布 commit `fa7444d`，archive SHA-256 `16a6d39e76ab743466406e6b8e1617e7bc129f84931c47bacf8949fd00d9db06`；PostgreSQL Claim 修复 commit `4c30565c`，API archive SHA-256 `a3018a88215fde89dbaae8f6f92894fb0c0c058b6bbd9f20f45fcfcf5fdc7973` |
| Fresh backup 与 rehearsal | 完成 | BackupJob `77b5fb3a-8c7e-42dc-b410-c6f19167b0c2`；19,983,666 bytes；SHA-256 `6e77e8b88bebe678a0aa1d6bef0c9f22cae13e7f4b703d3de21fba3aa0758ef8`；PostgreSQL 16 restore 和 `pg_restore --list` 通过 |
| Production migration | 完成 | catalog 0035 至 0038、ingestion 0014 按精确计划应用；post-plan 为空；旧 3.0.0 image 在 additive schema 上 ready |
| 馆藏保护 | 完成 | Page identity hash 与 8 个 ORIGINAL aggregate hash 不变；3,135 个 Page、165,728,337 bytes ORIGINAL 和活动索引 `3005|3005` 均保持 |
| T4 只读 smoke | 完成 | readiness 3.0.1、Semantic 非 fallback、Viewpoint baseline、Reader Range 206、匿名 Ask 权限、公开目录和真实实体页通过；publication blocker 与 stale Projection 均为 0 |
| SafeWebFetcher 与 SearXNG | 英文正向路径完成 | SearXNG 恢复后 adapter 8 条、直接诊断 10 条；真实 lead 转为 HTTP 200、120,000 字符 Evidence。数据库写入回滚；中文页面仍待核实 |
| 生产事务回滚写入 | 完成 | 未保存题名使旧 Run/Candidate stale，43 个字段重规划；DocumentRevision/EvidencePack 8 个字段候选；2 页 OCR 仅调度；Person/Scholar、译者仅责任者、CuratedClaim、公网页码、EditorialRevision、DomainChange、9 个 Projection 和权限均通过；临时数据与 8 个 callback 全部回滚 |
| PostgreSQL Claim 修复 | 完成 | 首次 smoke 暴露 `FOR UPDATE + DISTINCT`。改用相关 `EXISTS` 后，Claim 与 EditorialRevision 定向测试 11 项通过；候选镜像和正式部署镜像均在真实 PostgreSQL 通过 Claim 采用、单 Editor 发布和公开 Work locator。没有 migration、Web 或索引变更，因此未机械重跑 897 项后端回归 |
| Observation | 完成 | 自切换以来 API、Worker、Ingestion Worker、Beat、Web、Edge 和 SearXNG fatal pattern 为 0；除 Meilisearch 既有历史一次重启外，各服务 RestartCount 为 0 |
| Rollback | 入口保留并验证 | pre-v301 API/Web image、Compose/env、源码 archive、fresh backup、活动索引状态和手动回退脚本已保存；应用回退兼容性已验证；未执行破坏性数据库 restore |

Library Synthesis Candidate 尚未实现。远程 4070 客户端当前只执行 `claim_extraction`，真实 Laptop 尚未连接生产。中文网页 Evidence 与 Claim gold benchmark 仍待核实。有限页 OCR 的实际识别执行仍由真实上架旅程验证，事务内的仅调度检查不能替代它。
