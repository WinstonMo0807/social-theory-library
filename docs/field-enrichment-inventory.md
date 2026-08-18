# Field-Aware Web Enrichment Inventory

更新日期为 2026-08-17。本文件记录 Task 5 修改前的真实源码状态。它是源码 inventory，不是 production provider 或公网验收记录。

## Current entry points

| 页面或入口 | 对象与字段 | 当前来源 | 是否 field-aware | 当前候选与证据 | 当前采用行为 |
| --- | --- | --- | --- | --- | --- |
| Scholar Admin 编辑页 | Person 名称、原文名、aliases、生卒年、简介 | 馆内 Person、Wikidata、VIAF、LOC、OpenAlex，可选 AI filter | 否。请求只有 `entity_type=person` 与整个人名 query | 返回临时 entity card。SourceRecord 保存 provider payload，但没有字段 Candidate 或 supporting span | 点击后直接改 React draft，管理员随后保存 Scholar。没有持久候选审核事务 |
| Discipline Admin | name、foreign_name、search_aliases、description | 馆内目录、Wikidata、LOC | 否 | 同上 | 点击后直接改当前 draft |
| Subdiscipline Admin | name、foreign_name、search_aliases、description | 馆内目录、Wikidata、LOC | 否 | 同上 | 点击后直接改当前 draft |
| Legacy TheorySchool / Topic Admin | 名称、外文名、aliases、description | 馆内目录、Wikidata、LOC | 否 | 同上 | 点击后直接改当前 draft |
| KnowledgeNode Admin | canonical name、alias、summary | 馆内 KnowledgeNode、Wikidata、LOC | 否。node type 只决定 entity query 类型 | 同上 | 点击后合并 aliases 并改 draft。mapped legacy identity 由现有 KnowledgeNode 路径处理 |
| Metadata Review | Work / Edition 题名、作者、年份、出版社、ISBN、DOI 等 | PDF、Crossref、OpenLibrary、Google Books、OpenAlex、GROBID、可选 AI | 是，Candidate 按 field_name 保存 | MetadataCandidate、CandidateEvidence、SourceRecord、score factors、conflict group 与 FieldLock | 候选先填表单。保存复核时才把相符候选标为 accepted，并写 Work / Edition |
| Theory Review queue | Work/KnowledgeNode relation、新节点、timeline | PDF Page 与 EvidenceSnippet | 按 task type，但不是联网字段核对 | TheoryReviewTask 与 PDF evidence | 审核动作写 draft/pending graph 对象，不直接公开 |
| QueryLexicon Candidate Admin | PersonNameVariant、KnowledgeNodeAlias | PDF/OCR/SemanticChunk | 是，限定 lexical term | QueryLexiconCandidate 与逐条 PDF Evidence | 单事务写 authority，再由 ChangeEvent 更新派生 QueryLexicon |
| Timeline / ReadingPath Admin | 事件与策展字段 | 人工编辑、馆藏关系 | 当前无通用联网入口 | 没有 external field candidate | 人工直接编辑；ReadingPath 仍是 editorial object |

## Existing provider architecture

### Authority suggestions

`catalog.services.authority_suggestions` 已实现以下能力。

- Wikidata、VIAF、LOC 和 OpenAlex provider。
- 馆内 entity 候选优先，远端候选去重。
- Provider allowlist、HTTPS、DNS private-range 拒绝、timeout、redirect 禁止和响应大小限制。
- SourceRecord 七日缓存与 provider-specific identifier 保留。
- 可选 AI 只排序输入候选，不能注入新 ID。

缺口在于请求没有 target ID、field name、current value、form context 或 requested mode。返回值是 entity suggestion，不是可审核 field candidate。Wikidata 或 search response 的摘要也没有被转换成真实网页 supporting span。

### Bibliographic providers

`ingestion.services.provider_gateway` 已实现 Crossref、OpenLibrary、Google Books、OpenAlex 与 GROBID 的统一调用，包含 SourceRecord、fingerprint、TTL、rate interval、有限 retry、circuit breaker、bounded response 和 partial warning。

这套实现与 UploadItem / Edition 紧密关联。Task 5 应通过 adapter 复用其 provider 与 Candidate normalization，不应复制一个新的书目 provider gateway。

## Candidate and review paths

| 模型 | 适用范围 | 可复用能力 | 不能承担 Task 5 的原因 |
| --- | --- | --- | --- |
| MetadataCandidate / CandidateEvidence | 单个 UploadItem 的书目复核 | field_name、JSON value、来源、冲突、证据、人工决定、FieldLock | 父对象强制是 UploadItem，不能定位 Person、KnowledgeNode、relation 或 ReadingPath |
| EntityResolutionCandidate | 入库时人物与分类对象消歧 | 多因素 identity、possible entity、conflict | 同样绑定 UploadItem，且候选语义是 entity identity，不是任意字段值 |
| QueryLexiconCandidate / Evidence | PDF 术语对与名称变体 | 多证据、dedup、Accept/Reject 事务、authority mutation | 只允许 PDF lexical term，不能表达年份、机构、分类或解释性关系 |
| TheoryReviewTask / EvidenceSnippet | PDF 理论关系、节点与 timeline | 关系审核和馆藏页码证据 | 面向 PDF 与 theory workflow，不保存网页 source document 或通用字段值 |
| SourceRecord | Provider request 与 bounded raw response | 可空 UploadItem、request fingerprint、TTL、错误与 provider metadata | 不显式保存 source class、canonical URL、页面标题、checksum 和 supporting span |

## Task 5 implementation boundary

- 保留旧 `/api/catalog/admin/authority-suggestions/` 与现有 Metadata Review 作为兼容入口。
- 新增通用 EnrichmentCandidate 与 EnrichmentEvidence。它们不替代 PDF 专用候选。
- Structured adapters 复用现有 authority 和 bibliographic provider 实现。
- General web search 只发现 URL。Candidate evidence 必须来自随后安全 fetch 的实际页面文本。
- Accept 由 FieldPolicy 对应的 mutation adapter 写 Person、ScholarProfile、PersonNameVariant、Edition、KnowledgeNodeAlias、KnowledgeNodeDiscipline、KnowledgeNode parent 或 KnowledgeRelation。
- Entity picker 复用 Task 4 SearchService 的 admin visibility；不新增 autocomplete engine。
- 最终综合架构验收再决定是否将旧 entity-card suggestion、MetadataCandidate 与通用 candidate 的 UI 或 provider adapter进一步合并。

## Task 5 implementation result

- 旧 AuthoritySuggestions 保留 endpoint 与只读 identity cards，但前端已取消直接填入 draft 的操作。它只在管理员点击后请求，不再随输入 debounce 联网。
- 新增统一 FieldEnrichmentService、FieldPolicyRegistry、StructuredSourceAdapter、SearXNG WebSearchAdapter、SafeWebFetcher、FieldMutationRegistry 和字段值 validator。
- 新增通用 EnrichmentCandidate / EnrichmentEvidence 与 admin-only API、Django Admin Evidence inline、Accept/Reject actions。
- Scholar、Discipline、Subdiscipline、Topic 与 KnowledgeNode 编辑页接入显式 FieldEnrichmentControl。Work/Edition 继续使用已有 Metadata Review，同时可从同一后端 service 以 target type `edition` 请求 publication year、publisher 与 ISBN。
- 解释性 KnowledgeRelation 只有明确关系词和两份独立来源时才达到 Accept evidence gate；Accept 只创建 pending relation。
- 搜索摘要从不进入 EnrichmentEvidence。actual page fetch、supporting text、canonical URL、retrieved time 与 checksum 都是必填审计信息。

## Final integrated acceptance candidates

- 评估旧 `/catalog/admin/authority-suggestions/` 是否在所有编辑页迁移后删除，或保留为纯 identity discovery adapter。
- 评估 MetadataCandidate 与 EnrichmentCandidate 的书目 UI 是否合并，避免长期双重书目候选表面。
- 评估 QueryLexiconCandidate、TheoryReviewTask 与 EnrichmentCandidate 可共享哪些 Evidence 展示组件；PDF 与外部字段语义继续保持不同模型。
- 决定 Django Admin 与 Next Admin 的最终审核入口，避免两个长期并行的管理员操作面。
- 在最终 production cutover 前验证 SearXNG 或替代 adapter 配置、真实 Provider rate limit、robots/terms、公开域名 SSRF 保护、migration 0029 与回退。
