# Unified Scoped Search Inventory

更新日期为 2026-08-17。本文件记录 Task 4 修改前的真实源码状态。它是源码 inventory，不是生产验收记录。

## Public routes

| Route | 当前搜索框与文案 | 当前调用 | 实际检索对象 | 位置 | 问题 |
| --- | --- | --- | --- | --- | --- |
| `/` | 检索书名、学者、理论、主题与馆藏原文 | 提交到 `/explore`，再调用 `/catalog/search/` | Work、ScholarProfile、TheorySchool、Topic、Passage | 后端 global | 跨实体意图明确，但 URL 和 API 没有显式 `context=global` |
| `/explore/original` | 原文检索 | `/catalog/search/` | Work、Scholar、Theory、Topic、Passage，按组展示 | 后端 global | 是现有 Global Search；context 依赖 route 约定，没有统一 contract |
| `/explore/opinions` | 输入问题或观点 | `/catalog/semantic-search/` | SemanticChunk / passage | 后端 semantic | 概念边界正确，不应并入 Entity Search |
| `/explore/ask` | Ask Library | Reading conversation API | RAG passage evidence | 后端 RAG | Task 4 不修改 |
| `/scholars` | 搜索中文名、外文名或译名 | `/catalog/scholars/?search=` | ScholarProfile / Person | 后端 entity | Scope 正确；旧实现只要求 ScholarProfile published，没有统一 Person public authority boundary；分页 URL 存在但 loader 未传 page |
| `/topics` | 搜索研究主题、研究领域或核心概念 | `/catalog/topics/?search=` | Topic | 后端 entity | Scope 正确；loader 丢失分页 envelope |
| `/subdisciplines` | 搜索子学科、研究对象或问题 | 先调用 `/catalog/subdisciplines/?discipline=`，再在页面数组 `includes` | Subdiscipline | 前端本地 | 只筛当前返回页，分页、Unicode、count 和 backend visibility 不一致 |
| `/theory-schools` | Hero 声称搜索理论、学者、概念或馆藏；目录又称搜索理论传统 | `/catalog/theory-schools/?search=` | 只有 legacy TheorySchool | 后端 entity | Hero placeholder 与行为不一致；与 normalized `/theories` 并存，属于兼容 presentation path |
| `/theories` | 搜索理论 | `/catalog/search/?context=theories` | KnowledgeNode canonical identity | SearchService scoped | 页面搜索不再混入学者、作品或 passage |
| `/theories/directory` | 搜索名称、别名或外文名 | `/catalog/theory-system/nodes/?type=&discipline=&q=` | 指定 node type 的 KnowledgeNode | 后端 entity | Scope 和 URL state 正确；沿用 mapped legacy canonical identity |
| `/theories/timeline` | 搜索事件、学者、著作或概念 | `/catalog/theory-system/timeline/?q=` | 只返回 TimelineEvent | 后端 timeline | 输入字段跨关系，但结果仍是 event context，语义正确 |
| `/theories/graph` | 搜索当前节点 | 已加载 graph.nodes 本地筛选 | 当前有限图谱中的 node/work/scholar | 前端局部 | 文案明确为当前图谱，不属于 catalog search；保留本地交互 |
| `/theories/reading-paths/[slug]` | 无搜索框 | ReadingPath detail | 当前 ReadingPath 的阶段 | 无 | 不猜测“搜路径”或“路径内搜作品”；统一 service 只准备 `reading_paths` context |
| `/reader/[assetId]` | 搜索文档 | `/catalog/assets/<id>/search/?q=` | 单个 Asset 的 Page/Passage | 后端 document | 是 document-local search，不并入 Entity Search |

## Admin and editor routes

| Route / component | 当前实现 | 结论 |
| --- | --- | --- |
| Admin topbar 与 `/admin/library` | URL `q`，调用 `/ingestion/items/?search=` | 明确搜索馆藏项目，scope 正确 |
| Metadata review queue | 后端 search 文件名/题名，status 再对当前页本地筛选 | status 应发送给后端，避免只筛第一页 |
| Scholars Admin | 先载入 `/catalog/admin/scholars/` 第一页，再用 JS 筛姓名和 aliases | 应改用既有 Admin SearchFilter；draft 数据只允许 Admin endpoint |
| Theory nodes Admin | `/catalog/admin/theory-system/nodes/?node_type=&status=&discipline=&q=` | 后端 scoped，保持 |
| Theory timeline Admin | `/catalog/admin/theory-timeline/?...&q=` | 后端 scoped，保持 |
| Theory graph explorer | 当前 graph 数组本地筛选 | 有限交互数据，保持，不当作重复 engine |

## Backend paths before Task 4

| Path | 角色 | 当前状态 |
| --- | --- | --- |
| `/catalog/search/` | global exact/full-text search | 自定义大视图，分组返回 Works、Scholars、Topics、Theories、Passages；context 不显式 |
| `/catalog/semantic-search/` | passage/viewpoint search | 与 entity search 职责不同，Task 4 不改 |
| `/catalog/works/` | Work list | 无 query search；Work/Edition 已按 Work 聚合展示 |
| `/catalog/scholars/` | Scholar entity list | DRF SearchFilter；使用 mixed Person.aliases，Person authority_status 未统一限制 |
| `/catalog/topics/` | Topic entity list | DRF SearchFilter，public Topic only |
| `/catalog/theory-schools/` | legacy TheorySchool list | DRF SearchFilter，public legacy presentation only |
| `/catalog/disciplines/` | Discipline list | 自定义 `q`，public Discipline only |
| `/catalog/subdisciplines/` | Subdiscipline list | 已支持 `q`，但前端没有使用 |
| `/catalog/theory-system/nodes/` | normalized KnowledgeNode list | 支持 type、discipline、q，public node only |
| `/catalog/theory-system/search/` | mixed theory landing search | 已删除；无正式消费者，职责由 `context=theories` 与显式 global search 分担 |
| `/catalog/theory-system/reading-paths/` | ReadingPath list | public paths，当前不支持 q |

## Task 4 decisions

- SearchContext 采用 `works`、`scholars`、`disciplines`、`subdisciplines`、`theories`、`topics`、`reading_paths` 与 `global`。
- `global` 必须显式。空 global query 返回空分组，不执行全站检索；旧 Explore 空 query browse 通过兼容 adapter 保留。
- `/catalog/search/` 继续是唯一协调入口。显式 context 返回共享 envelope；没有 context 的旧 payload 暂时兼容并标记 deprecated。
- 现有 entity list endpoint 保留为 adapter，并复用同一个 SearchService query constraint。最终综合验收再决定删除哪些兼容路径。
- `theories` 优先返回 published KnowledgeNode。已映射的 TheorySchool、Subdiscipline、Concept 不再成为第二个 canonical search identity；未映射 legacy TheorySchool 仅作为兼容 presentation result。
- Topic 始终保持 Topic identity，不因同名 KnowledgeNode 自动合并。
- Public Scholar 必须同时满足 Person verified 和 ScholarProfile published。后台搜索仍可显式读取 draft，但不通过 public SearchService 泄漏。
- 原文、观点、单文档搜索保持独立。Global 可以分组协调 entity 结果，legacy Explore 继续单独显示 Passage group。
