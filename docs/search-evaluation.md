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

只有 2 和 3 计入 Recall、MRR、Precision 与可用原文率。nDCG 保留 0 至 3 的完整分级增益，用于识别把“相关但不足”的 1 级材料排在完全不相关材料之前的差异。

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

## Task 2A 配置快照补充

当运行显式选择 V2，或有效环境默认版本为 V2 时，`SearchEvaluationRun.config_snapshot` 还记录 `query_lexicon_revision`、active generation、normalization/source registry 版本、`ranking_profile`、branch weights、trust multipliers、expansion limits、`language_detector` 和 `search_implementation_version`。这些值用于解释一次运行使用的查询词表与规则，不代表检索质量概率。

`evals/semantic_search/task2a_cross_language.schema.json` 现已升级为 Task 2B-0 的正式 query 记录格式。它保存稳定 query ID、查询语言、检索方向、查询类型、预期实体、固定 split 和四级人工 judgment。模板只有 10 条未标注候选，不是 gold dataset，也不代表当前馆藏一定存在答案。

## Task 2B-0 人工评测基础

Task 2B-0 新增三条离线管理命令。它们不会切换活动索引，也不会修改公开 V2 feature flag。

```powershell
python manage.py audit_semantic_search_benchmark

python manage.py prepare_semantic_search_benchmark `
  --dataset ../evals/semantic_search/task2a_cross_language.template.jsonl `
  --dry-run

python manage.py prepare_semantic_search_benchmark `
  --dataset <真实 query 数据集> `
  --index-version <index UID 或 UUID> `
  --output-dir ../data/semantic-search-benchmark/<run-id>
```

正式准备标注包时，每条 query 分别运行 V1、V2、纯 lexical 和纯 dense，各取最多 20 条。V2 只为离线 Recall@20 返回更多已经排好序的候选，公开默认仍是 10 条，ranking 参数没有改变。四路候选按稳定段落标识去重，再用固定 seed 排成与系统 rank 无关的盲标顺序。任一路发生非预期降级时，命令停止，不生成偏向剩余系统的标注包。指定的 SemanticIndexVersion 必须已有冻结的 runtime config snapshot，工具不会用当前 runtime 猜测旧索引配置。

标注包包含馆藏原文和人工判断，应写入已忽略的 `/data/` 或仓库外目录，不得提交 Git。

标注包包含以下文件。

- `annotation.html` 是轻量人工页面。候选来源、rank 和 branch provenance 默认折叠，页面没有预选或推荐 grade。
- `annotation.jsonl` 是去除检索来源的盲标记录。
- `diagnostic-pool.jsonl` 保存四路 rank、V2 branch provenance、阶段耗时和候选数。
- `qrels.template.jsonl` 的 grade 全为 null，只能由人工填写。
- `dataset.frozen.jsonl` 保存固定的 diagnostic、dev 和 test split。
- `manifest.json` 保存数据 hash、索引版本、QueryLexicon revision、pool 方法、完整 `baseline_v2a` 快照及参数 hash。

人工页面下载 judgments 后，可运行：

```powershell
python manage.py score_semantic_search_benchmark `
  --dataset <dataset.frozen.jsonl> `
  --pool <diagnostic-pool.jsonl> `
  --judgments <人工下载的 judgments.jsonl> `
  --split dev `
  --output <metrics.json>
```

评分前必须给候选池中的每个 candidate 填写人工 grade，未标注项不会被默认为 0。评分命令默认只计算 dev，读取 test 必须显式传入 `--split test`。指标包括 Recall@5、Recall@20、Precision@5、MRR 和 nDCG@10。Recall、Precision 与 MRR 把 2 至 3 级视为有效证据，nDCG 保留 0 至 3 级的全部等级信息。输出分别按方向、query type 和 split 汇总，并记录 p50、p95、样本足够时的 p99、V2 resolver、sparse、dense、fusion、rerank 耗时、branch 数和 candidate 数。参数调整只能使用 dev。test 在参数冻结前不得参与调参。

Task 2A 的参数现标识为 `baseline_v2a`。当前本地默认配置 hash 为 `79650a79de2c5c973172d14a6b61c6b72fdd46983b56484501940d23f89bd8c3`。该 hash 只标识这次源码和本地有效配置，不能当作生产配置证据。

最初的本地 SQLite 快照只有 5 个 Work、917 个 Page 和 0 个 SemanticChunk，无法用于正式评测。2026-08-16 已改用经恢复验证的真实馆藏备份，在隔离 PostgreSQL 与 Meilisearch 上建立 3,005 文档的 evaluation index。该环境不改变生产 migration、QueryLexicon 或活动索引。

历史 language refresh 当前归为 B。数据库中的 chunk language 可以重新计算，但要让 Meilisearch filter metadata 同步，现有代码必须重新提交完整 semantic document。源码不能证明这条路径会保留原 embedding，因此本任务没有实现或运行 metadata refresh。

## Task 2B-0.5 隔离评测环境

隔离环境的完整构建和安全规则见 [semantic-search-evaluation-environment.md](semantic-search-evaluation-environment.md)。新增命令只负责生成 search-only bundle、导入全新 evaluation PostgreSQL、在独立 UID 建立 evaluation Meilisearch、生成 snapshot manifest 和提出未标注 pilot 候选。

写入命令要求 evaluation mode、明确的数据库名称、隔离 host、独立 Meilisearch URL 和关闭的公开 V2 flag。导出命令使用 PostgreSQL repeatable-read read-only 事务。bundle 不含账户、session、Reader 私有数据或原始文件，但包含 Page 和 SemanticChunk 原文，只能保存在仓库外或已忽略目录。

## 真实馆藏 diagnostic pilot

隔离环境当前使用 PostgreSQL 16.14、Meilisearch 1.37.0 和 UID `semantic_passages_eval_real_library_20260816_r62`。SemanticIndexVersion 为 `5e017013-52b1-5af9-a3f5-b1a87fead79c`，状态为 ready，文档数为 3,005。模型仍为 `paraphrase-multilingual-MiniLM-L12-v2`，revision 与维度均未改变。Evaluation build 重新计算了 embedding，但没有 activate，也没有写生产索引。

QueryLexicon 在 evaluation authority source 上重建为 revision 1。完整派生有 14 个实体和 69 条 entry，public active 范围只有 5 个实体和 23 条 entry。Person 为 0，确认的中英双语实体为 3。该覆盖率限制了真实人物译名和理论术语 expansion，不能用 ranking 参数补救。

当前提出 34 条未标注 diagnostic 候选。方向分布为 zh_to_zh 8、en_to_zh 8、mixed 6、zh_to_en 6、en_to_en 6。它们已完成 V1、V2、纯 lexical 与纯 dense top 10 pooling，得到 766 个 unique judgments。每题 candidate 中位数为 22，p95 为 28，最少 14，最多 29。标注包默认盲化来源，`gold_generation` 为 `human_only`。

若正式 benchmark 仍采用相同 pooling 深度，120 条 query 的人工工作量按当前中位数约为 2,640 个 judgment，按当前 p95 约为 3,360 个。这个估算只反映候选池大小，不代表 34 条题目已经被批准，也不能替代人工相关性判断。

四路 pooling 总耗时 62 秒。V1 p50 为 557.41ms、p95 为 1,023.52ms。V2 p50 为 286.53ms、p95 为 1,013.44ms。V2 QueryLexicon resolver p50 为 5.47ms、p95 为 8.44ms。34 条 V2 查询均返回结果且没有非预期 fallback。11 条 query 使用 supplemental branch，只有一条匹配到 QueryLexicon 实体，其余主要是 deterministic `intent_rewrite`。

尚无人工 relevance grade。34 条 query 的 `usable_query_count` 仍为 0，不能计算可信的 V1/V2 精度差异。当前英文 detector passage 主要是书后索引或中英混合引文，因此六条 zh_to_en 和六条 en_to_en 只能作为管理员审阅候选，不能直接进入正式 test。

这组 pooling 只覆盖 repair 前的 3,005 文档。其标注包已经写入 `PRE_CORPUS_REPAIR.json`，禁止继续形成正式 qrels。Task 2B-1 继续封锁。

## 真实 corpus integrity gate

2026-08-17 的只读 inventory 证明 876 个 failed SemanticChunk 都是同一次 embedding 配置下载 DNS 失败。chunk text、locator 和稳定 ID 均已存在。它们集中在同一个 draft Work，不属于 OCR 原文或 authority 数据错误。恢复在 disposable PostgreSQL 副本与隔离 Meilisearch 中复用原 chunk/index pipeline，连续执行两次后仍为 876 个 ready、0 failed，且 chunk ID、document ID 和 Page 文本不变。

repaired shadow 使用 SemanticIndexVersion `cf0988a5-841c-423d-b403-ee7c80891098` 和 UID `semantic_passages_eval_real_corpus_repaired_20260817_r63`。数据库 ready chunk、unique record ID、unique document ID 和 Meilisearch document count 均为 3,881。missing、extra、ID mismatch 和 schema drift 均为 0。该版本保持 ready，没有 activate，也没有改变公开 V1。

后续算法比较必须使用同一 repaired UID。命名上区分三组结果。

- PUBLIC V1 表示公开历史 UID 的现网行为，只作为运行参考。
- SHADOW BASELINE 表示在 repaired UID 上执行 V1 query behavior。
- SHADOW V2 表示在相同 repaired UID 上执行 `baseline_v2a`。

正式比较只能优先使用 SHADOW BASELINE 与 SHADOW V2。不能拿 3,005 文档的公开 V1 与 3,881 文档的 shadow V2 直接解释为 ranking 改善。

一致性检查命令如下。默认只读。只有非 active version 且数据库、远端文档及 schema 完全一致时，才允许显式使用 `--repair-metadata`。

```powershell
python manage.py audit_semantic_index_consistency `
  --index-version <uid-or-uuid>
```

`SemanticIndexVersion.document_count` 对 active version 表示当前 UID 的实际文档数，对 ready 与 retired version 表示冻结时的实际文档数。`expected_document_count` 继续表示建立快照的预期值。active asset 的增量写入、删除和零 chunk 清理都要同步当前计数。

repaired corpus 的 detector 统计为 zh 2,636、en 438、mixed 547、unknown 260。stored language 与 detector 的 exact mismatch 为 3,005，占 77.4285%。按语言族计算的 mismatch 为 748，占 19.2734%。旧 3,005 条仍保留历史 `zh-CN`，本轮没有修改生产 metadata 或 language threshold。

34 条 pilot 候选必须重新 pooling。旧 766 个 candidate 不继续标注，直到新池冻结后才开始 3 至 5 条 query 的人工流程验证。
