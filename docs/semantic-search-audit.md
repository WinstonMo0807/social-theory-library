# 观点检索代码审计

审计日期：2026-07-31
适用版本：2.2.x

## 1. 当前系统架构

项目由 Vinext 前端、Django REST API、PostgreSQL、Redis、Celery、Meilisearch 和独立 PaddleOCR 服务组成。PDF 原件保存在 NAS 挂载目录。API 与 Worker 共享馆藏、公开文件和入库目录。上传、OCR、文本持久化、原文索引和发布由 Celery 串行执行，当前 Worker 并发为 1，适合 8GB 内存的 NAS。

公开检索由 `api/catalog/views.py` 提供。原文索引写入 `passages` Meilisearch 索引。阅读器使用 `Page`、`TextBlock` 和 `Passage` 的页序与坐标数据定位结果。现有所谓模糊检索位于 `api/catalog/services/semantic_search.py`，可选择轻量词法近似或 Meilisearch hybrid 请求，但尚未形成独立、可维护的语义分块与索引状态。

## 2. 当前搜索流程

原文检索接收题名、责任者、正文和筛选参数。API 查询馆藏元数据，并从 Meilisearch 获取全文段落，结果携带作品、版本、PDF 页序和跳转地址。文献发布时调用 `api/ingestion/services/indexing.py` 写入索引；下架或替换时按 `asset_id` 删除旧条目。

现有模糊检索接收查询后，使用字符 n-gram、`SequenceMatcher` 和知识关系加权，或直接向原文索引发起 hybrid 请求。它只完整支持文献类型与语言筛选，前端显示未经校准的相似度百分比。查询理解、稳定的向量模型版本、语义分块、重排、去重、同书限额、反馈和索引任务状态均不完整。

阅读器文档内搜索使用 `/api/catalog/assets/{asset_id}/search/`。后端已经按页返回命中摘要、页码标签和高亮坐标。前端只显示命中总数，并在回车时跳到首条结果，没有可选择的命中候选列表。

## 3. 当前文本分块方式

`api/ingestion/services/extract.py` 先使用 PyMuPDF 读取文本层。可提取文字过少时，调用 PaddleOCR。页面、文本块和段落分别写入 `Page`、`TextBlock` 与 `Passage`。

当前 `Passage` 主要在单页内按约 700 个字符机械合并文本块。它保留页码与合并坐标，适合原文检索和阅读器高亮，但无法稳定表达完整观点，也不能可靠保存章节、小节、前后段关系和跨页段落。页眉页脚已有重复边注识别，但目录、参考文献、脚注、双栏顺序、断词和跨页断段仍可能进入结果。

## 4. 当前模糊检索的问题

1. 轻量模式本质上仍是词法近似，不能理解自然语言改写、因果判断和研究问题。
2. hybrid 模式复用原文块，没有独立的分块版本、模型版本和内容哈希。
3. 过滤条件少于原文检索，作者、年份、学者、流派、专题和标签无法可靠进入后端查询。
4. 没有标准 RRF 融合、可替换重排器和重排故障回退。
5. 同页重复、相邻重叠和同一本书占据大量前排结果未被系统处理。
6. 相似度被显示为百分比，容易被误解为观点相同程度。
7. 索引失败与重建缺少清晰状态，管理员无法单本重建、只重试失败项或清理孤立条目。
8. 文献替换、下架与删除只维护原文索引，没有独立语义索引的一致性检查。
9. 缺少可扩展的标注集、搜索反馈与质量评估程序。
10. 模型或外部服务不可用时，当前提示和降级行为不够明确。

## 5. 可以复用的现有模块

- `Page`、`TextBlock` 和 `Passage` 已保存原文、页序、书页标签和页内坐标，可作为语义分块的可靠来源。
- `api/ingestion/services/indexing.py` 已实现 Meilisearch 设置、公开权限过滤、发布写入和下架清理。
- Celery、Redis、处理中心和失败重试基础已经存在。
- `GlobalSearchView` 已实现文献类型、作者、年份、语言、开放状态与流派筛选，可抽成原文和观点检索共用的过滤结构。
- `PassageFocusView` 与阅读器 `passage` 参数已能定位页码和坐标，可兼容新的语义块定位器。
- 现有本地 MiniLM 配置、OpenAI 兼容接口和 Ollama 配置可收敛为可替换的 Embedding 适配层。
- 现有后台设置与处理中心可承载语义索引管理，无需另建管理应用。

## 6. 不应修改的核心模块

- 不改变 PDF 原件、下载与 Range 读取接口。
- 不改写阅读器现有 `Page`、`TextBlock`、高亮、划线、笔记、书签和阅读进度关系。
- 不用语义分块替换现有 `Passage`，原文检索继续使用原索引和页级文本层。
- 不让语义索引失败阻止上传、在线阅读、下载、普通原文检索和发布。
- 不引入 RAGFlow、Dify 或 LangChain 重写业务代码。
- 不在首版引入独立 Qdrant 服务，避免给 8GB NAS 增加常驻内存和维护负担。
- 不向外部服务发送全文，除非管理员明确开启并配置外部提供方。

## 7. 需要修改的文件

后端主要涉及：

- `api/catalog/models.py` 与迁移文件
- `api/catalog/services/semantic_search.py`
- 新增语义分块、索引、模型适配和评估服务
- `api/catalog/views.py`、`serializers.py` 与 `urls.py`
- `api/ingestion/services/extract.py`、`pipeline.py`、`indexing.py` 与 `tasks.py`
- `api/ingestion/views.py` 和复核序列化器
- `api/catalog/services/citations.py`
- `api/config/settings.py` 与环境变量示例

前端主要涉及：

- `web/app/explore/page.tsx`
- `web/components/reader-shell.tsx`
- `web/components/admin-shell.tsx`
- `web/components/admin-sections.tsx`
- `web/components/metadata-review.tsx`
- `web/app/about/page.tsx`
- `web/lib/server-api.ts`
- `web/app/globals.css`

## 8. 可能涉及的数据迁移

需要新增语义块、语义索引任务、搜索反馈、出版地证据、出版社规范和出版地修改历史数据表。`Edition.publication_place` 暂时保留为兼容字段，由已确认的主要出版地同步写入。这样旧页面、引用和已有数据不会在迁移后失效。迁移只新增表和索引，不删除既有字段，可逆操作只需删除新增表。

已有馆藏不会在迁移时同步生成向量。后台任务会按内容哈希逐本建立语义块与索引，支持暂停、恢复和失败重试。

## 9. 性能风险

- 首次全库生成向量会长期占用 CPU。必须限制并发，并与 OCR 串行或错峰执行。
- Meilisearch 首次下载本地 Hugging Face 模型需要网络，模型目录必须持久化。
- 大模型、1024 维向量或常驻 Cross-Encoder 可能超过 8GB NAS 的舒适范围。
- 跨页分块和上下文会增加数据库与索引体积，应以内容哈希避免重复处理。
- 搜索时同时执行关键词与向量召回会增加延迟，需要超时、候选规模上限与故障降级。
- 章节识别和双栏顺序仍依赖 PDF 质量，低置信结果要保留原文与页内坐标，不能用清洗文本覆盖阅读器文本层。

## 10. 回退方案

通过 `SEMANTIC_SEARCH_ENABLED` 整体关闭观点检索。关闭后页面仍可使用原文检索，向书库提问保持不可用状态。Embedding 不可用时，观点检索退回关键词召回；重排器不可用时使用 RRF 结果；查询改写失败时只使用原始查询；语义索引未完成的文献仍可由原文检索找到。新增表不修改现有检索数据，数据库回退不会损坏原文索引。

技术依据使用 Meilisearch 官方的本地 Hugging Face Embedder、hybrid search 与任务监控能力，以及 Sentence Transformers 官方多语言 MiniLM 模型卡。模型和引擎选择的取舍见 `docs/semantic-search-design.md`。
