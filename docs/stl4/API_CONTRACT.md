# STL 4.0 当前接口契约

## 2026-10-21 学者公开投影与私人关注

既有admin/knowledge-preview/{object_type}/{object_id}/纳入契约，GET仅在scholar支持featured_source_id和reading_path_ids未保存选择覆盖。前者UUID或空清除，后者单个逗号分隔最多100 UUID或空清人工关联；重复/未知参数拒绝。只修改内存中的草稿副本，继续受控预览与真实公开资料投影；自动路径关联和完整分页总数保留。异步选择变更取消旧请求，以本次选择的返回决定预览，错误保留输入并可重试。

catalog/scholars列表与slug详情保留原URL，新增明确PublicScholarDirectory/PublicScholarDetail，含真实筛选/分页、正式资料字段、作品准确版本与责任范围、公开知识/问题/事件/关系/主题/阅读路径。候选关系必须显式请求及双权限；目录curated_topics来自正式人工推荐，与related_topics分开。旧栏目和旧嵌入消费者保持兼容。

Contribution.scope输入为edition或chapter；章节必须给asset_id/document_revision_id/outline_revision_id/outline_node_id/title/page_start/page_end。公开scope附status/notice/reader_href；失效返回chapter unavailable与空chapters，不泄露旧身份。后台省略scope保持原值。

reading/source-follows增加scholar_id（ScholarProfile UUID）和by-request查回。命令响应owner_id/record/receipt，固定request_id及expected_revision，不自动重放401写请求；隐私清除后的回执不能重建记录。schema205路径保留原203，TypeScript生成同步。Discovery/library metadata保留warnings code/message，准确章节筛选不支持或超限会明确报错。0073/0019仅源码，正式接口验收未执行。

## 2026-10-21 公共路径与私人跟读

catalog/theory-system/reading-paths列表按q/search、topic、discipline、node、difficulty、page筛选；详情revision/compare_to选正式版本。PublicReadingPath含稳定stages/items、准确材料身份、available/no_fulltext/unavailable/withdrawn/revision_changed、明确替代书目、学习问题/争论/公开署名与最多50版历史。列表批量投影，既有公共消费者统一DTO；草稿预览仅编辑权限且无私人写入。

reading/path-follows列表/创建、UUID详情/进度/笔记/删除、by-path、by-request、copy-plan、upgrade-preview及upgrade要求X-Reader-Owner；写入request_id固定，已存在对象expected_revision，创建附expected_source_revision，升级附target_revision。返回owner_id/record/receipt。copy的普通reading-plans GET/PATCH/export也核对owner；PATCH新增request_id和item_minutes，旧模型生成入口不能再有损复制路径。删除后回执不重建资料。

本组纳入7条私人路径和2条既有管理路径，203路径完整保留原194；管理集合仅GET/POST，具体对象沿现权限。stage_groups有准确输入结构。schema与TypeScript生成类型同步；0072/0018尚未应用，正式接口验收未执行。

## 2026-10-21 图谱与私人视图契约

GET catalog/theory-system/graph沿原入口，center_kind四类、center slug/UUID、depth1–3、limit≤120、edge_limit≤300、多值node_type/relation_type、discipline、start_year/end_year、三态has_collection、selected_node、works_page及include_candidates。节点键kind:UUID，学者为ScholarProfile；边键实际模型名:UUID。正式边含方向、说明、来源状态和至多6条精确当前原文；candidate_edges独立最多60条，普通账户请求候选403且不泄露数量。返回真实截断、当前子图计数、筛选说明、12个准确公开版本分页；no-store并Vary Cookie/Authorization。

reading/graph-views列表/创建、UUID详情/更新/删除及by-request要求当前X-Reader-Owner。POST固定request_id/data；PATCH增加expected_revision；DELETE以查询携带nonce/版本。响应owner_id、record、receipt，分页20。数据白名单只允许名称、公开中心/筛选/选择/布局；候选不保存。保留最少回执，删除后旧请求返回deleted不复活。隐私沿saved_knowledge组新增graph_views叶对象。0017未应用。194路径保留191旧路径，生成TypeScript同步，正式接口验收待全量完成。

## 2026-10-21 时间线契约

GET /catalog/theory-system/timeline/继续原事件身份，支持topic/author/event_type多值、discipline/node、q、year_from/year_to、has_collection、sort、year、page、focus及related_to。结果包含当前24项分页和完整scope_count/year_groups（按year与event_types计数）/bounds；focus计算真实页。详情增加subject_edition、subject_status、evidence_source、related_events/related_count及knowledge_relations/knowledge_relation_count。事件与来源作品/版本/文件/修订独立，来源须当前授权Page逐字核对。

管理timeline新增date_precision、subject_edition；响应准确声明evidence_file、edit_version及editorial_revision。列表仅GET/POST，详情延续原读写/发布权限。兼容旧公共timeline保留并同步公开过滤和出处资格。Schema新增纳入3个既有时间线路径至191，原188全部保留，生成TypeScript同步。0071未应用，正式API验收未运行。

## 2026-10-20 子学科与真实目录

新增GET catalog/theory-system/directory：type/discipline/parent/q/page，公开真实父级分组与返回路径、每页20条、总数、直属子项数和循环截断提示。无效400、未公开筛选或越界404、真实空结果200。规范关系补source_node_type/target_node_type，不从名称判断概念类型。

既有subdisciplines列表改轻量9字段，featured=true/false在分页前过滤；详情增加公开关联、独立来源与阅读路径，works_page每页48，works_pagination返回count/page/total_pages。非法页400、越界404；同页core_works/works和关系来源一致，编排来源独立。详情discipline/parent可空，列表discipline仅公开id/name/slug。证据版与默认卡片版独立，准确asset/revision/page/edition_label随各自入口。

OpenAPI188路径保留原185路径，前端生成类型同步；没有重复运行路由、新迁移或实际数据修改。详见SUBDISCIPLINE_DIRECTORY_20261020。

## 2026-10-20 PDF45–49理论条目收口

既有content-placements/node/{id}公开响应新增public_detail：确认用法、真实归属、title/explanatory_object/period/context以及准确span/asset/document_revision/page/reader_url；来源失效只计unavailable_usage_count，不回旧正文。规范理论公开书目增加edition_id/document_revision_id/source_status，关系增加逐项复核evidence；has_works在分页前过滤。

新增catalog/theory-system/nodes/{slug}/citation提供当前公开网页条目引用；reading/saved-knowledge/{node_id} GET/POST要求本人X-Reader-Owner。POST为saved/expected_version/request_id，GET可按原request_id查本人回执；同nonce不同内容409，旧已应用回执不重建删除记录。privacy新增saved_knowledge全链；前端隐私写入固定owner且不自动重放401。0016未应用。

旧TheorySchool关系/旧图谱/旧时间轴也在读回时核对当前版本、文件/作品归属、页和访问范围。无可核定位的旧层级原文不公开；明确后台预览保持权限内信息。185路径保留此前175路径，OpenAPI/TypeScript同步；详细语义见THEORY_DETAILS_20261020。

## 2026-10-20 Reader OCR状态

GET/POST distribution/assets/{asset_id}/ocr-status提供安全状态及pause/resume；GET的request_id只查本人已发命令。普通GET仍按当前文件权限；写/查回要求管理能力、X-Reader-Owner、固定nonce、job_id/job_version、source_sha256及document_revision_id。job_version原样回传，不能重格式化时间。已处理内容分unavailable/awaiting_publication/published/admin_preview；没有公开OCR正文。新增1路径至175，原174保留，无新迁移，详见READER_OCR_STATUS_20261020。

## 2026-10-20 并读与独立校准

catalog/parallel的versions/segments/candidates共用激活快照/Asset/DocumentRevision和Discovery首推候选；分页最多20段/6候选，focus返回实际窗口offset，失效来源409。reading/parallel-tasks提供本人列表/详情/nonce查回及CAS保存，X-Reader-Owner必需，任务来源身份不可改。

parallel-calibrations分本人投稿、public和admin表面；书目或单条对齐范围显式确认，私人note/terms不投稿；review/publish/reject独立命令，公开按匿名权限重验且每页最多20记录。新增16路径至174，原158保留；0015只编写，OpenAPI/TS同步，详细payload与边界见PARALLEL_READER_20261020。

## 2026-10-20 Reader版本与私人记录

asset manifest返回PublicReaderManifest/轻量PublicReaderWork，选定Edition/Asset/Revision身份一致。明确次版本的详情、图片与原文定位独立核验自身公开资格，不再依赖主版；馆藏集合规则保持。SSR只按需转发访问cookie，禁止redirect。

Annotation增加可选request_id和加密标签tags；同owner同请求同内容幂等，冲突409，未知结果先查原UUID。PATCH不迁移来源。原annotations/bookmarks/progress/history共7路由纳入契约表面至158，不增加重复运行路由。生成TS已同步，0014未应用，详见READER_20261020。

## 2026-10-20 作品详情与版本

原works/{slug}改PublicWorkDetail，支持当前发布快照slug/Edition UUID；selected edition贯穿元数据/目录/图片。relations为7类真实公开关联预览（每类最多6），CatalogEdition新增access_state而availability保持原二态；不返回受限文件身份。公开图片新增edition_id并重验。共享目录链接使用发布快照身份。151路径未新增，schema与前端类型同步；细节与边界见WORK_DETAIL_20261020。

## 2026-10-20 Discovery逐版本状态

Discovery响应增加documents（状态/当前书目/原文数/最多6个公开版本/200上限标记）。新增POST remove-document（edition_id、expected_generation），仅本会话可见来源、原访问权限和幂等移除，运行中换代继续。新API路径共151，OpenAPI/TS同步；具体状态含义和权限见DISCOVERY_DOCUMENTS_20261020。

## 2026-10-20 公共检索与本人记录

GET /catalog/search/?context=global&scope=catalog 提供Work合并、多版本、同版本过滤、分面与年份分布，公开主版本和当前快照约束。原search其他分支保留，用anyOf描述兼容载荷。GET /reading/search-records/要求owner_id本人，分页最大20，读取不启用保留。

Discovery GET新增sort=relevance|year_desc|year_asc及当前来源bibliography/attribution、真实is_new/added_count；context返回当前书目和同书候选。取消恢复沿expected_generation，cursor绑定排序与代次。共享私人分页带X-Reader-Owner并关闭401重放；具体字段及边界见五份检索单元文档。OpenAPI新增2路径至150，原其他接口保留，生成类型同步。

## 2026-10-19 公共交互检查点

- POST /catalog/feedback/匿名回执；GET/PATCH /catalog/admin/public-feedback/及详情严格管理权限。GET /reading/source-status/匿名复核公开状态；source-follows列表/详情本人隔离，POST要求X-Reader-Owner、nonce与expected_revision。完整字段见对应单元文档。
- POST /reading/citation-preview/公开来源预览，selected_text唯一匹配到真实范围，复用citation_bundle。研究新建/选材增加expected_owner_id，选材增加request_id/note/notes，旧客户端兼容。公开预览不回传未发布或私有正文。
- Schema新增7路径至148，保留原141路径，明确反馈类别/状态/公开来源状态枚举和列表operation ID，前端生成类型同步。隐私分类增加source_follows。源码契约不代表联调或上线通过。

## 2026-10-18 公共导航

PDF18继续使用现有公开会话、GET /explore?q=、/account?section=settings与/logout行为，无新数据库/API。当前标签页仅保存允许的公共来源位置，30分钟到期；账户/后台/认证路径、未知参数、编码目录逃逸不进入返回链接。共享Dialog焦点恢复preventScroll。管理入口以access_back_office能力显示，原服务端权限不变。导航源码接入与静态检查不等于真实浏览器验收。

## 2026-10-18 文件工作台、OCR与私有预览

- 文件接口 `/catalog/admin/works/{id}/files/`、同作品editions、edition files/requests/generate-reader/adopt/rights/prepare-public/content/impact.csv 同步前端和命名serializer；GET/HEAD与Range复用原文件权限，写入使用修订+nonce。采用/公开准备各自明确确认，独立于上传和主版本选择。详见WORK_FILES_20261018.md。
- `/ingestion/ocr-workspace/{asset}/` GET返回真实页状态/筛选/来源指纹/修订和任务；POST save/prepare/apply/review/start/pause/resume/cancel按能力鉴权。人工正文与人工核验分别保存，策略实际传递原worker/provider。详见OCR_WORKSPACE_20261018.md。
- 本人稿件/私人来源的preview和preview-file接口按purpose、owner和代次隔离；预览生成/取消有独立CAS/nonce，下载前后重验，不能将派生PDF位置作为原DOCX精确页码。详见DOCX_PRIVATE_PREVIEW_20261018.md。
- 当前验证表面新增15路径至141；原126条路径内容未变。DocumentRevisionApplyModeEnum供页码/人工正文共享，避免同名mode产生歧义。schema及前端生成类型已同步，正式运行待验收。

## 2026-10-18 反证、资料操作与页码映射

- 研究轮次GET支持mode=all/search/counterargument及order=oldest/newest，在本人项目内解密筛选后分页。反证命题与条件合计最多1200字符；可选文本条件允许清空。decision支持confirm/clear、request_id、relation、note、attribution、scope_note、save_as_note；显式保存笔记与本人决定原子持久化，理由必填，request_id异内容409，旧决定留历史。
- `/reading/privacy/` GET/PATCH本人保留偏好、真实计数和任务，PATCH须expected_revision；`items/?category=&page=`返回真实对象revision。`operations/` POST仅导出或创建删除预览；`command/` confirm/cancel/retry按修订执行；`download/`再次核对本人资料、研究子轮次及公开来源。最多2活动任务、500项/25MiB，失败逐项保存，删除重试重新预览，取消不恢复已完成删除。
- `/catalog/admin/assets/{id}/page-mapping/` GET当前数据/候选/历史、可选revision_id；POST save/analyze/segment/restore/prepare/publish。携带expected_revision/source_fingerprint，写操作携带request_id，publish还需revision_id/prepared_fingerprint。候选不改变当前公开Page；采用有发布权限，公开文件复制正文解释并走既有发布。缺页只为元数据，双页最多两个标签，不生成不存在的物理页。公开Page/EvidenceReference新增printed_labels与printed_label_precision=spread/page/unknown，体检对spread保留页码待核对。
- 输入、State/Revision/Preview响应、枚举、API schema与前端生成类型同步。详情与保护边界见对应单元文档，正式运行和视觉验收仍待核实。

## 2026-10-18 笔记授权与私人来源

- 笔记新增服务端筛选/计数、origin_note/source_summaries、usage GET/POST、revision删除和研究memory_reminders。实际内容/类型/来源变化撤销旧范围；确认不等于授权。完整字段见[CONFIRMED_NOTES_20261018.md](CONFIRMED_NOTES_20261018.md)。
- 私人来源使用citation-sources集合/原件/文字/OCR/命令接口；稿件manuscript分页、private_source_ids、sources和match_private命令接入真实来源。来源ID/generation/hash/覆盖断点独立校验，公开EvidenceReference不混用。详见[CITATION_PRIVATE_SOURCES_20261018.md](CITATION_PRIVATE_SOURCES_20261018.md)。
- 前后端及OpenAPI同步。0010迁移只编写，未执行；数据/权限/设备负载与视觉验收仍待核实。

更新时间：2026-10-18。当前接口以本文件、相关单元接入记录、实际源码和生成schema为准。`docs/stl-4.0/API_CONTRACT.md`只保留历史追溯，不再作为独立主线；本文不代表全站验收通过。

## 2026-10-18 稿件版本与目录校准

- 稿件版本新增本人`GET/POST /reading/citation-audits/{id}/versions/`，POST使用multipart与request_id、expected_revision、check_changed_only。每版独立加密保存，严格增量比较与恢复时来源复核；详细字段及边界见[CITATION_VERSIONS_20261018.md](CITATION_VERSIONS_20261018.md)。
- 目录沿`/catalog/admin/assets/{id}/outline/`接入当前文件摘要、候选来源及历史；edit新增base_revision_id、逐节点calibration_status和clear_position。保存候选、明确采用、历史恢复分别执行；详细契约见[OUTLINE_CALIBRATION_20261018.md](OUTLINE_CALIBRATION_20261018.md)。
- 前后端类型与OpenAPI已同步。两项均不新增数据库表/迁移，不连接生产，不启动检索质量评测；运行与视觉验收仍待统一阶段。

## U01 公共首页聚合

`GET /api/catalog/home/`

- 认证：`AllowAny`，接口不读取登录用户身份；访客、读者和工作人员得到相同的公开聚合。
- 缓存：响应 `Cache-Control: no-store`。首页内容来自当前公开数据，不能由浏览器或服务端把旧私有结果复用给另一用户。
- 成功：HTTP `200`。所有区域成功且至少一个内容区域有公开内容时 `status=ready`；空馆藏或没有公开策划时仍返回 `200`，并用 `status=empty` 和分区状态说明业务空态。
- 局部故障：HTTP `200`、顶层 `status=partial`。故障区域 `sections.<name>.status=unavailable`、`count=null`，其余区域仍可展示；不得把故障伪装为 `empty`。
- 全部区域故障：HTTP `503`、顶层 `status=unavailable`。响应仍保持同一 JSON 形状，区域消息只给可行动的公开提示，不回传内部异常。

顶层响应：

```json
{
  "schema_version": "4.0",
  "visibility": "public",
  "status": "ready|empty|partial|unavailable",
  "config": "SiteConfig|null",
  "works": "WorkCard[]",
  "random_works": "WorkCard[]",
  "scholars": "ScholarProfile[]",
  "topics": "Topic[]",
  "issues": "RecommendationIssue[]",
  "issue": "RecommendationIssue|null",
  "issue_count": "integer|null",
  "hot_searches": "string[]",
  "sections": "HomeSections"
}
```

`HomeSections` 的每个区域都返回 `{status, source, count, message}`：

| 区域 | 数量/来源 | 公开边界 |
|---|---|---|
| `works` | 最近公开馆藏，最多12项 | 只经过当前正式公开版本和可读资格 |
| `random_works` | 首页随机/推荐馆藏，最多4项 | 先读当前公开推荐快照，再以公开馆藏补足 |
| `scholars` | 当前已发布且人物已核验的学者，最多6项 | 未核验人物不会因推荐快照进入首页 |
| `topics` | 已发布主题，最多5项 | 关系计数只统计当前公开作品及已批准关系 |
| `issues` | 当前公开策划期，最多4项 | 只读已发布修订；未来排期不展示 |
| `issue` | `issues[0]` 或 `null` | 仅为首页首个策划期的同一对象，不复制另一套身份 |
| `issue_count` | 当前公开策划期总数 | 数据不可用时为 `null`，不是零 |
| `hot_searches` | 达到匿名聚合阈值且通过敏感信息过滤的查询 | 不读取个人阅读记录；暂时不可用时显示空列表并保留分区故障状态 |
| `config` | 当前公开站点配置或默认配置 | 不返回草稿；配置区域失败时前端可使用已知默认文案并显示状态 |

## 前端映射

- `web/lib/api/home.server.ts` 只调用上述正式聚合；失败不注入示例馆藏，配置允许使用代码内默认文案以保留导航。
- `web/components/public/home-public-view.tsx` 依据 `sections` 显示空态、局部故障和重载入口；卡片、数量、策划署名和封面来自接口，不从终稿图片造数据。
- `web/components/public/home-interactions.tsx` 的“继续阅读”只在当前会话已认证后请求 `/api/reading/progress/`；未登录、切换账号、401 或网络失败不得显示上一位用户的进度。
- 搜索表单只导航到 `/explore?context=global&q=...`；空查询不提交，查询文本不写入私人存储。
- 学者、主题和随机荐读的轮换在已返回的公开数组内完成，不创建推荐策略、不写入快照，也不改变公开排序。

## 相关正式身份和权限

首页卡片只能导航到由现有适配器生成的作品/版本/Reader 身份。首页不暴露物理文件路径、后台草稿、未发布修订或私人笔记。公开阅读、下载、复制和引用继续由对应的正式接口执行；首页聚合本身不授予额外权限。

## 当前验证边界

已完成 Python 目标模块的 `compileall` 与目标首页前端 ESLint；全量 TypeScript 仍被三个与 U01 无关的旧 live 测试隐式 `any` 错误阻断。尚未运行 Django 测试、前端构建、浏览器验收、逐图视觉回归或部署，因此本契约只记录实现和静态检查，不代表 U01 验收通过。

## 支持与反馈入口

`POST /api/catalog/feedback/`

- 认证：`AllowAny`。登录用户只写入当前账号关联；访客不建立账号身份。
- 请求：`category` 为 `content|function|citation|accessibility|other`，`body` 为 4–5000 字符，`contact` 为可选邮箱，`path` 为发生问题的站内路径。
- 成功：`201`，返回反馈 UUID、`submitted` 状态和不包含内部信息的确认文案。表单不会把 PDF、私人笔记或访问令牌提交到反馈记录。
- 失败：沿用统一 JSON 错误响应；字段错误不会伪装成提交成功。
- 持久化：反馈进入 `catalog.PublicFeedback`，默认状态为 `submitted`，按状态和提交时间索引。迁移已写入 `0067_publicfeedback.py`，尚未在当前环境执行数据库迁移。

## 持续研究与证据比较

`/api/reading/research-projects/` 及其 `turns/`、`selections/`、`comparison/` 子资源继续使用同一 owner-only Django API。项目和轮次写入均携带 `expected_revision`；会话动作携带 `request_id`，重复请求返回第一次结果，内容不一致返回409。

- 轮次明确保存 `parent_id` 与 `scope`；scope 可以是已保存范围、当前可用选材的 passages 或全馆 library。取消只改变当前轮次状态，已有 `result_refs`、项目选材和旧轮次不删除；后台读取跨页轮次时沿同一项目权限和分页约束。
- `ResolvedEvidence.reference_id` 是后端生成的稳定身份；跨页 anchors 使用组合身份。每次读回重新检查 owner、公开版本、DocumentRevision、EvidenceSpan、PDF页码和 content_hash。来源撤回或版本变化时保留身份与个人笔记，但不回显旧正文和 Reader URL。
- 比较矩阵 `dimensions` 最多20项、`cells` 最多200项，行是维度，列由 `column_id`（edition/work/asset）标识文献或版本；保存个人 `note` 与引用身份。读时的 evidence_status 为 selected/partial/unavailable/missing。已保存旧格可以保留失效引用，新格只能引用当前选材，不能由服务生成系统判断。
- 研究页和比较页不把模型、索引、generation 或制品身份作为普通读者控件；这些字段只留在诊断/API契约。

## 观点检索深度阶段

`POST /api/catalog/discovery-search/` 与其状态读取接口继续返回同一 Discovery 会话。首屏 `passages` 使用当前已稳定的 QueryLexicon、稀疏/向量融合、mMARCO 初排和来源校验；启用 `STL_DEEP_RETRIEVAL_ENABLED` 后，后台在同一 `generation` 中追加深度阶段，并在首屏完成交接时换发一个受同一代次约束的深度 `task_id`，避免旧 worker 回写。

- `task_progress.deep` 返回 `baseline_ready`、`deep_queued`、`deep_running`、`completed`、`partial` 或 `unavailable`；旧 worker 状态会在序列化边界映射到这些公开状态。
- 深度阶段只读取独立配置的 EG2 768 维索引，最多保留40个候选，最多20个 BGE 深排候选和10个上下文候选；`passages_deep` 保存同一来源身份上的深度排序和相邻证据上下文。
- `completed` 或 `partial` 的深度排序只有在再次通过发布资格、访问权限、DocumentRevision、EvidenceSpan/页码和原文指纹核对后，才会用于首屏 `passages`；深度服务缺失、超时、取消或任务排队失败时继续返回基础结果。
- `retrieval_identity` 只记录实际返回的索引、embedding、reranker 制品和版本。未配置或未加载的模型保持空值，不把 pipeline 版本写成索引代次，不把 mMARCO 冒充 BGE。
- 该契约不提供模型管理或第三步质量评测页面；生产启用需要隔离制品、generation、allowlist 和服务健康证据。

## 2026-10-18 个人阅读计划（R21）

- `POST /api/reading/reading-plans/` 使用幂等 `request_id`。目标无选材时复用 Discovery；显式 EvidenceReference 或公共路径仍沿同一公开修订身份。创建界面可读取本人研究选材，不写入示例书目。
- `PATCH /api/reading/reading-plans/{id}/` 必带 `expected_revision`。支持目标、基础、预算、顺序、状态、笔记、替换、本人估计和明确采纳建议；`preview=true` 只返回计算结果，不保存、不换revision、不排任务。确认预览仍以原revision再次提交，冲突返回409。
- `weekly_minutes` 1–10080 与 `duration_weeks` 1–52 形成总预算，乘积最多100000分钟；也可使用 `budget_minutes` 或原 `time_budget`。修改预算方式清除旧方式的遮蔽字段。`language_preference`最多160字符，只用于导读提示，不声称已做语言硬筛选。
- `use_confirmed_memories`默认false；`confirmed_memory_ids`最多40，仅本人仍confirmed的笔记。保存、执行任务、写回和读取时检查授权和版本；旧候选撤销状态为 `authorization_changed`。未授权时不会查询所有笔记。本人已明确采纳的文字与完成记录作为人工结果保留。
- 完成项保留原材料与位置，不能用同一请求降回pending后替换。替换普通材料时，如果有相关先修关系，必须显式 `remove_related_prerequisites=true`，只移除相关关系并保留原关系记录；其他关系保留。替换项回到pending。
- 条目读回包含实际公开封面、作者、出版年、availability、来源与阅读URL；所有 URL 以当前发布修订核实，整文件 Reader 也绑定revision。失效材料不提供可点击阅读入口。先修来源也会重新解析。
- `command/` 支持cancel/retry/enhance；`export/`重新校验来源并返回私人记录，浏览器提供打印/保存PDF。JSON与前端schema已重新生成；真实任务/打印分页和全部权限回归待统一验收。

## 2026-10-18 引文体检（R25–R27，部分接入，待统一验收）

视觉来源仅为最终 PDF `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第208–215页的实际页面图像。此处记录已接入的源码契约与未覆盖需求，不把图集审核标签、控件存在或静态检查当作功能及视觉验收。

### 路由、身份与任务

- 前端 `/account/citation-audits` 对应三步上传与本人任务列表；`/account/citation-audits/{id}` 对应解析预览及报告总览；`/account/citation-audits/{id}/issues/{issueId}` 对应单条引文、候选版本、原文与人工核验。issueId 为同一 CitationAudit 的 occurrence ID，不另建报告库或馆藏。
- API 基础路径 `/api/reading/citation-audits/`，列表分页、详情、原稿、OCR、导出及命令均要求登录并过滤本人。响应 `Cache-Control: private, no-store`，`Vary: Cookie, Authorization`。前端读写前后核对 cookie owner，身份变化清空私有视图、待上传文件和预览 URL；会话与权限回归仍待统一执行。
- 复用现有加密 CitationAudit、Celery 任务及共享公开来源。记录有 `revision/status/generation/error_code/completed_units/total_units/poll_after_ms/created_at/updated_at/finished_at`；状态为 queued、running、completed、partial、failed、canceled。进度来自实际阶段 queued/parsing/ocr/matching/checking/report 和处理单元，不估算完成百分比或固定耗时。
- 上传、排队命令及恢复按 owner 序列化，同一 owner 最多两项活动任务；超限返回409。取消增加 generation，使旧 worker 不能回写；已完成的解析、核验和人工决定保留。源码约束不等于真实设备并发与负载测量。

### 能力与创建

- `GET capabilities/` 返回 `accepted_filetypes/max_upload_bytes/max_pdf_pages/max_occurrences/max_active_jobs_per_owner/default_checks`，以及 `checks[]`、`scopes[]`、`ocr`、`analysis`。检查项包含 `id/label/available/required/description`，版本页码还声明 `requires`。本地 OCR/模型的 available 仅表示配置及允许的本地端点资格，`service_verified=false` 明确未进行运行健康探测，不可显示为服务已验收。
- `POST /` 使用 multipart：`file`、UUID `request_id`、可选本人 `project_id`、重复的 `checks` 字段及 `scope`。接受 PDF/DOCX，最大12 MiB；文件签名、PDF页数、DOCX解包和文本规模沿现有解析边界校验。成功返回202及持久记录。幂等身份包括原稿内容摘要、名称、项目和显式选项；相同请求返回已有记录，复用请求ID但改变内容返回409。前端在失败时保留本地文件、选项和相同请求ID。
- 默认检查项为 `citation_identification/bibliography_identity/version_page`。引文识别必选；版本与页码依赖书目身份；不选择某项就不执行相应自动核验。新上传的 `scan_ocr` 必须显式选择且本地 OCR 配置符合条件，默认不执行；未选择扫描识别的扫描部分保留为待核实。历史无 checks 记录沿原有行为兼容。
- `scope` 默认且当前仅接受 `public_library`，使用当前公开且本人可访问的馆藏版本/原文。capabilities 中 `private_materials` 明确 unavailable，私人稿件仅用于本人检查，不进入公共馆藏。没有通过虚构私人来源能力提交范围。
- `deep_analysis` 在上传阶段不可选。报告中须本人选择具体可访问 EvidenceReference，再用 `analyze` 单独发起本地关系分析；配置缺失则明确拒绝，已有结果保留。模型产出属于待核对候选，不替代人工结论。
- `data` 保存 `filename/filetype/manuscript_revision/checks/scope/file_size_bytes/manuscript_stats/bibliography/occurrences/warnings/stage`。统计只记录实际解析的字节、文本单元、字符、PDF页数或DOCX段落/内嵌图像；不适用或尚未解析的统计不填演示值。PDF页码与DOCX XML部件、段落、字符位置分开，不把段落当作Word排版页码。

### 人工决定、来源与局部重查

- `POST {id}/command/` 必带 `expected_revision`，不匹配返回409。前端保留本地决定/校正文案，用户核对最新记录后再提交。活动任务期间除cancel外不能修改核验记录。
- `decision` 接受单条 `occurrence_id` 或批量 `occurrence_ids`（二选一、1–1000项）。决定为 `accepted/ignored/corrected/needs_review`，`note`最多4000字符；任一ID不属于本稿件则整批不保存。`corrected_text`最多4000字符，非空值只允许单条corrected决定，作为本人的校正文案独立保存，不覆盖原稿、原始识别文字或旧决定。前次人工决定进入 `decision_history`。
- `match` 用 `entry_id/edition_id` 确认当前公开的候选版本，保存旧选择并重查该书目关联的引文；`link` 用 `occurrence_id/entry_ids` 保存本人书目对应关系并重查该条。候选仅为身份提示，题名相似、书目存在不等于原文或论断通过。
- `retry` 可带 `occurrence_ids` 仅重查已解析记录中的所选项；更换候选版本只影响相关引文。失败/取消后的重试保留已完成记录，OCR失败导致重新解析时保留 `parse_history` 和人工决定的稳定映射。该局部重查针对同一份原稿，并未实现上传新稿版本后的差异识别或增量重查。
- 每次详情/导出重新核验候选版本的公开资格，以及当前与历史 findings 中 EvidenceReference 的权限、DocumentRevision、EvidenceSpan、页码和内容摘要。来源撤回或改变后清除过时公开正文、Reader链接与模型建议，标记需重新核对；原稿和本人已保存决定仍保留。原文预览复用 Reader/PdfCanvas，与有效来源修订及规范化坐标绑定，不能把失效缓存当成当前证据。

### 预览、下载与未覆盖范围

- `GET {id}/original/` 返回本人加密记录解密后的原始文件附件；按需 PDF 预览使用本地 blob URL 与已有 PdfCanvas，关闭或会话变化时回收。DOCX 预览只显示实际识别的引文附近文本和位置，精确字体/分页仍通过下载原稿查看，不调用外部文档预览服务。
- `GET {id}/ocr/` 返回真实OCR进度和单元状态；带 `unit_id` 可取该单元解析记录。`GET {id}/export/` 返回 `schema_version=1` 的私人记录JSON并重新校验来源；前端保留报告JSON，并在重新核对owner后读取完整export快照，提供打印/保存PDF；打印包含全部引文、书目、实际来源、人工修正与历史，不受当前分页筛选限制。不可访问来源不打印旧片段，会话变化/权限失效/afterprint清除打印快照；打印版式与分页仍待统一验证，不写回Word/PDF原稿。
- 待实施/待验证必须分开保留：私人材料匹配、稿件新版本差异及增量重查、DOCX精确排版/原稿编辑回写尚未覆盖；PDF209的完整三栏解析流程仍需逐图核实。真实设备内存与排队负载、真实OCR/模型、权限与恢复、导出内容及全部桌面/移动视觉验收未运行。B03、B04、B05、B06不能据本次源码接入标记通过。
