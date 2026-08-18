# Semantic Search Evaluation Environment

## 用途和边界

Task 2B-0.5 为观点检索建立可删除、可重建的独立数据面。它只服务离线评测，不接收真实用户流量，也不参与生产索引切换。

环境只包含两项常驻服务。

- PostgreSQL 16 保存经过筛选的馆藏、逐页文本、SemanticChunk、authority source、重建后的 QueryLexicon 和一个 evaluation SemanticIndexVersion。
- Meilisearch 1.37 保存 UID 以 `semantic_passages_eval_` 开头的独立索引。

`compose.evaluation.yaml` 不启动 API、Web、Redis、Celery、OCR 或生产 Edge。端口只绑定 `127.0.0.1`。环境变量示例位于 `evals/semantic_search/evaluation.env.example`。真实密码应放在仓库外，不能提交 Git。

以下操作仍被禁止。

- 对生产 PostgreSQL 执行 migration 或任何写入。
- 修改生产 Meilisearch、活动 SemanticIndexVersion 或生产 QueryLexicon。
- 开启公开 V2 feature flag。
- 调整 `baseline_v2a` 参数、embedding model 或 reranker。
- 把 bundle、标注包、馆藏文本、数据库或索引提交 Git。

## 数据来源优先级

首选已有数据库 backup、read replica 或一次性数据库副本。现有 `BackupJob` 继续负责完整灾难恢复归档，本任务没有建立第二套通用备份系统。完整归档可能含账户和读者数据，不能直接作为 evaluation DB。

如使用完整 backup，应先恢复到 `evaluation-source-postgres`。这个可选服务与最终 evaluation DB 使用不同端口和 volume。恢复、migration 和数据筛选只发生在这个一次性副本。导出成功并核对 checksum 后，应确认 Compose project 和 volume 名称，再清理含敏感数据的 source-copy volume。

只有在连接确实可审计为只读时，才允许从 read replica 或生产读取。导出命令把所有 ORM 查询放在 PostgreSQL `REPEATABLE READ READ ONLY` 事务中，并回读 `transaction_read_only`。无法确认时立即停止。命令不调用 Celery，不保存模型，也不执行 migration。

## Search-only bundle

`export_semantic_search_evaluation_snapshot` 只导出以下模型。

- Work、Edition、用于语义索引的 normalized Asset 引用、Page 和 SemanticChunk。
- Contribution 和 WorkKnowledgeRelation，用于作者、理论、主题和概念过滤。
- Person、PersonNameVariant、Discipline、Subdiscipline、TheorySchool、Topic 和 Concept。
- KnowledgeNode、KnowledgeNodeAlias 和 LegacyKnowledgeMapping。
- 指定 SemanticIndexVersion 的无 secret 配置快照。

不会导出账户、password hash、JWT、session、API token、Reader 数据、阅读历史、笔记、收藏、私人书单、原始 PDF、OCR 文件、Cloudflare 配置或 AI key。`created_by`、`reviewed_by` 等用户外键置空。Asset 文件名和文件 hash 改为 evaluation 占位值。页面和 chunk 原文会保留，因此 bundle 只能写在仓库外或已忽略的 `data`、`output`、`tmp` 目录。

导出按冻结索引的 parser version、chunk version、embedding model 和 ready 状态选择 chunk。解析出的 chunk 数必须与 SemanticIndexVersion 冻结文档数完全一致，否则停止。SemanticChunk 没有直接的 index-version 外键，这个一致性检查不能省略。

示例命令如下。应从 `api` 目录运行，并用实际 Python 环境替换命令前缀。

```powershell
python manage.py export_semantic_search_evaluation_snapshot `
  --snapshot-id pilot-2026-08 `
  --index-version <source-index-uid-or-uuid> `
  --source-kind backup_restore `
  --output-dir ../data/evaluation/pilot-2026-08/bundle
```

每个模型写入独立 JSONL。`bundle-manifest.json` 记录 migration heads、PostgreSQL 版本、读事务属性、Work/Page/Chunk 数量、源 QueryLexicon 状态、源 SemanticIndexVersion、模型和维度、目标 UID、配置 hash，以及每个文件的 SHA-256。

## 构建隔离环境

复制环境变量示例到仓库外，再启动目标 PostgreSQL 和 Meilisearch。

```powershell
docker compose `
  --env-file <outside-repo-evaluation.env> `
  -f compose.evaluation.yaml `
  up -d evaluation-postgres evaluation-meilisearch
```

当前机器没有 Docker CLI，因此这条 Compose 配置尚未由本轮真实解析或启动。不能把 YAML 静态检查写成服务已运行。

连接 target evaluation PostgreSQL 后，依次执行 migrations 和导入。

```powershell
python manage.py migrate --noinput

python manage.py import_semantic_search_evaluation_snapshot `
  --snapshot-id pilot-2026-08 `
  --bundle-dir ../data/evaluation/pilot-2026-08/bundle
```

写入命令有额外门槛。

- `SEMANTIC_SEARCH_EVALUATION_MODE=true`。
- 实际数据库名必须与 `SEMANTIC_SEARCH_EVALUATION_DATABASE_NAME` 一致，且名称包含 `eval`。
- PostgreSQL host 必须是本机或包含 `eval`。
- 当前 Meilisearch URL 必须与独立确认值一致，host 必须是本机或包含 `eval`。
- `SEMANTIC_SEARCH_V2_ENABLED` 必须为 false。

导入只接受刚完成 migrations 的数据库。migration 0013 在空库中产生的确定性 authority seed 会先从 evaluation DB 清除，再加载源 authority。账户、session 或 Reader 私有表只要有一条记录，导入就停止。Authority 使用基础 manager 批量载入，不产生虚假的 ChangeEvent。随后在同一 evaluation DB 运行 full reconciliation，重新派生 QueryLexicon。源 QueryLexiconEntry 不会被盲目复制。

## Evaluation semantic index

导入会创建一个确定性 UUID 的 SemanticIndexVersion。UID 为 `semantic_passages_eval_<snapshot-id>`，初始状态为 building，不会成为 active。

```powershell
python manage.py build_semantic_search_evaluation_index `
  --snapshot-id pilot-2026-08
```

当前源码只能把完整 semantic document 提交给 Meilisearch。Meilisearch 会使用源版本冻结的同一模型、revision、维度、pooling 和 document template 重新生成 evaluation embedding。这个过程只写 evaluation Meilisearch，但确实会重新 embedding。它不能被描述为复制生产向量。

如果中途失败，版本标为 failed。确认同一 evaluation UID 后可用 `--resume` 幂等 upsert。最终 Meilisearch 文档数必须等于 evaluation DB 的 SemanticChunk 数，版本才变为 ready。命令不会调用 activate。

## Baseline audit 和 snapshot manifest

首次 audit 必须在任何 language refresh 之前运行。它比较 stored SemanticChunk.language 与 Task 2A detector，但不更新字段。

```powershell
python manage.py audit_semantic_search_evaluation_environment `
  --snapshot-id pilot-2026-08 `
  --bundle-dir ../data/evaluation/pilot-2026-08/bundle `
  --smoke-query "<人工选择的馆藏查询>" `
  --smoke-query-language zh `
  --output ../data/evaluation/pilot-2026-08/snapshot-manifest.json `
  --require-ready
```

`--require-ready` 要求以下条件同时成立。

- migrations current，Work、Page 和 SemanticChunk 均可定位，chunk 数大于零。
- QueryLexicon 有 active generation 和 revision。
- evaluation SemanticIndexVersion 为 ready。
- evaluation Meilisearch 可读，文档数与 DB 一致。
- 账户、session 和 Reader 私有表全部为空。
- 同一条真实 query 的 V1、baseline_v2a、pure lexical 和 pure dense 都返回结果，非 lexical 路径不允许静默 fallback。

最终 manifest 记录数据量、QueryLexicon revision 和 coverage、SemanticIndexVersion、模型、维度、evaluation UID、Meilisearch 文档数、bundle checksum、historical language audit、四路 smoke 结果和 `baseline_v2a` config hash。它同时明确 `semantic_index_activated=false`、`baseline_language_metadata_modified=false`。

## Pilot query 与盲标

环境 ready 后可生成数据支持的候选清单。

```powershell
python manage.py prepare_semantic_search_pilot_candidates `
  --snapshot-id pilot-2026-08 `
  --limit 60 `
  --per-direction-minimum 5 `
  --output ../data/evaluation/pilot-2026-08/pilot-query-candidates.jsonl
```

候选来自 active QueryLexicon 中确认的中英文术语，并要求目标语言馆藏至少有 substring 候选。输出只记录潜在实体、方向、query type、出现数量提示和选题理由。它不输出 passage ID，不填写 expected entity gold，也不生成 relevance grade。substring 只用于减少无数据候选，不能代替人工相关性判断。

人工需要从候选中选择和改写 30 条 diagnostic pilot。五个方向各至少 5 条，并补足 conceptual、comparison、mechanism、quoted phrase、hard negative、OCR 轻微错误和 mixed book。选定记录应转写为 `task2a_cross_language.schema.json`，gold 保持空。

随后复用 Task 2B-0 的四路 pooling 与盲标包。

```powershell
python manage.py prepare_semantic_search_benchmark `
  --dataset <human-approved-30-query-pilot.jsonl> `
  --index-version semantic_passages_eval_pilot_2026_08 `
  --pool-top-k 20 `
  --output-dir ../data/evaluation/pilot-2026-08/annotation
```

至少人工完成 3 至 5 条 query 的全部 pooled candidate，才能确认盲标文件流程可用。这个小样本只用于流程验收，不能计算或宣称 V2 优劣。完成 pilot 后，再用实际 unique candidate 的 median、p95 和 max 估算 120 条正式 benchmark 的 judgment 总量。

## 2026-08-16 真实馆藏执行状态

已经从可恢复备份建立隔离 PostgreSQL 16.14 与 Meilisearch 1.37.0。search-only bundle 有 3 个 Work、1,106 个 Page 和 3,005 个 ready SemanticChunk，不含账户、session、Reader 私有数据、原始 PDF 或 secret。导入后的 QueryLexicon revision 为 1。Evaluation index UID 为 `semantic_passages_eval_real_library_20260816_r62`，SemanticIndexVersion 状态为 ready，公开 feature flag 保持关闭。

首次索引构建暴露出一次提交整本书文档会超过 evaluation Meilisearch 的内存限制。构建器现在默认按 128 条文档提交，最大 batch 为 1,000，只影响 evaluation build。失败不会修改冻结 SemanticChunk 的状态。全新目标库重试后通过 25 个 batch 写入 3,005 个文档，容器没有再次重启。

真实 historical language audit 显示 3,881 条 source chunk 的 stored language 全为 `zh-CN`。Task 2A detector 判为 zh 2,636、en 438、mixed 547、unknown 260，family mismatch 为 32.0794%。Evaluation 使用的 3,005 条中，detector 判为 zh 2,257、en 182、mixed 306、unknown 260，family mismatch 为 24.8918%。baseline metadata 没有更新。

34 条待管理员确认的候选已完成四路 top 10 pooling，生成 766 个待判断 candidate。盲标包位于 evaluation 根目录下的 `annotation/real-pilot-review-20260816`。这些记录没有 expected entity gold 或 relevance grade。人工 3 至 5 条完整流程仍未完成，Task 2B-1 继续封锁。
