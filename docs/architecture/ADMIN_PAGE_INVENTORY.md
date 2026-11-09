# 管理端完整页面清单

[架构目录](README.md) · [模块调用链](ADMIN_MODULE_CONTRACTS.md) · [组件使用表](ADMIN_COMPONENT_INVENTORY.md)

由 `scripts/architecture_page_map.py` 根据 TypeScript AST 生成，共79个入口。page/handler与兼容跳转分别保留；同一组件复用不等于独立业务。M编号连接人工核对的业务契约。全部业务页面经过 `app/admin/layout.tsx → AdminShell`；route handler只执行重定向，不运行React布局。

| URL | 入口与类型 | JSX入口/跳转 | 入口直接读取的 query | 业务链 |
| --- | --- | --- | --- | --- |
| `/admin` | [app/admin/page.tsx](../../web/app/admin/page.tsx) · page | AdminDashboard | —（见组件参数） | [M00](ADMIN_MODULE_CONTRACTS.md#m00) |
| `/admin/about` | [app/admin/about/page.tsx](../../web/app/admin/about/page.tsx) · page | SiteContentEditor | —（见组件参数） | [M13](ADMIN_MODULE_CONTRACTS.md#m13) |
| `/admin/about/preview` | [app/admin/about/preview/page.tsx](../../web/app/admin/about/preview/page.tsx) · page | SiteContentEditor | —（见组件参数） | [M13](ADMIN_MODULE_CONTRACTS.md#m13) |
| `/admin/analytics` | [app/admin/analytics/page.tsx](../../web/app/admin/analytics/page.tsx) · page | AdminAnalytics | —（见组件参数） | [M00](ADMIN_MODULE_CONTRACTS.md#m00) |
| `/admin/backups` | [app/admin/backups/page.tsx](../../web/app/admin/backups/page.tsx) · page | StorageWorkspace | —（见组件参数） | [M17](ADMIN_MODULE_CONTRACTS.md#m17) |
| `/admin/candidates` | [app/admin/candidates/page.tsx](../../web/app/admin/candidates/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/knowledge", await searchParams) | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/cataloging/[sessionId]` | [app/admin/cataloging/[sessionId]/page.tsx](../../web/app/admin/cataloging/[sessionId]/page.tsx) · page | CatalogingWorkbench | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/cataloging/[sessionId]/candidates` | [app/admin/cataloging/[sessionId]/candidates/page.tsx](../../web/app/admin/cataloging/[sessionId]/candidates/page.tsx) · page | CatalogingWorkbench | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/cataloging/new` | [app/admin/cataloging/new/page.tsx](../../web/app/admin/cataloging/new/page.tsx) · page | ManualCatalogForm | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/content` | [app/admin/content/page.tsx](../../web/app/admin/content/page.tsx) · page | PlacementDirectory | —（见组件参数） | [M12](ADMIN_MODULE_CONTRACTS.md#m12) |
| `/admin/content/[pageType]/[pageId]` | [app/admin/content/[pageType]/[pageId]/page.tsx](../../web/app/admin/content/[pageType]/[pageId]/page.tsx) · page | PlacementWorkspace | —（见组件参数） | [M12](ADMIN_MODULE_CONTRACTS.md#m12) |
| `/admin/disciplines` | [app/admin/disciplines/page.tsx](../../web/app/admin/disciplines/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/distribution` | [app/admin/distribution/page.tsx](../../web/app/admin/distribution/page.tsx) · page | DistributionAdmin | —（见组件参数） | [M17](ADMIN_MODULE_CONTRACTS.md#m17) |
| `/admin/intake/[itemId]` | [app/admin/intake/[itemId]/page.tsx](../../web/app/admin/intake/[itemId]/page.tsx) · page | IntakeWorkspace | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/knowledge` | [app/admin/knowledge/page.tsx](../../web/app/admin/knowledge/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/library` | [app/admin/library/page.tsx](../../web/app/admin/library/page.tsx) · page | WorkLibrary | —（见组件参数） | [M02](ADMIN_MODULE_CONTRACTS.md#m02) |
| `/admin/library/assets/[assetId]/ocr` | [app/admin/library/assets/[assetId]/ocr/page.tsx](../../web/app/admin/library/assets/[assetId]/ocr/page.tsx) · page | OCRWorkspaceView | —（见组件参数） | [M03](ADMIN_MODULE_CONTRACTS.md#m03) |
| `/admin/library/assets/[assetId]/outline` | [app/admin/library/assets/[assetId]/outline/page.tsx](../../web/app/admin/library/assets/[assetId]/outline/page.tsx) · page | DocumentOutlineWorkspace | —（见组件参数） | [M03](ADMIN_MODULE_CONTRACTS.md#m03) |
| `/admin/library/assets/[assetId]/page-mapping` | [app/admin/library/assets/[assetId]/page-mapping/page.tsx](../../web/app/admin/library/assets/[assetId]/page-mapping/page.tsx) · page | PageMappingWorkspace | —（见组件参数） | [M03](ADMIN_MODULE_CONTRACTS.md#m03) |
| `/admin/library/works/[workId]` | [app/admin/library/works/[workId]/page.tsx](../../web/app/admin/library/works/[workId]/page.tsx) · page | WorkflowEditor | —（见组件参数） | [M02](ADMIN_MODULE_CONTRACTS.md#m02) |
| `/admin/library/works/[workId]/files` | [app/admin/library/works/[workId]/files/page.tsx](../../web/app/admin/library/works/[workId]/files/page.tsx) · page | WorkFilesWorkspace | —（见组件参数） | [M02](ADMIN_MODULE_CONTRACTS.md#m02) |
| `/admin/media` | [app/admin/media/page.tsx](../../web/app/admin/media/page.tsx) · page | MediaLibrary | —（见组件参数） | [M14](ADMIN_MODULE_CONTRACTS.md#m14) |
| `/admin/people` | [app/admin/people/page.tsx](../../web/app/admin/people/page.tsx) · page | PersonAuthorityWorkspace | —（见组件参数） | [M05](ADMIN_MODULE_CONTRACTS.md#m05) |
| `/admin/preview/evidence/[objectType]/[objectId]` | [app/admin/preview/evidence/[objectType]/[objectId]/page.tsx](../../web/app/admin/preview/evidence/[objectType]/[objectId]/page.tsx) · page | EvidenceCurationEditor | —（见组件参数） | [M10](ADMIN_MODULE_CONTRACTS.md#m10) |
| `/admin/preview/knowledge/[objectType]/[objectId]` | [app/admin/preview/knowledge/[objectType]/[objectId]/page.tsx](../../web/app/admin/preview/knowledge/[objectType]/[objectId]/page.tsx) · page | AdminKnowledgePagePreview, KnowledgePublicationReview, SiteFooter, SiteHeader | —（见组件参数） | [M04](ADMIN_MODULE_CONTRACTS.md#m04) |
| `/admin/preview/works/[editionId]` | [app/admin/preview/works/[editionId]/page.tsx](../../web/app/admin/preview/works/[editionId]/page.tsx) · page | AdminWorkPagePreview, SiteFooter, SiteHeader | —（见组件参数） | [M04](ADMIN_MODULE_CONTRACTS.md#m04) |
| `/admin/processing` | [app/admin/processing/page.tsx](../../web/app/admin/processing/page.tsx) · page | ProcessingCenter | —（见组件参数） | [M15](ADMIN_MODULE_CONTRACTS.md#m15) |
| `/admin/processing/health` | [app/admin/processing/health/page.tsx](../../web/app/admin/processing/health/page.tsx) · page | AdminSystemHealth | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/health/candidates` | [app/admin/processing/health/candidates/page.tsx](../../web/app/admin/processing/health/candidates/page.tsx) · page | CandidateReview | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/health/knowledge` | [app/admin/processing/health/knowledge/page.tsx](../../web/app/admin/processing/health/knowledge/page.tsx) · page | KnowledgeWorkspaceDiagnostics | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/query-lexicon` | [app/admin/processing/query-lexicon/page.tsx](../../web/app/admin/processing/query-lexicon/page.tsx) · page | QueryLexiconWorkspace | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/semantic-index` | [app/admin/processing/semantic-index/page.tsx](../../web/app/admin/processing/semantic-index/page.tsx) · page | IndexMaintenance, SemanticIndexAdmin | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/settings` | [app/admin/processing/settings/page.tsx](../../web/app/admin/processing/settings/page.tsx) · page | SettingsAdmin | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/processing/status` | [app/admin/processing/status/page.tsx](../../web/app/admin/processing/status/page.tsx) · page | SystemStatusCenter | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/publication` | [app/admin/publication/page.tsx](../../web/app/admin/publication/page.tsx) · page | PublicationDesk；preservingAdminRedirect("/admin/about?panel=history",params,undefined,["site","panel"]); preservingAdminRedirect(`/admin/intake/${encodeURIComponent(itemId)}`, params, "publication", ["item"]) | —（见组件参数） | [M04](ADMIN_MODULE_CONTRACTS.md#m04) |
| `/admin/publication/[itemId]` | [app/admin/publication/[itemId]/page.tsx](../../web/app/admin/publication/[itemId]/page.tsx) · page | PublicationReviewEntry | —（见组件参数） | [M04](ADMIN_MODULE_CONTRACTS.md#m04) |
| `/admin/publication/knowledge/[objectType]/[objectId]` | [app/admin/publication/knowledge/[objectType]/[objectId]/page.tsx](../../web/app/admin/publication/knowledge/[objectType]/[objectId]/page.tsx) · page | KnowledgeHistory | —（见组件参数） | [M04](ADMIN_MODULE_CONTRACTS.md#m04) |
| `/admin/query-lexicon` | [app/admin/query-lexicon/page.tsx](../../web/app/admin/query-lexicon/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/query-lexicon", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/reading-paths` | [app/admin/reading-paths/page.tsx](../../web/app/admin/reading-paths/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M09](ADMIN_MODULE_CONTRACTS.md#m09) |
| `/admin/recommendations` | [app/admin/recommendations/page.tsx](../../web/app/admin/recommendations/page.tsx) · page | CurationProjectWorkspace, RecommendationIssueList | —（见组件参数） | [M11](ADMIN_MODULE_CONTRACTS.md#m11) |
| `/admin/recommendations/issues/[issueId]` | [app/admin/recommendations/issues/[issueId]/page.tsx](../../web/app/admin/recommendations/issues/[issueId]/page.tsx) · page | RecommendationIssueEditor | —（见组件参数） | [M11](ADMIN_MODULE_CONTRACTS.md#m11) |
| `/admin/recommendations/issues/[issueId]/preview` | [app/admin/recommendations/issues/[issueId]/preview/page.tsx](../../web/app/admin/recommendations/issues/[issueId]/preview/page.tsx) · page | IssuePreviewFrame, RecommendationIssueEditor | —（见组件参数） | [M11](ADMIN_MODULE_CONTRACTS.md#m11) |
| `/admin/recycle` | [app/admin/recycle/page.tsx](../../web/app/admin/recycle/page.tsx) · page | RecycleBin | —（见组件参数） | [M17](ADMIN_MODULE_CONTRACTS.md#m17) |
| `/admin/review` | [app/admin/review/page.tsx](../../web/app/admin/review/page.tsx) · page | ReviewQueue | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/review/[itemId]` | [app/admin/review/[itemId]/page.tsx](../../web/app/admin/review/[itemId]/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect(`/admin/intake/${encodeURIComponent(itemId)}`, await searchParams, "bibliography") | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/scholars` | [app/admin/scholars/page.tsx](../../web/app/admin/scholars/page.tsx) · page | ScholarsAdmin | —（见组件参数） | [M06](ADMIN_MODULE_CONTRACTS.md#m06) |
| `/admin/scholars/[scholarId]` | [app/admin/scholars/[scholarId]/page.tsx](../../web/app/admin/scholars/[scholarId]/page.tsx) · page | ScholarsAdmin | —（见组件参数） | [M06](ADMIN_MODULE_CONTRACTS.md#m06) |
| `/admin/scholars/[scholarId]/relations` | [app/admin/scholars/[scholarId]/relations/page.tsx](../../web/app/admin/scholars/[scholarId]/relations/page.tsx) · page | ScholarKnowledgeRelations | —（见组件参数） | [M06](ADMIN_MODULE_CONTRACTS.md#m06) |
| `/admin/scholars/people` | [app/admin/scholars/people/page.tsx](../../web/app/admin/scholars/people/page.tsx) · page | PersonAuthorityWorkspace | —（见组件参数） | [M05](ADMIN_MODULE_CONTRACTS.md#m05) |
| `/admin/search` | [app/admin/search/page.tsx](../../web/app/admin/search/page.tsx) · page | AdminDashboard | —（见组件参数） | [M00](ADMIN_MODULE_CONTRACTS.md#m00) |
| `/admin/semantic-index` | [app/admin/semantic-index/page.tsx](../../web/app/admin/semantic-index/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/semantic-index", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/settings` | [app/admin/settings/page.tsx](../../web/app/admin/settings/page.tsx) · page | LegacySettingsRoute | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/status` | [app/admin/status/page.tsx](../../web/app/admin/status/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/status", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/storage` | [app/admin/storage/page.tsx](../../web/app/admin/storage/page.tsx) · page | StorageWorkspace | —（见组件参数） | [M17](ADMIN_MODULE_CONTRACTS.md#m17) |
| `/admin/subdisciplines` | [app/admin/subdisciplines/page.tsx](../../web/app/admin/subdisciplines/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/support/feedback` | [app/admin/support/feedback/page.tsx](../../web/app/admin/support/feedback/page.tsx) · page | FeedbackWorkspace | —（见组件参数） | [M19](ADMIN_MODULE_CONTRACTS.md#m19) |
| `/admin/support/parallel-calibrations` | [app/admin/support/parallel-calibrations/page.tsx](../../web/app/admin/support/parallel-calibrations/page.tsx) · page | ParallelCalibrationWorkspace | —（见组件参数） | [M19](ADMIN_MODULE_CONTRACTS.md#m19) |
| `/admin/system-health` | [app/admin/system-health/page.tsx](../../web/app/admin/system-health/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/health", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/system-health/candidates` | [app/admin/system-health/candidates/page.tsx](../../web/app/admin/system-health/candidates/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/health/candidates", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/system-health/knowledge` | [app/admin/system-health/knowledge/page.tsx](../../web/app/admin/system-health/knowledge/page.tsx) · page | 重定向 / 包装入口；preservingAdminRedirect("/admin/processing/health/knowledge", await searchParams) | —（见组件参数） | [M16](ADMIN_MODULE_CONTRACTS.md#m16) |
| `/admin/taxonomy` | [app/admin/taxonomy/page.tsx](../../web/app/admin/taxonomy/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/theories` | [app/admin/theories/page.tsx](../../web/app/admin/theories/page.tsx) · page | TheoryNodesAdmin | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theories/[nodeId]` | [app/admin/theories/[nodeId]/page.tsx](../../web/app/admin/theories/[nodeId]/page.tsx) · page | TheoryNodesAdmin | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theories/disciplines` | [app/admin/theories/disciplines/page.tsx](../../web/app/admin/theories/disciplines/page.tsx) · page | DisciplinesAdmin | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/theories/reading-paths` | [app/admin/theories/reading-paths/page.tsx](../../web/app/admin/theories/reading-paths/page.tsx) · page | ReadingPathWorkbench | —（见组件参数） | [M09](ADMIN_MODULE_CONTRACTS.md#m09) |
| `/admin/theories/relations` | [app/admin/theories/relations/page.tsx](../../web/app/admin/theories/relations/page.tsx) · page | TheoryRelationsAdmin | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theories/subdisciplines` | [app/admin/theories/subdisciplines/page.tsx](../../web/app/admin/theories/subdisciplines/page.tsx) · page | SubdisciplinesAdmin | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/theories/timeline` | [app/admin/theories/timeline/page.tsx](../../web/app/admin/theories/timeline/page.tsx) · page | NormalizedTimelineAdmin | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theory-nodes` | [app/admin/theory-nodes/page.tsx](../../web/app/admin/theory-nodes/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theory-relations` | [app/admin/theory-relations/page.tsx](../../web/app/admin/theory-relations/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theory-schools` | [app/admin/theory-schools/route.ts](../../web/app/admin/theory-schools/route.ts) · handler | handler：legacyTheorySchoolAdminTarget → /admin/theory-nodes | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theory-schools/[entityId]` | [app/admin/theory-schools/[entityId]/route.ts](../../web/app/admin/theory-schools/[entityId]/route.ts) · handler | handler：legacyTheorySchoolAdminTarget → /admin/theory-nodes | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/theory-timeline` | [app/admin/theory-timeline/page.tsx](../../web/app/admin/theory-timeline/page.tsx) · page | KnowledgeLegacyRedirect | —（见组件参数） | [M07](ADMIN_MODULE_CONTRACTS.md#m07) |
| `/admin/topics` | [app/admin/topics/page.tsx](../../web/app/admin/topics/page.tsx) · page | TaxonomyAdmin | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/topics/[entityId]` | [app/admin/topics/[entityId]/page.tsx](../../web/app/admin/topics/[entityId]/page.tsx) · page | TaxonomyAdmin | —（见组件参数） | [M08](ADMIN_MODULE_CONTRACTS.md#m08) |
| `/admin/uploads` | [app/admin/uploads/page.tsx](../../web/app/admin/uploads/page.tsx) · page | AdminUpload, UploadSourceContext | —（见组件参数） | [M01](ADMIN_MODULE_CONTRACTS.md#m01) |
| `/admin/users` | [app/admin/users/page.tsx](../../web/app/admin/users/page.tsx) · page | AccountWorkspace | —（见组件参数） | [M18](ADMIN_MODULE_CONTRACTS.md#m18) |
| `/admin/visual-review` | [app/admin/visual-review/page.tsx](../../web/app/admin/visual-review/page.tsx) · page | VisualReviewWorkspace | —（见组件参数） | [M20](ADMIN_MODULE_CONTRACTS.md#m20) |
| `/admin/welcome` | [app/admin/welcome/page.tsx](../../web/app/admin/welcome/page.tsx) · page | SiteContentEditor | —（见组件参数） | [M13](ADMIN_MODULE_CONTRACTS.md#m13) |

## 兼容与次级入口

- `KnowledgeLegacyRedirect` 依据 selected/object 类型和ID映射到人物、主题、学科、路径、作品或理论；保留筛选、分页、return_to和hash。`taxonomy`额外识别旧kind/type/theory。
- `/admin/theory-schools/[entityId]` 是307 handler，加入 `node_type=theory_tradition` 和 `legacy_id`，继续经 `/admin/theory-nodes` 到新页面。
- `/admin/review/[itemId]` 进入同一收件工作区的 bibliography；cataloging candidates 复用工作台并打开助手，不是第二套编目数据库。
- `/admin/publication?site=...` 转网站历史；`item` 转收件发布段。`/publication/knowledge/...` 是历史页；真正审核在 `/preview/knowledge/...?...review=1`。
- `/admin/recommendations` 默认项目工作台；`view=home`进入首页推荐位置，`view=legacy`进入旧推荐期列表。文章编辑器与preview route仍独立存在。
- `/admin/preview/**` 的 frame/review、作品的 edition、files/outline/OCR次级入口，以及视觉复核入口均在此表保留；侧栏不可见不等于不存在。
- `/admin/settings` 的旧栏目映射由 `LegacySettingsRoute` 决定；运行维护统一迁往 `/admin/processing/*`。具体键与组件中的 `searchParams.get` 位置见静态索引，不把重定向当成功保存。
