# 3.0.6 管理端架构与功能画像

2026-09-21版本边界：本文保留3.0.6基线供能力追溯。3.0.7已在工作区改为十三项直接展开的入口，并增加固定预览、推荐期、共享原文策展与学者关系；尚未公网切换。最新入口与实现/检查边界见[3.0.7交付](V3.0.7_COMPLETION_RELEASE.md)，本文不覆盖新增界面。

更新于2026-09-20。本文描述本仓库实际代码和同日运行快照，供任何AI或开发者独立审计，不需要原对话。它不是下一版设计稿，也不宣称所有操作都在生产实测。运行版本、镜像和证据边界见[当前状态](CURRENT_STATE.md)与[最终交付](V3.0.6_COMPLETION_RELEASE.md)。

## 1. 管理员究竟在管理什么

管理端与公开站是同一Web应用，管理界面在`web/app/admin`，不在Django自带Admin里。页面调用同一个Django API。PostgreSQL保存馆藏和人工决定，NAS保存文件，任务与检索服务负责派生处理，没有另一套需要同步的“后台书库”。

对管理员而言，日常工作单位是“当前作品的一个出版版本”。上传批次只是来源，PDF只是该版本的文件。没有PDF的期刊文章、报告或其他纯书目也可以单独建目。一个作品可以有多版本，不应按UploadItem或文件名猜正在编辑的对象。

| 管理员用语 | 实际对象 | 必须保留的区别 |
| --- | --- | --- |
| 作品 | Work | 跨版本共享题名、简介、类型等作品信息 |
| 出版版本 | Edition | 出版年、出版机构、标识符、贡献者、主版本及当前发布 |
| 文件与历史 | Asset、Page、DocumentRevision | PDF文件版本、稳定页标识、正文解释版本是三件事 |
| 这次整理 | CatalogingSession、UploadItem | 手工会话不伪造上传记录；来源可回查 |
| 已填写但未保存 | 浏览器表单 | 尚未写数据库；切换/退出保护不能用自动保存替代 |
| 已保存但未公开 | 工作字段或EditorialRevision | 新对象与已公开对象的保存路径不同，不是每次都新建一张“草稿表” |
| 当前公开内容 | CatalogPublicationRevision或知识对象正式数据 | 书目快照和知识发布服务不同，不能只查Edition.state |
| 建议与人工决定 | Candidate、FieldDecision、FieldLock及日志 | 建议不自动成为事实，锁优先于新机器结果 |

模型在[catalog/models.py](../api/catalog/models.py)、[ingestion/models.py](../api/ingestion/models.py)和[reading/models.py](../api/reading/models.py)。私人笔记、进度、收藏、批注不属于管理员公开编目字段，也不进入默认智能推荐上下文。

## 2. 当前导航、页面与责任

实际菜单来自[admin-shell.tsx](../web/components/admin-shell.tsx)，当前43个`page.tsx`入口的完整映射、API、兼容和测试索引继续维护在[后台能力清单](V3.0.6_ADMIN_CAPABILITY_INVENTORY.md)。下表是任务解释，不另建第二份路由清单。

| 菜单组 | 当前入口 | 主要操作及边界 |
| --- | --- | --- |
| 待办与上架 | 今日工作、上传与批次、手工编目、待办与复核、发布管理 | 多来源队列；未绑定版本的上传也保留；从记录进入准确版本进行填写、复核和发布 |
| 馆藏 | 作品、图片库、版本与文件、馆藏质量 | `library`按view切换作品/Edition/质量查询，服务端筛选计数分页；选版、补/换PDF、重新OCR；图片能回到引用对象 |
| 知识与关联 | 内容管理、学者、人物查重、学科、子学科、理论传统、主题、知识关系 | Studio解释公开内容来源；专门编辑器管理真实字段与关联；人物合并不改署名职责 |
| 公开展示 | 网站页面、阅读路径、推荐、关于书库内容、品牌与首页 | 页面入口回到Studio；阅读路径人工编排；推荐使用真实选择规则；网站设置/关于内容不使用书目发布修订 |
| 处理与服务 | 处理中心、资料来源、AI服务、检索词、语义检索、运行状态、专业自检 | 服务与任务各有时间和作用范围；查看不代表执行外部检测；普通编辑不必经过诊断页完成上架 |
| 系统管理 | 文件存储、备份、审计与统计、用户与权限、运行设置 | 存储与备份不是同一个模块；普通配置与Owner敏感能力分开；不显示密钥 |

编目工作页采用聚焦布局，窄屏导航/预览可切换。`adminTaskScope()`只是作用范围说明，不代替API权限。菜单中的锚点或query入口也不等于新的page文件。

## 3. 一本馆藏的共同工作页

三种起点复用[WorkflowEditor](../web/components/admin/workflow/workflow-editor.tsx)：

- 上传：`/admin/intake/[itemId]`，保留来源批次/上传，未建立Edition时显示等待而不是打开别的作品。
- 手工：`/admin/cataloging/new`创建真实会话，再到`/admin/cataloging/[sessionId]`。
- 维护：`/admin/library/works/[workId]?edition=...`，准确Edition是文件和发布上下文。

外层分组由[file-presentation.ts](../web/components/admin/workflow/file-presentation.ts)定义：书目信息、文件与阅读、人物及知识关联、预览与发布。底层仍有文件、作品、版本、贡献者、分类、策展等步骤，领域校验没有因分组而删除。文献类型的字段规则由[catalog/contracts/fields.py](../api/catalog/contracts/fields.py)决定，不把图书、期刊文章、整期期刊、学位论文和报告当作同一套必填框。

服务端[admin_workspace.py](../api/catalog/services/admin_workspace.py)返回身份、数据、工作流、候选、权限及能力结果；[catalog_availability.py](../api/catalog/services/catalog_availability.py)从既有记录计算PDF、全文、语义、观点和问答等独立能力，不外调、不检查私人记录。公开状态复用[publication_commands.py](../api/catalog/services/publication_commands.py)中的`catalog_publication_state()`和`catalog_health()`，前端不能重写`state === published`来判断成功。

队列由[admin_queue.py](../api/catalog/services/admin_queue.py)及[workflow_views.py](../api/catalog/workflow_views.py)查询；先构造全来源记录再分类、筛选和分页，当前仍有Python内存分类，大库扩容时须实测，不能声称所有待办都是纯SQL分页。书目列表使用服务端筛选分页，计数不是当前页条数。公开主版本的列表资格与非主版本的有效公开修订分开。

### “保存草稿”分别是什么意思

| 页面/动作 | 保存范围 | 是否跳转、何时对外生效 |
| --- | --- | --- |
| 书目顶部“保存书目修改”/快捷键 | 当前Edition工作页所有已改栏目；整页事务 | 留在当前页，返回最新edit_version与反馈；不发布 |
| “确认本节内容” | 当前栏目的显式保存与人工确认 | 不强制跳下一节，也不替其他栏目确认 |
| “保存草稿并退出” | 保存当前所有修改后前往明确的返回位置 | 只有这个退出动作主动离开；失败保留当前输入 |
| 学者、理论、主题、学科、子学科、阅读路径 | 当前对象的表单；已公开对象通过编辑修订隔离 | 通常留在原对象；首次创建学者/主题会替换为真实ID地址，不是跳到另一条记录 |
| 图片、封面或单独关联操作 | 按钮说明的图片选择/关系等独立范围 | 不隐式保存整页；有未保存输入时要求先处理；已公开对象仍需发布对应草稿 |
| 推荐策略与本期推荐 | 策略保存和本期选择是两个命令 | 预览真实候选含自动补足，明确确认才发布同一组；不是EditorialRevision |
| 品牌/首页设置、关于书库内容、运行设置 | 对应设置项或About块 | 保存即影响后续读取或运行配置；没有虚构的统一待发布草稿；部分运行项仍需重载/检查 |

整页命令是`POST /api/catalog/admin/library/works/{work_id}/edits/`，传`edition_id`、`edit_version`、`request_id`、`sections`、`confirm_sections`及`suggestions`，复用[workspace_edits.py](../api/catalog/services/workspace_edits.py)与原分节保存。过期版本409，AuditEvent保存同一请求回执，超时重试沿用原请求。共享Work草稿归属另一个Edition时拒绝混入；不是静默采用最后写入。

知识编辑主要由[editorial_read.py](../api/catalog/editorial_read.py)、[editorial_revision_views.py](../api/catalog/editorial_revision_views.py)、[editorial_revision.py](../api/catalog/services/editorial_revision.py)提供私有读取版本和If-Match冲突保护。不要假设所有旧接口都有同样的自动生成契约；修改前必须读目标view。

### 发布与结果

先保存、查看已保存内容的预览与实际差异、核对阻断/警告，再明确发布。命令接受与公开生效是两层结果。数据库事务不包含外部索引原子更新；事件/消费者失败有原任务记录和恢复入口，合法旧公开版本在新版本准备时继续服务。预览是受控私有API，不是公开URL，也不包括未保存的浏览器输入。

## 4. 智能填写是如何帮助管理员的

目标是减少逐字段填写，不是增加一个独立智能工作台。实际服务为[field_assistant](../api/catalog/services/field_assistant/service.py)、其[字段策略](../api/catalog/services/field_assistant/policies.py)、[知识表单预填](../api/catalog/services/field_assistant/editorial_prefills.py)及现有ResearchRun/元数据候选。

1. 打开字段助手读取已有结果，不隐式发起收费调用。需要新结果时明确查找；白名单内当前未保存编目信息可以作为查询条件，但不因此写入正式对象。
2. 建议展示当前值、候选、来源、依据与影响。输入改变时按字段依赖/指纹识别旧结果；异步查找完成后只读轮询回到当前字段。
3. 可预填字段先填入当前表单并可撤销，管理员可继续改；正式保存才按候选/版本/权限/人工锁重新校验并记录来源与最终值。
4. 作者、译者先核对具体Person和职责，保留其他署名；未知姓名进入已有新建/查重流程，不自动创建或合并。不能把人物ID建议当普通字符串。
5. 关系、观点或创建实体等有独立领域影响的动作仍需明确确认，不伪装成只改输入框。拒绝区分人物、版本、来源、内容等原因。

使用结果复用FieldDecision/Log、候选和AuditEvent，可追到原记录。修改后采用、移除、未分类修改分开；采纳率不等于准确率，没有依据不填成本或节时。LoRA与训练导出暂缓，现有来源记录不意味着已满足训练授权、质量或数据集规范。

前端书目助手是[field-assistant-control.tsx](../web/components/admin/workflow/field-assistant-control.tsx)，知识/策展助手是[curation-field-assistant.tsx](../web/components/admin/curation/curation-field-assistant.tsx)。审计应实际点击填写、修改、保存、重开，而非只找“采用”文字。

## 5. 封面、文件和OCR

| 能力 | 当前实现 | 管理员控制与限制 |
| --- | --- | --- |
| 上传后封面推荐 | `pipeline.py`在原件安全校验和阅读副本准备后、AI书目和整本文字/OCR前调用`prepare_early_cover_candidates`；本地PyMuPDF排序少量前页 | Worker未执行或文件未合格时显示等待；不是上传瞬间完成。只生成候选，不自动替管理员选定 |
| PDF任意页/图片/默认封面 | [EditionCoverEditor](../web/components/admin/workflow/edition-cover-editor.tsx)→[cover_views.py](../api/catalog/cover_views.py)→[covers.py](../api/catalog/services/covers.py)/media | 默认少量候选可展开、指定PDF物理页预览/选择、上传JPEG/PNG/WebP、使用默认样式；文章可不选封面 |
| 封面保存 | Edition上下文、文件指纹、Work锁、人工决定、AuditEvent回执；已公开走EditorialRevision | 不改原PDF/Page，不删除旧图；图片最多12MiB，Edge该路径允许13MiB请求开销，其他API仍2MiB |
| 推荐卡片图片 | 工作页独立折叠“为推荐卡片另选图片” | 不另选时沿用书封；不与封面选择混作一个动作 |
| 补充/替换PDF | `POST /api/catalog/admin/editions/{id}/files/`，复用[edition_files.py](../api/catalog/services/edition_files.py)和原入库/安全校验 | 不要求查找UploadItem ID；保留原件和旧阅读引用，失败不抹掉稳定版本。新文件有自己的Asset/Page，不能假称新PDF复用所有旧Page ID |
| 当前馆藏重新OCR | [EditionOcrControl](../web/components/admin/workflow/edition-ocr-control.tsx)在文件区和处理中心复用；[catalog_ocr.py](../api/ingestion/services/catalog_ocr.py)复用ProcessingJob | 已发布/未发布均可选择当前有效PDF；后台需RETRY_JOBS。同来源/请求防重复，晚到旧任务不能覆盖新来源 |
| OCR进度与恢复 | 每页结果保存后累计，2秒只读查询；识别、整理、生成阅读文件、公开更新分阶段 | 暂停/继续/取消及全库暂停分别解释；取消不删文件/已保存结果；无总数不伪造百分比，不用计时器模拟进度 |
| OCR历史呈现 | [ocr_inventory.py](../api/ingestion/services/ocr_inventory.py)、[processing_center.py](../api/ingestion/services/processing_center.py)读取当前Work/Edition及未发布名称 | 默认书名/版本、已完成/总页、剩余量、最后更新与可操作状态；页码范围和技术ID展开查看，旧任务仍可追溯 |

OCR接口不是另开一套REST服务：`GET /api/ingestion/processing-center/?ocr_edition_id=...`只读上下文；POST动作包括`start_ocr`、`pause_catalog_ocr`、`resume_catalog_ocr`、`cancel_catalog_ocr`。进度100%不等于新正文已公开。重新OCR保留同文件Page身份和私人引用，文档解释沿用DocumentRevision；文件替换与同文件重新OCR必须分开设计。

## 6. 知识内容到底上到哪里

Studio主入口`/admin/knowledge`中的页面树和对象面板说明内容来源、可编辑范围、缺失原因、草稿、编辑入口与预览；专门编辑页复用同一工作区信息。后端权威登记为[public_knowledge_control.py](../api/catalog/services/public_knowledge_control.py)，对应文档是[后台编辑—公开读取对照](V3.0.6_PUBLIC_CONTROL_MATRIX.md)。登记完整不代表实际组件已经消费字段，必须沿公开API和组件继续查。

| 对象/填写内容 | 管理位置 | 实际公开消费者 |
| --- | --- | --- |
| 学者身份、生平、机构、研究内容、代表作品/关系 | `/admin/scholars/[scholarId]`，Person与ScholarProfile不是一个ID | `/scholars/[slug]`及生平、作品、理论等二级页；`scholar-public-view`/`scholar-section-public-view` |
| 理论传统/概念/争论的名称、简介、问题、关系 | `/admin/theories/[nodeId]`及`/admin/theory-relations` | `/theories/[slug]`和理论二级组件；兼容theory-schools路由保留映射 |
| 理论时间线事件 | 理论页`?section=timeline`，默认关联当前理论；旧`/admin/theory-timeline`保留 | 理论公开时间线及复用事件的学者/主题模块，按各自关联与公开过滤读取 |
| 主题介绍、关联作品/学者/理论、路径等 | `/admin/topics/[entityId]` | `/topics/[slug]`和二级页，详情view还补入关联结果，不只读TopicSerializer |
| 学科/子学科介绍、研究问题、图片、层级 | `/admin/disciplines`、`/admin/subdisciplines` | 学科目录和`/subdisciplines/[slug]`；统计与关系来自公开对象，不是手填数值 |
| 阅读路径介绍、阶段、顺序、必读和理由 | `/admin/reading-paths?path=...` | `/theories/reading-paths/[slug]`及关联页面；人工编排，不等于Topic中的内嵌路径JSON |
| 首页推荐、自动补足与轮换 | `/admin/recommendations` | 首页指定placement的RecommendationSnapshot；预览使用同规则并签名，确认发布同一组 |
| 品牌、首页/关于内容 | `/admin/settings#public-display`、`/admin/about` | SiteHeader/Footer、首页和About；无EditorialRevision时保存直接生效 |

时间线填写的是“发生什么、何时发生、与哪个理论/作品有关、根据什么”。事件关联作品与出处作品分别选择；出处还需准确Edition、阅读Asset及实际页序，经[timeline_evidence.py](../api/catalog/services/timeline_evidence.py)校验后才生成合法Reader定位。只写书名与页码不能推定文件可读。

关系生成模块应编辑关系，统计应解释口径，推荐应编辑选择规则，不能统一变成不会生效的文本框。空模块可能是未填写、无已公开关联、资格不足或功能未适用，不能一律报“AI失败”。

## 7. 人物、媒体、服务与系统的独立责任

- 人物查重：普通编辑可查找，Owner才能合并预览/执行/记录回滚。预览以作品、版本、署名职责与公开位置解释；保留指纹、幂等、同名不同人、双学者档案、唯一关系及后续修改冲突限制。依据[person_merges.py](../api/catalog/services/person_merges.py)。合并保存与公开结果更新分开。
- 媒体库：MediaAsset原件、MediaRendition、当前/草稿/历史引用分开。上传不等于在某页使用；选图回到精确对象/版本；历史引用保护保留。依据[media.py](../api/catalog/services/media.py)。
- 处理中心：普通ProcessingJob和SemanticIndexJob在全量查询后分页，来源保留，不造第三套任务真相。对象失败可回馆藏；健康读取HealthCheckRun并标注过期/未知，重新检查是明确动作。服务连通不等于内容可靠。
- 词典/语义：专业诊断与失败样例保留，派生索引有版本和来源，不能为变绿而切活动索引或标成功。普通Admin看状态，Owner控制敏感重建/切换。
- 备份：设置中的真实BackupJob及恢复记录，不是“文件存储”的Provider列表。备份文件存在不能证明能恢复；最近生产恢复演练证据见部署说明，库中不提交备份包。
- 审计/统计：按时间范围、对象和已有记录解释，不展示私人正文，不制造准确率、节省时间或成本。
- 运行设置：按能力分开普通运行参数、敏感Provider/模型/Prompt、全局恢复。环境引用不等于向界面发送密钥。

## 8. 实际权限表

依据[capabilities.py](../api/common/capabilities.py)、[permissions.py](../api/common/permissions.py)、[ownership.py](../api/accounts/ownership.py)。表是领域摘要，每次改具体接口仍须核对其权限类和动作分支。

| 能力 | Editor | Administrator | System Owner |
| --- | --- | --- | --- |
| 上传、手工建目、编辑、候选、书目/知识发布、受控预览 | 是 | 是 | 是 |
| 撤回馆藏（上传与维护两入口） | 否 | 是 | 是 |
| 重新OCR、任务暂停/恢复/重试/取消 | 否 | 是 | 是 |
| 处理/系统导航、普通AI/检索运行配置、用户管理 | 否 | 是 | 是 |
| 人物合并、正式备份、全局恢复、活动索引切换 | 否 | 否 | 是 |
| 敏感Provider/模型/Prompt管理、角色管理 | 否 | 否 | 是 |

OCR对象进度GET允许后台人员只读，不代表Editor可发起处理；处理中心导航另有系统状态能力门槛。Owner由配置身份判定，普通Django`is_superuser`不是授权捷径。没有强制双人审批。匿名和读者不能借预览/图片接口读取草稿；私人数据仍按登录用户隔离。

## 9. 给后续AI的修改地图与风险

| 想改什么 | 先读哪里 | 不能只改哪里 |
| --- | --- | --- |
| 菜单/返回/兼容 | `admin-shell.tsx`、`admin-route-context.ts`、43入口清单 | 只改菜单文字；必须保留对象、版本、筛选及安全返回 |
| 保存与智能填写 | WorkflowEditor、workspace_edits、work_editor、field_assistant | 只改采用按钮；还要保存范围、锁、来源、冲突和重试 |
| 发布判断/队列 | publication_commands、publication_eligibility、catalog_availability、admin_queue | 只用Edition.state或只改颜色，不能忽略快照和列表资格 |
| 学者/主题/理论编辑 | knowledge-workspace、knowledge-admin、theory-system-admin、editorial读写服务 | 只改诊断页；必须到公开serializer和实际组件核对 |
| 公开模块控制 | public_knowledge_control及公开consumer | 只加一条登记就宣称模块可编辑或已显示 |
| 文件/OCR/封面 | edition_file_views、cover_views、catalog_ocr、pipeline、processing | 另造上传/任务系统；覆盖原件或重建已有Page |
| 排版/Reader | `web/styles/`、实际公开二级组件、`web/components/reader/`、reader-failure | 只看首页/横向溢出，或用隐藏内容达成尺寸检查 |

大组件和领域服务仍有复杂度，例如WorkflowEditor、theory-system-admin、knowledge-admin、catalog/models.py和ingestion/views.py。可以删改UI和退役旧实现，但须先证明调用者、实际替代与兼容范围；不能把当前代码说成理想架构，也不能以减少文件/按钮数代替任务简化。

已删除的旧UI为`field-enrichment-control.tsx`、`item-publication-control.tsx`、`metadata-review.tsx`；Git历史可恢复。旧Review写API、TheorySchool兼容来源、预览及诊断路由尚保留，不能误认为清理完成就可以删表。详细退役记录在能力清单。

当前已知边界：Work草稿跨版本保护不是多分支协同编辑；复杂人物冲突仍阻断；旧复杂JSON契约未全部自动生成；真正外部OCR/模型的吞吐和正确性没有本次新验收；封面算法没有准确率评测；LoRA不是已开发能力。尚未进行最终源码全路由/全角色/五视口完整组合重验，不能说“全部场景已通过”。

## 10. 可直接交给另一AI的任务

> 请先读AGENTS.md、docs/GPT_ARCHITECTURE_CONTEXT.md、docs/ADMIN_ARCHITECTURE_PROFILE.md、docs/INGESTION_AND_PUBLICATION.md、docs/CURRENT_STATE.md，再按问题核对真实源码、43入口清单和单一公开控制登记。目标是让多名不懂内部术语的管理员用最简单的操作完成工作。先保持只读，分清当前实现、当前运行、历史问题、测试证据和设计推测。逐项说明用户填写什么、保存到哪里、是否离开当前页、在哪里预览、何时公开、失败后怎么恢复。不要将已修的3.0.5问题当现状，不要只改首页、菜单或样式，也不要省略手工编目、已发布维护、时间线、封面和OCR。给出可比较方案、涉及数据/API/权限、迁移与退役条件；取得明确实施授权后再改代码，不删除原件、私人数据或历史修订，不擅自换技术栈或新建第二套书库。

代码位置是导航，不是测试结果；更改后的结论必须指向本轮真实命令、响应与界面操作。生产只读核对也不能替代管理员写入或外部服务验收。
