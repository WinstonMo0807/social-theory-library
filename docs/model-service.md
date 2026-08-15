# 模型与外部服务说明

更新日期：2026-08-15

## 1. 证据边界

- [SOURCE] 本文记录当前源码实际读取的 AI、外部元数据、OCR 和语义检索配置。
- [USER] 本轮不写入真实密钥，不下载生产模型，不自动部署 NAS 或公网。
- [UNKNOWN] NAS 当前环境变量值、模型文件完整性、容器运行参数和公网服务可用性没有在本轮核验。
- [SOURCE] 所有可选服务均有降级路径。可选服务不可用不应删除原始 PDF，也不应代替管理员作发布决定。

## 2. 当前服务边界

| 服务 | 当前实现状态 | 主要输入 | 持久结果 | 失败时行为 |
| --- | --- | --- | --- | --- |
| PaddleOCR | 已接入，按页批处理 | 需要 OCR 的 PDF 页 | Page、Block、OCR 状态、可选 OCR PDF | 保留原始 PDF；任务标记失败并允许重试 |
| Remote OCR | 可选接入 | PDF 或指定页 | 与本地 OCR 相同的规范页数据 | 配置不完整时显示不可用，不假装已配置 |
| 外部元数据 Provider | 部分实现 | DOI、ISBN、题名或期刊 PDF | SourceRecord、MetadataCandidate、CandidateEvidence | 返回 warning，继续本地解析和人工复核 |
| 元数据 AI | 已有受限客户端和候选生成，默认关闭 | 截断后的文档摘录 | SourceRecord、候选及模型来源 | 返回 disabled 或 unavailable，不中断入库 |
| Meilisearch 关键词检索 | 已实现 | 公开馆藏和全文分块 | 书目索引与 passage 索引 | 外部搜索不可用时仍可使用数据库侧的有限降级结果，具体范围需按接口核验 |
| Hugging Face 语义检索 | 已有离线模型检查和版本化索引 | 规范全文分块、查询文本 | SemanticChunk、SemanticIndexVersion、Meilisearch 向量文档 | 自动降级为关键词查询，不向读者暴露原始网络错误 |
| 检索评估 | 数据模型、同步与 Celery 执行器、管理员 API 和管理界面已实现 | 评估查询与人工相关性判断 | Evaluation Set、Query、Judgment、Run、Result、进度和指标 | 不影响生产查询，也不切换活动索引 |
| 观点检索 reranker | rules 已实现；有界 `local_http` adapter 已实现，真实模型服务待核实 | 问题与有界候选原文 | 查询诊断中的生效与降级状态，不修改馆藏 | 服务不可用时保留 RRF 或规则排序 |

## 3. 元数据 AI

### 3.1 支持的 provider

当前 `AIClient` 支持以下值。

- `none`
- `ollama`
- `vllm`
- `openai_compatible`

默认值为 `none`。上传批次还必须显式开启 AI 候选建议，模型才会参与该批次。全局 provider 已配置但批次开关关闭时，不会调用 AI。

### 3.2 配置

| 环境变量 | 当前用途 | 默认值或限制 |
| --- | --- | --- |
| `AI_PROVIDER` | 选择 provider | `none` |
| `AI_BASE_URL` | Ollama 或 OpenAI 兼容服务根地址 | 空。启用 provider 后必填 |
| `AI_API_KEY` | 可选 Bearer 密钥 | 空 |
| `AI_METADATA_MODEL` | 元数据候选模型 | 空。启用 provider 后必填 |
| `AI_CLASSIFIER_MODEL` | 预留分类模型名 | 空。当前元数据流程未消费 |
| `AI_VISION_MODEL` | 预留视觉模型名 | 空。当前元数据流程未消费 |
| `AI_TIMEOUT` | 单次请求超时 | 60 秒，限制为 3 至 600 秒 |
| `AI_MAX_CONCURRENCY` | 进程内并发上限 | 1，限制为 1 至 8 |
| `AI_MAX_INPUT_CHARS` | 发送给模型的最大字符数 | 16000，限制为 1000 至 100000 |
| `AI_ALLOWED_HOSTS` | 允许访问的主机名 | 本地模板为 `localhost,127.0.0.1,ollama,vllm` |

当前代码不读取 `EMBEDDING_MODEL` 或 `RERANKER_MODEL` 这两个通用变量。embedding 使用 `SEMANTIC_SEARCH_MODEL`。V1 规则配置使用 `SEMANTIC_SEARCH_RERANKER`，观点检索 V2 的可选模型服务使用 `SEMANTIC_SEARCH_V2_RERANK_*`。部署时不要新增没有 consumer 的同义变量。

`.env.example`、`.env.production.example` 和 `.env.nas.example` 已列出 AI 配置。当前 `.env.nas-192.168.5.6.example` 没有列出这组 AI 变量，因此不能把该专用模板视为 AI 配置完整的证据。

### 3.3 安全和写入规则

- `AI_BASE_URL` 只允许 HTTP 或 HTTPS，并且主机必须出现在 `AI_ALLOWED_HOSTS`。
- 客户端不提供文件、Shell、浏览器或网络工具给模型。
- 文档摘录被明确标记为不可信输入，模型不能用 PDF 内文字改变系统指令。
- 请求温度为 0，响应必须符合服务端 JSON Schema。
- 每次调用最多尝试两次。格式不合法会返回 `ai_invalid_output`，服务异常会返回 `ai_service_unavailable`。
- 输入按 `AI_MAX_INPUT_CHARS` 截断。当前流程不会把完整 PDF 直接发给 AI。
- AI 输出先成为候选。`select_best()` 明确排除 AI 来源，AI 不会静默写入 Work、Edition 或正式知识关系。
- 结果记录 provider、model、prompt version、延迟、尝试次数和输入哈希。SourceRecord 不保存整本 PDF。
- LLM 自报的 confidence 不作为系统评分。候选由本地评分服务按来源、证据、强标识符、一致性和冲突重新计算。

### 3.4 已实现与待实现

已实现：

- 元数据候选的严格 JSON 输出。
- 候选来源和证据持久化。
- 默认关闭、按批次启用、调用失败后继续入库。
- 本地 Ollama、vLLM 和 OpenAI 兼容接口抽象。

部分实现或待实现：

- `AI_CLASSIFIER_MODEL` 和 `AI_VISION_MODEL` 尚未进入真实业务调用。
- AI health 有服务级接口，但完整后台模型注册、版本管理和测试记录仍未实现。
- AI 关系候选还没有统一使用 RelationCandidate/RelationAssertion 的完整审核流程。
- 外部服务的数据出境告知和管理员逐批授权界面仍待实现。当前最安全的默认配置是 `AI_PROVIDER=none`。

## 4. 外部元数据 Provider Gateway

### 4.1 当前 provider

| Provider | 当前操作 | 触发条件 |
| --- | --- | --- |
| Crossref | DOI 精确查询、期刊题名查询 | 已识别 DOI，或期刊记录人工刷新且没有强标识符 |
| Open Library | ISBN 查询、图书题名查询 | 已识别 ISBN，或图书记录人工刷新且没有强标识符 |
| Google Books | ISBN 查询、图书题名查询 | 与 Open Library 相同，可选 API key |
| GROBID | 期刊 PDF header 解析 | 文档判为期刊论文，且 GROBID 已配置并启用 |

VIAF、Library of Congress、ORCID、OpenAlex、Wikidata 和 WorldCat 适配器目前没有在 Provider Gateway 中完成。RIS、BibTeX、CSL-JSON 和 sidecar JSON 已由元数据复核页的独立导入接口解析为待审候选，不经过 Provider Gateway，也不会直接写入正式书目。Zotero 直接导入和 PDF 与元数据成对上传仍待实现。

中文来源优先策略也尚未实现。当前代码会依据 DOI、ISBN、文档类型和题名选择上表来源，没有中文网站优先排序器。管理员仍需在候选卡中检查来源和版本是否匹配。

### 4.2 配置

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `METADATA_PROVIDER_ENABLED` | 逗号分隔的启用列表 | `crossref,openlibrary,google_books` |
| `METADATA_PROVIDER_ALLOWED_HOSTS` | provider 出口允许列表 | `api.crossref.org,openlibrary.org,www.googleapis.com` |
| `METADATA_PROVIDER_TIMEOUT_SECONDS` | 单次调用超时 | 12 秒，限制为 3 至 120 秒 |
| `METADATA_PROVIDER_RETRIES` | 失败后的附加重试次数 | 1，限制为 0 至 3 |
| `METADATA_PROVIDER_CACHE_SECONDS` | 成功结果缓存期 | 86400 秒 |
| `METADATA_PROVIDER_CIRCUIT_FAILURES` | 打开短期断路前的失败数 | 3 |
| `METADATA_PROVIDER_CIRCUIT_SECONDS` | 暂停请求时长 | 300 秒 |
| `METADATA_PROVIDER_MIN_INTERVAL_MS` | 同 provider 最小请求间隔 | 150 毫秒 |
| `METADATA_PROVIDER_MAX_RESPONSE_BYTES` | 单个来源快照最大保存量 | 1048576 字节 |
| `GOOGLE_BOOKS_API_KEY` | Google Books 可选密钥 | 空 |
| `GROBID_SERVICE_URL` | GROBID 根地址 | 空 |

若启用 GROBID，必须同时把其主机加入 `METADATA_PROVIDER_ALLOWED_HOSTS`。否则 gateway 会以 blocked 状态拒绝请求。

### 4.3 运行行为

- 成功和失败都会建立 SourceRecord。成功记录包含请求指纹、候选快照、provider version 和过期时间。
- 缓存按上传记录、provider、operation 和请求指纹读取。
- 保存的原始响应有大小上限，避免外部服务返回无限 payload。
- 配置健康检查只检查 enabled、URL 和 allowlist，不发真实网络请求。显示 configured 不代表远程服务当前可用。
- 批次关闭外部补充时，pipeline 不调用 provider，并写明该批次已关闭外部元数据补充。
- 全部 provider 不可用时，本地 PDF 解析、OCR、人工编辑和管理员发布仍可继续。

## 5. OCR

### 5.1 批次策略

| 策略 | 当前行为 |
| --- | --- |
| `auto` | 先提取原生文字，按页判断。只把没有可靠文字的扫描页排入 OCR |
| `force` | 所有页面进入 OCR |
| `skip` | 不排 OCR。若检测到扫描页，Edition 标记为 `ocr_status=disabled`，语义索引保持 `not_indexed` |

默认策略是 `auto`。它能避免对可复制的 born-digital PDF 做无意义 OCR，并支持混合型 PDF 只处理部分页面。

[SOURCE] 页码任务与语义任务采用独立条件。OCR 被停用时，页码识别仍可使用 PDF PageLabels、原生页眉页脚和文件页序继续工作；语义任务只在 `ocr_status` 为 `not_required` 或 `succeeded` 时排队。扫描件选择 `skip` 后不会因发布而重新进入语义索引。

### 5.2 provider 模式

后台 `SiteSetting` 的 `ocr_runtime` 支持三种模式。

- `nas_preferred` 先调用 `PADDLEOCR_SERVICE_URL`，失败后仅在远程 URL、模型和 API key 都完整时调用 Remote OCR。
- `nas_only` 只调用 NAS PaddleOCR。
- `remote_only` 只调用完整配置的远程 OCR。

OCR 请求固定声明中文、英文和繁体中文，当前值为 `ch,en,chinese_cht`。这能覆盖中英数字混排的语言请求，但是否正确识别真实乱码样本仍需以 OCR 输出和 Reader 文字层共同验收。

### 5.3 Django 侧配置

| 环境变量 | 用途 | 当前默认 |
| --- | --- | --- |
| `PADDLEOCR_SERVICE_URL` | 本地 OCR 服务根地址 | 空；Compose 中通常指向 `http://paddleocr:8010` |
| `OCR_REMOTE_API_URL` | 远程 OCR 根地址 | 空 |
| `OCR_REMOTE_API_KEY` | 远程 OCR 密钥 | 空 |
| `OCR_REMOTE_MODEL` | 远程 OCR 模型名 | 空 |
| `OCR_REQUEST_TIMEOUT_SECONDS` | OCR 请求超时 | 3600 秒 |
| `OCR_PAGE_BATCH_SIZE` | 每个后台任务处理的页数 | 4，限制为 1 至 50 |

OCR Runtime 页面保存的 mode、remote URL 和 remote model 会在任务运行时读取。API key 和 NAS URL来自进程环境。修改环境变量后必须重启 API 与 worker。仅修改数据库中的 runtime 设置不需要重启，但每个任务会记录当时的 settings version。

### 5.4 OCR 服务容器配置

下列变量由 `ocr_service` 消费，不是 Django 业务设置。

- `OCR_PRIMARY_LANGUAGE`
- `OCR_FALLBACK_LANGUAGE`
- `OCR_RENDER_DPI`
- `OCR_MAX_PAGES`
- `OCR_ENABLE_STRUCTURE`
- `OCR_REQUIRE_FALLBACK`
- `OCR_REQUIRE_STRUCTURE`
- `OCR_REQUIRE_PERSISTENT_MODELS`

当前 Compose 默认关闭 structure，要求持久模型目录，不把繁体回退或 structure 设为整体 readiness 的必需项。生产值仍应从实际容器只读核对。

### 5.5 降级与保护

- ORIGINAL_PDF 不由 OCR 覆盖。
- 阅读器视觉层继续使用稳定原始或规范 PDF。
- OCR 成功后逐页文字、坐标和可选 OCR_PDF 成为派生数据。
- OCR_PDF 只有通过文件、页数、校验值和来源验证后才能成为默认下载。
- OCR pending、failed 或 disabled 不阻止管理员发布。发布台会显示 warning。
- OCR 失败不应改变 publication status，也不能删除原文件。
- 自动重试由任务记录约束。失败任务保留错误、engine、attempt、起止时间和手工重试入口。

## 6. 语义检索与 Hugging Face

### 6.1 当前配置

| 环境变量 | 用途 | 当前模板值 |
| --- | --- | --- |
| `SEMANTIC_SEARCH_ENABLED` | 总开关 | `true` |
| `SEMANTIC_SEARCH_PROVIDER` | embedder provider | `huggingFace` |
| `SEMANTIC_SEARCH_MODEL` | 模型 repo ID | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `SEMANTIC_SEARCH_MODEL_REVISION` | 固定模型 revision | 模板使用精确提交哈希 |
| `SEMANTIC_SEARCH_MODEL_POOLING` | pooling | `useModel` |
| `SEMANTIC_SEARCH_MODEL_CACHE` | 本地模型根目录 | `/models` |
| `SEMANTIC_SEARCH_OFFLINE_MODE` | 应用侧离线检查 | `true` |
| `HF_HUB_OFFLINE` | Hugging Face 客户端离线模式 | `1` |
| `SEMANTIC_SEARCH_RATIO` | 关键词与语义融合权重 | `0.72` |
| `SEMANTIC_SEARCH_RERANKER` | reranker 名称 | `rules` |
| `SEMANTIC_SEARCH_REQUIRED` | 是否把语义失败视为必需服务失败 | `false` |
| `SEMANTIC_INDEX_STAGE_BATCH_SIZE` | 候选版本每批排队量 | `1` |
| `SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS` | 候选索引等待上限 | `1800` 秒 |
| `SEMANTIC_SEARCH_TIMEOUT_SECONDS` | 查询超时 | `30` 秒 |
| `SEMANTIC_SEARCH_MAX_CONCURRENT` | 查询并发上限 | `2` |

当前模型健康检查会确认 Hugging Face cache 目录、snapshot、revision 引用和关键文件。离线模式下缺文件会返回模型不可用，不会临时联网下载。

### 6.2 查询降级

语义查询先建立关键词候选。只有语义开关开启、engine 为 `meilisearch_hybrid` 且模型健康检查通过时，才请求向量候选。

以下情况会降级为关键词结果。

- 本地模型目录或 revision 不完整。
- Meilisearch 向量请求失败。
- 语义开关关闭。
- 当前策略明确选择 keyword。

返回值会给出 `fallback_used` 和 `fallback_reason`。前台显示简洁说明，不显示 Hugging Face DNS 等原始错误。`SEMANTIC_SEARCH_RATIO` 只在同时存在关键词和向量结果时表示融合权重，不是质量分数。

### 6.3 版本化索引

当前源码可创建独立 UID 的 `SemanticIndexVersion`。候选快照会分批建立，不影响 active 索引。人工切换路径会验证以下内容。

1. 候选版本状态为 ready。
2. 全部任务成功完成，没有 partial 任务。
3. 候选版本具有完整、无密钥的配置快照；构建和评估都显式使用该快照。
4. 本地模型健康检查通过。
5. Meilisearch 实际文档数、任务统计和预期文档数一致。

提交不同模型时不会提前覆盖生产 `semantic_search_runtime`。通过验证并由管理员确认后，系统才在数据库事务中把旧 active 版本标为 retired，激活候选版本，并把候选快照中的运行字段提升为有效配置。旧索引不会在该事务中被删除，便于回退。

当前 MiniLM 仍是 embedding 模板默认模型。Qwen3-Embedding-0.6B 没有被设为当前生产模型。`Qwen/Qwen3-Reranker-0.6B` 只是 V2 adapter 的模板候选名称，默认 provider 仍为 `rules`，本轮没有下载或运行该权重。更换 embedding 前必须建立新 revision，并使用本馆中英文查询评估，不能直接覆盖旧向量。

### 6.4 评估现状与尚未完成项

- SearchEvaluation 已有管理员页面与 API。它支持评估集、单条查询、人工相关性判断、dry-run、同步执行和 Celery 异步运行。等级 1 明确表示“同主题但未回应”，只有等级 2 和 3 计为有效证据。
- 当前指标包括 Recall@20、nDCG@10、MRR、Precision@5、Top5 Useful Passage Rate、Top3 Direct Response Rate、zero result rate、p50、p95、Reranker 生效率和降级率。评估不会切换活动索引。
- `catalog.0023` 保存任务 ID 和已完成查询数。`catalog.0024` 保存更新后的四级判断文案。`benchmark_opinion_search` 可以比较 V1、V2-A、V2-B、V2-C 和 Rerank Top K 为 8、12、16、24、32 的结果。
- `catalog.0025` 保存候选索引的无密钥运行快照与协作式暂停请求。`catalog.0026` 为观点反馈增加非空条件唯一键，使同一账号或匿名第一方会话的重复反馈更新原票。
- `evals/semantic_search/seed_queries.jsonl` 只有未标注问题，不包含伪造 gold。没有真实判断和真实索引时，比较结果统一标为 `待核实`。
- 批量评估集导入、跨索引版本报告和系统级并发资源采样尚未完成。
- Meilisearch 在目标 NAS 断网条件下是否完全只读本地 Hugging Face cache，仍需真实环境写入和查询验证。

### 6.5 观点检索 V2 与 Reranker

[SOURCE] V2 保留现有 embedding 和 V1。模板默认 `SEMANTIC_SEARCH_V2_ENABLED=false`。首轮只在查询阶段增加 Meilisearch 关键词召回、dense 召回、RRF、有界精排、相邻重复去除和上下文恢复。当前 SemanticChunk 与索引文档已经包含题名、章节、原文、前后文和页码，因此不改变 embedding 或分块时，无需仅为了首轮 V2 重建全部索引。

V2 profile 如下。

| Profile | 当前含义 |
| --- | --- |
| `fast` | 原始问题的关键词与 dense 召回，加 RRF，不扩展、不调用模型精排 |
| `balanced` | 在 fast 上对小候选集执行 passage 级模型精排，不加入 parent context |
| `precision` | 加保守问题类型、最多三条补充表达、规则信号和包含题名、章节、相邻段落的模型精排 |

`semantic_reranker.py` 只负责调用持久模型服务。它不会在 Django 请求中加载模型，也不会发送完整 PDF。当前 adapter 约束包括：

- provider 只允许 `rules` 或 `local_http`。
- 主机必须在 `SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS`。
- 不跟随重定向，URL 不允许嵌入凭据、查询参数或片段。
- 精排候选最多 64 条，每条候选有字符上限，请求总体有大小边界。
- 服务错误、超时或返回格式错误时设置 `reranker_fallback`，保留已有排序。

| 环境变量 | 用途 | 模板默认 |
| --- | --- | --- |
| `SEMANTIC_SEARCH_V2_ENABLED` | 公共查询是否默认使用 V2 | `false` |
| `SEMANTIC_SEARCH_PROFILE` | `fast`、`balanced` 或 `precision` | `precision` |
| `SEMANTIC_SEARCH_DENSE_TOP_K` | dense 候选上限 | `50` |
| `SEMANTIC_SEARCH_SPARSE_TOP_K` | 关键词候选上限 | `50` |
| `SEMANTIC_SEARCH_FUSION_TOP_K` | RRF 后候选上限 | `24` |
| `SEMANTIC_SEARCH_RERANK_TOP_K` | 模型精排候选数 | `24` |
| `SEMANTIC_SEARCH_FINAL_TOP_K` | 最终返回上限 | `10` |
| `SEMANTIC_SEARCH_QUERY_EXPANSION_MAX` | 补充表达上限 | `3` |
| `SEMANTIC_SEARCH_V2_RERANK_PROVIDER` | `rules` 或 `local_http` | `rules` |
| `SEMANTIC_SEARCH_V2_RERANK_URL` | 持久重排服务完整地址 | 空 |
| `SEMANTIC_SEARCH_V2_RERANK_MODEL` | 服务端模型名 | `Qwen/Qwen3-Reranker-0.6B` |
| `SEMANTIC_SEARCH_V2_RERANK_API_KEY` | 可选 Bearer 密钥 | 空 |
| `SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS` | 允许访问的主机 | 本地服务名与回环地址 |
| `SEMANTIC_SEARCH_V2_RERANK_TIMEOUT_SECONDS` | 单次调用超时 | `15` 秒 |
| `SEMANTIC_SEARCH_V2_RERANK_MAX_TEXT_CHARS` | 单候选最大字符数 | `4000` |

`Qwen/Qwen3-Reranker-0.6B` 的[官方模型卡](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)把它描述为多语种文本重排模型。它尚未在本 NAS 验证，不能从模型卡推断本馆精度、单次耗时或内存峰值。BGE-M3 和 BGE reranker 的可选方向见 [FlagEmbedding 官方仓库](https://github.com/FlagOpen/FlagEmbedding)。模型选择必须使用 `docs/opinion-search-v2-benchmark.md` 中的馆内评估。

完整设计、首轮无需重建的依据、渐进式重建条件和 V1 回退见：

- `docs/opinion-search-v2-audit.md`
- `docs/opinion-search-v2-design.md`
- `docs/opinion-search-v2-benchmark.md`

## 7. 设置生效规则

| 配置来源 | 生效方式 | 验证方法 |
| --- | --- | --- |
| `.env` 和 Compose 环境变量 | 相关容器重启后加载 | 查看 System Health 的有效配置，并运行最小测试 |
| `SiteSetting.ocr_runtime` | 新 OCR 任务运行时读取 | 查看任务的 settings version 和实际 engine |
| `SiteSetting.semantic_search_runtime` | 查询和索引服务运行时读取 | 查看当前运行配置、模型健康和测试查询 |
| 上传批次策略 | 创建批次时冻结在 UploadBatch | 查看批次详情和 UploadItem preflight summary |

保存设置只能证明值已存储。必须同时核对 consumer、有效配置和一个真实但低成本的测试请求。模型或 embedding 变更还需要建立新索引，不能只重启服务。

## 8. 生产前检查

1. 环境文件没有真实密钥进入代码包、日志或版本管理。
2. AI 和 metadata provider 的 allowlist 只包含明确批准的主机。
3. AI 默认保持关闭，除非管理员确认数据范围和模型服务。
4. PaddleOCR 模型在持久卷，容器重启后仍能通过 readiness。
5. 远程 OCR 配置不完整时显示 not configured，不降低本地 OCR 健康状态。
6. Hugging Face 模型的 repo、revision、tokenizer、config 和权重均已预置。
7. 断开公网后运行一次语义写入与查询，确认没有隐式下载。
8. 新索引完成计数验证和本馆查询评估后再人工切换。
9. 旧 active 索引、旧模型和原始 PDF 的回退入口仍可用。
10. 用真实扫描书、born-digital PDF 和中英数字混排页分别验收 OCR、复制、搜索和引用页码。

以上检查未完成时，模型服务状态应标为待核实，不应写成生产可用。

## 9. 2026-08-15 候选整理与书库问答增量

### 9.1 人物与知识对象权威候选

[SOURCE] `catalog.services.authority_suggestions` 先查本馆人物、学科、子学科、理论节点、理论流派与主题，再按查询语言与对象类型请求外部候选。候选只回到管理表单，采用动作仅修改当前草稿，不自动合并实体、锁定字段或发布。

| 查询情形 | 候选来源 | 用途与限制 |
| --- | --- | --- |
| 全部对象 | 本馆权威库、Wikidata | 本馆已有实体优先显示；Wikidata 为外部候选，不是定案来源 |
| 人物 | VIAF、OpenAlex | 用于别名、原文名、权威标识和当代学术人物辅助消歧 |
| 非中文查询 | Library of Congress Linked Data | 补充外文人物、机构与受控主题候选 |
| 中文查询 | 本馆、Wikidata；人物再查 VIAF 与 OpenAlex | 不因英文来源排名高就覆盖中文译名或生卒年冲突 |

[SOURCE] 外部请求仅允许 HTTPS 且主机必须在 `AUTHORITY_PROVIDER_ALLOWED_HOSTS` 中，禁止自动跟随重定向，默认检查 DNS 是否解析到私网、回环或链路本地地址，响应上限为 500 KiB。成功响应建立七天有效的 `SourceRecord`；缓存命中不再请求外网。

[UNKNOWN] Wikidata、VIAF、LOC 和 OpenAlex 在 NAS 网络下的真实可用率、限流和中文候选质量待核实。当前实现没有绕过凭据访问中文商业书目站，也没有抓取未明确允许的页面。

### 9.2 `candidate-reconciliation-v2`

[SOURCE] `ingestion.services.ai_candidate_filter` 增加了社会理论书库专用候选整理提示词与严格 JSON Schema。其输入必须是系统已获得的候选、`SourceRecord` 和证据标识；模型不能自行联网，不能生成白名单外 ID，不能直接写库。

当前契约要求：

- 区分抽象作品和具体版本，不用出版社当前总部推断历史出版地。
- 不把作者、译者、编者、出版者、发行者和印刷者混成同一角色。
- 中外文人物可以用姓名、简繁体、译名和拼音召回，但不得仅凭同名合并。
- 理论影响、批判、代表学者、奠基作品和时间轴解释始终带 `requires_human_review=true`。
- 输出只能是 `retain`、`reject` 或 `needs_review`，不接受模型自报置信度。

[SOURCE] 权威候选界面另使用 `authority-candidate-reconciliation-v2` 做可选重排。两个模型路径都只影响候选顺序或处理标记，管理员仍需手工采用。

[UNKNOWN] 真实本地小模型、中转站、返回质量和并发峰值本轮尚未运行验证。

### 9.3 “向书库提问”模型边界

[SOURCE] 问答使用已有 `AI_PROVIDER=none|ollama|vllm|openai_compatible` 抽象，并从 `AI_LIBRARY_MODEL` 读取问答模型。`AI_LIBRARY_MAX_CONCURRENCY`、`AI_LIBRARY_MAX_OUTPUT_TOKENS` 与 `AI_LIBRARY_MAX_OUTPUT_CHARS` 限制并发和输出。发送给模型的上下文只来自当前仍已发布、可读且资产归属匹配的馆藏片段。

[SOURCE] 会话模式包括自动判断、只依据书库和不检索书库。模型经上游真实流式响应后，Django 用 `meta`、`delta`、`sources`、`done` 与 `error` 事件向前端传递 SSE。来源先显示书名、作者、印刷页码与 PDF 页序，读者主动展开时才解密并返回摘录。只返回回答实际引用的来源。

[SOURCE] 问答正文、来源摘录和会话历史以现有私有文本加密服务保存。每个用户只能读自己的会话。历史回答中的 `[S#]` 标识在生成新一轮请求前会被移除，避免旧引用错绑到新来源。原始 retrieval context、向量、相似度、系统提示词和服务端密钥不返回给浏览器。

[SOURCE] 模型未配置、停用或暂时不可用时，status API 会返回有限的用户可读说明。已有会话和当时仍可用的来源可继续阅读，但不会伪造新回答。

[UNKNOWN] 本地 Ollama/vLLM/OpenAI-compatible 服务的真实流式兼容、Redis 并发槽和 NAS 长连接稳定性待核实。
