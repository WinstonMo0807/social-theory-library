# 2026-10-18 检查点依赖核对

## 2026-10-18 页码与Reader继承依赖补存

逐文件读diff后，将本单元必需的既有修改一并保存：catalog/views/public_response_serializers/serializers（公开目录、坐标、修订/来源身份、OCR阅读策略）；distribution/serializers/services（策略契约及同源OCR副本守卫）；catalog/search_geometry/evidence_envelope/document_intelligence（坐标缓存身份、文字范围、几何摘要与不可变证据）；ingestion/tasks的process_outline_job（已提交目录服务的实际Celery入口）。geometry/public_outline/public_hot_searches等引用的实现已在HEAD，不重复新建。

distribution/views仅保存经审查的同源OCR副本选择和Range/OpenAPI相关差异；继承的备份dispatch差异仍留工作区，与本单元不混存。test_resilient_publication_v260保留既有几何fixture补充，同时将页73回归改为新候选→prepare→明确采用契约。schema_urls保存与实际业务路由一致的既有入口及本轮新增入口。以上为源码恢复依赖，不称本轮新功能或正式验收；未启动任务、备份或服务。

本轮只静态核对源码与 Git。HEAD 321787d 的研究、Reader 和 API 已引用工作区未提交/未跟踪实现；旧提交不能单独作为完整恢复证据。以下源码保留原实现并纳入恢复检查点，不代表功能验收通过。

| 已提交调用方 | 必需的既有工作区实现 |
|---|---|
| config/settings.ApiContractMiddleware | common/middleware.py 的同名类 |
| home_views / discovery_projection | analytics.public_hot_searches / text.page_text_range |
| catalog/urls、后台目录与内容编排、任务 | outline/content_placement/editorial_assistance 路由与服务、editorial_blocks/discovery_material、ProcessingJob 枚举 |
| catalog 0066、ProcessingJob 类型 | catalog 0064→0065 迁移链，ingestion 0020；只保存源码，不执行迁移 |
| private_ocr | ocr_provider 的 bytes、timeout、headers、transport 参数，python-docx 与 RapidFuzz 依赖声明 |
| Discovery 深度与研究回读 | ranking_applied、服务制品身份校验、ConvMemory 不改变主结果顺序及契约用例 |
| Reader shell / research client | 实际匹配的 Reader hooks、坐标/目录/引用/分页/轮询 helpers 与文档类型 |

静态扫描覆盖已跟踪应用 Python/TypeScript 的本地导入及新增依赖的递归导入。未加载应用、未调用模型、未运行正式测试；动态导入、服务配置和运行一致性仍在最终验收中核实。凭据模式检查只用于避免误纳明显令牌，不等于全仓安全审计。

本批明确路径：

- `api/catalog/content_placement_urls.py`
- `api/catalog/content_placement_views.py`
- `api/catalog/editorial_assistance_views.py`
- `api/catalog/migrations/0064_document_outline_revision.py`
- `api/catalog/migrations/0065_content_placement_choice.py`
- `api/catalog/outline_views.py`
- `api/catalog/services/analytics.py`
- `api/catalog/services/api_contract.py`
- `api/catalog/services/content_placements.py`
- `api/catalog/services/discovery_material.py`
- `api/catalog/services/document_outline.py`
- `api/catalog/services/editorial_assistance.py`
- `api/catalog/services/editorial_blocks.py`
- `api/catalog/services/retrieval/deep_pipeline.py`
- `api/catalog/services/text.py`
- `api/common/middleware.py`
- `api/ingestion/migrations/0020_editorial_assistance_job.py`
- `api/ingestion/models.py`
- `api/ingestion/services/ocr_provider.py`
- `api/ingestion/services/source_identity.py`
- `api/requirements.txt`
- `api/tests/test_deep_pipeline_contract.py`
- `web/app/reader/[assetId]/page.tsx`
- `web/components/admin/ocr-index-work-helper.tsx`
- `web/components/pdf-canvas.tsx`
- `web/components/pdf-continuous-viewer.tsx`
- `web/components/public/issue-block-view.tsx`
- `web/components/reader-book-notes.tsx`
- `web/components/reader/types.ts`
- `web/components/reader/use-reader-citation.ts`
- `web/components/reader/use-reader-document.ts`
- `web/components/reader/use-reader-navigation.ts`
- `web/components/reader/use-reader-page-overlays.ts`
- `web/components/reader/use-reader-records.ts`
- `web/components/reader/use-reader-search.ts`
- `web/lib/api.ts`
- `web/lib/api/curation-workspace.client.ts`
- `web/lib/api/document-outline.ts`
- `web/lib/api/read-all-pages.ts`
- `web/lib/api/reader-failure.ts`
- `web/lib/api/reader.server.ts`
- `web/lib/api/research-navigation.ts`
- `web/lib/api/task-polling.ts`
- `web/lib/reader-coordinates.ts`
