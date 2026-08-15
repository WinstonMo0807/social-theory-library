# 观点检索技术方案

设计日期：2026-07-31
目标设备：绿联 DH4600，8GB 内存，CPU 模式

## 1. 检索引擎

首版复用现有 Meilisearch，不新增 Qdrant。原文检索继续使用 `passages` 索引，观点检索使用独立的 `semantic_passages` 索引。独立索引可以采用不同分块与 Embedder 设置，也能在关闭或重建观点检索时避免影响原文检索。

Meilisearch 社区版支持本地 Hugging Face Embedder、语义查询和 hybrid search。应用层负责统一筛选、RRF 候选融合后的补充排序、重叠去重、同书限额和可解释结果。索引服务不可用时，API 退回数据库关键词候选。

暂不选择 pgvector，因为当前 PostgreSQL 镜像没有该扩展，替换数据库镜像会提高升级风险。暂不选择 Qdrant，因为现有引擎已具备所需能力，新增常驻服务会增加内存、镜像和备份成本。RAGFlow、Dify 与 LangChain 不进入实现范围。

## 2. Embedding 模型

默认模型为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。它支持中英文等 50 种语言，输出 384 维向量，Apache-2.0 许可证，模型规模约 0.1B，适合 CPU 与 8GB NAS。模型由 Meilisearch 本地加载，缓存目录持久化，容器重建不重复下载。

`BAAI/bge-m3` 保留为管理员可选方案。它支持多语言、长文本和 dense/sparse 能力，采用 MIT 许可证，但 1024 维与更大模型会显著增加内存、首次索引时间和磁盘占用，不作为默认值。外部 OpenAI 兼容 Embedding 适配器默认关闭，开启时后台明确提示会发送经过分块的馆藏文本。

## 3. Reranker 与查询改写

首版提供可替换 Reranker 接口。默认使用无常驻模型的规则重排，综合 RRF 排名、章节命中、关键词覆盖、来源质量和重复惩罚。轻量 Cross-Encoder 只保留适配入口，本版不默认下载或常驻加载。规则重排发生异常时直接保留混合召回顺序。

查询理解第一层始终离线运行，完成查询清洗、类型判断、关键词抽取、馆内人物、流派、专题与概念扩展。第二层查询改写为可选提供方，默认关闭。原始查询始终参与检索，改写失败不影响结果。向书库提问只保留 API 契约和关闭的 UI 入口，不生成回答。

## 4. 数据结构

新增 `SemanticChunk`，字段包含文献与作品外键、起止 PDF 页、章节、小节、段落序号、原文、规范化文本、前后文、语言、文献类型、解析版本、分块版本、模型与版本、内容哈希、定位器 JSON、索引状态、错误与时间。

定位器保存一个或多个 `{page_index, printed_label, bbox, text}`。跨页段落可以作为一个搜索结果，同时仍能跳到首个命中页并展开后续页。原始文本永远用于前台展示，规范化文本只用于检索。

新增 `SemanticIndexJob`，记录单本、批量、失败重试、清理、暂停和测试任务的状态、进度、Celery 任务号、尝试次数、错误摘要和统计。

新增 `SemanticSearchFeedback`，记录脱敏查询哈希、可选评估查询、结果块、排名、相关或不相关、用户和调试数据。私人批注与笔记不进入索引。

出版地使用独立的 `PublicationPlaceEvidence`、`PublisherAuthority` 与 `PublicationMetadataRevision`。`Edition.publication_place` 作为兼容字段，只同步已确认的主要出版地。多出版地与不同地点类型保存在证据表。

## 5. 分块与清洗

分块来源为持久化后的 `TextBlock`，不直接改写阅读器文本层。处理顺序为：

1. 剔除已识别的页眉页脚与孤立页码。
2. 依据版面类型与标题特征识别章节、小节、目录、脚注和参考文献。
3. 修复段内断行、拉丁连字符和多余空格，原文另存。
4. 以自然段为基础。短段在同一小节内合并，过长段按句子拆分。
5. 检测跨页未结束段落，并用定位器保存两页关系。
6. 保存前后段上下文，计算内容哈希和分块版本。

首版目标块长度为 250 至 900 个汉字或等量字符，允许根据完整句子越界，不按固定长度硬切。目录与参考文献默认降低排序权重，不从数据库删除。

## 6. API 结构

- `GET /api/catalog/search/`：原文检索，保持现有行为并扩展专题、概念和标签筛选。
- `GET /api/catalog/semantic-search/`：观点检索，接收与原文检索一致的筛选条件、排序、上下文和同书限额。
- `POST /api/catalog/semantic-search/feedback/`：提交相关性反馈。
- `GET /api/catalog/passages/{id}/focus/`：兼容原文段落和语义块定位。
- `GET /api/catalog/assets/{id}/search/`：阅读器文档内搜索，返回按页和命中顺序排列的候选。
- `GET/POST /api/catalog/admin/semantic-index/`：查看状态、暂停、恢复、重建、重试失败和清理孤立索引。
- `POST /api/catalog/admin/semantic-index/test-query/`：管理员测试查询并查看调试排名。
- `GET/PATCH /api/catalog/site-config/` 与公开统计接口：关于页内容和动态统计。
- 出版地候选、确认、修改和重新识别接口挂在现有元数据复核项目下。

## 7. 异步任务流程

上传 PDF 后，原有流程完成文献记录、解析、OCR、文本清洗、页与原文块保存、原文索引和发布。随后建立语义索引任务，状态依次为分块、生成向量、写入索引和完成。任务失败时文献标记为部分完成，但不撤销发布。

内容哈希由公开 PDF 校验值、分块版本和模型版本组成。哈希未变化时不重复生成。单本任务可重试，批量任务只分派尚未完成或版本过期的文献。Worker 并发保持 1，后台可暂停新任务。

文献更新先删除该 `asset_id` 的旧语义条目，再构建新块。删除或下架会同时清理 `passages` 与 `semantic_passages`。孤立清理任务比较数据库资产和索引中的 `asset_id`。

## 8. 混合检索与排序

关键词召回与向量召回各取最多 80 条，通过 Reciprocal Rank Fusion 合并为 50 条。可选 Reranker 处理前 30 条。结果按页内文本相似度去重，相邻段落可合并上下文但只保留一个主结果。默认前 10 条同一作品最多 2 条，用户可关闭该限制并查看本书更多段落。

返回结果包括原文、章节、小节、页序、印刷页码、上下文、定位地址、查询理解、主要相关概念和匹配说明。公开页面只显示“高度相关”“较为相关”“可能相关”。开发模式另行返回关键词名次、向量名次、RRF、Reranker、最终名次和耗时。

## 9. 回退方式

- Embedding 不可用：使用数据库和 Meilisearch 关键词候选。
- Reranker 不可用：保留 RRF 顺序。
- 查询改写不可用：只搜索原始查询。
- 向量索引不可用：观点检索返回带降级说明的关键词结果。
- 尚未完成语义索引的文献：仍参与原文检索。
- OCR 失败：文本型 PDF 继续使用原文本层。
- 单本失败：记录错误并继续处理其他文献。
- `SEMANTIC_SEARCH_ENABLED=false`：恢复原有原文检索，观点检索显示未启用。

## 10. 配置与性能估计

新增配置沿用现有环境变量风格：

- `SEMANTIC_SEARCH_ENABLED`
- `SEMANTIC_SEARCH_PROVIDER`
- `SEMANTIC_SEARCH_MODEL`
- `SEMANTIC_SEARCH_RERANKER`
- `SEMANTIC_SEARCH_RATIO`
- `SEMANTIC_SEARCH_TIMEOUT_SECONDS`
- `SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK`
- `SEMANTIC_SEARCH_QUERY_REWRITE_ENABLED`
- `SEMANTIC_SEARCH_REQUIRED`
- `SEMANTIC_SEARCH_INDEX_CONCURRENCY`
- `SEMANTIC_SEARCH_MODEL_CACHE`

384 维向量比 1024 维方案节省约 62.5% 的向量存储。实际索引耗时取决于 PDF 数量、页数和 CPU，不能在开发机测试后宣称为 NAS 实测。后台将显示单本文献耗时、累计吞吐、查询平均值和 P95。OCR 与全库重建不并行，保证在线阅读和原文检索优先。

## 11. 选择理由与维护成本

方案只新增数据库表、应用服务和一个 Meilisearch 索引，不增加常驻容器。MiniLM 使用 Apache-2.0，BGE-M3 使用 MIT，Meilisearch 社区版为 MIT。首版不会提交模型文件，模型缓存由部署目录持久化。主要维护成本是首次模型下载、索引版本升级后的后台重建，以及管理员积累质量标注。

若真实评估证明 MiniLM 无法满足中文社会科学观点检索，再以同一适配接口测试 BGE-M3 或外部模型。只有当 Meilisearch 在实际馆藏规模下无法稳定提供混合检索时，才评估 Qdrant，避免在没有证据时增加服务复杂度。
