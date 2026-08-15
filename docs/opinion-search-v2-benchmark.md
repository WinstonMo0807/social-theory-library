# 观点检索 V2 评估与性能基准

更新日期：2026-08-15

## 1. 基准回答的问题

本基准不只检查“有没有搜索结果”。它要回答下列问题。

1. 第一阶段是否召回了真正有用的原文。
2. 有用原文是否进入前 3 或前 5。
3. 同主题但未回答的问题是否被错误推到前面。
4. Reranker 是否真的参与，而不是保存了配置后静默降级。
5. 增加查询分析和上下文后，精度收益是否值得 NAS 的延迟与内存成本。

## 2. 证据边界

- [SOURCE] 当前已有 `SearchEvaluationSet`、`SearchEvaluationQuery`、`SearchEvaluationJudgment`、`SearchEvaluationRun` 和 `SearchEvaluationResult`。
- [SOURCE] 当前已有管理员 API、同步预检、Celery 执行、进度展示和逐条结果保存。
- [SOURCE] `benchmark_opinion_search` 可以依次比较 V1、V2-A、V2-B、V2-C 和五个 Rerank Top K。
- [SOURCE] `evals/semantic_search/seed_queries.jsonl` 只有八条未标注中文问题，不含伪造原文或 gold judgment。
- [SOURCE] 每次运行把查询、filters、当时的人工判断和稳定段落 ID 保存为不可变快照，并记录 SHA-256；以后修改评估集不会改写旧运行的证据条件。
- [UNKNOWN] 当前没有真实馆藏 benchmark 结果。所有精度、延迟、CPU、RAM、GPU 与并发结论都是 `待核实`。
- [SOURCE-LIMIT] 当前管理命令按评估查询顺序执行。它不等于 5 并发或 10 并发负载测试，也不采集系统级 CPU、RAM、GPU 和磁盘 I/O。

## 3. 人工评估集

### 3.1 查询覆盖

第一组可从 50 条高质量问题开始，随后逐步扩展到 300 至 500 条。每一轮都保留版本说明，不要把后来补标的数据与早期运行混在一起解释。

建议覆盖：

- 理论概念。
- 原因解释。
- 社会机制。
- 学者比较。
- 路径与主张。
- 条件与评价。
- 历史过程。
- 理论或经验关系。
- 记忆不完整的原句。
- 中英混合概念和外国学者译名。
- 中文专著、中文期刊、译著和外文原著。

示例种子位于 `evals/semantic_search/seed_queries.jsonl`。种子只是标注起点，不是完整评估集。

### 3.2 四级标注

| 等级 | 定义 | 例子性质 |
| --- | --- | --- |
| 3 | 原文直接回应问题 | 明确给出命题、机制、路径或比较判断 |
| 2 | 对回答具有实质证据价值 | 提供关键条件、过程或论据，但不能单独构成完整回应 |
| 1 | 同主题但未回应 | 只谈同一对象、历史或背景，没有回答问题 |
| 0 | 无关 | 对象、命题或上下文均不匹配 |

等级 1 是核心困难负样本。纯向量检索最容易把这类段落排在前面。人工判断必须阅读命中段、章节和相邻上下文，不能根据系统分数自动生成。

### 3.3 标注质量

- 每条查询至少有一个 2 级或 3 级段落，才能执行评估。
- 关键查询建议由两位管理员独立判断，再处理分歧。
- 判断记录使用稳定 `chunk_document_id`，避免文字修订后完全丢失对应关系。
- 如果页码、OCR 或分块错误导致无法判断，应先修数据，不要把技术缺陷强行标为 0。
- 评估集要记录适用的馆藏快照和索引版本，避免馆藏扩充后把两次运行直接视为同一条件。

## 4. 核心指标

| 指标 | 当前定义 | 解释重点 |
| --- | --- | --- |
| Recall@20 | 前 20 覆盖的已知 2 或 3 级段落比例 | 第一阶段有没有把正确原文找出来 |
| nDCG@10 | 前 10 的分级排序质量 | 3 级是否比 2 级更靠前；0 和 1 不得分 |
| MRR | 第一个 2 或 3 级结果的倒数排名 | 第一条有用证据出现得有多早 |
| Precision@5 | 前 5 中 2 或 3 级结果所占比例，分母固定为 5 | 前屏结果有多少真正有用 |
| Top5 Useful Passage Rate | 前 5 至少有一个 2 或 3 级结果的查询比例 | 读者能否在前 5 找到可用原文 |
| Top3 Direct Response Rate | 前 3 至少有一个 3 级结果的查询比例 | 高位结果是否真正回应问题 |
| Zero Result Rate | 没有返回结果的查询比例 | 召回覆盖与可用性 |
| p50、p95 | 当前顺序评估中的查询耗时分位数 | 查询延迟，不代表并发资源峰值 |
| Rerank Fallback Rate | 精排发生降级的查询比例 | 模型方案是否真实执行 |
| Reranker Applied Rate | 外部模型实际参与的查询比例 | 防止把 rules 或降级结果误写成模型效果 |

只有等级 2 和 3 计入有效证据。等级 1 不参与 Recall、MRR、Precision 或 nDCG 增益。

## 5. 消融方案

| 名称 | 真实代码路径 | 主要问题 |
| --- | --- | --- |
| V1 | 数据库关键词、页级补充、dense、RRF、旧 rules、反馈、严格馆藏交错 | 当前基线 |
| V2-A | Meilisearch 关键词、dense、RRF，不扩展，不精排 | 全量关键词召回和新去重本身贡献多少 |
| V2-B | V2-A 加小候选 Cross-Encoder，不使用 parent context | passage 级模型精排贡献多少 |
| V2-C | 保守查询扩展、问题类型信号、Cross-Encoder、题名章节和相邻上下文 | 上下文和查询结构是否进一步提高回答相关性 |
| V2-C Top K | 8、12、16、24、32 | 精度、延迟与内存的实际拐点 |

V2-B 和 V2-C 只有 `reranker_applied_rate=1` 且 `rerank_fallback_rate=0` 时，才是有效的模型消融。否则命令会标记 `待核实`。

## 6. 运行前检查

1. 指定评估集处于 active。
2. 每条查询至少有一个 2 或 3 级 judgment。
3. 指定索引为 ready、active 或 retained 的 retired 版本。
4. 该索引版本保存了完整、无密钥的运行快照；候选评估使用这一快照生成查询向量，不要求先修改当前生产配置。
5. Meilisearch 实际文档数大于 0。
6. 索引记录文档数与实际文档数没有未解释差异。
7. V2-B 或 V2-C 所需 reranker 已配置并通过最小测试。
8. 运行期间不切换活动索引、不修改评估标注、不重建相同索引。

预检失败时不应绕过 blocker。先修复数据或配置，再重新运行。

## 7. 命令

命令应在 Django 项目目录 `api` 中运行。

### 7.1 查看帮助

```powershell
python manage.py benchmark_opinion_search --help
```

### 7.2 只做预检

```powershell
python manage.py benchmark_opinion_search `
  --evaluation-set "社会理论检索基线" `
  --index-version "<index-uid-or-uuid>" `
  --semantic-ratio 0.72 `
  --dry-run
```

`--dry-run` 只核对依赖与标注，不生成任何模拟指标。输出中 V1、V2-A、V2-B、V2-C 和 Top K 变体均应标明尚未执行。

### 7.3 执行真实比较

```powershell
python manage.py benchmark_opinion_search `
  --evaluation-set "社会理论检索基线" `
  --index-version "<index-uid-or-uuid>" `
  --semantic-ratio 0.72
```

命令会为每个变体建立独立 `SearchEvaluationRun`。它只查询指定索引和写评估记录，不激活索引，不下载模型，不修改 PDF。

## 8. 阶段耗时

[SOURCE] V2 debug 响应记录以下阶段。

- `query_analysis_ms`
- `sparse_retrieval_ms`
- `dense_retrieval_ms`
- `rrf_ms`
- `rerank_ms`
- `dedup_ms`
- `context_fetch_ms`
- `total_ms`

同时记录：

- `sparse_candidate_count`
- `dense_candidate_count`
- `fusion_candidate_count`
- `rerank_candidate_count`
- `rule_rerank_candidate_count`
- `final_result_count`

逐条评估结果分别保存关键词通道分数、dense 通道分数和最终排序分数。它们用于诊断，不能跨查询直接解释为概率。

`query_embedding_ms` 当前为 `null`。查询向量由 Meilisearch 在 dense 请求中生成，应用无法把这段时间从 dense 请求中可靠拆出。不要填入估算值。

生产日志只记录查询哈希、profile、索引 UID、阶段耗时、候选数和降级状态，不记录完整问题或馆藏原文。

## 9. NAS 性能测试

当前管理命令不能完成系统级并发压力测试。部署前需要在获得 NAS 授权后另行执行，并保留工具、参数、时间与原始记录。

至少测试：

- 单查询顺序执行。
- 5 个并发查询。
- 10 个并发查询。
- Top K 为 8、12、16、24、32。
- reranker 正常和故意停用两种状态。
- 后台无重任务、OCR 运行和语义回填运行三种负载情形。

每组记录：

- p50、p95、p99 latency。
- CPU 使用率与峰值。
- RAM 和 swap 峰值。
- GPU 或 VRAM。如果没有 GPU，明确写 CPU-only，不报错。
- 磁盘 I/O。
- HTTP 429、超时与 reranker fallback 次数。
- 搜索进程、模型服务和后台 worker 的并发参数。

当前这些数值全部为 `待核实`。不要根据模型参数量或他人 benchmark 推算 NAS 表现。

## 10. 结果报告模板

### 10.1 精度

| 方案 | Recall@20 | nDCG@10 | MRR | Precision@5 | Top5 Useful | Top3 Direct | Reranker Applied | Fallback | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| V1 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 不适用 | 待核实 | 未运行 |
| V2-A | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 不适用 | 待核实 | 未运行 |
| V2-B | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |
| V2-C | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |

### 10.2 Top K 与资源

| Rerank Top K | Precision@5 | Top3 Direct | p50 | p95 | CPU 峰值 | RAM 峰值 | 状态 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |
| 12 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |
| 16 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |
| 24 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |
| 32 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 待核实 | 未运行 |

空表是有意保留的证据边界。只有命令和 NAS 监控的真实输出可以填入。

## 11. 如何选择生产方案

不按单一指标选方案。建议依次判断：

1. Recall@20 是否下降。召回丢失时，后续精排无法补救。
2. Top3 Direct 和 Top5 Useful 是否稳定改善。
3. 等级 1 困难负样本是否明显减少。
4. p95 与资源峰值能否在 NAS 上承受。
5. 5 并发和 10 并发时是否频繁触发限流或降级。
6. 中文专著、中文期刊和中英混合子集是否存在一类明显退化。

如果 V2-C 只带来很小的精度变化，却显著增加 p95 或 RAM，应优先使用 balanced。若 reranker 在当前 NAS 不稳定，可先启用 V2-A。不要为了采用某个新模型而牺牲可用性。

## 12. 索引重建与历史馆藏

首轮 V2 在索引字段和 embedding 不变时，不需要重建全部索引。先用活动索引比较 V1 与 V2。

若后续改变模型、document template、解析版本或分块版本，应建立新的 `SemanticIndexVersion`，按小批次渐进回填。历史馆藏可逐批进入候选索引。活动索引继续服务，直到候选完成文档数核对、评估和管理员确认。

新发布 PDF 继续进入当前活动索引。候选全量版本建立期间如何处理后来发布的增量，需要在切换前核对候选快照与实际文档数。不得让候选版本在缺少新增馆藏时直接切换。

## 13. 失败与回退

- Reranker 不可用时，V2 回到关键词、dense 与 RRF，记录 fallback。
- Dense 不可用时，V2 使用关键词和页级降级，评估运行停止，避免把降级结果当成完整 V2。
- V2 逻辑异常时，关闭 `SEMANTIC_SEARCH_V2_ENABLED`，公共查询回到 V1。
- 新索引失败时，旧 active 继续服务。
- 已激活新索引需要回退时，只能选择仍保留且已验证的旧版本，不能删除数据库、索引或原始 PDF。

## 14. 一手资料

- [Meilisearch hybrid search](https://www.meilisearch.com/docs/capabilities/hybrid_search/getting_started)
- [Meilisearch Search API](https://www.meilisearch.com/docs/reference/api/search/search-with-post)
- [Qwen3-Reranker-0.6B 官方模型卡](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- [FlagEmbedding 官方仓库与 BGE-M3、BGE reranker 说明](https://github.com/FlagOpen/FlagEmbedding)
- [DAPR，ACL Anthology](https://aclanthology.org/2024.acl-long.236/)

这些资料用于说明架构选择。它们不构成本馆精度或 NAS 性能的验证记录。
