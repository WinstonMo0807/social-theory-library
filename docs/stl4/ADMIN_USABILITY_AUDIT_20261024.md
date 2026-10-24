# 管理端无引导使用事实核验

2026-10-24。接续首页/探索及理论/学者/主题/策划报告，按用户要求的八个一级分类使用 [grilling 作者规则](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md)自行追问。本次只有一个一级分类“管理端”，不为每幅状态图重新访谈。环境与代码事实由代理查明，Ponytail full 用于选择现有机制中的最小修正。

范围严格按 `docs/stl4/ATLAS_INDEX.csv`：module 的实际值为“管理端”，80–179页，共100张，含136页替换图 NEW-A16。每张均实际用 view_image 打开唯一 final-r2 PDF 提取原图 `tmp/pdfs/stl4-full-review-20261024/view-NNN.*`；136为PNG，其余99张为JPEG。没有使用CSV的旧image_path、旧总览或其他图片。图中数量、书名、百分比、成功状态均是设计示例，不作为系统已有数据或业务成功证据。

本子任务只新增本报告，不修改业务源码、其他记录或提交。没有运行测试、构建、浏览器、业务请求、上传、备份、恢复、评测、迁移或生产操作。行号是审计快照，主线并行修复可能改变行号或实现；以下“已定位”及“图已读”均不等于正式交互、权限、设备或视觉验收通过。

**交接更新。** 四项A01–A04已由主线保存为`ac9d1f3`，不是仍待开发的缺陷。本子任务定点回读已看到：存储按owner保存非秘密原命令并显式按原编号核对/继续、未知owner/超时回执保留；手工/收件接入useUnsavedForm及已保存基线；导航按最具体路径归组；文件页安全return_to与真实列表回退。主线报告目标ESLint 0错误/3条既有img警告、TypeScript noEmit退出0；这些检查由主线运行，本子任务未重新运行。下文保留初始触发路径与行号供统一验收追溯，**A01–A04状态均为源码已修、静态检查已记录、运行与视觉待统一验收**。回收恢复、人物归并跨刷新和共享选书离页三项由主线继续接修，本报告不提前认定完成。

## 一、管理这一分类的一轮追问

1. **第一次进后台，能否找到下一步？** 今日工作可按状态、任务类型、责任人和时间筛选；收件与编目、馆藏、处理、策划、知识、发布及维护分别有入口。初查发现“运行维护”的实际地址与active分组不一致，A03已由主线修正，待运行。
2. **拿到一批PDF，是否能区分传输、识别、身份核对和发布？** 上传沿原分片/R2服务，批次预约按本人和固定request_id；识别状态来自原任务。收件确认独立决定现有版、新版或新作品，完全重复可以复用；不会仅凭同名自动合并。未知预约可查回，正式发布另行确认。
3. **没有PDF，或只有单篇文章，是否能先准确建书目？** ManualCatalogForm及原Work/Edition/CatalogingSession链路已接，文章卷期/起止页、章节容器和责任角色有真实字段。初查的未保存表单及收件选择离页缺口A02已由主线修正，待运行。
4. **修改是否影响唯一原件、人工决定和读者旧引用？** 文件服务先保存不可变original，再准备阅读副本；新增/替换/采用分开，采用有版本和当前文件核对。目录、页码、OCR均保存修订和来源身份，候选采用不同于自动提取。人工字段和正文受保护。此处没有证据可声称任意文件、任意原文定位均已经正确。
5. **任务失败或断网，能否从已保存工作继续？** 处理中心沿既有任务和检查点，有固定命令回执、暂停/继续、失败范围、结果和明确恢复入口；不将心跳超时等同于可立即接管。存储页原先的待定请求跨刷新缺口A01已由主线修正，待运行。回收恢复和人物合并同类边界由主线续修，见后文。
6. **不知道后台术语的人，能否从发布阻断回到具体修改，再回同一检查？** 发布检查已有真实草稿iframe、版本/来源指纹与阻断提醒，发布按钮等待预览ready。文件页原先丢失检查返回上下文、默认返回地址不存在的A04已由主线修正，待运行。
7. **普通管理员是否会误获馆长权限或读者私人内容？** 能力由服务端定义；RUN_BACKUP、MERGE_AUTHORITY等仍是馆长范围，不应因图中有按钮就对普通管理员开放。账户管理先预览能力差异，再以目标版本与预览hash确认；不读取旧密码。管理引用影响与回收关系不应借维护理由暴露私人笔记正文。
8. **“备份成功”“恢复演练”“恢复上线”是否清楚分开？** 存储源码将备份生成、归档校验、隔离恢复清单及签名演练记录区分。界面没有执行生产恢复或清理入口。缓存候选扫描与可执行清单尚未接通，页面明确说明，不能登记为清理已完成。
9. **选书编排时是在改本页，还是改全馆资料？** 本页推荐理由、展示字段、内部收获及分组在EditorialRevision中；准确版本仍引用同一馆藏。修改公共题名/作者转原馆藏。选书临时清单的返回/刷新保护仍有缺口，列入待补。
10. **质量评审是否可以拿服务连通或模型自评冒充？** 不可以。170–172图表达人工真值、原文对照及基线/候选区别；`QUALITY_REVIEW_20261023.md`已记录D010禁止本轮新建第三步评测页。既有评估仅保留定位，本轮未执行，也不因读图重启评测开发。

## 二、四项优先断点与最小修正

### A01 / P1 存储待定请求无法跨刷新或同账户重挂查回

- 图示依据：161–163，备份/校验请求结果须核对，失败可继续，不能把未确认响应当作任务没创建。
- 源码证据：`web/components/admin/storage-workspace.tsx:51,57,61–84`的unresolved、pending与request_id只在state/ref中。StorageWorkspace在43–45行收到session变化便按epoch重挂。POST有30秒deadline，同一挂载可按原values重发；组件没有待定请求会话记录、回执读取或离页保护。共享`usePersistentWorkspace`的operation也明确只存内存，并在identity/session变化时清除。
- 触发路径：发起备份/校验 → 响应中断或超时 → 刷新/同账户重新核验 → 原编号丢失 → 再按发起操作产生新编号。服务端可能已登记原任务；这是一条重复发起和无法确定结果的路径，不代表每次超时必然重复。
- 已有保护：`api/distribution/storage_workspace.py:196–254`在账户锁中重查会话/能力，以request_id、发起者和范围验证备份回执；274–287行对校验同样去重；计划使用AuditEvent和版本检查。问题在客户端恢复范围，不应撤掉服务端保护。
- 最小实现：复用本项目`useCatalogCommand`/`useUploadReservation`模式，在发送前按owner保存最少的请求编号、操作类别及必要对象身份，不能保存备份绝对路径/归档内容。服务端补按当前owner查回已登记操作的只读回执；计划、备份、校验各读取既有记录。不应只凭404便宣布未执行。若提供停止未执行请求，必须与执行采用同一领域锁和取消墓碑；这部分不能只做前端清除按钮。未查清前冻结新写入，离页明确提醒。换账户不展示或重发前账户操作。
- 待统一验收：返回响应前断网、提交后刷新、同owner重新核验、明确换账户、同编号不同范围、两个标签并发、排队/运行校验去重；核对只出现预期任务并能找回确切结果。未执行。

### A02 / P1 手工编目与收件未保存输入可直接离页丢失

- 图示依据：85–90，延期继续、手工长表单、保留已填信息与恢复。仅未提交输入的保护与已发送请求防重应分别实现。
- 源码证据：`web/components/admin/workflow/manual-catalog.tsx:39–55`把draft、责任者、版本选择存在React state，55行“取消”是直接Link，57行还有收件面包屑；整个组件未使用`useUnsavedForm`。`intake-confirmation.tsx:31–46`的choice/picked同样只在state，46行直接返回批次；也未接离页保护。两者已有的`useCatalogCommand`仅持久化已经发送的request_id，不保存未提交表单。
- 影响：普通管理员填完文章卷期、责任角色或重复身份决定后，经导航查看其他对象/返回批次，可丢失尚未保存的信息；不需要接口失败才触发。此处没有证据表明已成功保存的服务器草稿丢失。
- 最小实现：沿用`web/lib/use-unsaved-form.ts`，以规范化表单与当前saved/empty、choice与服务器draft的差异计算dirty。保存成功更新基线，取消离开时说明放弃输入；保存后continue/defer/confirm内部跳转明确放行。待定命令仍先查回，不以dirty=false解除请求恢复锁。不能把带个人资料的整张表单写入localStorage以替代保护。
- 待统一验收：普通链接、取消、返回批次、浏览器刷新/关闭、保存失败后导航、保存成功继续、确认成功跳转；额外核对浏览器历史返回。现有hook只拦anchor click和beforeunload，不能仅接hook便宣称所有程序跳转/popstate已保护。

### A03 / P2 运行维护首页落入“文件与处理”导航组

- 图示依据：158–172，管理员应从运行维护继续进入服务、存储、备份、回收与反馈等明确入口。
- 源码证据：`web/components/admin-shell.tsx`的navigationGroups将“运行维护”href设为`/admin/processing/status`，其paths却未包含该地址；“文件与处理”paths为`/admin/processing`。render用`entry.paths`前缀计算active，且只在active时展开children。因此点击运行维护到达canonical status路由后，会展开文件与处理子导航，运行维护子导航不展开。
- 最小实现：让运行维护显式拥有canonical status/health等系统子路由，同时从文件与处理active判定排除这些系统地址。以最长且明确的归组匹配保证一个主要active；不更改能力检查或后台API授权。旧status/system-health/settings地址与redirect仍应保留原参数。
- 待统一验收：桌面和手机从运行维护进入状态→存储/备份/回收，直接深链和旧入口重定向、带query、无对应权限时的锁定表现。未运行。

### A04 / P2 文件页默认返回地址不存在，发布检查返回上下文未使用

- 图示依据：95–98文件往返，131–137从发布检查修正问题后回到同一对象。
- 源码证据：`web/components/admin/library/work-files-workspace.tsx:84`将“返回版本与文件”指向`/admin/library/works?view=editions`。当前`web/app/admin/library/works/`只有`[workId]`，列表真实页面为`web/app/admin/library/page.tsx`；它把view交给WorkLibrary，正确默认目标是`/admin/library?view=editions`。已读路由配置/legacy helper未见为错误路径提供重定向，未实际HTTP请求。
- 上下文证据：`publication-review.tsx:43`使用`withAdminReturn(row.href,path)`把当前检查页放入return_to；`publication_desk.py:77–84`的PDF/OCR/版权检查指向files的准确edition/tab。目标files组件45–58行读取edition、分页和tab，却不读取return_to，84行使用固定链接。AdminShell只提供今日工作/搜索/策展特定返回，不能补上发布检查返回。
- 最小实现：文件页优先消费经`safeAdminHref`验证的return_to并使用准确标签，否则回`/admin/library?view=editions`。工作台→files、files→OCR/目录/页码等维护入口按需要保留当前对象链路；避免嵌套无限return_to。发布检查在修正完成后重新取最新版本和fingerprint，不用旧预览继续发布。
- 待统一验收：从馆藏列表进入文件再返回，从发布检查的PDF/OCR/授权项进入files并回检查，准确edition和tab保持，外部/非法return_to回安全默认页，修订变动后重新检查。未执行。

四项已逐条通知主线，并已由主线修正保存于ac9d1f3。本节是发现快照，不将源码修改或静态检查视为运行通过；当前实施状态见报告开头交接更新。

## 三、确认可复用的调用链与保护

下列是本轮重点打开或定点读取的源码。其余图的源码对应点见逐图表，未逐个执行，也没有把历史文档的“已实现”直接升级为实测。

| 环节 | 实际源码与关键位置 | 证据与边界 |
|---|---|---|
| 入口/会话/能力 | `web/components/admin-shell.tsx`的navigationGroups、canViewRoute、会话跳转；`api/common/permissions.py`的RequiresCapability；`api/common/capabilities.py` | UI能力只影响展示；API仍检查当前权限。备份/人物合并不应向普通管理员擅自开放。A03不需要改权限模型。 |
| 今日工作/馆藏 | `web/components/admin-dashboard.tsx`的WorkRow、AdminDashboard；`work-library.tsx`的URL筛选、versionsHref | 下一步和return_to已有机制。列表真实入口是/admin/library。实际队列内容、空库及筛选正确性待跑。 |
| 上传/预约 | `admin-upload.tsx`的contentFingerprint、addFiles、recoverReservation、upload；`use-upload-reservation.ts`；`api/ingestion/upload_workspace.py`的owner、UploadWorkspaceView、UploadBatchReceiptView | 账户+内容摘要恢复；批次范围与本人回执；上传完成不等于识别完成。未上传真实文件，非安全上下文等降级待运行。 |
| 收件身份 | `intake-confirmation.tsx`的IntakeBody、run、recover；`api/ingestion/intake_confirmation.py`的actor_for、version、candidates、post、receipt | 同名与完全重复分开；new_work/new_version/use_edition由管理员明确选择；目标版本和请求内容指纹受检。A02初查未保护未发送输入，现已补离页提醒，待运行。 |
| 先建书目 | `manual-catalog.tsx`的ManualBody、save、accept；`api/catalog/manual_catalog_views.py`的ManualCatalogView、receipt、ManualCatalogReceiptView | 原Work/Edition/Session，不建另一份库；目标版/手工会话按owner和版本；明确选择人物或新建。已保存版本不等于已发布。 |
| 元数据/并发 | `workflow-editor.tsx`的OwnedWorkflowEditor、保存/差异/exit及returnHref；`catalog-edit-diff.tsx`；`api/catalog/editorial_read.py`的编辑版本防护 | 字段锁、候选与人工决定既有服务继续保留，409不自动覆盖本地输入。候选采用不能悄悄更改锁定值。 |
| 文件 | `work-files-workspace.tsx`的Workspace、generate；`work-file-actions.tsx`的上传/采用对话框；`api/catalog/services/edition_file_intake.py`的_submit_file、prepare_reader_input | 先保存original且不覆盖；补充/替换/生成阅读副本分别有身份。仍须核对真实存储与并发事务，A04是导航问题。 |
| 媒体 | `media-workspace.tsx`的WorkspaceEditor、accept、save；`api/catalog/media_workspace_views.py`的MediaWorkspaceView、receipt及ReceiptView | 当前slot、edition、version与来源信息有契约；已有会话请求编号/回执可复用。上传入媒体库不自动公开。 |
| 处理与恢复 | `processing-workspace.tsx`的execute、commandFeedback；`api/ingestion/processing_workspace_views.py`的ProcessingWorkspaceView/ReceiptView；`services/processing_recovery.py`的recovery_state、recover_processing_task | 固定原请求、任务版本与能力；未知命令先查回。心跳/租约必须结合原队列身份，不能凭“过期”直接重复执行。主线还在改相关源码。 |
| OCR/页码/目录 | `ocr-workspace.tsx`、`page-mapping-workspace.tsx`；`outline_views.py`；`services/document_outline.py`的extract_outline、edit_outline、adopt_outline、public_outline | 来源修订、人工文字、准确PDF几何和原件保护。目录needs_review/旋转问题已由主线修正，不再列作未修；真实多栏/扫描样本仍待统一验收。 |
| 索引 | `index-maintenance.tsx`的Maintenance及useCatalogCommand；`api/catalog/index_maintenance_views.py`；旧`semantic-index-admin.tsx` | 新维护面与旧评估分开。来源/词法/向量状态不混为质量分数；切换沿权限与版本。没有执行基准或索引操作。 |
| 预览/发布 | `publication-review.tsx`、`publication-ledger.tsx`；`api/catalog/services/publication_desk.py`的review_details/desk；`services/publication_commands.py`的prepare_revision、activate_revision、rollback_revision | 真实草稿iframe、相应版本/fingerprint、仅书目与全文模式分开；旧正式修订不因新稿处理失败消失。待定发布载荷有会话保留，仍需实际原子性/并发核验。 |
| 规范人物 | `person-resolution-workspace.tsx`的MergeReview、RecordReview；`services/person_merges.py`的prepare_person_merge、merge_people、rollback_person_merge | 人工确认+preview fingerprint+馆长能力，原身份保留，撤回需要新状态核对。下面列出客户端跨重载恢复边界，不推断后端会误合并。 |
| 账户 | `accounts/account-workspace.tsx`的Editor；`api/accounts/user_management_views.py`；`user_management.py`的preview/command/lookup | 能力差异、目标expected_version、preview_hash与请求编号；密码只在内存、回执不含密码。旧会话撤销与权限变化仍待真实双账号核验。 |
| 存储/恢复 | `storage-workspace.tsx`；`api/distribution/storage_views.py`；`storage_workspace.py`的storage_command、write_restore_report；`backup_integrity.py`的verify_archive | 备份/校验/演练分离，原归档完整性与路径约束保留。当前无生产恢复和缓存删除入口；A01只解决恢复信息，不代替执行权限。 |
| 回收 | `recovery-workspace.tsx`的ObjectDetail/restore；`api/catalog/recycle_workspace.py`的detail、confirm_restore | 账户/版本/依赖+原request_id回执；恢复原身份为草稿，不自动恢复公开。读取管理关系有界，不能借恢复查看读者私人内容。 |
| 网站/编排 | `use-site-content.ts`的persist/recover；`placement-workspace.tsx`的change/act/recover；`placement-catalog-picker.tsx`的add/finish | 原EditorialRevision、原公开投影和真实来源；本页文案与全馆书目分离，internal_goal不应公开。选书临时state另有离页缺口。 |

知识编辑、专题编辑/选材、时间线和阅读路径继续沿上一批已追踪的原编辑器与publication服务，不复制第二套关系/馆藏/任务。对应近期记录包括 `CATALOG_EDITOR_20261023.md`、`INTAKE_CONFIRMATION_20261023.md`、`MANUAL_CATALOG_20261023.md`、`STORAGE_BACKUP_20261023.md`、`RECOVERY_WORKSPACE_20261023.md`、`QUALITY_REVIEW_20261023.md`、`CONTENT_PLACEMENT_20261023.md`。本轮定点重读了后六份相关边界，不能把其中历史静态结果当作本轮重新运行。

## 四、100张实际阅读登记

每行的“图中事实”仅说明该张终稿要求；不是实现截图或数据核验。所有行的运行/几何状态统一为**待统一验收**。路径中的NNN为该行页码，136使用png，其余使用jpeg。

| 页 | ID | 实际原图所见与必须保留的流程事实 | 源码对应/审计边界 |
|---|---|---|---|
| 80 | M01-main | 今日工作按待办类别、所有者、状态、类型筛选；逐条继续处理。 | admin-dashboard；真实队列待核。 |
| 81 | M01-states | 无待办、无权限、加载失败有明确下一步，不填示例任务。 | AdminDashboard、AdminShell。 |
| 82 | M02-main | PDF批量收件，上传与识别分阶段；批次名、文件选择、状态表。 | AdminUpload、UploadBatchView。 |
| 83 | M02-sub01 | 批次详情与恢复；已完成文件仍可继续编目，暂停/失败分开。 | upload-workspace、预约回执。 |
| 84 | M02-states | 不支持/超限/部分失败/重复材料有逐项处理，不全批重做。 | addFiles、失败行与重试；未真传。 |
| 85 | M03-main | 原文件与候选对照，明确使用已有版、新版或新作品。 | IntakeBody、IntakeConfirmationView。 |
| 86 | M03-sub01 | 同名不同书、原文与译本、内容完全重复需分别决定。 | candidates、目标版本、原件hash。 |
| 87 | M03-states | 无候选、候选不确定、处理中、失败可保存或延期。 | run/recover；A02。 |
| 88 | M04-main | 先建书目，材料类型、责任者和版本分组；保存与继续补文件。 | ManualBody、ManualCatalogView。 |
| 89 | M04-sub01 | 单篇文章有期刊、年卷期、页码、DOI，责任角色明确。 | ManualForm字段契约；未保存。 |
| 90 | M04-states | 无封面不妨碍草稿，重复提醒/失败保留当前输入。 | manual-catalog；A02。 |
| 91 | M05-main | 并列编辑栏目与作品/版本侧栏，当前草稿与公开状态分开。 | OwnedWorkflowEditor。 |
| 92 | M05-sub01 | 题名、作者等字段有来源候选与人工编辑，预览对应当前对象。 | WorkflowSectionBody/助手。 |
| 93 | M05-sub02 | 多窗口比较最新与未保存修改，逐项选择合并。 | CatalogEditDiff、编辑版本检查。 |
| 94 | M05-states | 未保存、冲突、无权限/失败不伪装成功，输入可继续。 | WorkflowEditor；真并发待核。 |
| 95 | M06-main | 出版版本、原件、阅读副本、公开状态分别管理。 | WorkFilesWorkspace；A04。 |
| 96 | M06-sub01 | 补充与替换预览，明确保留旧文件并说明影响。 | UploadWorkFileDialog、_submit_file。 |
| 97 | M06-sub02 | 历史文件及引用影响可看；不自动把旧引用改绑新文件。 | WorkFiles影响/历史；权限待核。 |
| 98 | M06-states | 无文件/处理中/失败时仍能管理书目，旧可用版继续服务。 | 文件任务/采用状态；未运行。 |
| 99 | M07-main | 字段助手逐字段显示当前值、候选、依据和采用选择。 | MaterialAssistant、FieldAssistant。 |
| 100 | M07-sub01 | 单字段差异与人工锁；只重生指定候选，不覆盖人工决定。 | workflow与field_decisions。 |
| 101 | M07-states | 无模型/无证据/低质量OCR仍可人工填写，不编造补全。 | 助手错误/来源契约待跑。 |
| 102 | M08-main | 封面用途、来源、许可、说明和当前/历史图分开。 | MediaWorkspaceEditor。 |
| 103 | M08-sub01 | 从准确PDF页选图后才准备候选，不以错误文件页代用。 | preparePdf、media_workspace_views。 |
| 104 | M08-sub02 | 裁切/旋转/比例、历史封面恢复与多用途影响。 | transform/version/slot核对。 |
| 105 | M08-states | 无封面/图片失败/权限不足有明确状态，缺可选图不硬阻断。 | media dirty/conflict/receipt。 |
| 106 | M09-main | 任务按类型/阶段/状态列真实进度、结果与失败。 | ProcessingWorkspace。 |
| 107 | M09-sub01 | 详情、日志、安全暂停/继续与失败范围，保留完成结果。 | execute、原processing服务。 |
| 108 | M09-states | 空队列/服务不可用/中断待核，不虚构ETA或假完成。 | recovery_state；主线并行完善。 |
| 109 | M10-main | 原页、当前文字和人工修订对照，按实际物理页。 | OCRWorkspaceView。 |
| 110 | M10-sub01 | 问题页逐项核对/重试，人工文字与已核验页受保护。 | OCR run/review/prepare。 |
| 111 | M10-states | 无文字、低质量、识别中/失败及权限限制分别提示。 | OCR来源身份/任务状态。 |
| 112 | M11-main | 原生/目录页/正文候选与当前已采用目录分开。 | extract_outline、outline_state。 |
| 113 | M11-sub01 | 同一页多个节点须正确相对落点，不全落页首。 | 几何验证；主线已接修正。 |
| 114 | M11-sub02 | 候选审核、人工修订、历史恢复显式采用。 | edit_outline/adopt_outline。 |
| 115 | M11-states | 缺书签、异常候选、无文字时需要人工复核，不承诺全书正确。 | needs_review已由主线修；未真样本。 |
| 116 | M12-main | 印刷标签与物理页分开，分段校准并预览影响。 | PageMappingWorkspace。 |
| 117 | M12-sub01 | 罗马前言、多段重编号、双页扫描和缺页显式记录。 | page_mapping；不虚造物理页。 |
| 118 | M12-states | 未确认/冲突/无可解析页有下一步，采用与发布分开。 | source fingerprint/修订；待跑。 |
| 119 | M13-main | 词法、语义、原文覆盖分别显示，明确为何搜不到。 | IndexMaintenance。 |
| 120 | M13-sub01 | 增量任务/候选索引/旧版切换有明确对象与进度。 | Index命令/版本；未切索引。 |
| 121 | M13-states | 无原文、未入索引、维度不符和服务失败不能都显示正常。 | 警告/状态；真实服务待核。 |
| 122 | M14-main | 策划项目/文章、负责人、团队、草稿/公开/归档。 | CurationProjectWorkspace。 |
| 123 | M14-states | 空项目、无权限、来源不足有明确继续动作。 | 项目权限；未实际创建。 |
| 124 | M15-main | 专题结构块可编辑/排序/插入，正文与准确来源分开。 | RecommendationIssueEditor。 |
| 125 | M15-sub01 | 文本、人物、概念、比较、时间线等结构块有明确选择。 | issue editor/原区块服务。 |
| 126 | M15-sub02 | 断线草稿/多人冲突保留本地与远端区别。 | useIssueDraft、DraftConflict。 |
| 127 | M15-states | 未保存/保存失败/来源失效不悄悄发布或清掉输入。 | issue版本/原回执；待跑。 |
| 128 | M16-main | 从同一馆藏按准确版本选材，智能建议有依据。 | IssueSelectionWorkbench。 |
| 129 | M16-sub01 | 每项证据可核正文、采用修改后采用或忽略。 | issue-source-picker/assistance。 |
| 130 | M16-states | 无证据/模型失败/部分完成保留已选材料与结果。 | 助手结果/取消边界待核。 |
| 131 | M17-main | 真实草稿预览与当前公开版分开，有检查清单。 | PublicationReview、WorkPagePreview。 |
| 132 | M17-sub01 | 阻塞项定位准确修改，再返回原检查，不只泛化错误。 | withAdminReturn；A04。 |
| 133 | M17-states | 未保存先保存，检查失败不显示完成，旧公开版保留。 | preview ready gate；未执行。 |
| 134 | M18-main | 发布对象、当前稿/公开版和历史、撤回分别明确。 | PublicationLedger。 |
| 135 | M18-sub01 | 撤回/恢复历史有影响确认，不直接重写旧历史。 | rollback_revision、版本检查。 |
| 136 | NEW-A16 | 最新替换图：版本差异、关联内容、PDF/OCR/定位/索引/授权检查。 | review_details；136.png实际已读。 |
| 137 | M18-states | 仅书目/全文模式、失败/权限/撤回有准确状态。 | publication mode及回执。 |
| 138 | M19-main | 人物规范名、异名、身份来源与状态供核对。 | PersonAuthorityWorkspace。 |
| 139 | M19-sub01 | 原文名/译名/标识/角色和内部说明分开。 | person_authority；实际同名待核。 |
| 140 | M19-sub02 | 归并前比较证据、方向及受影响引用，不按相似度自动合并。 | MergeReview、prepare_person_merge。 |
| 141 | M19-states | 同名保留独立、证据不足与合并冲突有动作。 | 仅馆长merge；跨重载待补。 |
| 142 | M20-main | 学者公开稿/草稿、人规范身份及作品/关系来源清楚。 | ScholarEditorFrame/原publication。 |
| 143 | M20-states | 无头像/资料少可继续草稿，未确认关系不冒充事实。 | 既有学者记录；未实测。 |
| 144 | M21-main | 理论概念、原文用法、来源和关系可编辑。 | KnowledgeNodeEditorFrame。 |
| 145 | M21-sub01 | 关系类型、方向、准确原文及确认状态逐项明确。 | relation_editorial；未实际采用。 |
| 146 | M21-states | 无证据、术语异名/冲突需人工核对，不自动合并。 | 候选/编辑权限边界。 |
| 147 | M22-main | 主题/学科树、材料选择、排序和公开预览。 | TopicEditorFrame/组织字段。 |
| 148 | M22-states | 防循环、同名提醒、空材料/权限失败保留编辑。 | TopicOrganization；运行待核。 |
| 149 | M23-main | 时间线事件、主体/出处与日期精度可编辑。 | timeline_editor、详情组件。 |
| 150 | M23-sub01 | 年/范围/不确定日期、主体版本与证据版本分开。 | date precision/subject edition。 |
| 151 | M23-states | 出处不足/日期冲突不虚造精确日期，保存为待核。 | 事件修订/发布服务待跑。 |
| 152 | M24-main | 公共路径按目标/阶段/材料安排，准确阅读入口。 | PathEditorFrame/ReadingPathWorkbench。 |
| 153 | M24-sub01 | 先修与相关关系分开，阶段顺序/循环需说明。 | ReadingPathDependencies。 |
| 154 | M24-states | 无材料/先修冲突/候选失败可人工继续，私人计划不被改写。 | reading_paths/原publication。 |
| 155 | M25-main | 账户、角色、能力说明及列表真实状态。 | AccountWorkspace、管理API。 |
| 156 | M25-sub01 | 角色变更前比较新增/保留/失去的能力及登录影响。 | preview_hash/expected_version。 |
| 157 | M25-states | 无权限只读、冲突/会话变更先核对，不绕过鉴权。 | CanManageUsers、owner/session。 |
| 158 | M26-main | 本地模型/外部服务、检查时间、任务与失败分开。 | local-services、系统状态；A03。 |
| 159 | M26-sub01 | 能力不可用说明缺什么，保留人工流程。 | backoffice服务状态；主线并行。 |
| 160 | M26-states | 未检查/失联不显示绿灯，连接成功不等于质量通过。 | 时间/状态契约；真实服务未测。 |
| 161 | M27-main | 存储位置/登记文件/备份状态，真实用量与未知值。 | StorageWorkspace、storage_snapshot；A01。 |
| 162 | M27-sub01 | 备份历史、归档校验与隔离恢复准备分开。 | storage_command/write_restore_report。 |
| 163 | M27-states | 低空间/目录断开/失败/无演练分别提示，清理先核影响。 | 无可执行清理；实际备份未跑。 |
| 164 | M28-main | 回收与归档、依赖及历史，恢复原身份。 | RecoveryWorkspace。 |
| 165 | M28-sub01 | 恢复前看依赖缺失与冲突，其他对象需分别处理。 | detail/confirm_restore。 |
| 166 | M28-states | 恢复受阻不强行公开，无记录/无权限有下一步。 | 草稿恢复；回执跨重载待补。 |
| 167 | M29-main | 网站/关于/首页公共说明按草稿与当前公开分开。 | SiteWorkspace、useSiteContent。 |
| 168 | M29-sub01 | 首页槽位从已公开策划/学者/主题选择并排序。 | SiteHomePicker；不自动发布来源。 |
| 169 | M29-states | 来源撤回/缺图/空槽与并发保存有具体反馈。 | site-content回执/冲突；未跑。 |
| 170 | M30-main | 检索与智能质量评审是人工真值与改进对照。 | D010边界，非普通读者反馈。 |
| 171 | M30-sub01 | 样本标注与原文对照，不靠模型自评分。 | 旧search_evaluation定位，未执行。 |
| 172 | M30-states | 缺标注、不再可比/过期/退化需明确，不虚报通过。 | 不新建第三步评测页，不跑基准。 |
| 173 | M31-main | 文字清单、当前条目、读者预览三栏，分组排序。 | PlacementWorkspace。 |
| 174 | M31-sub01 | 多选跨组移动、撤销/恢复仅改引用与顺序。 | move/undo/redo/重复检查。 |
| 175 | M31-sub02 | 本页推荐理由与全馆题名作者影响分开。 | patch、来源编辑跳转。 |
| 176 | M31-states | 未选择、多选、拖放、未保存/未发布/公开、手机操作均清楚。 | 编排dirty已保护；几何未验。 |
| 177 | M32-main | 共用馆藏搜索筛选，已选清单/分组/对外理由/内部收获。 | PlacementCatalogPicker。 |
| 178 | M32-sub01 | 选择准确版本与阅读落点，清单重排并返回编辑页。 | add/finish；临时清单待补保护。 |
| 179 | M32-states | 无结果、重复、仅书目全文未核实、版本不清须准确处理。 | public_eligible/reader_url gate；待跑。 |

## 五、其余已确认边界与尚未证实事项

- **回收恢复和人物归并的跨刷新恢复，主线续修。** 初查`recovery-workspace.tsx`的ObjectDetail/restore（原58–80行）unknown/pending只在state/ref；触发顺序为进入已删除对象→预览确认恢复→提交后响应中断→刷新或同owner会话重挂→原编号/查回入口丢失。服务端`recycle_workspace.py:205–224`已有准确回执且不会把旧编号用于后来重新删除的对象。人物对应`person-resolution-workspace.tsx`的MergeReview/submit（原140–164行）：馆长选择来源与目标→核对预览→确认合并→响应中断→刷新同一来源/目标→attempt丢失，原请求重试入口不再保留；后端`person_merges.py:246–269`仍验证idempotency与preview fingerprint，历史可供核对，不推断服务端错误重复合并。主线已接续修复，报告落地时未正式运行，不将并行编辑中代码计完成。不得通过清掉本地unknown声称已撤销服务端动作。
- **共享选书临时选择离页保护，主线续修。** 初查`placement-catalog-picker.tsx`的PlacementCatalogPicker（18/37行）selected在子组件内，“返回编辑页面”直接onCancel；其内部没有useUnsavedForm。父`placement-workspace.tsx`的WorkspaceBody（43–45/62行）dirty只比较已经进入父draft的items。触发顺序为打开无未保存修改的编排页→从馆藏选择书目→加入一个准确版本→填写本页推荐理由/内部收获→未点“完成选择并返回”即点“返回编辑页面”→重开选书，临时选择与文字消失；父dirty也无法保护此时刷新/普通导航。建议取消有选项时明确确认，或按owner在父内存暂留临时清单并计入dirty；不把内部收获落到URL或本地持久化。主线已接续修复，未运行验收，不要求另建选书系统。
- **M30是已记录决策边界。** 本轮实际查看170–172，并回读`QUALITY_REVIEW_20261023.md`和`DECISIONS.md:D010`。当前`/admin/processing/semantic-index`默认IndexMaintenance，`legacy=1`才渲染旧SemanticIndexAdmin。旧组件调用search-evaluations，不代表已经覆盖本轮Discovery全部方案；本轮不接新评测界面、不重新检索质量基准、不运行模型。普通反馈在`/admin/support/feedback`，不能把它当作170–172已完成。
- **存储清理与恢复演练未执行。** 页面110行明确写缓存扫描/可执行清单未接。原件、OCR成果、已用媒体/模型/活动索引不得仅按文件类型清除。恢复清单`restore_executed=false`；签名演练记录仅对应隔离数据库导入，不能代表账号登录、文件、索引和全站已恢复。
- **目录后续边界。** needs_review、来源几何和native人工状态已由主线修正，期刊候选已接原编目草稿，不能再列为未修缺陷。主线正在补原生字号/分栏信息和任务心跳，尚未真实样本运行。主线补充确认独立书签PDF导出已于`44ef916`接入源码并完成静态检查：目录export动作沿ProcessingJob，只接受已采用版本，生成独立私有WEB_DERIVATIVE，回读标题/层级/物理页/坐标并核对原件前后指纹，下载沿既有审核文件接口；不替换原件或公共PDF。此为主线交接的源码/静态状态，本子任务未运行真实生成，不能声称下载成品书签已通过实际核验。
- **只读源码尚不能证明的内容。** 批次跨端/跨重载续传、真实同名/完全重复比较、存储失联与容量、原件复制完整性、任务硬中断/接管、两人同时修改、角色即时撤销、私人正文过滤、实际发布索引切换及全部移动端交互均待统一验收。没有从图示数据推断这些场景已经成功。
- **旧实施记录中的未完项仍保留。** M27增量/独立索引备份、保留策略编辑、并发写入下数据库与文件一致性；M28有界依赖摘要之外的JSON编排引用、存储缺失检查、同名改名/批量恢复；M31完整模板内指定区域嵌入、M32按作品归并展开版本和跨目标页面保留选择，不能由本轮静态读图计清零。是否继续实施按主线既定范围决定，本报告不自行扩项。

## 六、统一验收时的代表性路径

| 场景 | 最小代表样本/动作 | 要核对的结果 |
|---|---|---|
| 普通管理员入口 | 今日工作→运行维护→存储/回收，手机更多菜单；另用内容编辑身份 | 正确active与可达子导航；无权限不越权。 |
| 收件与未保存输入 | 两部同名书、同作品译本、完全重复PDF；长文章书目未保存返回 | 明确身份决定、原件复用；离页提醒/保存继续不丢输入。 |
| 传输恢复 | 分片/R2各一例，预约响应丢失、刷新、重选同内容、换账号 | 绑定本人及内容摘要，查回原批次，不重复建文件位/馆藏。 |
| 任务恢复 | 原生PDF、扫描PDF、部分失败任务、旧worker迟到结果 | 已保存结果保留、失败范围明确，旧身份不能覆写新任务。 |
| 人工正文与目录 | 人工锁字段/文字、罗马页/多段编号、同页多标题/旋转裁切 | 候选≠人工确认；准确来源/几何，重跑不覆盖人工。 |
| 文件与发布往返 | 从检查PDF/OCR/授权项进files，切准确edition，修改后回检查 | 无错误返回路径；新版本重新检查；旧公开稿持续可用。 |
| 未知命令 | 备份、校验、回收恢复分别在提交后丢响应/刷新/同owner重验 | 原编号可查、不能假定失败或重复提交；权限重验。 |
| 人物与账户 | 同名不同人、归并后又有编辑；普通admin与馆长预览角色变化 | 不自动合并，不擅授馆长，不把私人内容暴露为依赖。 |
| 备份与演练 | 数据库备份/含原件备份、checksum不符、隔离目标及签名演练记录 | 生成/完整性/隔离导入/全站恢复分开，生产不可逆步骤另确认。 |
| 内容编排 | 已公开版、仅书目、撤回源；选书未finish返回、跨组移动、撤销 | 准确版本与来源权限，本页与全馆修改分开，内部收获不公开。 |
| 视觉与可访问 | 管理100张逐图桌面/移动/状态、键盘、焦点、弹层/触控/缩放 | 服从final-r2几何与行为，真实状态可达后才记录通过。 |

这些是待统一执行的验收样本，不是本轮已运行记录。报告保持源码事实、主线实施、静态检查、运行验收及公网切换五个状态分开。

## 主线接续修正

## 2026-10-24 八类209原图阅读完成与三处恢复补足

前置ac9d1f3。ADMIN_USABILITY_AUDIT_20261024按管理整类自问并登记80–179共100图，合并此前公共/知识64图与读者45图，FINAL_ATLAS_REVIEW_20261024现209/209实际原图已读。只有原图阅读和源码追问完成，尚未进行实施截图对比、像素一致或真实无引导操作；全站原96源码接入/110部分/3按D010排除的实施口径不能因此清零。

修复管理剩余三处：回收恢复按账户保留原对象/版本/请求并在重开时恢复详情，已收到匹配回执才清除；人物归并在规范库与旧入口均可按原编号继续核对，身份不确定结果保留，表单正文不写浏览器存储；共享选书清单提升到当前编排工作区，返回编辑再打开保留版本、理由与内部收获，完成选择才加入草稿，离站前提示未保存。人物规范表单也补未保存输入保护。没有改权限、模型、原视觉构图或生产数据。

337ec6→fb6e9c目标ESLint0错误/4既有img提示及TypeScript noEmit0；未运行测试、浏览器、真实归并/恢复/保存、构建、迁移或生产。内网预览未启动：本机现有preview库为旧演示数据，不能直接冒充当前书库；继续准备实际环境条件和已登记产品缺口。

## 2026-10-24 上传详情接入原后台任务控制

前置d38c049。管理类继续按普通管理员追问，沿已读唯一PDF82–84接入所选文件的文件/OCR/索引任务暂停、继续和取消；沿原任务命令、能力、版本、固定请求和回执，不另起任务系统。暂停请求明确等当前安全步骤，取消保留原件和已保存结果。未知结果按账户保留原请求，重新打开详情可查回；无独立任务阶段明确说明，未授权账户不请求任务队列。

批次摘要复用原阶段查询，列表按真实任务显示处理中/已暂停，上传记录终止后独立任务仍可刷新。合并即时结果与批次摘要时同时比较任务更新时间，避免旧快照覆盖新状态。传输按钮明确“暂停传输”，当前文件详情仅挂载所选一项，隐藏弹层不启动后台请求。没有新表或迁移。

4fa12a禁连DB契约生成0错误10既有警告；e81a35同步337路径类型；3869fc→e1f6ab目标ESLint和TS noEmit均0；1d06f6后台AST/目标差异空白0。状态同步验收样例只编写未运行，没有测试、浏览器、实际任务命令、构建、部署或数据变更。原图已读与实现已验收仍分开，M02尚须精确几何/移动状态和批量后台任务控制；继续已登记全站产品缺项及内网预览准备。


## 2026-10-24 批次任务范围与文件身份纠正

前置e5049cd。重新实际读取唯一PDF82–84，沿管理整类无引导追问修正两处：单文件阶段原按同一出版版本的当前文件取任务，可能带入另一个文件；现统一按原上传记录或明确Asset.source_asset派生关系读取，未绑定文件时不借用同版本任务，Discovery来源索引也纳入原阶段显示。

M02补“管理本批文件的后台任务”，在新页打开原M09以保留当前上传。批次范围绑定本人上传记录，SQL按准确文件派生过滤原ProcessingJob/SemanticIndexJob，列表/计数/分页/详情共同保持范围；不存在、他人或无效批次不退回全站任务。复用原本页选择、暂停/继续/取消、固定请求与回执，不建立批次执行器；清空搜索仍保留批次，显式退出范围才看全部。未生成独立任务的收件步骤仍回原批次。清空列表改站内确认，说明只移除浏览器选择。

4f0211四Python AST及8条SQLite/PostgreSQL SQL编译，数据库连接禁止；434598契约0错误10既有警告，c575f2同步344路径，682960目标ESLint0。75ac9f→e153f3 TypeScript noEmit退出0。同版本不同文件/明确派生/等待文件/他人批次用例只编写未运行。没有测试、浏览器、实际上传/任务命令、迁移、构建、部署或生产。全站仍有已登记产品缺项与真实内网预览准备，逐图原图读取不等于实施页视觉通过。

## 2026-10-24 备份中断恢复与维护弹层反馈

前置65b7572。重新实际读取唯一PDF161–163，按管理整类追问发现备份硬中断可永久停在运行中；现按配置的Celery硬时限加100秒显示待核对。具有原RUN_BACKUP权限的账户可在站内确认后关闭超时记录；账户/token/版本/原请求回执与任务行锁重核，已完成/状态变化不误关闭，未知响应沿原编号恢复。

原备份生成器在数据库导出、逐文件复制、归档及最终登记处核对原执行身份。关闭后迟到成功/失败不能覆盖决定，只清理本次未被接受的临时归档；已有归档和原件保留。新归档使用完整任务UUID和排他创建，文件名冲突不覆盖、不误删已有文件。没有新增备份执行器、迁移、真实关闭、文件清理或生产动作。

维护弹层接共用Dialog，错误及原请求恢复入口在当前弹层可见，不再被背景遮住；恢复按钮在表单内明确为非提交按钮。备份计划编辑增加未保存关闭/离页保护，取消继续保留输入。关闭超时记录不声称终止工作进程，重新发起仍需明确动作。

71f267禁止DB契约0错误10既有警告，f6eb86同步344路径；355cb8目标ESLint0；d3a250四AST及4条SQLite/PostgreSQL读/条件更新SQL编译；初次TS指出详情缺feedback属性，已补；e372a3目标ESLint0、441578→592f4a TypeScript noEmit0。延迟导出/完成、关闭回执重放、状态冲突及旧归档保护用例仅编写。没有测试、浏览器、备份、校验、迁移或部署。M27缓存扫描/执行清单、可编辑保留规则及增量/独立索引备份仍需继续，不能将本次恢复补足计为这些功能完成；现有OCR/媒体/原件不能仅按类型当作缓存删除。

## 2026-10-24 材料编辑人工锁与横向候选比较

前置6d1ad82。继续管理整类grill-me自问并实际重读唯一PDF94。编辑页现有人工锁只能阻止候选而缺少明确管理入口，现按原FieldLock接字段旁入口与统一核对弹层：显示当前已保存值、原锁定值、版本、操作者和说明；明确确认锁定或解除。作品字段展示跨版本影响，出版字段仅本版。关联对象显示真实名称，缺失明确显示不可用；未发布Work/Edition草稿按编辑页投影读取，不错误锁住旧公开值。书目文字与公开状态不因锁操作改变。

原workspace edits新增独立field_locks命令，共用账户/token/能力、Work/Edition锁、版本、整批事务与原请求查回/停止；未知结果持久化原编号，不能生成新编号重做。要求先保存表单，禁止锁决定夹带书目修改，关联知识额外检查EDIT_DRAFT_AUTHORITY。共有字段的其他版本锁进入workspace版本指纹，旧窗口不再漏掉这些变化。锁与书目改写、候选采用、发布分别执行，无新表或迁移。

候选书目补2至4来源横向比较及仅看差异，保留当前填写、人工锁与逐字段采用，窄屏可横向滚动。填入仍是未保存草稿，原来源和撤销链保留；查找信息变化立即停用旧候选。候选请求补X-Editor-Owner、前后本人核验和响应归属，不跨账户复用结果。

422a44契约0错误10既有警告；0eb544同步347路径；2578c6六AST及8条SQLite/PostgreSQL查询静态编译（禁连DB）；2a52b6目标ESLint0错误2既有导航提示；2db567 CSS解析。首次TS发现旧列表读取可空data，已修；2423a4→8dc88e TypeScript noEmit退出0。跨版本锁、明确解除不改正文、旧请求阻断、整批回滚、读者权限、已保存未公开值及独立Edition草稿用例仅编写。没有测试、浏览器、实际锁变更/查找、迁移或发布。M05人工锁/横向比较源码已接，精确视觉与真实运行待核实；M07其他候选命令持久恢复及全量原位关联材料仍待继续，内网预览尚未启动。

## 2026-10-24 材料助手决定的原请求恢复

前置c6bc281。继续管理整类grill-me自问，沿已读唯一PDF99–101的字段助手，书目采用、拒绝和新建人物/知识草稿接固定请求与回执。复用原FieldAssistantService、候选、人工锁、来源及AuditEvent；新接口核对本人、活跃账户/token、书目版本与独立创建/知识权限，并在同一事务保存决定及回执。采用补充候选保持ResearchRun→Edition→Work锁顺序。已完成请求返回原结果，停止尚未执行的请求后迟到写入被拒绝；无新表或迁移。

编辑器按本人/版本保留原请求编号，查回/同请求重试/明确停止均在原助手内可达，未决时暂停书目其他写入。刷新恢复只报告已发生的结果，不把已创建对象填入后来变化的行；新建人物等待期间修改姓名也不会被迟到结果覆盖。查回后保留未保存填写再刷新。共用命令钩子补每次请求的独立存活范围，换账户/目标后不处理旧响应；身份异常、权限变化、404/409及未知响应保留编号，只有明确400/422回滚错误可清除。

136802四AST及6条SQLite/PostgreSQL静态SQL编译（禁连DB）；a79993契约0错误10既有警告，生成契约已含349路径；1eac29目标ESLint0错误2既有导航提示，6e010e最终责任者组件ESLint0。8c9cc8→405f44 TypeScript noEmit0，责任者迟到行核对后3dddce→b54fe9最终类型检查也退出0。重复建立/回执查回/停止迟到请求/版本变化/内容不匹配/他人隔离用例仅编写。没有测试、浏览器、实际候选决定、迁移或部署。M07书目持久恢复源码已接，其他知识对象的命令恢复、原位完整关联材料与精确视觉/运行仍待完成；内网预览未启动。

## 2026-10-24 新建书目预填与来源保留

前置54d405f。继续管理整类grill-me自问，实际重读唯一PDF88–90。基本信息内按原风格增加可展开的元数据预填，明确点击才使用原免费来源服务，按字段查看当前值/候选/出处、仅填空白或逐项采用；来源关闭、超时、无结果仍可手工保存。采用只更新草稿，支持撤销，预填后再次人工修改不会被撤销误覆盖；可保留填写并移除过期来源。作者/译者只是姓名，必须继续选馆内人物或明确新建身份；不按同名合并。查询期间输入改变不使用旧结果。

复用原provider_gateway、SourceRecord、MetadataCandidate、CatalogFieldDecision及书目命令事务；保存时核对本人签名来源（24小时）、原来源记录和人工锁，登记实际采用/改填及原证据，不标记已确认或发布。未知保存沿原UUID恢复，不重复登记来源或人物；签名篡改/过期/跨人/重复字段/来源消失整批回滚。共享作品字段不借新增版本改写，已有版本选用不应用新建表单；保存后的共享作品标志回传，刷新后仍显示共同字段限制。手工书目版本纳入原workspace字段决定/人工锁版本。免费来源查询提取为共用函数，原已保存书目入口继续复用；Open Library作品级结果不当作具体版本出版信息，语言纳入原来源缓存键。

e827d3七AST与8条SQLite/PostgreSQL查询静态编译（禁连DB）；30f2b0契约0错误10既有警告，b5c38d同步350路径；643e04 CSS解析；f40748目标ESLint0错误2既有img提示。首次TS发现年份数值窄化不足，修复后6e7e1b→286321 TypeScript noEmit0；d9c61a目标diff空白0。来源签名/他人隔离/重复请求/手工改填/不自动建人物/失效来源恢复用例仅编写。没有测试、浏览器、真实外部查询、保存、迁移或部署。M04预填来源源码已接，PDF89其他格式附件与相关链接入口、精确视觉/完整运行状态继续；全站及内网预览未完成，不能计公网切换就绪。

## 2026-10-24 新建书目补充材料与版本归属

前置a769738。继续管理整类grill-me自问，依据刚重读的唯一PDF89后续操作双栏补PDF文件/其他补充材料入口。附件复用原Edition文件页及PDF/DOCX/TIFF上传，补充原件入口默认不生成阅读副本，管理员可明确改选原有转换选项；原件、处理任务、预览、明确采用和公开准备仍走原链。修复尚未保存的新版本误跳旧版本上传的风险：必须先保存本次版本，再补文件；已保存版本可直接到对应页面。

新增EditionSupportingMaterial只保存同一版本的后台说明与HTTP/HTTPS相关链接，不复制馆藏或文件。catalog0080仅声明、未应用。说明/链接管理支持分页、编辑、归档恢复、原请求查回/重试/停止；User锁重核本人/账户/token/编辑能力、Edition锁和全列表版本防并发覆盖，固定请求内容指纹防重复。仅管理端接口返回，不进入公开序列化、读者私人资料或发布快照；链接不自动抓取、拒绝夹带账户密码或其他协议。归档保留正文及审计，无原件删除、公开文件切换或数据迁移执行。

界面沿纸白/炭黑/砂金变量和共用站内弹层。说明编辑有未保存保护、保存失败原编号核对及最新内容对照；查回已创建结果将继续编辑绑定到原对象，避免误建第二份。归档确认显示具体材料，未知响应返回可见恢复入口；来源列表为空与加载失败分别显示。该新表属于catalog业务，现重置工具动态模型清单涵盖它，生产清理仍须新鲜计划/备份恢复核对和用户最终确认。

25fd8c六AST、catalog迁移声明对齐和8条SQLite/PostgreSQL静态SQL编译（禁连DB）；157703契约0错误10既有警告；084bd3同步352路径并解析2 CSS；1ae908目标ESLint0错误2既有img提示；306dec→54a7a2 TypeScript noEmit0。重复请求、归档恢复不改公开、停止迟到请求、版本冲突、普通读者/其他版本隔离及危险链接用例仅编写。没有测试、浏览器、实际附件上传/材料写入、迁移或部署。M04预填和补充入口源码已接，仍需精确视觉与完整真实运行核实；全站其他缺项及内网预览继续，不计公网切换就绪。

## 2026-10-24 材料助手的原位书目与依据文件

前置16c18f9。继续管理整类grill-me自问并重读唯一PDF99、100。材料助手中栏增加真实相关材料选择，右栏保留出处与当前页预览，可查看明确关联的书目、版本及原依据文件。候选证据携带原asset/edition/work/page和来源链接，缺少身份时明确说明，不自动猜测当前阅读文件或版本。历史文件不在列表第一页时，按原编号返回inspected_file，仍校验所属版本与后台权限，不开放采用/发布动作。

原位分页预览复用受权限保护的WorkFilePreview，跳到证据记录页码；越界提示并定位末页，下载仍核验原文件身份。未记录具体文件或无分页格式时说明限制。中栏列表移动可折叠，维持PDF三栏和原纸白/炭黑/砂金变量；没有新增文件、材料副本或图像参考。

236633四AST、4条SQLite/PostgreSQL静态SQL编译禁连DB；052581契约0错误10既有警告；679484 CSS解析与352路径契约同步；3a098f目标ESLint0错误1封面img提示。首次类型检查dadba8发现旧WorkFilesState样例缺少inspected_file，同步后29c12e→990b07 TypeScript noEmit退出0。历史文件跨页定位、版本隔离、来源身份及无文件不猜测用例仅编写。没有运行测试、浏览器、实际文件读取/业务操作、迁移或部署。M07原位书目依据已接，其他知识对象来源与命令恢复、精确视觉/实际状态继续；内网预览尚未启动，不计公网切换就绪。

## 2026-10-24 知识字段与原文观点决定的请求恢复

前置098ab14。继续管理整类grill-me自问，沿唯一PDF99–101。CurationFieldAssistant统一接入原请求保存/查回/重试/停止，覆盖原知识、学者、主题、学科、阅读路径及作品观点入口。复用EnrichmentCandidate、DerivedClaim、CuratedClaim、EditorialRevision及AuditEvent，不新建候选库或表。原服务继续核验来源时效、身份、已有值和草稿/公开边界；接口额外锁本人并核对token/编辑与审核能力、候选对象和字段、当前已保存版本及请求内容指纹。

采用知识候选保持ResearchRun→candidate→target锁顺序，人物同时锁现有学者资料；作品观点按Work→Claim并核对字段类别。停止与执行同账户锁，晚到原请求不可再写。超时、断网及身份异常保留原编号，刷新后只查回事实，不自动把旧值填入后来修改的表单；未保存填写阻止直接采用和刷新覆盖。拒绝理由保留，重复同编号返回原回执。来源摘录保留明确文件/版本/页码及外部链接，复用上一检查点原位预览；正式馆内记录链接使用真实slug。同名记录及同值候选保留独立编号，避免把不同人物/候选当作同一来源支持。链接只允许本站内容或无夹带凭据的HTTP/HTTPS。

bb6d8f及最终77875d六AST、10条SQLite/PostgreSQL SQL静态编译，禁连DB；3dcb40契约0错误10既有警告并同步354路径（补入新增接口白名单）；c394e2目标ESLint0错误；b0ed81→cc25ee、最终ec2f8e→188c21 TypeScript noEmit退出0。重复决定、停止晚到写入、保存版本变化、跨对象/读者/账户隔离和同名不混并用例仅编写。没有测试、浏览器、候选实际采用/拒绝、迁移或部署。M07各对象源码恢复与现有来源接入已补，完整来源覆盖、精确视觉和运行状态仍待核实。下一步继续M08其他对象选图/用途/历史和全站余项；内网预览未启动。
