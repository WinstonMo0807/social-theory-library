# 检索、整书恢复与自动维护运行优化

2026-11-14。用户要求不等Mac到货继续底层开发，并保护11月15日的观点检索演示。本检查点未部署到NAS或公网；正式版本/活动索引保持，候选重型worker/beat保持停止。Intelligence不恢复，MCP不动。

## 已修复的具体调用路径

| 问题与触发条件 | 修复 | 保留的约束 |
|---|---|---|
| `discovery_inference._call`的每条推理请求调用`ensure_service`，服务不就绪时规范化、向量和重排可各等15秒；原HTTP超时为130秒 | 交互查询通过`interactive_inference`共享模型预算，默认8秒、配置范围1至30；启动通知不等待冷服务，同一请求内不重试已失败路径；连接不可用/资源忙后停止后续可选模型调用 | 下一次查询重新尝试，后台索引/模型调用仍沿原超时；明确降级警告，不把接口失败说成零命中。预算不是全搜索8秒的硬性SLA，SQL/Meili/连接与流读取仍须测量 |
| 图召回在每个来源/身份上调用公开资格查询，并在多个OCR片段上重复装载页面 | 按限定陈述集批量建立本次读取的资格结果，继续调用同一`assertion_public`规则；页面prefetch共享，身份召回先取有界ID再取选中资料 | 仍核对当前发布、来源版本、实体归并和撤回；模型调用后重新核验。不建立跨请求权限缓存，不修改图算法或放宽扩展预算 |
| 原文窗口尚未全部完成时，每次代理/远程返回都重建全书OCR节点并重新切窗 | v2在既有CurationArtifact保存stage1/windows范围计划，恢复时读取不可变快照、核验哈希并重建原始输入；范围计划不复制整书正文 | 结构/范围/模型预算变化重新规划，损坏计划拒绝；旧v1任务不强制切换，已完成结果不重跑。跨窗口重复名称的有界候选资料只在本次执行内复用，独立定义与语境仍保留 |
| 临时资源等待缺少自动恢复；失败订阅可能持续排在扫描前列；已有订阅发布新修订时可能没有编纂通知 | 既有beat每次最多选5项资源等待接续、30项到期订阅；失败保存指数退避，1分钟起最多1小时；原出版回调同时标记已有启用订阅 | 不接续人工暂停、模型失败、外部代理/远程等待或有效租约；不启用全馆策略，不自动审核或发布。重复消息不能把正在执行的任务改成等待资源 |

`retrieve_channel`记录召回、知识图、来源校验、排序、最终校验与locator耗时。原Discovery会话保留白名单数值，刷新后可继续诊断；不是另一套可见任务或监控数据库。推理计数/耗时是同一query task的累计值，以query_task_cumulative标明，不应把各通道累计数再次相加。可选图查询的数据库异常在事务边界内回滚并给出knowledge_graph_unavailable，已校验原文仍保留；基础来源查询真正失败时仍沿原错误路径，不伪造成功。

## 实际验证

- 首轮59项通过：`test_knowledge_runtime_optimization`、`test_knowledge_automation`、`test_compilation_plan`、`test_continuous_wiki`、`test_rag_knowledge_linkage`、`test_logical_retrieval`、`test_contextual_retrieval`。
- 第二轮71项通过：新增冷服务通知检查，并覆盖`test_discovery_sessions_v308`、`test_discovery_projection_v308`、`test_retrieval_collection_bounds`、`test_intelligence_remote`、`test_intelligence_evolution`及运行/图联动检查。两轮有重叠，不宣称130个不同测试。
- 24陈述夹具按原select_related预取和原请求内visibility缓存进行公平SQL对照，逐身份形式29次，批量形式7次；独立复跑通过，并检查来源撤回、实体撤回及归并后的可见性。初次测量未复用旧缓存的120次不采用，不作为优化基线。
- 8秒预算、已失败请求不重复外呼、下一查询恢复、后台策略保持通过故障注入验证，没有真实模型调用。
- 部分整书恢复测试禁止调用prepare/windows或查询DocumentNode，同时核验下一窗口与快照逐字一致、先前成功无候选结果保留、篡改计划失败。
- 三书既有245份分析/884947纳入字符、335份Wiki输入通过本机规划完整性及严格预算复核。0 SQL、0模型调用、0业务写入；这不是新模型质量或NAS吞吐验证。
- `makemigrations --check --dry-run --noinput`退出0；0103/0104在测试库执行。环境为本机Python3.14.6/隔离SQLite，不代表Mac/ARM/PostgreSQL通过。
- 正式`/api/ready/`轻量读取一次200、0.228秒。只读Docker检查正式和候选API均运行，候选worker/beat仍停止，NAS_ON_DEMAND_ENABLED=true、推理超时130秒。没有调度、重启、写库或索引操作。探针不证明观点检索演示功能通过；也未据推理容器running声称模型已就绪。
- 会话诊断持久化及现有会话14项通过；最终运行优化、可选图数据库故障隔离、原文联动与语境检索15项通过。上述轮次有重叠；没有将重复执行累加成不同测试数量。Django check无问题、git diff --check通过。

本机检查命令在`api`目录执行，沿现有虚拟环境；设置`DATABASE_URL=sqlite:///:memory:`、`DJANGO_DEBUG=true`后使用`python -m pytest <上述相关文件> -q --tb=short`。弃用提示来自pypinyin，测试环境staticfiles目录缺失提示仍保留，未删除断言或修改权限以通过检查。

## 迁移与回退交接

1. 从GitHub取得`codex/stl-knowledge-intelligence`，先核对CURRENT_PROGRESS和当前正式源码差异。2026-11-14获取的origin/main仍为fb918113；正式镜像还有其他覆盖修改，不直接按分支名替代运行源核对。
2. 当前NAS候选仍停在0102。新增代码依赖0103计划版本和0104接续时间/次数字段；未迁移前不得只覆盖运行文件。API的ready会报告待迁移状态。
3. 在独立恢复环境检查备份和`python manage.py inspect_knowledge_runtime`，执行`python manage.py migrate --plan`后再对隔离库执行`python manage.py migrate --noinput`。0104不遍历原文、不调用模型、不启动索引，也不删除旧记录。
4. 新配置`DISCOVERY_QUERY_INFERENCE_BUDGET_SECONDS=8`已列入`.env.example`。在线模型冷启动降级与热模型语义结果均须实测，不能单凭降低等待时间决定模型质量通过。
5. 源码回退保留新增列和产物；停用新执行器后回退，旧代码不能消费v2任务。不通过逆迁移删除新产物，也不整库恢复覆盖此后人工决定。完整Mac数据/文件/安全配置交接沿MAC_CODEX_HANDOFF_20261114.md。

## 演示与切换结论

本次允许评估切换，不执行公网切换。演示前保持当前正式API、活动索引、队列、DNS/隧道和写入端；不把GitHub推送等同生产部署。源代码开发、测试和交接已经继续进行，不以硬件未到货为开发阻塞。

整套切换的实际未完成条件包括：候选新结构索引未补齐；此前48.923秒查询尚未在新代码下做同输入复测；新增迁移未在隔离PostgreSQL验证；配置Provider、冷热模型以及真实入库后的自动编纂尚未完成运行验收。原NAS超时缺少调用栈，不能以本轮消除了已知重复等待路径就宣布全部根因已解决。

用户补充演示会随机提问，不准备复用固定路线或答案。按通用检索链路开发和验证，不以题目缓存掩盖故障；单次实际查询也不能证明任意问题的检索质量或持续可用性。不通过全馆重建来准备演示。若之后考虑生产切换，须先保留正式恢复点、核验代表性原文和旧URL、完成有限索引接续及通用查询链路复测，再提交具体切换范围与回退入口供用户授权。
