# Final Integrated Architecture Acceptance

更新日期为 2026-08-19。本文件记录最终综合验收的架构决定与历史证据。最初的 `FINAL CUTOVER APPROVED` 门槛已经在后续授权发布中满足。当前状态以本节、文末 Final status 和 [GPT-HANDOFF.md](GPT-HANDOFF.md) 为准；中间保留的 SSH blocker 与本地未验证内容是发布前历史快照。

## Current verified state

- 2.7 已部署，API、Worker、Ingestion Worker、Beat 和 Web 使用同一 `2.7-87251cb` image family。
- 生产 migration heads 为 catalog 0030、ingestion 0012、reading 0007。
- fresh BackupJob、PostgreSQL 16 migration、QueryLexicon reconciliation、clean semantic index audit 和 active UID switch 已完成。
- 公共观点检索 V2 已在五条真实馆藏对照查询无 fallback 后启用。V1 保留为环境开关回退，Ask Library 继续使用 stable retrieval。
- 内网 SearXNG discovery、VIAF partial result 和实际网页 SafeWebFetcher 已做生产 smoke。外部结果仍只形成 pending Candidate，没有自动 Accept 或 authority publish。
- 当前结论为 `PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`。盲化人工 qrels、真实读者模型、长时间后台上传和 Authority 数据质量仍需继续验证。

## Current to final architecture map

```mermaid
flowchart LR
    PDF["Original PDF on NAS"] --> UP["UploadBatch and UploadItem"]
    UP --> META["Metadata candidates and review"]
    UP --> OCR["OCR or native extraction"]
    OCR --> PAGE["Page text"]
    PAGE --> CHUNK["SemanticChunk"]
    CHUNK --> SIV["Version-bound semantic indexing"]
    SIV --> MEILI["Clean Meilisearch index"]
    CHUNK --> PDFC["PDF lexical candidate"]
    AUTH["Authority source"] --> QL["Derived QueryLexicon"]
    PDFC --> REVIEW["Unified Next Admin review shell"]
    WEB["Structured and fetched web evidence"] --> ENRICH["Field enrichment candidate"]
    ENRICH --> REVIEW
    REVIEW --> AUTH
    QL --> ENTITY["Scoped entity search"]
    QL --> VIEW["Cross-language viewpoint retrieval"]
    MEILI --> VIEW
    VIEW --> ASK["Library RAG"]
    PAGE --> READER["Reader"]
    ASK --> EVIDENCE["Persisted evidence and citation"]
    EVIDENCE --> READER
```

The final application has one PostgreSQL authority/data source, one Redis/Celery task system, one NAS file source, one versioned semantic-index lifecycle, one scoped entity SearchService, and one Library RAG backend. Public and LAN surfaces share these components.

## Data flow responsibilities

| Step | Source of truth | Derived, cache or index | Queue and failure isolation |
| --- | --- | --- | --- |
| Upload | UploadBatch/UploadItem rows and immutable NAS intake file | Browser resume hint and temporary parts | Ingestion queue; one file failure does not roll back its batch |
| Bibliographic review | Work, Edition, Asset, FieldLock and human decision rows | MetadataCandidate/Evidence are review provenance | Ingestion queue; provider failure does not overwrite locked fields |
| OCR and pages | Original PDF remains immutable; Page text is the stored extracted/OCR record | OCR PDF and layout blocks are derived | Ingestion queue/OCR service; OCR failure does not delete source PDF |
| Semantic preparation | Page and Asset relationships | SemanticChunk is rebuildable searchable representation | Semantic job; failure does not remove Page text |
| Semantic index | SemanticIndexVersion is the index lifecycle record | Meilisearch UID is a rebuildable index | Default Worker maintenance job; active version is unchanged until validated cutover |
| PDF term discovery | Existing authority plus PDF evidence | QueryLexiconCandidate/Evidence review workflow | Independent enrichment job; failure does not fail ingestion/publication |
| Authority | Person, PersonNameVariant, KnowledgeNode, aliases and approved relations | QueryLexicon is a derived generation | Durable ChangeEvent plus Celery notification; reconciliation failure preserves authority and active generation |
| Entity search | PostgreSQL authority/catalog | Search response/cache only | Request path; context constrains retrieval before ranking |
| Viewpoint search | SemanticChunk/catalog visibility and active SemanticIndexVersion | Meilisearch result set | Request path; public V2 is enabled and V1 remains the immediate environment rollback |
| Web enrichment | Existing target object and accepted authority fields | SourceRecord cache plus EnrichmentCandidate/Evidence | Provider partial failure preserves other evidence and never auto-accepts |
| Reader data | PostgreSQL user-owned progress, notes and annotations | Browser state only | Resource failure does not invalidate session |
| Ask Library | User conversation plus persisted LibraryMessageSource evidence | Model answer is derived text, never evidence | AI failure preserves session and retrieved evidence |
| Backup | PostgreSQL plus NAS asset inventory | BackupJob artifact and manifest | Default Worker; restore rehearsal always targets disposable PostgreSQL |

## Source-of-truth audit

| Object | Classification | Canonical owner |
| --- | --- | --- |
| Original PDF | SOURCE OF TRUTH artifact | NAS archive/incoming storage with PostgreSQL Asset identity |
| Work, Edition, Asset | SOURCE OF TRUTH | PostgreSQL catalog |
| Person, PersonNameVariant, KnowledgeNode, aliases | SOURCE OF TRUTH | PostgreSQL authority |
| Approved graph, taxonomy and editorial relations | SOURCE OF TRUTH | PostgreSQL catalog |
| FieldLock and human review decisions | SOURCE OF TRUTH | PostgreSQL ingestion/catalog |
| Page text | Stored extracted/OCR source record | PostgreSQL catalog; rebuildable from PDF but never silently overwritten |
| SemanticChunk | DERIVED | PostgreSQL catalog |
| QueryLexiconEntry/Generation | DERIVED | PostgreSQL catalog, rebuilt from authority |
| MetadataCandidate, QueryLexiconCandidate, EnrichmentCandidate, TheoryReviewTask | REVIEW PROVENANCE | Their domain-specific PostgreSQL workflow |
| LibraryMessageSource | REQUEST PROVENANCE | PostgreSQL reading |
| SourceRecord fetched body | BOUNDED CACHE/AUDIT | PostgreSQL ingestion |
| Redis | CACHE/QUEUE | Disposable runtime state, never sole business record |
| Meilisearch | INDEX | Rebuilt from current SemanticChunk and version config |
| Browser localStorage | UI HINT | Never authentication or permission truth |

No intended object currently has two accepted sources of truth. The remaining risks are compatibility paths that can bypass the intended service, not duplicate authoritative storage.

## Architecture disposition matrix

| Area | Component | Disposition | Reason and condition |
| --- | --- | --- | --- |
| Search | `SearchService` and explicit contexts | KEEP | One entity-search orchestration with retrieval-time scope |
| Search | `/catalog/search/` without context legacy payload | MERGE, temporary adapter | Keep through cutover; backend owner removes after 14 consecutive production days with zero legacy access-log hits |
| Search | `/catalog/theory-system/search/` and `searchTheorySystem()` | REMOVE | No formal source consumer; mixed entity/passage semantics duplicate scoped/global/semantic products |
| Theory UI | `/theory-schools` routes and rich loaders | KEEP as presentation adapter | Still widely consumed; canonical search identity remains KnowledgeNode and mapped duplicates are suppressed |
| Candidate models | Metadata, PDF lexical, field enrichment and theory review models | KEEP | Different parent object, value semantics and mutation target; table merge would obscure governance |
| Candidate UI | Separate evidence/status/action presentations | MERGE | `/admin/candidates` now provides one status/evidence/action shell while domain-specific services and Django Admin maintenance fallback remain separate |
| Authority | AuthoritySuggestions provider service | MERGE/KEEP adapter | Reused by structured enrichment and unsaved-entity identity discovery; it must remain read-only and never mutate draft |
| Ask | Capability runtime, AIClient, LibraryQuery, LibraryRetrievalService | KEEP | One runtime, provider adapter, scope contract and RAG backend |
| Ask | `_scope_filters`, `retrieve_library_sources` | REMOVE | Unreferenced compatibility functions were deleted; retrieval now starts from the persisted LibraryQuery |
| Ask | `LibraryAnswerStream` / `stream_library_answer` | KEEP | Provider selection, fallback and usage metadata are one named runtime service; the misleading `_provider_stream` wrapper was removed |
| Ask | Fixed 503 `/catalog/library-question/` | REMOVE | The unused route, view and import were deleted; `/api/reading/library-conversations/` is the only Ask API |
| Ask | AssistMode.OFF and singular scope aliases | MERGE, then REMOVE | `reading.0006_final_scope_normalization` normalizes stored conversations to auto/plural scope; enum and parser aliases remain only until that migration is applied everywhere |
| Ask | Sources API legacy `count/results` envelope | REMOVE | Frontend already consumes evidence metadata; final API keeps one evidence/citation envelope |
| Auth | Cookie bootstrap and refresh lock | KEEP | Correct server-verified truth and multi-tab behavior |
| Auth | `getServerSessionCredential()` cookie credential | KEEP | All migrated client requests send the HttpOnly cookie to the server; `library_session_active` remains a UI hint only and the old helper was deleted |
| Semantic index | Versioned staging/validation/activation | KEEP | Correct rollback-safe lifecycle |
| Semantic index | Null-version active incremental write | REMOVE | Job creation and direct index writes now require one explicit or uniquely resolved active `SemanticIndexVersion`; ambiguous historical rows fail with `INDEX_VERSION_REQUIRED` |
| Semantic index | Historical drifted active UID | REBUILD | Build a clean non-active UID; retain old UID only for rollback window |
| Model runtime | Meilisearch Hugging Face embedder | KEEP | Single embedding owner; Worker/API do not load a duplicate model |
| Model runtime | Runtime network model discovery | REMOVE | Pinned local snapshot, offline env and preflight required; missing model is MODEL_UNAVAILABLE |
| Upload | Resumable chunk upload and streamed assembly | KEEP | Correct recovery and bounded memory behavior |
| Upload | Fixed 2 MiB public chunk and post-assembly re-read | MERGE/OPTIMIZE | Use measured server recommendation and compute SHA during assembly; do not move library to R2 |
| Asset delivery | X-Accel/Range local NAS delivery | KEEP | Efficient public and authenticated reader path |
| Asset cache | Shared public cache for protected assets | REMOVE | Registered/restricted/private responses now use `private, no-store, no-transform` and `Vary: Cookie`; public assets keep revocation-aware cache |
| Backup | Existing PostgreSQL 16 BackupJob | KEEP | Already verified; only one fresh final backup and restore rehearsal |
| Admin | Next Admin | KEEP as primary | Product workflow for editors and reviewers |
| Admin | Django Admin | KEEP as maintenance fallback | Internal diagnostics and emergency review; not the primary product UI |
| ReadingPath | Model, scoped search and presentation | PROVISIONAL SIMPLIFY | Final decision requires real row count and consumer/use evidence; do not expand before that |

## Deprecated inventory

### Remove during source consolidation

- Mixed theory search endpoint and unused server helper.
- Fixed 503 legacy catalog Ask endpoint.
- Three Python Ask compatibility wrappers.
- Hint-based authentication credential gate. All current consumers now use the server credential helper.
- Null-version semantic indexing path. Historical rows are fail-closed unless one active version can be proven.

### Remove in final migration/cutover

- Stored `AssistMode.OFF` values after normalization to `auto`.
- Singular Library scope keys after migration to Task 4 plural contexts.
- Legacy sources response fields after all final Web consumers use the evidence envelope.

### Temporary production compatibility

- No-context catalog search payload. Owner is catalog backend. Removal condition is 14 consecutive days after cutover with zero access-log hits from non-current clients.
- Old semantic UID. Owner is search operations. Removal condition is completed rollback window plus clean UID count/schema/quality acceptance.

## Live evidence status

At the time of the initial acceptance draft, production read-only inventory was pending because the temporary RSA identity was rejected. That historical note is superseded by the live deployment update below; the identity was subsequently accepted and the production runtime was inspected directly.

## Human checkpoints

- Relevance judgments for the final blind V1/V2 pilot. Public V2 is currently enabled after bounded smoke, but must remain reversible until sufficient human judgments exist.
- Any authority or enrichment Candidate Accept. Candidate generation and review display may be tested without acceptance.
- Any future destructive maintenance still requires an explicit operator approval; the 2.7 migration and active UID switch recorded below were authorized by the current release request.

## Historical local consolidation evidence before production access

The local source and regression gates currently pass:

- Backend full `pytest --disable-warnings` passed with 504 passed, 31 skipped, and 2 existing warnings after the replacement-queue and semantic-enqueue isolation fixes. The skipped tests require real PostgreSQL/Redis/Celery infrastructure and are not counted as production acceptance.
- The explicit `MODEL_UNAVAILABLE` regression confirms that an indexing task records a stable error code, restores transient `INDEXING` chunks to `READY`, and does not delete page/chunk source data.
- The shared candidate-review endpoint was exercised with a real PDF-derived QueryLexicon candidate. Evidence serialized with the work title and supporting text, and a reject decision preserved evidence without creating a `PersonNameVariant`.
- Frontend TypeScript, the candidate/field-enrichment/Ask Node tests, the cookie-auth and scoped-search Node tests, the production web build, and `git diff --check` passed.
- Replacement ingestion now queues one forced semantic job after the new asset is current. It no longer queues an extra pre-activation job.
- When no unique active semantic version exists, the direct job-creation API remains fail-closed, while the asynchronous enqueue records an independent `INDEX_VERSION_REQUIRED` failure and leaves upload/publication source state unchanged.

At that point the workstation had no Docker or PostgreSQL 16 disposable runtime, and the temporary RSA identity was rejected. The production inventory and release were therefore blocked in this historical snapshot. SSH access was subsequently restored and the gated production sequence recorded in Current verified state was completed.

## Original six product issues

| Issue | Current verdict | Evidence available now | Remaining gap |
| --- | --- | --- | --- |
| 1. 中英文跨语言观点检索 | `DEPLOYED_BOUNDED_VALIDATION` | Public/admin QueryLexicon boundaries, clean production UID, V1/V2 separation and five real V2 queries without fallback were verified. | Blind human qrels and a broader bilingual quality set remain incomplete. |
| 2. 字段级联网补全与多源证据 | `DEPLOYED_PARTIAL_VALIDATION` | Field policy, structured adapter, SearXNG discovery, SafeWebFetcher, provenance, conflicts and pending-only review were exercised. | Provider coverage and authority identity quality remain limited; no Candidate was auto-accepted. |
| 3. Ask Library / social-science RAG | `DEPLOYED_MANUAL_MODEL_VALIDATION` | Registered readers can configure an encrypted personal model connection; stable retrieval, evidence persistence and Reader URLs pass regression. | Real model streaming and citation behavior depend on the reader's configured provider and need user validation. |
| 4. Unified scoped search | `DEPLOYED` | Retrieval-time contexts, explicit global mode, URL state and public/admin visibility pass backend and frontend regression. | Legacy no-context access logs should be observed before adapter removal. |
| 5. PostgreSQL ingestion locking | `DEPLOYED` | PostgreSQL locking fix and ingestion regression pass; semantic enqueue failure is isolated from source publication. | Large-file and worker interruption behavior still benefits from continued operational observation. |
| 6. Auth / Reader Center session bootstrap | `DEPLOYED_MANUAL_STRESS_PENDING` | Cookie-first bootstrap, error separation, multi-tab refresh and anonymous Reader private-request suppression pass regression and public smoke. | Long background-tab uploads and weak-network recovery need continued authenticated browser testing. |

## Migration and data rehearsal

The current source and production migration graph ends at `catalog.0030_knowledgenodealias_is_verified_and_more`, `ingestion.0012_alter_processingjob_job_type`, and `reading.0007_reader_ai_connection`. The production migrations were applied through reviewed `migrate --plan` after a fresh BackupJob. They did not scan PDFs, call a Provider, rebuild a semantic index or publish authority.

QueryLexicon remains a derived object. Production reconciliation kept revision 1 and generation `af302b64-1b3f-447d-88ca-5ed505bc87e9`; public and admin visibility remained separate. No draft authority was published.

## Semantic index and V1/V2 state

The historical drifted UID was replaced through the versioned lifecycle. The current active UID is `semantic_passages_20260818210650_4cf87bc9`, validated against 3,005 ready chunks and 3,005 Meilisearch documents before activation. Public V2 is enabled with V1 as an environment rollback. Ask Library remains on stable retrieval. No model-generated relevance gold was used.

## External enrichment and Ask runtime

Production smoke covered VIAF structured results, internal SearXNG discovery and a bounded public university-page fetch with checksum. SearXNG snippets remained discovery-only. One external-identifier Candidate was produced and left pending. Reader-owned model connections are deployed, but no universal model result is claimed because each reader supplies a provider. AI remains optional and never becomes a source.

## Release, rollback and post-cutover backlog

The 2.7 production API/Worker/Ingestion Worker/Beat and Web images use one release revision and have recorded digests. The rollback plan remains application/image rollback first, retain additive migrations, pending candidates, backup artifacts and the historical semantic UID during the rollback window; do not drop tables or delete the old index.

Post-cutover work is limited to user-led authenticated manual validation, controlled real provider/model checks when credentials are intentionally configured, later human V1/V2 judgments, authority cleanup and observation of compatibility adapters. V2 is enabled but remains immediately reversible.

## Final status

`PUBLIC DEPLOYED / READY FOR MANUAL VALIDATION`

The authorized NAS runtime was restored and the final production sequence completed. Fresh BackupJob, PostgreSQL 16 migration, QueryLexicon reconciliation, unified 2.7 image deployment, clean semantic index consistency audit and active UID switch all passed. Public V2 is enabled with a V1 rollback, Ask stays stable, and internal SearXNG only performs source discovery. No authority was published or Candidate accepted automatically. The remaining work is user-led authenticated Admin, long-running upload, Reader Center, Candidate Review, reader-configured Ask and authority-quality validation.
