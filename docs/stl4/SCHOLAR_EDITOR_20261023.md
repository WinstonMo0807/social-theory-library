# M20 学者公开页编辑（2026-10-23）

## 2026-10-24 学者导读与生平的结构化富文本

前置22790f8。重新实际读取唯一PDF142–143，按管理整类无引导复核补导读/生平正文、粗体、斜体、下划线、引用、列表与安全链接；复用原IssueTextEditor/IssueProse/normalize_text_format，不保存任意HTML，不新增编辑库或身份表。原Person.biography和ScholarProfile.short_description仍为唯一正文；原curation/发布修订只保存绑定相同文字的格式，旧客户端或资料候选更换正文后旧偏移不套用。公开页使用正式快照，未保存预览使用同一渲染。300/1000为建议篇幅，不截断历史长文；导读仍遵守原400字字段，生平超过30000字保留纯文本。

共享编辑器补中文输入法、原生文字粘贴、UTF-16位置/格式安全约束；学者页合成输入期间不保存或切换页签，发布锁同时作用于富文本。原useScholarSave覆盖学者/主题/事件/路径，未知保存后收到权限/版本/验证拒绝仍保留原UUID与正文，必须查回或沿服务器停止，不误清掉可能已成功的请求。

32b0c3禁止数据库生成契约0错误10既有警告，a156bd同步375路径；d5ebac七Python AST和两CSS语法解析退出0；fbbcee目标ESLint退出0；6da440→bcfabe TypeScript noEmit退出0。五组文字绑定/发布投影/Unicode/链接/长文验收定义仅编写未运行。无新增迁移，无测试、浏览器、实际业务或部署。M20完整原位关系与事件状态、精确页面几何及全站其他登记项仍待；继续实施，预览未启动。


前置检查点 ac28461。唯一视觉依据为 final-r2 第142–143页；直接渲染文件位于 tmp/pdfs/stl4-final-m20-20261023/page-142.png 和 page-143.png。两页均实际读取。此单元为源码部分接入，不等于全量开发或正式验收。

## 页面与原服务

- 原 ScholarsAdmin 继续使用同一 ScholarProfile、Person、EditorialRevision、AuditEvent。新建入口可从人物规范的既有 Person 建立档案，检查一对一关联、有效身份及名称等原值；不会借建档覆盖人物规范，已有学者只能回到原档案。
- 原表单改为基本信息、代表作品、理论与关系、时间线、推荐阅读、页面预览六栏。右侧页面状态、真实公开链接、选书与推荐理由，窄屏底部预览/发布。肖像仍沿原媒体服务，未保存输入沿原离页提醒。
- 代表作品与推荐阅读复用正式馆藏版本。按公开快照题名分页搜索，每页12部；已选列表单独核对，提供显式上移/下移/移除和本页推荐理由，不添加排序库。缺失/撤回作品保留原编号并提示，不能用虚构条目替代。
- essential_work_ids 继续原字段，新增 recommended_work_ids（最多24部）与 work_recommendations（每部最多2000字），都保存在原 curation 和发布修订内，无新表。新增代表作品要求当前正式贡献；新增推荐材料要求当前公开资格。原历史选择保留但读者端仍按正式资格过滤。
- 公开作品按已保存顺序优先展示，推荐阅读明确为编者选择，不推断作者身份。公开读取使用正式学者快照及当前有效出版版本；不会提前公开未发布理由。
- 理论、人物、主题及生平事件显示真实正式记录和来源；候选审核、详细编辑、其余分页继续原管理入口。旧自由文本保留于折叠记录，不自动晋升为正式事件/关系。
- 预览使用原公开组件、同一日夜主题及桌面/移动 iframe。未保存选择改用原受保护预览地址的只读 POST，在内存中投影；不把理由或大批选择塞进 URL，不保存修订。发布仍按原保存版本检查、确认、回执恢复。

## 保存、账户与恢复

原学者 create/_guarded_edit 外层增加事务包装：必须 X-Editor-Owner，锁内读取当前 User、有效状态、token_version 和实际编辑/创建能力。新建必须固定 Idempotency-Key UUID；编辑正文使用同一固定UUID。兼容原发布准备/肖像/回收流程及其原恢复记录。

原 AuditEvent 主键保存请求UUID，记录 actor/对象/请求HMAC/已保存版本，不记录表单正文。重试先核对原回执再检查旧CAS版本；同编号不同内容拒绝，已删除对象不会自动重建。重放返回当前保存版本并重新装载表单，不能把旧输入标成最新。失败响应在事务内回退。

useScholarSave 的正文只留当前页面内存；sessionStorage 只留按账户隔离的请求UUID。未知网络结果保留原请求；重载后只查回执。保存与查回互斥，避免迟到查回清除下一次保存。账户切换重挂编辑器，读写前后核对同一身份。普通保存后刷新原详情，发布检查取得真实新版本。

AdminPrivateResponseMixin 继承原 PrivateAccountResponses，增加可选 X-Editor-Owner 比对，保留原服务端调用兼容，响应 private/no-store 并 Vary Cookie/Authorization。学者预览纳入此边界。新选书、保存、回执接口明确要求编辑账户。所有者读者资料仍在原 reading 接口，没有把后台编辑权限扩展为读取读者私人研究/笔记。

## 契约

- 原 POST /api/catalog/admin/scholars/：可选 existing_person_id（仅新建），原 serializer 和修订服务；新增新建请求编号要求。
- 原 PATCH /api/catalog/admin/scholars/{id}/：If-Match 保留；编辑正文返回 save_receipt，重放含 save_replayed。
- GET /api/catalog/admin/scholars/commands/{request_id}/：仅原 actor 可查原 AuditEvent；返回对象仍存在与否，不重新执行。
- GET /api/catalog/admin/scholars/{scholar_id}/work-selection/：kind=essential|recommended，q/page 或独立 ids；严格参数、限制数量、正式版本数据。
- 原 /api/catalog/admin/knowledge-preview/{type}/{id}/ POST：新增 ScholarPreviewRequest，只有引用、作品与路径选择；受保存版本和身份校验。原主题请求仍有效。
- 公共 ScholarWork 新增 is_recommended/recommendation_reason，ScholarDetail 新增 recommended_works；来源与资格沿原链路。原279条契约保留，新增2条，共281。

## 已做的静态核对

- tmp/stl4-scholar-editor-static-20261023.py：46个Python AST、48个SQLite/PostgreSQL SQL编译、模型/迁移声明比较；禁止任何数据库连接。64d009退出0，46文件中包括本单元新服务及原共享边界。
- 同次只生成OpenAPI：0错误、10个既有catalog返回类型提示；tmp/stl4-scholar-editor-schema-warnings.log。契约生成脚本保留原路径并只允许新增学者前缀，退出0；CSS仅语法解析。
- web 的 tsc --noEmit --incremental false 与本单元目标ESLint：3ef178退出0，3条img提示（两条新选书、1条原公开卡片）。封面使用原受控图片地址与原始图像，不接外部优化服务。
- 上述之后仅补了推荐理由展示范围条件；b47797重新解析本单元Python语法，a4ad97及后续返回的TypeScript/目标ESLint退出0。

未运行任何测试、浏览器、构建、真实业务/账号操作、迁移、任务或生产连接；本单元无迁移。catalog0075、reading0022/23/24及历史记录的其他待执行迁移仍未执行。

## 后续剩余

M20两视图记部分接入。严格富文本工具栏/原位关系与事件完整编辑、所有候选和窄屏状态、PDF逐像素布局与完整业务仍待；没有把链接到成熟编辑器当作终稿全部实现。继续M21–M24及尚未覆盖的入库、处理、系统和策划视图，最后统一完成尚缺状态。用户当前禁止测试/浏览器，正式B01–B06验收均不能据此判定通过。

未来统一验收应覆盖：同一Person重复建档冲突；两账户/撤销权限/会话切换；保存断网重试、并发版本、删除后查回；作品排序/撤回/理由与发布快照；只读预览不写入；原媒体及发布恢复；全部桌面/移动状态。以上为待执行项目。
