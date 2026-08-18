# 观点检索人工评估种子

此目录用于建立社会科学馆藏自己的观点检索基准。`seed_queries.jsonl` 只包含查询、问题类型和标注提示，不包含任何虚构的相关段落或评分。

## 标注规则

- 0 表示不相关。
- 1 表示同主题但没有回应问题。它是最重要的困难负样本。
- 2 表示对回答问题具有实质证据价值。
- 3 表示原文直接回应问题。

标注者必须打开对应 PDF，核对原文、文件页和印刷页码。不能依据搜索分数、摘要或模型解释代替人工判断。每条查询至少需要一个 2 级或 3 级段落，才能进入自动评估。

## 使用顺序

1. 将种子查询录入 `SearchEvaluationSet`。
2. 用现有检索取得候选，并补充人工找到的漏检段落。
3. 两名标注者独立判断有争议的 1、2、3 级边界。
4. 确认稳定 `chunk_document_id` 和 PDF 证据。
5. 先运行 `benchmark_opinion_search --dry-run`。
6. 依赖健康且 gold 完整后，再执行真实比较。

当前种子不构成完整评估集。NAS CPU、内存、Reranker 延迟、并发 5 与并发 10 的表现均需在目标环境实测，状态为 `待核实`。

## Task 2B-0 双语 benchmark 记录格式

`task2a_cross_language.schema.json` 沿用原文件名，并升级为稳定的 Task 2B-0 schema。每条 query 保存 `query_id`、查询语言、方向、query type、预期实体、固定 split 和 `gold_judgments`。judgment 必须包含 Work ID、稳定 chunk document ID、文件页、0 至 3 级人工判断及 reviewer note。

`task2a_cross_language.template.jsonl` 只有 10 条候选问题，五个方向各 2 条。它不含 gold，也没有根据当前搜索结果填分。当前本地 SQLite 没有 SemanticChunk，不能把模板算作可用 benchmark。

正式标注包必须用 `prepare_semantic_search_benchmark` 合并 V1、V2、纯 lexical 和纯 dense 的候选。指定索引需要有冻结的 runtime snapshot。包内包含馆藏原文，输出应放在已忽略的 `/data/` 或仓库外目录。`annotation.html` 默认隐藏来源算法，`diagnostic-pool.jsonl` 保留 rank 和 branch provenance 供事后诊断。评分命令要求每个 pooled candidate 都有人工 grade，不会把漏标项当成不相关。它默认只计算 dev，test 必须显式选择。训练性检查使用 diagnostic split，调参只看 dev，test 在参数冻结前保持封存。

## Task 2B-0.5 evaluation 数据面

`compose.evaluation.yaml`、`evaluation.env.example` 和 `docs/semantic-search-evaluation-environment.md` 定义独立 PostgreSQL、Meilisearch、search-only bundle、QueryLexicon rebuild、snapshot manifest 与 pilot 流程。真实 bundle、manifest、候选和标注包必须放在 `/data/` 或仓库外，不能放在本目录提交 Git。

当前开发机没有真实 SemanticChunk、evaluation 服务或获准 snapshot。候选生成命令会在 chunk 为零、QueryLexicon 不可用或 evaluation index 未 ready 时停止，不会用模板凑足 30 条。
