# 搜索评估基线

## 当前实现范围

当前源码已经建立可持久化、可回溯的评估数据基础、管理员 API、Celery 异步任务和后台管理界面。它复用现有 `SemanticIndexVersion`，没有创建另一套索引版本对象。运行评估不会切换活动索引、下载模型或连接 NAS。

迁移 `catalog.0020_semantic_chunk_stability_and_search_evaluation` 增加以下对象。

- `SearchEvaluationSet` 保存一组馆内检索评估题目及说明。
- `SearchEvaluationQuery` 保存查询文本、规范化文本、过滤条件和固定顺序。
- `SearchEvaluationJudgment` 保存人工相关性等级。等级从 0 到 3。判断同时保存可空的语义分块外键和不可变的 `chunk_document_id`。
- `SearchEvaluationRun` 保存一次评估所用的现有索引版本、混合检索权重、配置快照和指标结果。
- `SearchEvaluationResult` 保存每个查询的逐条排序结果、分数、相关性等级和耗时。

管理员 API 位于以下路径。

- `GET/POST /api/catalog/admin/search-evaluations/sets/`
- `GET/PATCH /api/catalog/admin/search-evaluations/sets/<id>/`
- `POST /api/catalog/admin/search-evaluations/sets/<id>/queries/`
- `GET/POST /api/catalog/admin/search-evaluations/runs/`
- `GET /api/catalog/admin/search-evaluations/runs/<id>/`

`runs/` 的 POST 默认使用 `mode=dry_run`。显式提交 `mode=execute` 会在当前请求中执行，提交 `mode=enqueue` 会交给 `catalog.tasks.run_search_evaluation`。`catalog.0023_search_evaluation_task_tracking` 保存任务 ID 和已完成查询数，后台语义索引页会轮询运行进度。当前仍没有批量评估集导入器和跨索引版本对比报告。

## 稳定段落标识

`SemanticChunk.document_id` 根据数字文件、解析版本、分块版本和页面定位信息生成。它不包含 OCR 文本和 embedding 模型名称。相同定位上的文字修订或模型更新会更新原记录，保留原 UUID。这样 `build_semantic_chunks(force=True)` 不再先删除全部分块。

读者反馈另存 `chunk_document_id`。如果一次解析确实移除了原定位，分块外键可以按既有 `SET_NULL` 规则释放，但反馈仍保留当时对应的稳定段落标识。迁移会为已有分块和已有反馈回填该标识。

## 评估数据约定

评估集应使用本书库真实的中英文查询，覆盖理论概念、作者与作品、观点陈述、原句记忆和跨语言表达。人工判断应针对具体段落，不应根据搜索引擎自身分数生成。

观点检索使用下面的四级人工判断。

- 0 表示不相关。
- 1 表示同主题但未回应问题。这一等级是用于检验精度的困难负样本，不计为有效证据。
- 2 表示对回答问题具有实质证据价值。
- 3 表示原文直接回应问题。

只有 2 和 3 计入 Recall、MRR、Precision 与可用原文率。nDCG 同样不给 0 和 1 排序增益，避免只找到同主题段落也获得正向分数。

评估运行会在 `metrics` 中保存以下键。

- `recall_at_20` 表示前 20 条结果覆盖的已知相关段落比例。
- `ndcg_at_10` 表示前 10 条结果在分级相关性下的排序质量。
- `mrr` 表示第一个相关结果倒数排名的平均值。
- `precision_at_5` 表示前 5 个位置中 2 级或 3 级原文所占比例。分母固定为 5。
- `top5_useful_passage_rate` 表示前 5 条中至少存在一个 2 级或 3 级原文的查询比例。
- `top3_direct_response_rate` 表示前 3 条中至少存在一个 3 级原文的查询比例。
- `zero_result_rate` 表示没有返回结果的查询比例。
- `p50_latency_ms` 和 `p95_latency_ms` 表示查询耗时分位数。
- `rerank_fallback_rate` 表示 Reranker 降级的查询比例。需要精排的方案出现降级时，不能把该次结果当作对应方案的有效对比。
- `reranker_applied_rate` 表示外部精排模型实际参与的查询比例。V2-B、V2-C 和 Top K 比较只有在该值为 1 且没有降级时才算完成。

每次运行必须记录 `index_version`、`semantic_ratio` 和 `config_snapshot`。新模型应先生成新的 `SemanticIndexVersion`，完成评估和人工确认后再使用现有安全切换流程。评估对象本身不得改变活动索引。

同步运行最多接受 50 条查询。每条查询至少需要一个人工标注为 2 级或 3 级的稳定段落。候选索引必须处于 ready、active 或 retired 状态，模型配置必须与当前查询模型一致。若候选索引不可读、没有文档或查询发生关键词降级，预检或运行会失败并保留明确错误。

`config_snapshot` 可以固定 `search_version`、`search_profile` 与 `rerank_top_k`。未提供这些值的旧调用维持原有检索默认值。异步运行会从已保存的配置快照恢复这些参数，因此不会因 worker 启动时间不同而静默改变比较方案。

## V1 与 V2 比较命令

先用后台人工标注真实馆藏段落，再运行：

```powershell
python manage.py benchmark_opinion_search `
  --evaluation-set "社会理论检索基线" `
  --index-version "semantic_passages_candidate" `
  --dry-run
```

去掉 `--dry-run` 才会依次执行 V1、V2-A、V2-B、V2-C，以及 Rerank Top K 为 8、12、16、24、32 的 V2-C。命令只读取指定索引并创建评估运行，不激活索引。预检、Meilisearch、本地模型或人工 gold 不完整时，输出会标为 `待核实`，不会生成或填入模拟指标。

## 后续接入边界

后续可在独立变更中增加批量评估集导入、跨索引版本报告和旧结果保留策略。当前后台已经支持逐条录入查询和人工相关性判断，但不应把这套管理界面当作批量标注工具。接入更多自动化前仍需明确查询文本隐私和运行资源上限。当前 API 仅允许管理员访问。

`evals/semantic_search/seed_queries.jsonl` 只提供查询类型和标注提示，没有预填馆藏段落或相关性。它不能作为 gold dataset，也不能产生模型优劣结论。
