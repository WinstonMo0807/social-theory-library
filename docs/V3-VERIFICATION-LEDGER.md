# Social Theory Library 3.0 Verification Ledger

更新时间：2026-08-24

本记录只登记实际执行的检查。环境依赖、生产验证和真实馆藏质量评估在完成前均标为待核实。工程严格按四个 Wave 推进，不再拆分子 Phase。

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
- 当前 Processing Center 如实显示 6 个 optional Provider 降级、1 个缺失能力、21 个等待任务，blocking 0，stale Projection 0。
- 普通 Editor 的正式馆藏写入、两页选择性 OCR、真实 CuratedClaim 发布和登录后的 Ask Answer Composer 没有在生产制造测试数据，继续标记为待核实。
- 一次前端命令曾在仓库根目录误执行并因缺少根级 `package.json` 退出。改在 `web` 目录执行后通过。这是命令目录错误，不是产品失败。
- 一次 Django 检查从 `api` 目录误用 `\.venv` 相对路径，三条命令均未运行。改为 `..\.venv` 后 `check`、migration drift 和 migration inventory 通过。
- 一次 pytest 包装调用只取得了后台 session，未收集测试输出。随后用同一目标命令正确轮询，测试通过；该空输出不计入通过数。
