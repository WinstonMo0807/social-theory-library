# 理论、学者、主题与策划的无引导使用核验

2026-10-24。接续 `PUBLIC_USABILITY_AUDIT_20261024.md`，按用户要求的八个一级分类继续使用 [grilling 作者规则](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md)自行追问。环境事实由代理查明，不将可从图和代码确认的问题交给用户重复回答。Ponytail full 仅用于选择最小修法，不缩减来源与权限核查。

范围以 `docs/stl4/ATLAS_INDEX.csv` 的实际 module 为准：理论流派45–60共16张、学者62–66共5张、主题68–71共4张、特别策划73–78共6张，合计31张。每张均实际用 view_image 打开 `tmp/pdfs/stl4-full-review-20261024/view-NNN.*`，仅采用唯一 final-r2 PDF 提取原图。CSV中的旧image_path没有作为视觉依据。重叠视图按49、54/55、57、60、63/66、69/71、74/76/78的最终状态理解。

本轮只写本文件。未改业务源码、提交、运行测试、构建、浏览器、业务请求、模型或生产操作。以下是读图与静态调用链证据，均不表示实施页面、设备、真实数据或权限验收通过。源码行号是审计时快照；主线并行修复可能使其移动。

## 一、按四分类追问

**理论流派。** 不知道学派名的初学者能否从学科、概念或人物进入；关系图是否能改用列表和键盘操作；两个用法是否有准确原文而非自动推定立场；时间线是否区分事件版本与证据版本；公共路径能否按阶段开始阅读、另存本人计划，并在改版时保留本人进度？总览、目录、概念比较、局部图、事件来源和公开路径已有实际链路。发现K01图谱登录返回、K02收藏请求恢复两个断点，K04为路径阶段往返的缺口。

**学者。** 中文译名、异名和同名人物能否区分；资料少、无头像是否仍可从真实作品开始；作者、编者、译者、章节作者是否被混为整部作品作者；关系说明是否有确认状态和来源；关注是否仅属于本人？目录、同名区分、准确出版版本和章节责任均已有代码。候选关系服务端要求原文查看与知识编辑双权限，前端不把普通登录当作候选访问资格。本轮未定位新的必然阻断，仍须实际样本验收，不能据此标通过。

**主题。** 不知道作者名字的人能否按问题、概念和分支进入；多个主题分支是否保留范围；书目、可读全文、明确计划补充是否区分；原文线索阅读后能否回到当前主题；来源撤回后是否泄露旧材料？层级、公开问题、准确版本、真实空态和关注均已有链路，但主题返回地址被Reader共享安全解析器排除，见K03。

**特别策划。** 读者能否筛文章、理解公开署名、按目录阅读、核对段落来源、提交明确署名的评论；展览能否从稳定展项进入准确PDF，图片或原文不可用时继续看导读；上一项/下一项是否保护未保存笔记？正文区块、原文抽屉、展项、评论和原Reader均已接入。本轮未新增确定阻断；公开/本人评论并发、真实来源变更、展项跳转和图像失败仍待运行，不能以有入口代替功能通过。

## 二、具体断点与最小建议

### K01 / P2 匿名“保存当前视图”在登录往返丢失当前图谱

- 图示依据：53保存当前视图，55中心/层级/关系类型与移动图谱连续探索。
- 源码：`web/components/public/graph-saved-views.tsx:131` 的匿名链接将next固定为 `/theories/graph`，仅已有 `initialSavedView` 才附 `saved_view`。而当前 `view` 含中心、深度、筛选、选中对象、模式、缩放和偏移；`theory-graph-workspace.tsx:95` 的分享已复用 `graphHref(graphParamsForView(savedView))`。
- 路径：访客从学者或主题中心展开关系、选择依据 → 保存当前视图 → 登录 → 回到无原参数的默认图谱。所操作视图没有被编码到返回地址，不能靠用户记住中心恢复。
- 最小建议：复用现有 `graphParamsForView` 和 `graphHref` 生成公开返回地址；已有saved_view恢复分支继续保留。只带公开图谱状态，不将私人标题、候选关系或会话令牌写入URL；无有效view时不声称可保存当前状态。
- 待统一验收：访客调整中心/层级/筛选/选中正式边/缩放后登录，核对同一公开视图；登录/首次注册、对象撤回和范围变更分别验证。未执行。

### K02 / P1 知识收藏的原请求标识在会话重新核验时丢失

- 图示依据：47–49收藏/返回与动作状态，53保存恢复所体现的同类恢复要求。
- 源码：`web/components/public/knowledge-node-actions.tsx:19–29` 每次session change增加epoch，并以 `node.id:owner:epoch` 重挂Actions；`unknown`只存在Actions子组件state。`save:59–85`在请求发出/异常时持有的command没有父级存储；请求还在等待时也没有跨重挂的nonce记录和离开保护。
- 影响边界：已发收藏可能由服务端完成，前端被会话核验重挂后失去原request_id，“核对原操作”入口随子组件消失。同一owner重新核验也会发生这条状态丢失。这里不推断服务端会重复写入或跨账户泄漏：`api/reading/knowledge_saves.py:receipt_for/command`仍有owner、固定请求、版本和防重放保护。
- 最小建议：复用 `graph-saved-views.tsx:18–27` 的父级owner绑定command ref与 `useUnsavedForm` 模式，在发请求前保存command/dispatched标志；同账户重验后先以原request_id查回，不能另造请求冒充重试。明确换账户后不将原命令或收藏显示给新账户；不在Web Storage保存私人状态。
- 可直接复用接口：`knowledge-actions.client.ts:knowledgeSaveRequest` 已支持requestId；`knowledge_save_views.py:49–54` GET查原回执；不需要新表、迁移或新API。
- 待统一验收：请求半途会话变化、成功回包丢失、同owner重新核验、真正换账户、删除后旧请求重到、离开/取消离开。未执行。

### K03 / P1 主题原文返回地址被共享解析器清空

- 图示依据：71“原文线索，在阅读中返回”；70–71从主题作品进入阅读后仍须知道来源主题。
- 源码：`web/components/public/topic-content.tsx:13,21,29,36` 在作品与原文线索链接写入 `/topics/{slug}/{section}?page=...` 的return_to；`reader-shell.tsx:259`统一调用 `safeResearchReturn`，而 `web/lib/api/research-navigation.ts:14–18`只允许account/research/explore/recommendations。topics不在其中，返回地址被清空；Reader约392行仅当researchReturn非空才画返回动作。
- 普通用户影响：主题的“查看完整文献”确实能开准确PDF，但Reader缺少图71要求的主题返回动作。浏览器后退或原标签仍在不等于这条产品返回链已实现。
- 最小建议：共享安全解析器显式接受公开主题路由，继续保留同站、单斜杠、反斜杠和控制字符限制；保留主题栏目/分页及合法锚点。Reader按该来源显示“返回主题”。不要改为接受任意路径，也不改变当前原文访问资格。
- 待统一验收：主题作品筛选、原文线索第2页/单条模式、桌面与手机阅读返回、主题被撤回或slug变化。未执行。

### K04 / P2 公共路径从后续阶段去阅读，缺少明确阶段返回契约

- 图示依据：59–60阶段选择、继续阅读和下一阶段；目标是让读者按路线往返。
- 源码：`public_reading_paths.py:182`产生asset/page/revision原文链接；`reading-path-materials.tsx:27`直接使用该URL，没有return_to。`reading-path-workspace.tsx:23,29,46`只在React state保存所选stage，未写入地址；`web/app/theories/reading-paths/[slug]/page.tsx:25`仅恢复action/revision/copy，没有阶段参数。重新挂载时默认第一阶段。
- 结论范围：缺少由源码明确保证的“回同一阶段/材料”路径，刷新或重新进入无法按当前地址恢复阶段。浏览器返回是否恰好保留组件，须真实浏览器验证，本报告不把未执行结果写成总会丢失。
- 最小建议：用公开稳定stage ID和材料锚点建立可验证返回地址，保留公开revision；路径页只接受当前公开快照中存在的阶段。沿现有Reader返回机制显式允许 `/theories/reading-paths/{slug}` 并显示“返回阅读路径”。私人copy仅复用已有本人校验，不暴露进度/笔记；不从阅读页数推断“完成”。
- 待统一验收：访客/跟读/私人副本在第2阶段以后打开PDF，返回/刷新/重新进入；路径改版或材料撤回时给明确回退。未执行。

K01–K03已通过协作消息交主线处理，尚未对主线修复做运行验收。前一份报告U01–U03由主线告知已修，本报告不将它们重新列为未修。

## 三、31张实际读图登记

每行均已实际打开对应view-NNN原图。下表是图示要求与静态定位，全部保留“待运行”的状态；不是31张实施页面通过。

| PDF页 / ID | 从图追问的读者目标 | 本轮源码事实与待核实范围 |
|---|---|---|
| 45 MISSING-02 | 从搜索、学科与馆藏理论开始 | TheoryOverview/knowledge.server → overview/nodes；公开空库与读取失败分开，查询/分页待运行 |
| 46 R15-main | 原词、译名、作者用法与关系能核对原文 | TheoryDetailPublicView/TheoryUsageExplorer/TheoryRelations；准确来源引用，不由人物顺序推断立场 |
| 47 R15-sub01 | 两项用法选择、替换、清空、开始比较 | selected最多2项，compare ID在URL，来源各自保留版本；K02收藏恢复，比较往返待运行 |
| 48 R15-sub02 | 学派人物/作品、争论、入门及相关区别 | tradition分支、DebateSection、TheoryRelations；旧流派映射沿规范身份，不自动同名合并 |
| 49 R15-states | 多译名、关系依据、无原文、比较与手机 | 当前公开用法与别名、缺来源说明和其他版本入口；K02，实际溢出/键盘/撤回待运行 |
| 50 MISSING-05 | 搜索子学科、看精选和全部 | SubdisciplineListView以published和既有SearchService筛选，未发布不填示例 |
| 51 NEW-T02 | 按问题进入理论、人物来源、核心文献与路径 | SubdisciplinePublicView；准确版/原文分开、关联依据及文献分页，失效/分页重试已有 |
| 52 R17-main | 从局部关系/列表查看方向与依据 | TheoryGraphWorkspace/GraphInspector → LocalTheoryGraphView/build_public_graph；公开依据和候选分开 |
| 53 R17-sub01 | 改中心、深度、视图并保存/分享 | GraphCanvas、GraphSavedViews、graphParamsForView；K01，缩放与触屏/保存恢复待运行 |
| 54 R17-sub02 | 目录展开、选择详情、原文与上一级 | TheoryDirectory/TheoryDirectoryView；公开层级、选中条目失败/空态、移动Dialog |
| 55 R17-states | 少关系、大范围、取消及候选权限 | graph生成号/Abort/30秒超时/保留已读范围；候选须明确权限，不以普通登录开放 |
| 56 R16-main | 按时间/主题/作者/事件筛选，打开真实作品 | TheoryTimelineWorkspace/TimelinePicker/timeline_publication；URL条件与事件选择，待运行 |
| 57 R16-states | 同年多事件、不确定日期、独立来源 | TimelineEventDetails区分subject_edition/evidence_source；相关不冒称影响；实际多事件/范围待运行 |
| 58 R20-main | 按主题/基础挑公共路径，另存计划 | ReadingPathList/reading-paths.server → ReadingPathListView；公开浏览与私人保存区分 |
| 59 R20-sub01 | 选择阶段、读指定章节并记本人进度 | ReadingPathWorkspace/Materials/usePathPersonal；准确来源、本人进度与私有副本，K04 |
| 60 R20-states | 缺材料、改版、版本比较与保留笔记 | upgrade预览/固定请求/历史修订/替代材料已接；不以页码自动完成，K04与并发待运行 |
| 62 R11-main | 通过译名/推荐/全部进入学者 | ScholarDirectory → loadPublicScholars/public_scholar_directory；真实推荐与公开档案 |
| 63 R11-states | 领域/时期/流派筛选、异名/同名/无头像 | 选择条件保留URL、同名卡保留生卒年、规范姓名和异名说明；时期按记录交叠，待样本 |
| 64 R12-main | 从学者作品/问题/时间线/关系继续研究 | ScholarProfile/ScholarContent；research_href、准确作品、来源与公开路径，不要求先登录 |
| 65 R12-sub01 | 人物资料来源、原文与关系说明能展开 | profile_sources外部HTTP(S)来源、EvidenceCurationView与ScholarRelations；真实出处待人工核对 |
| 66 R12-states | 稀疏档案、未确认关系、同名及章节责任 | public_scholars候选权限与快照贡献范围；ScholarWorkCard不会把失效章节升成整版作者 |
| 68 R13-main | 从主题问题而非学者名字开始 | TopicDirectory → loadTopicDirectory/public_topic_directory；正式主题、推荐与真实计数 |
| 69 R13-states | 层级筛选、搜索、暂无原文/重名/无结果 | HierarchyChoices最多20分支、正式快照匹配、分支并集再与其他条件相交，待运行 |
| 70 R14-main | 导读、核心问题、学者、作品与概念 | TopicProfile/TopicContent八栏目及既有栏目路由；准确版本/明确计划条目区分 |
| 71 R14-states | 原文线索阅读返回、撤回关联与资料推荐 | EvidenceCard/TopicFollowButton/unavailable_links；K03，公开来源清洗与本人关注恢复待运行 |
| 73 R18-main | 搜文章并从相关人物/材料继续阅读 | EditorialDirectoryView/EditorialRelated → public_editorial；真实公开署名，不从账户推断策划人 |
| 74 R18-states | 筛选/排序/分页/手机目录、缺图与空专题 | editorialHref保留公开条件、图片onError与真实空态；实际返回滚动位置待运行 |
| 75 R19-main | 按文章目录读段落、查看上下文和准确引用 | RecommendationIssueView/IssueBlockView/EditorialSource；原文抽屉重验SharedCitation，返回文章 |
| 76 R19-states | 原文抽屉、不可用来源、知识注释和评论 | ArticleComments绑定准确公开修订与明确同意；公开/本人/审核接口分权，异步及并发待运行 |
| 77 X03-main | 从章节挑稳定展项、进入原版PDF | exhibits/ExhibitionBody/EditorialReader；稳定ID，manifest对文件/正文/出版版本逐项核对 |
| 78 X03-states | 上下展项、缺图/原文、设置和本人笔记 | selectedExhibit失效提示；ReaderShell嵌入沿离开保护，useReaderNavigation保留exhibit并更新page；真实手势/保存待运行 |

## 四、接口、数据和权限事实

- 公开理论总览/节点/目录/图谱/时间线/路径分别沿 `theory_system_views.py`、`theory_directory_views.py`；相应公开视图使用AllowAny。图谱是局部查询，选择中心/范围错误有明确不可用状态，前端有30秒超时与取消。未知中心不应换成另一对象伪装成功。
- 图谱候选通过 `services/theory_graph.py` 独立授权。学者候选通过 `services/public_scholars.py:_candidate_relations`；明确请求仍须原文查看与知识编辑双权限。候选状态不参与正式关系数量；普通读者不能因登录获得后台候选正文。
- `views.py:TopicListView/TopicDetailView/ScholarListView/ScholarDetailView`均为AllowAny。服务复用正式EditorialRevision、已核验异名、当前活动CatalogPublicationRevision、真实关系与来源，不从草稿、同名或私人记录补公开信息。学者作品沿贡献快照，不以新编辑的Contribution覆盖公开责任。
- `public_topics.py:_evidence/public_topic_detail`和`public_scholars.py:_evidence`沿已发布编排重新核对当前原文文字/身份；主题撤回关联只返回失效标识和说明。主题的反馈入口复用公开feedback，不引入新权限。
- `KnowledgeSaveView`与SourceFollows写接口只允许本人；知识收藏GET支持原request_id查回，服务端owner锁、版本、回执先行、防删除后复活均存在。K02是客户端恢复入口丢失，不能以此否定服务端已有保护。
- 阅读路径公开快照为每项保留准确edition/asset/document revision/page；`usePathPersonal`复用固定请求/回执、owner核验、升级预览与本人笔记，公共路径更新不自动改写私人副本。运行时版本变化、未知结果和多设备并发尚未验证。
- 专题沿RecommendationIssue/公开EditorialRevision与 `public_editorial.py` 投影；展项Reader再读取manifest并校验准确文件与正文，未公开原文不借其他版本。`PublicArticleCommentsView`为AllowAny；本人评论IsAuthenticated且核对owner，审核为CanPublishAuthority；公开署名和正文需明确提交，私人笔记不随评论发布。

## 五、统一验收仍需覆盖

1. 31图对应桌面/390px手机、长名称、多译名、无肖像/封面、空库、来源失效和API失败；本轮只看终稿原图，没有看实施截图或操作页面。
2. K01–K03修复后的登录/注册/会话核验往返，K04所选阶段/材料的刷新与返回。保持安全返回白名单，不扩大公开访问或在URL中放私人资料。
3. 学者同名、整版与章节作者/编者/译者、规范学者与Person身份、主题分支交叠、正式关系与候选的代表性真实样本；引用/影响内容必须人工查原文，接口返回不能证明学术判断正确。
4. 公共路径旧版/新版与私人副本、已完成进度保留、被移除材料的笔记、明确替代材料；不得通过旧修订重新公开撤回正文。
5. 专题排期、匿名署名、正文与评论修订绑定、文章变版后旧评论、回包丢失后的查回、展项前后切换和未保存笔记、图像/原文失败后的可用下一步。

无需为本批问题增加依赖、技术栈、平行资料库或模型。所列修复均可围绕现有返回地址、owner绑定命令和公共快照完成。报告交接不替代统一验收，也不升级任何图的验收状态。
