# Discovery 会话排序与取消恢复（2026-10-19）

本单元接续唯一 final-r2 PDF 第 30–32 页，已实际读取该 PDF 提取图像，复核第 32 页取消保留材料与本轮新增状态。共享引用单元已由主线保存为 bf1705b。本记录只覆盖会话控制后端与类型，页面、公开书目信息及上下文由主线独立完成。

## 当前实现

- GET `/api/catalog/discovery-search/{id}/?sort=relevance|year_desc|year_asc`，默认相关度。只对本次已物化并按当前发布修订和权限重验的原文材料排序，不触发检索或模型任务，不改变第一推荐方案、三通道召回或深度推荐算法。
- 年份来自当前公开书目；缺失或无效年份放在末尾，同年保留原推荐顺序。排序先于分页。签名 cursor 绑定会话、排序和推荐顺序；年份分页按年份与稳定原位置继续，前页来源被撤回不会使后续来源被跳过。恢复/扩展改变代次后旧年份 cursor 拒绝，客户端从首屏刷新。原相关度 cursor 继续保留基线/深度前缀兼容规则。
- 原 retry 允许 `canceled`，沿事务锁和 `expected_generation` CAS 恢复。本次恢复立即保留三通道与既有深度 refs，重用原 worker 追加流程。已有深度阶段成功时仍按原机制更新推荐前缀，失败保留旧前缀。本轮没有改深度排序策略。
- 重复 retry 只有与实际接受的 retry 回执一致才视为幂等；单纯取消导致的 generation 增加，不再被误判成已接受该 retry。取消后迟到的旧 worker 仍被 generation/task_id/status 阻止。
- 恢复或扩展前，仅在原 session.results 的 `_resume` 元数据保存三通道来源身份集合（id + source_revision；原文集合也包含既有深度来源），不存正文或书目副本。下一次恢复会更新比较基线。
- 当前重验的行返回 `is_new`。初次检索全部为 false，恢复后只有新身份为 true。`added_count` 是本次当前可见原文材料的新增总数，覆盖所有已物化分页，去除深度/基线重叠与已经失效的来源；不是当前页条数，也不是全部三通道对象数。
- 新增 `sort` / `added_count` 响应及 TypeScript `DiscoverySort`，各通道类型增加可选 `is_new`。主线负责客户端参数与页面接入、最终 OpenAPI 生成。

## 权限与数据

匿名能力令牌和本人会话权限保持原机制；恢复继续收窄已有权限，读取继续重新核对来源。年份排序、新增计数均不使用过期正文或索引摘要作最终展示。没有新增表或迁移，没有账户、私人数据或生产操作。

## 静态证据

2026-10-19 实际执行：

- Python `ast.parse` 读取本单元 sessions/views/新回归文件，3 文件退出 0。
- `node node_modules/eslint/bin/eslint.js lib/api/discovery.types.ts`，在 web 目录执行，退出 0。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false`，在 web 目录执行，session 5310，退出 0。
- `git diff --check -- api/catalog/services/discovery_sessions.py api/catalog/discovery_views.py web/lib/api/discovery.types.ts`，退出 0。
- 新回归 6 个测试函数、8 个参数案例，仅编写。覆盖分页前排序、同年/未知年份、来源撤回、cursor 跨排序/会话/代次、权限失效、取消后的幂等恢复、迟到旧任务、新增去重/失效/下一轮重置和 GET 参数透传。

没有执行 pytest、浏览器、正式功能/视觉回归、构建、模型、检索质量评测、迁移或部署。静态通过不代表 PDF 逐图验收通过。

## PDF32 仍为部分接入

逐文献的处理中/待处理/已完成数量、无直接材料、暂不可读、可用版本与移出本次范围尚未闭环。当前 `task_progress` 的单位是 channels，只能呈现通道进度，不能改文案冒充文献处理数量，也不能将索引完成或没有召回解释为本次逐书分析完成或相关性低。

已检查的最小复用路径：

1. `DiscoverySourceState` 关联原 `ProcessingJob`，并有当前索引代、来源修订、expected_count/completed_count/error；只能用于文献检索准备与索引状态。配合既有 `discovery_coverage` 与公开版本/Reader 资格检查，能真实说明正文或索引未就绪。
2. 本次当前重验的 passages 可以按 edition_id 聚合“已获原文材料数”，不能推断已检查文献总数或无匹配结果。查看可用版本需要沿相同 Work 的当前公开 Edition 重新核对，不能从撤回来源缓存取旧书目。
3. 要支持完整逐文献状态，应在现有会话 JSON 增加有界的本次来源身份、source_revision、状态与安全错误代码清单，在实际逐文献处理阶段写回，继续 generation/task_id/status CAS。不持久化第二份正文，不新建书库。缺乏真实执行事件的状态保持未知。
4. 移出本次范围需同时维护明确排除的来源身份、当前读回过滤与后续 worker 范围；不能只在前端隐藏卡片。需要主线作为后续完整单元实现并补权限/并发回归。

## 冻结白名单

- `api/catalog/services/discovery_sessions.py`
- `api/catalog/discovery_views.py`
- `web/lib/api/discovery.types.ts`
- `api/tests/test_discovery_session_controls_20261019.py`
- `docs/stl4/DISCOVERY_SESSION_CONTROLS_20261019.md`

前三文件同时包含主线此前新增的展示字段，本单元只追加 sort/new/canceled 控制，未覆盖原改动。未改主线 source/projection/context、页面、全局记录、生成 schema，未提交；由主线合并检查点。
