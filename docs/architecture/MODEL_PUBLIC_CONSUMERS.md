# 数据模型与实际消费者

[架构目录](README.md) · [字段明细](inventory/model-fields.csv) · [直接代码引用](inventory/model-consumers.csv)

下面按业务对象解释写入→读取。CSV的4478条直接引用包括管理、服务、任务和serializer，并非4478个公开接口；公开与私人边界必须用本表和eligibility代码判断。

| 对象/存储 | 主要写入链 | 读取/公开消费者 | 生效与保留规则 |
| --- | --- | --- | --- |
| Work / Edition | pipeline、manual_catalog_views、workspace_edits、work_editor | PublicWorkDetailSerializer、WorkCardSerializer、CatalogEditionSerializer、home/search | 公开从活动CatalogPublicationRevision取值；草稿Work字段不能补进旧快照 |
| Contribution / Person | 编目责任者、人物规范命令、作用范围编辑 | contribution_projection、书目作者、证据作者归属、学者作品 | role/scope/approved与版本共同约束；合并需影响核对 |
| ScholarProfile / PersonNameVariant | scholar editor、scholar_media、person_authority | public_scholars、scoped_search、学者页面 | 档案公开与人物规范状态都参与过滤；内部说明不公开 |
| KnowledgeNode / Alias / 分类连接 | theory_system_views、editorial_drafts | theory-system公开接口、目录、graph、节点页、检索词表 | 草稿/发布状态；异名确认与身份映射不是自动同义合并 |
| TheorySchool / Concept / LegacyKnowledgeMapping | 遗留记录与人工映射服务 | 兼容路由、canonical_identity适配 | 不是新建的第二个知识图；映射必须合法 |
| Topic / Discipline / Subdiscipline及Work连接表 | taxonomy编辑与工作台classification/knowledge | public_topics、学科/子学科页面、public_taxonomy_snapshot | 端点撤回实时屏蔽，历史快照保留来源 |
| KnowledgeRelation / PersonNodeRelation / ScholarRelation | 独立关系编辑与正式修订 | graph、相关人物/节点、关系依据 | source/target/direction/类型与证据分别保留，候选不直接进入公开图 |
| TheoryTimelineEvent / TimelineEventRelation | timeline editor、参与者选择 | 理论/学者时间线与事件详情 | 日期精度与角色独立；公开需approved/有效来源 |
| Asset / Page | 文件校验、提取、OCR、人工校订 | manifest、PDF交付、Reader、passage focus、原文搜索 | 文件身份、access_status、活动阅读文件与登录一起判断 |
| DocumentRevision / EvidenceSpan | 文本处理、证据定位 | evidence_envelope、ClaimEvidence、Reader定位、检索来源 | 固定revision/checksum；失效须显式标记 |
| EvidenceSnippet | theory-system/evidence | EvidenceSnippetSerializer、WorkNodeRelationSerializer | file/page/quote固定，返回revision由当前活动快照推导；追溯限制见审计报告 |
| Passage / TextBlock / SemanticChunk / Discovery投影 | extract、semantic_chunks、discovery_indexing | 文档内搜索、Discovery、语义检索、书库问答 | 派生；版本/权限变化需失效或重建，不成为人工真相来源 |
| MetadataCandidate / EntityResolutionCandidate | 外部源、OCR、AI、人工导入 | 字段助手、复核队列、身份选择 | 采用/拒绝/冲突/依赖失效分开；保留来源与决定 |
| FieldLock / CatalogFieldDecision / DecisionLog | 人工确认与锁定、撤销命令 | 工作台预检、候选策略、发布阻断 | 人工锁优先；一项依赖变化可使确认需要重新核对 |
| DerivedClaim / CuratedClaim / ClaimEvidence | claims提取→人工筛选/采用→publish_work_curated_claims | 高价值候选、正式观点与证据/研究消费者 | DerivedClaim.shadow不是正式知识；CuratedClaim仍需发布 |
| EditorialRevision / CanonicalObjectRevision | 各对象保存/发布协议 | 管理预览、历史、正式对象/文章/编排 | target身份与base版本核对；保存不等于发布 |
| CatalogPublicationRevision | publication_commands→knowledge_publication | public_editions/active_catalog_snapshot、公开书目与文件 | active pointer与metadata_ready等联合判断；合法历史修订可恢复 |
| KnowledgePublicationEvent / ProjectionState | 正式变更事件、依赖引擎 | 处理/发布状态页、索引与缓存刷新 | 有lease、attempt、error；后台失败不伪造已同步 |
| ReadingPath / Stage / Item | ReadingPathWorkbench、work_curation | public_reading_paths、路径列表/详情、作品相关路径 | 材料可固定edition/asset/revision与页码；私人计划不在这里 |
| CurationProject / RecommendationIssue | 项目与文章编辑器 | 项目成员工作台；public_editorial公开文章 | 项目团队权限；文章active/scheduled修订；公开byline显式授权 |
| EvidenceCuration / Reference | shared_curation | PublicEvidenceCurationView、公开证据模块 | 来源修订与公开资格重新核对；删除摆放不删除原文 |
| content_placement类型EditorialRevision | content_placements命令 | PublicPlacementView、页面内容区 | 父对象锁、独立草稿/公开修订、来源撤回过滤 |
| SiteSetting | site-content命令、editorial_issues | SiteConfigView、site.server、home.server、欢迎页 | 网站共享草稿范围需明确；内部配置不等于public=true |
| MediaAsset / MediaRendition / 发布媒体引用 | media服务、对象图片选择 | 公开封面/肖像/策划图片受控接口 | 原文件与裁切版本保留；上传不等于已被正式引用 |
| UploadBatch / UploadItem / ProcessingJob | 上传与任务命令 | 管理队列、处理中心、发布准备 | 业务任务状态写PostgreSQL；队列投递不等于完成 |
| ReadingProgress / Annotation / Bookmark / SavedItem | 登录Reader与账户操作 | 本人阅读、笔记、收藏界面 | user过滤；原文修订变化不静默重绑注释 |
| ReadingList / PersonalReadingPlan / ResearchProject / CitationAudit / ResearchMemory | 本人工作区与任务 | 本人账户、授权AI上下文、显式分享 | 加密正文/数据与owner范围；不进入公共catalog证据包 |
| LibraryConversation / Message / Source | 书库助手和连续研究 | 本人对话与可追溯来源 | 源失效时不能继续作为可公开证据；对话正文私有 |
| User / ProviderCredentialSecret | 账户与馆长设置 | 登录/权限；Provider gateway内部解密 | 密码哈希/凭据不回显；公开署名不直接暴露账户信息 |

主要公开过滤依据：[publication_eligibility.py](../../api/catalog/services/publication_eligibility.py)、[public_work_detail.py](../../api/catalog/public_work_detail.py)、[public_editorial.py](../../api/catalog/services/public_editorial.py)、[evidence_envelope.py](../../api/catalog/services/evidence_envelope.py)。
