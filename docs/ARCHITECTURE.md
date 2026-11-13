## 2026-11-13 新馆藏编纂策略

knowledge_automation复用SiteSetting的私有配置和AuditEvent，新增/api/knowledge/automation/。发布回调enroll只在同一KnowledgeCompilation建立待接续身份，执行、原文核验、缓存和ChangeSet仍为原服务。限定启用后first_published_at及正式可检索版本，已有逐书配置优先，恢复扫描每轮5本。配置启用后接续waiting_configuration，缺失配置保留错误，无隐式外部模型或代理回退。无新数据库或schema；本检查点未部署。

## 2026-11-13 分析来源选取版本

编纂prepare与检索原文均按有类型的叶节点取正文，references/unresolved容器只组织层级，不再重复其子段落。leaf-ranges-v1进入阶段一来源输入和持续订阅指纹。已有分析窗口的旧选取计划拒绝原地重写，通过原持续编纂reconcile建立新任务，保留旧任务与产物；未变化的窗口仍使用既有内容缓存。无新队列、正式知识写入入口或schema。

## 2026-11-13 OCR目录范围与历史兼容

outline-v10仅在已识别目录的相邻续页接纳重复的短标题/独立页码。沿现有分列/行聚合算法组合有缩进和相邻位置依据的多行标题，以章首位置扣除奇偶页边距，章节和前后附录身份保持；不将OCR错误页码自动改成猜测值。正文匹配要求完整标题的长度覆盖，连续且横向重叠的正文框只有能复现完整目录标题时才组合，坐标使用实际框并集。

自动匹配可附raw_text_range，字段为start/end/exact/page_text_hash/unit=unicode_codepoint。它只在原始有序TextBlock与完整Page.text之间从起点逐块匹配、间隔全为空白时产生。结构读取时重新核对整页哈希、原文区间和标题，允许区分标题与下方重复论述，不用相似度或PDF坐标反推文本偏移。历史快照不变。v4覆盖同时保存最终自动目录的unresolved_contents；v9/v10目录均可走已有导出和恢复服务。

## 2026-11-13 顺序综合与增量编纂联动

execute将最后一个顺序fold交给compile_wiki，编纂输入argument_context保存完整summary/development/limitations、source_artifact_hash、last_window、total_windows和unreviewed状态。此语境用于保留跨章概念变化、相反解释及范围限定；它没有新的原文证据地位，Wiki引用仍限定为本批经过原文回查的Assertion候选。该输入进入原有产物缓存键，不升级全局prompt版本，不使未变化章节重读。

在现有编纂输入预算内先保留完整综合和目标身份，再将完整陈述分批，已有区块逐块纳入并列明未读区块。综合或单条陈述装不下时给出明确失败，要求有依据地缩短综合或调整预算，不静默裁剪。此改动修复已存在的“综合仅展示、编纂未消费”断点，不增加新的任务系统、正式写入服务或模型配置。

## 2026-11-13 目录显示文字与原文范围

stl-raw-structure-v3在已确认人工目录的显示标题无法直接匹配时，只检查该节点保留的同页generated_heading观测；需有效归一化位置、与人工定位一致、原文唯一命中且候选位置无歧义。保留人工显示名并记录retained_observation，不改OCR，不以模糊文本偏移造证据。结构重新映射沿原表创建新版本，批量保留解析小节和叶节点、跨页范围及脚注连接；历史节点不更新。

Docling局部重解析只替换所选页的解析标题，已校准目录仍权威。局部层级挂入当前目录容器，避免截取两页的局部一级标题变成整书一级章。解析返回页面尺寸，页边重复检测只用于排除长标题的页眉候选：原始位置在页首100字符内、解析框在上16%且至少3页近似重复（SequenceMatcher >=0.9）。相似度不参与证据定位；短标题或缺少页面尺寸保持未判定，不伪造几何。原始文本和历史锚点保留。此启发式经真实样本核验，不声称普遍完美。

## 2026-11-13 长书恢复读取

共享编纂执行每次租约重新创建内存回执缓存，按阶段批量加载本run的已完成输出，不重新加载这些产物的整段输入正文。仍按真实窗口顺序核算覆盖和fold；只对缺失或指纹变化的单元查跨run缓存/调用模型。已完成窗口的原文引用每次仍回查，取消与租约校验仍在写入路径执行。章节祖先按唯一节点和层级批量读取。跨run复用保存reused_from_artifact_id与reused_output_hash，模型调用为0，不把复用计作新生成；无候选分析保持empty。缓存不跨进程、租约或执行尝试保留。

## 2026-11-13 来源自动维护

出版outbox激活后，在事务提交回调中只登记该Edition的现有索引任务，不解析、OCR或删除索引。队列满时SourceState保留未入队标记，定期协调优先处理；原任务历史保留。活动代际超过400来源时使用每批200身份游标，合并当前来源与既有状态身份，因此撤回来源也能被清理。游标放validation_details，不进入模型/索引配置指纹。构建中的代际继续原完整审计，不因增量游标漏验来源。线上始终先做当前访问与撤回核验，物理清理可以延后。

## 2026-11-13 大馆藏查询预算

检索超过400个粗筛来源时不再枚举全馆scope_token，召回只读索引身份，最多核验1000个候选/分支；关键词分页到足够合法结果为止，向量一次有界窗口。返回仍逐条核对当前出版/正文修订、权限、准确原文和全部筛选，图分支、深检索、问答共用此边界。预算耗尽显示不完整。该方案解决来源数量硬中断，不承诺有限top-k涵盖全馆。

DiscoverySourceState增加当前出版/正文修订、文本校验和、访问状态及关键词/向量计数回执；索引完成时写入，来源改变使SQL连接条件失效。历史回填命令每批最多500条，不读正文、不调用模型、不重建索引。大范围简单筛选由SQL统计，复杂快照分类只在候选核验，全范围计数标为未知。0101是派生状态schema，正式知识来源保持原模型。

## 2026-11-13 原文、来源陈述与 Wiki 接线

新增的有界PPR分支从已发布Entity/Assertion/EvidenceAnchor查询投影，返回原文DiscoveryDocument并进入同一RRF、过滤、定位和消费者；没有增加图数据库或模型调用。问答保留多段固定修订锚点，逻辑上下文以命中为中心；原文工作区可核对关联陈述。短行索引窗口v2保留全部原始偏移及叶节点身份，旧进行中任务继续按v1断点恢复。人工Wiki正文/标题/范围变化通知相应订阅，机器应用不自循环。具体预算、真实三书范围验证与未完成项见 [联动记录](stl4/RAG_WIKI_LINKAGE_20261113.md)。Mac迁移后置；此处代码验证不等于NAS已部署或整书已完成。

## 2026-11-13 Mac mini 主服务与特化组合

用户已确定大部分服务迁至Mac mini、NAS主要存储。目标将网站/API/PostgreSQL/Redis/Meilisearch和知识计算放在Mac，数据库与活动索引使用本地磁盘，NAS保留馆藏文件和备份。迁移期间单一正式写入，公网仍待授权。技术栈、论文/源码取舍、特化契约和待验证项见 [组合方案](stl4/RAG_WIKI_MACMINI_COMBINATION_20261113.md)。机器尚未到货，不记为已部署。

编纂来源账本只在阶段一产物保存，进度以产物ID/哈希引用，旧run恢复时一次压缩；同一不可变结构恢复不再改写清单。覆盖指纹包含prompt/schema、模型身份、结构和范围，变化后仍重算。所有非人工草稿统一执行人工区块保护，草稿不能自我声明human_edited，管理员在同一审核服务实际修改区块后可保存。无schema改变，MCP transport及独立Intelligence范围保持。

## 2026-11-13 来源语境检索与持续 Wiki 实施

以下更新覆盖同日早先“建议、未实施”的对应部分，未实施的图检索和向量质量验证仍保留为后续条件。

- `retrieval/contextual.py`从真实书名、章节路径与节点类型构造确定性语境，单独存入context_text。不是LLM生成上下文，也不推断主张者；原文与原始偏移不变。统一检索增加同权限的contextual候选分支，与稀疏/向量按RRF融合（60，权重1/1/0.6），再复用重排、去重、文献多样性和定位校验。精确引文与限定文本域查询不启用此分支。仅语义能力已启用时调用原embedding/reranker。
- 新投影ID/来源幂等键包含context-v1。索引设置更新在来源完整性和任务归属校验后执行；旧有效索引/向量仍保留至替代回执完整。内部`_baseline`仅用于同来源对照，管理台接口返回实际分支数量。没有部署另一套向量库或RAG正式写入。
- `KnowledgeCompilation`为每个版本保存自愿启用、范围、执行方式、目标知识页和最后run，不复制调度系统。来源或页面依赖更新标记pending_refresh，经既有Celery/beat接续。同一来源、范围、页面基准和模型身份复用run；章节缓存独立于页面编辑。实际原文范围、解析/schema/prompt/Provider身份进入缓存。
- `execution_mode=agent`明确表示交互代理读原文并提交结果。`knowledge_compilation.submit_agent_result`检查操作者、范围指纹、任务版本、当前结构、schema和原文；重复回执幂等。配置模型调用数为0，代理响应另记，token/费用未知而非0。Provider执行仍经既有DocETL适配和严格不截断入口。
- OCR短行仅在模型输入中按同页、同类型、连续原始空白合并来源字段，覆盖账本保留原节点；不改变历史文本/offset。stl-raw-structure-v2对经验证的重复生成页眉和目录页码尾缀做保守映射，人工目录不忽略，历史结构不覆盖。
- `/api/knowledge/compilations/`、产物、代理提交与`/reviews/`接入原文/知识两工作区，共用原ChangeSet审核、应用、预览与发布。主题/专题页通过有界target_page_ids参与编纂；不从私人研究导入材料。没有恢复独立Intelligence工作台，MCP未改。

当前三部文献的指定章节代理实测在继续，尚不代表整书覆盖或大馆藏质量验证；无向量模型的环境只比较关键词和来源语境分支。

三书第一轮现已形成56项待审建议，详见 [真实范围与业务验证](stl4/RAG_WIKI_THREE_BOOKS_20261113.md)。候选回滚事务已走通同一审核/应用入口和20条证据的保存定位，未保留人工确认或发布。`assertion_evidence`仅合并同页同立场且隔原始空白的连续片段；不同页/立场/正文间隔保持独立。管理台可选择至多30个目标知识页、打开产物原文页，并显示当前阶段与范围内缺页。

## 2026-11-13 RAG / Wiki 算法研究与当前边界

用户已将独立 STL Intelligence 从本轮排除并要求撤下内网入口，后续重新开发。前端任务创建、阶段列表、恢复入口已移除，共用审核成为 `/admin/knowledge/review`；旧 URL 兼容跳转。`CurationRun`、`ChangeSet`、`/api/intelligence/` 共用接口及历史继续存在，没有把界面撤下描述为后台全部删除。审核列表目前仍复用旧 runs GET 返回的 drafts；没有建立第二个审核写入服务。MCP按用户已在其他工作中完成的状态排除，未独立验证其公网发布，也未修改。

### 已核实的实现与缺口

- `retrieval/search.py` 已统一实际消费者，含关键词/向量候选、RRF、有限异名/跨语种分支、重排、去重、作品多样性和来源权限复核。Meilisearch关键词排序不是默认BM25，不能把当前基线写成已运行BM25。当前候选向量就绪0；代码存在不能证明语义检索质量。
- Wiki已有Entity、来源独立的Assertion、不可变证据、唯一EditorialRevision正文、稳定区块、ChangeSet、发布投影和依赖失效。来源更新目前进行结构/索引更新和受影响区块失效，没有自动生成并审核增量Wiki patch的真实闭环。模型章节产物0，不能称已经完成长书编纂。
- Docling用于结构解析；DocETL用于结构化处理操作，均不等于完整RAG算法。当前没有部署GraphRAG、RAPTOR、LightRAG、HippoRAG或PageIndex算法管线。

### 论文与项目比较（截至2026-11-13查阅，以下为建议，未部署）

| 方法与一手来源 | 可借用的能力 | STL取舍 |
|---|---|---|
| [Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval) | 为小片段补来源上下文再做检索，与重排结合 | 优先比较。先用可信书名、章节路径、主张者等；模型补充内容是派生检索字段，不得改变原文或成为引用。 |
| [Late Chunking](https://arxiv.org/abs/2409.04701) | 在嵌入模型的上下文编码后进行片段池化 | 条件性实验。需要适用的token表示/池化能力，不是任意OpenAI-compatible embeddings接口都支持；仍受模型上下文上限约束。 |
| [RAPTOR，ICLR 2024](https://arxiv.org/abs/2401.18059) | 递归聚类摘要，多粒度检索 | 借用多粒度索引；语义聚类树不能替代真实章节顺序，摘要只能定位原文。 |
| [PageIndex官方实现](https://github.com/VectifyAI/PageIndex) | 文档树及推理引导的树检索 | 适合候选长书内深入定位，需与段落检索比较。当前百万文档FileSystem层标明cloud-only，不能当本地开源能力或全库容量证明。 |
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/) | 实体/关系、社区摘要、局部和全局检索 | 适合跨书主题与专题探索；社区不是学派，机器聚合不能成为正式身份关系。必须保留来源与论述归属，不能压成无来源关系。 |
| [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) | 推迟部分预计算，在查询预算内逐步读取 | 借用按需分析思路。官方研究/产品发布不能自动视为现有GraphRAG开源包已提供相同功能；其新闻语料成本不能转用为STL承诺。 |
| [LightRAG](https://arxiv.org/abs/2410.05779)、[官方仓库](https://github.com/HKUDS/LightRAG) | 图与向量双层检索、增量更新 | 可作为有界图检索的实验候选。须验证归并和更新语义是否保留同名概念、作品和相反解释；不整套接管STL正式库。 |
| [HippoRAG 2，ICML 2025](https://arxiv.org/abs/2502.14802)、[官方实现](https://github.com/OSU-NLP-Group/HippoRAG) | 段落/短语图与Personalized PageRank，多跳关联 | 针对跨书关联问题做小样比较。由STL限定边、语境、来源和预算，不能沿图无限扩散。 |
| [STORM，NAACL 2024](https://aclanthology.org/2024.naacl-long.347/)、[实现](https://github.com/stanford-oval/storm) | 多角度研究问题、提纲和有引文长文，支持自有检索器 | 用于专题编纂的提问/提纲环节，不等于持续Wiki的修订、冲突、审核和失效管理。 |
| [OpenScholar，Nature 2026](https://www.nature.com/articles/s41586-025-10072-4) | 学术检索、重排、反馈检索及引文支撑综合 | 借用证据回查和反馈循环。论文明确缺少社科评测，不能从其成绩推断中文社科书库效果。 |

[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)是持续编纂与交叉引用的设计说明，不是一套安装后即可完成的标准算法。STL需要数据库权威、人工保护、来源权限和编辑发布，不能直接照搬个人Markdown目录作为另一份正式知识库。

新研究可作为小样实验依据：[ReasonIR](https://arxiv.org/abs/2504.20595)关注推理需求与检索训练；2026年[AgentIR](https://arxiv.org/abs/2603.04384)预印本将搜索意图上下文纳入检索；2026年10月[Contextual Embeddings Beyond the Gold Chunk](https://arxiv.org/abs/2610.38854)预印本强调同时召回答案片段与核验所需证据。对STL的启发是检验“解释是否相关、证据是否完整”，而不只检验词义相似。这些结果尚未在本站验证，不据此直接替换生产模型。

### 拟采用的特化方式

1. **在线原文检索**：精确引文保持低成本词法通道；概念/问题检索使用多语向量、上下文补充和重排；复杂比较按预算拆分检索问题，扩大到段落、小节、脚注或有来源的陈述关系。作品/章节路由与全库段落检索并行保留，避免第一层选书失误后永远漏书。所有通道最后核对原文版本、权限与证据立场。
2. **离线长书编纂**：固定版本与章节结构；按完整段落/小节切窗并记录读取范围、缺页和失败窗口；保存带归属、条件和原文锚点的论点/概念记录。按章节顺序形成论证发展，保留可回查的逐章记录，不能仅递归压缩摘要而丢掉限定和反例。全文覆盖完成与解释通过审核分开。
3. **跨书知识**：有界匹配已确认身份、译名与概念语境；对照来源独立的Assertion，区分作者提出、转述、批评、编辑解释。相反结论可能来自时间、地区、对象或定义差异，不自动判一方错误。共现不生成影响关系，译者/编者不替代章节作者。
4. **增量Wiki**：从来源与已确认内容提出稳定区块patch，保留新证据、旧基准与修改理由；人工改动产生局部冲突，经同一ChangeSet审核、保存、预览、发布。来源更新只重做受影响的窗口、身份匹配及区块；生成页不能作为新陈述的唯一原文证据。
5. **馆藏规模**：PostgreSQL保持正式身份/陈述/修订，Meilisearch保持检索投影，Celery和既有计算节点负责批处理。昂贵的整书编纂按选书和受影响范围执行，不能每次新增文献就全馆重建。图、摘要和索引是可重建派生物，不另建需要同步的正式书库。生成、embedding、reranker分别核对Provider能力和预算，接口兼容不代表模型能力相同。

知识产物应服务既有组件：学者页按作品与时间展示论述变化；流派/概念页展示定义、语境与分歧；主题页建立问题、机制、条件和证据对照；特别策划形成问题驱动的阅读顺序与不同解释。每个内容块可见来源、覆盖、版本、人工编辑状态及公开预览。原文与检索工作区负责检索诊断和来源核验；知识编纂及审核子页负责内容、影响与发布，不恢复独立Intelligence工作台。

### 验证与执行顺序建议

先用真实授权样本比较当前关键词、混合+重排、上下文/章节增强，再选择一种图检索候选；不一次叠加所有算法。初始评估可选20—30部实际文献、60—100个问题，包含中文/英文、译本、长章、论文集、扫描件、同名概念、相反解释和无法回答的题目。样本与金标准尚未建立，数字是建议范围。

使用同一来源版本和受控模型预算比较标注候选池中的召回/排序、原文支持、主张归属、反方覆盖、版本与权限正确性，以及实际p50/p95时延、调用量、费用、索引体积和更新范围。人工核验核心证据，模型评分仅辅助。先证明观点检索改善，再验证一部长书的覆盖与中断恢复，最后验证新文献仅修改相关Wiki区块、人工修改能阻止覆盖。论文分数、上下文窗口标称长度、界面完成与本地语法检查均不是这些业务目标的证明。

## 2026-11-11 来源错误与索引批次

关键词执行跨短正文单元聚合最多20条，Meilisearch确认后才推进正文断点。已提交但未确认的当前单元重放使用稳定索引ID；同一版本有效旧投影继续保留。指定作品/资产在SQL范围内筛选后再加载已发布资料和关系，不改变来源权限。缺失历史快照的结构校验错误保存为manual_intervention；协调器不自动重试相同输入，修复来源后可通过现有任务恢复或新修订任务继续。API/管理台展示失败及正文处理入口，无schema变化。

## 2026-11-10 检索覆盖和编目审核写入

旧元数据复核的学术关联统一经academic_relations.propose_work_relations进入ChangeSet，关键词仅产生MetadataCandidate；WorkTopicRelation继续承担书目分类。检索结果返回实际关键词覆盖，未完整索引不得显示成功零命中。来源索引任务以DiscoverySourceState.job为当前归属，旧任务不能退休新结构投影；locator按批次加载片段/章节路径，原文与版本校验保持。

## 2026-11-10 结构执行失败与检索投影接续

document_structure继续复用CapabilityDemand租约及ProcessingJob。远程release原子保存失败/等待状态、原因和重试上限，恢复复用原ProcessingCenter服务与确定性任务ID，不另建调度系统。客户端可指定信任CA文件，仍校验证书和主机名。相同已发布正文仅重组结构时，旧有效向量保留到新投影语义就绪；关键词完成状态以当前完整来源回执判定，旧/新结果均重新执行来源权限校验。实体匹配预览由Knowledge规范查询补责任者和陈述作品来源，客户端候选ID不授予资料写入权限。

## 2026-11-10 人工正文结构与证据依赖

paragraph_corrections统一处理完整段落连续关系及最近校正撤销，基于不可变DocumentStructure/Node/Segment，不另建正文或证据表。请求标识、操作者、依据、基准结构、原节点及新节点进入结构来源；旧锚点不改绑。Docling重解析保护human_corrected节点，目录变化仅重映射层级。知识页证据依赖只比较固定正文哈希与active状态，兼容旧结构哈希但不能接受正文变动；章节推理仍按实际范围和解析版本缓存。

2026-11-10 `knowledge_entity_queries`以原约束资料和人物发布快照为名称/异名的读取权威，Entity迁移副本保留历史；DRF/MCP/检索/匹配共用。`knowledge_aliases`只在ChangeSet应用时形成未公开草稿，知识页预览列明异名发布范围，原有publish_page事务统一确认，草稿不参与公开查询。

## 2026-11-10 Entity类型资料

Entity以受约束的一对一外键复用OrganizationAuthority、TheoryTimelineEvent，研究对象使用ResearchObjectProfile。资料字段只在既有EditorialRevision中编纂，ChangeSet.entity/profile_patch记录审核、基准与应用回执；知识页发布事务激活对应类型修订，公开读取仍执行原类型和来源权限。事件保留原关联与合并历史；同名组织不再被名称唯一约束视为同一身份。管理入口/knowledge/entities/{id}/profile/和原事件资料工作区协同，Markdown与页面正文的唯一权威不变。

## 2026-11-10 查询协议与公开投影

检索入口services/retrieval/objects.search由DRF /api/search/query/、MCP unified_search及管理台已发布知识查询共用。返回分组状态与source_type，Wiki正文、书目/身份说明和原文引用保持语义区别。原文/人工策展复用既有Meilisearch，正文定位沿EvidenceAnchor DTO；作品、实体、知识页以PostgreSQL已发布投影执行有界文本匹配，返回has_more及coverage，不宣称全量语义召回。公开Entity资料使用确认异名及发布的人物快照，内部来源备注仅在管理端返回。查询不创建正式知识、不回写私人研究。

## 2026-11-10 学者关系兼容边界

ScholarRelation只保留历史身份、来源、已发布与未发布修订。旧HTTP保存转换到ChangeSet，公开关系及学者消费者统一读取来源独立的Assertion。旧取消回执与请求锁保留；回收站撤回转审核，旧直接发布返回明确替代入口。Django后台WorkKnowledgeRelation/PersonKnowledgeRelation只读。回填命令backfill_knowledge_core --relations --human-pages --batch-size 100按当前公开修订保留来源，数量与备份见CURRENT_PROGRESS；无ScholarRelation真实候选数据，测试夹具不能代替实书迁移。

2026-11-10 专题页可无Work/Entity主对象，以KnowledgePage自身范围提交人工ChangeSet（0098）。正文、标题、范围由同一EditorialRevision管理；公开/knowledge/{slug}仅读取发布投影，来源权限变化继续隐藏受影响区块。关联资料与跨知识页链接由既有resolve_target验证，不另建正文权威。

2026-11-10 身份归并：`knowledge_identity`保存Entity重定向，查询按明确归并展开，原Assertion端点与KnowledgePage不重写。原节点/人物归并命令继续负责权限、预览、事务、幂等和可回退记录；知识修改纳入指纹保护。类型资料里的`prose`只保存与原文完全相符的格式标记，继续作为类型资料功能保留，不与Wiki正文双向同步。

> 2026-11-10 知识架构增量：ChangeSet仍为唯一审核/应用服务；人工知识页可按Work/Entity范围提交，自动与MCP草稿须固定DocumentRevision。AssertionSource的文献出处与EvidenceAnchor精确证据分开；Assertion.supersedes保留历史修订。来源专属学术图谱从Assertion查询投影，已迁移旧关系只作历史兼容。详见[知识核心实现记录](stl4/KNOWLEDGE_INTELLIGENCE_20261109.md)。旧写入入口的剩余迁移明确列在该记录，不宣称已全部退役。

## 2026-11-12 本机 Codex MCP 策展

tools/stl_mcp 是本机stdio接口，通过现有严格主机校验的SSH通道在原API容器内启动固定Django命令分派，复用原编目、编辑修订、规范实体、EvidenceCuration与AuditEvent。没有远程MCP监听、第二套馆藏或数据库schema变更。模型仅可调用白名单读取/草稿命令；固定账户、token_version、作品范围、对象关联、人工锁、版本与逐项回执在服务端重核。独立本机SQLite仅存不可变计划、原请求编号及耗时，不承担正式业务状态；机器待审与人工确认/正式发布分开。三书6项维护增补已真实保存并跨进程回放验证。边界与实测见 `stl4/LOCAL_MCP_CURATION_20261112.md`。

# STL 当前架构

2026-11-10 候选管理设计采用原文与检索、知识编纂、Intelligence三个连通工作区。新增 KnowledgeBlockDependency 仅保存当前知识页区块的依赖投影，EditorialRevision仍是草稿正文来源；人工编辑与外部/模型建议共用ChangeSet。三个管理工作区及公开知识页投影已经接入，0094在隔离内网候选完成；正式环境未迁移。原文窗口与关键词检验共用现有检索服务，正文由不可变RevisionPage与locator提供。官方比较依据及状态见下方候选记录。

2026-11-10 新增[Knowledge Core / Intelligence 内网候选](stl4/KNOWLEDGE_INTELLIGENCE_20261109.md)，记录新模型、服务、locator、配置、隔离部署和未完成项。以下仍描述正式环境，不能将候选能力误作已上线。

当前架构文档已集中在 [docs/architecture](architecture/README.md)。基准为 2026-11-09 公网 STL 4.0 `curation-publish-r1`，包含实际运行文件核对、源码调用关系和只读页面观察。

| 主题 | 当前入口 |
| --- | --- |
| 产品与系统 | [项目概览](architecture/00_PROJECT_OVERVIEW.md) · [C4系统](architecture/01_SYSTEM_ARCHITECTURE.md) · [运行容器](architecture/02_RUNTIME_ARCHITECTURE.md) |
| 前端与管理端 | [前端架构](architecture/03_FRONTEND_ARCHITECTURE.md) · [管理地图](architecture/04_ADMIN_INFORMATION_ARCHITECTURE.md) · [组件](architecture/05_ADMIN_COMPONENT_MAP.md) |
| 数据与策展 | [领域模型](architecture/06_DOMAIN_MODEL.md) · [知识关系](architecture/07_KNOWLEDGE_GRAPH_AND_RELATIONS.md) · [流程](architecture/08_CURATION_WORKFLOW.md) |
| 服务与安全 | [API](architecture/09_API_AND_SERVICE_MAP.md) · [异步/OCR](architecture/10_ASYNC_TASKS_AND_OCR.md) · [权限](architecture/11_PERMISSIONS_AND_SECURITY.md) |
| 维护 | [设计系统](architecture/12_DESIGN_SYSTEM_AND_PAGE_PATTERNS.md) · [部署](architecture/13_DEPLOYMENT_AND_OPERATIONS.md) · [质量](architecture/14_TESTING_AND_QUALITY.md) · [问题](architecture/15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md) |

完整管理端入口、组件/接口清单、模型消费者及生命周期在架构目录中交叉链接。机器生成的引用只证明源码关系，实际语义和权限仍由对应章节说明。

旧增量文档保留在 [Git 历史快照](https://github.com/WinstonMo0807/social-theory-library/blob/315a3c48442afc9cafc79718c152e5e70352b13f/docs/ARCHITECTURE.md)。它是历史记录，不作为4.0当前架构入口。未来架构变更直接维护新目录，并更新[版本与证据](architecture/AUDIT_BASELINE.md)。
