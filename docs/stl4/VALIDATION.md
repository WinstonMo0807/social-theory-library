# 验收记录

## 2026-10-23 M25账户管理

M25最终9e6d4d AST32/SQL编译36/accounts+reading迁移声明比较/273契约/CSS退出0，0schema错误10旧警告。初次accounts声明差异仅本地化标签，在en上下文比较后通过。最终TS/目标ESLint91498e退出0。未测试/浏览器/真实账号/迁移/生产。

## 2026-10-23 R28接续

R28 f65197 AST24/SQL编译32/迁移声明退出0，eabfa7契约267/CSS退出0。ESLint367706发现渲染访问ref并已改状态，最终TS+ESLint c439d7退出0；无测试/浏览器/真实导出。

## 2026-10-23 R34分享静态记录

f78b9b AST23/SQL编译32/迁移声明比较退出0，禁止DB连接；15e1c9契约266/CSS解析退出0，schema0错误10旧警告；TS与目标ESLint eda30b退出0。末次sender缺失处理与导出补齐见SHARING_WORKSPACE_20261023。没有测试/浏览器/迁移/业务/通知/生产；fixture只同步collaboration计数类型。

## 2026-10-23 R34引用书单

R34书单引用只做静态：15AST/18SQL编译（禁止DB连接）、迁移声明对照、OpenAPI 0错误/10旧警告，3c3a8d退出0；契约/CSS d27496、TS e4342d、目标ESLint6ca668退出0。未测试/浏览器/业务/模型/迁移/生产。


## 2026-10-23 R30静态记录

`.venv/Scripts/python.exe tmp/stl4-replay-static-20261023.py`退出0，13AST/12SQL编译、数据库连接硬阻断、reading迁移声明一致、OpenAPI0错误/10既有catalog提示。`node tmp/stl4-replay-contracts-20261023.mjs`退出0，249+3=252路径与CSS解析。web目录TypeScript noEmit df75c9/057f1c退出0，5文件ESLint b252b8退出0。未测试/浏览器/业务调用/模型/队列/构建/迁移/生产。


## 2026-10-23 总览书签计数与旧笔记定位

前置af22a6f。原reader-center聚合加入Bookmark；笔记筛选同时包含笔记/摘录/书签，各分支仍本人过滤，导航数为两类之和。ReaderMaterials所选任务增加书签映射；旧#note-ID和当前record参数恢复原记录，清空搜索同步表单。无新路径/迁移，249路径、96/38/75。仅静态：schema/SQL/AST脚本与契约退出0；TS+目标ESLint 6e6413/37b3a8退出0。未测试/浏览器/业务运行。已实际读唯一PDF221–222，接着研究过程回放。


## 2026-10-23 R28仅静态检查

前置a84e707，详见NOTEBOOK_WORKSPACE_20261023。`.venv/Scripts/python.exe tmp/stl4-notebook-static-20261023.py` 最近7d95e3及最终同命令退出0；9AST/8SQL编译/reading迁移声明一致，数据库连接强制阻断；OpenAPI0错误、10既有catalog提示。`node tmp/stl4-notebook-contracts-20261023.mjs` 646217及后续退出0，保留244并新增5路径，共249，CSS解析。

`node node_modules/typescript/bin/tsc --noEmit --incremental false`（web目录）ab9fd4/e5be05、475d42/b5272e、737507/0ebae7、最终f31d4d/37cbbd退出0。目标10文件ESLint最终76c517退出0，3条已有img提示，无错误；新notebook组件没有提示。白名单33文件存在、git diff --check退出0；仅AST检查隐私结果集合不再以单UUID识别。没有运行测试、业务请求、队列、模型、浏览器、页面截图、构建、迁移、生产。全站视觉与业务验收仍待。


## 2026-10-23 计划隐私开关静态校正

前置1a02917。继续核对真实RETENTION字典时发现本批计划转换引用了并不存在的plans开关；已移除，计划仍由本人明确生成、在原分类删除中管理，不借用笔记/知识保存开关。静态AST额外核对本批require_retention字面量键均属于真实配置；444a4d退出0，0数据库连接、无业务调用。BOOKLIST_PLAN说明同步修正。

已实际读取唯一PDF181/182/216/217。旧荐书仅产生mailto，未找到专用小组成员/受限分享持久化实现；分享范围须另补真实服务。接着补R28统一笔记/摘录/书签及来源与选择范围，为明确分享提供基础。没有新迁移或测试/浏览器/生产；96/36/77、244路径保持。

## 2026-10-23 书单转计划静态记录

`.venv/Scripts/python.exe tmp/stl4-booklist-plan-static-20261023.py` 33f48b/98b6f2退出0，13AST/10SQL编译/reading迁移声明一致/0数据库连接；OpenAPI0错误和10既有catalog提示。`node tmp/stl4-booklist-plan-contracts-20261023.mjs` 135fae退出0，241保留+3=244并解析CSS。完整TS200821/e77795及807ed9/778c66退出0，目标ESLinte91e3b及后续同807ed9退出0。未测试/浏览器/业务操作/运行计划/PDF渲染/构建/模型/迁移/生产。

## 2026-10-23 R29书单静态记录

- `.venv/Scripts/python.exe tmp/stl4-booklist-static-20261023.py` aedeca退出0：12文件AST、10次两数据库SQL编译，禁止所有数据库连接；MigrationLoader(None)/ProjectState比较reading声明一致；OpenAPI0错误/10既有catalog类型提示。reader_center另外AST解析，未运行。
- `node tmp/stl4-booklist-contracts-20261023.mjs` 819ef0退出0：232原路径保留，纳入9书单路径，共241，CSS仅解析。后续相同契约重新生成。
- 完整TS 2c316e/7ef64e、c70fd6退出0；最终`tsc --noEmit --incremental false` f65874及后续完成记录见工具输出。10个目标ESLint05f80e退出0；新增组件曾报render读ref，已改显式状态与事件内读取。7917f2是在错误cwd启动ESLint，没有检查文件，已在web目录重跑。
- 最终PDF218、219、220实际已读取。没有测试、浏览器、真实导出/渲染、业务操作、构建、模型测评、迁移/周期任务执行或生产操作。0023仅文件，0022亦未执行。

## 2026-10-23 认证源码静态记录

- `.venv/Scripts/python.exe tmp/stl4-auth-static-20261023.py` 最终76244d退出0：5文件AST、8次SQL编译含锁，0数据库连接；OpenAPI0错误/10既有提示。首轮911b8a新增UserSerializer四项类型提示，补准确返回类型后消除。没有认证、验证码、邮件或Cookie实际请求。
- `node tmp/stl4-auth-contracts-20261023.mjs` 53c163退出0：228旧路径保留、4原auth路径纳入，共232；CSS解析。
- web11目标ESLint 058bb0/9e13e6退出0；最终3修改组件8cb1c9退出0。完整TS d55e16/98a433及5d14ad/f75a1b均退出0。
- 唯一PDF186–190实际已读，PDF187只提取注册局部照片9a95a4并查看；无实现页截图或浏览器检查，无测试/构建/迁移/生产。

## 2026-10-23 资料批量与转存静态记录

- `.venv/Scripts/python.exe tmp/stl4-reader-materials-static-20261023.py` 123355退出0：7文件AST、34次两数据库SQL编译，禁止连接；MigrationLoader(None)与ProjectState比较reading声明一致，没有执行迁移；OpenAPI0错误/10既有提示。
- web完整`tsc --noEmit --incremental false` a96c88/27b1cd及77f675/6447d8均退出0。7目标ESLint b91607退出0，原privacy img性能建议1项；最新两新增组件ESLint随77f675返回0。
- `node tmp/stl4-reader-center-contracts-20261023.mjs` 025d26退出0，228路径保持，生成类型/CSS解析。
- 没有运行测试、浏览器、真实业务、构建、迁移、模型或生产操作。后续待完整资料权限/删除影响/异步恢复/多标签转存的正式验收。

## 2026-10-23 R22静态检查（未运行测试）

- `.venv/Scripts/python.exe tmp/stl4-reader-center-static-20261023.py` b2e08a退出0：4文件AST、20次SQL编译、0连接，OpenAPI0错误/10既有提示。
- `node tmp/stl4-reader-center-contracts-20261023.mjs` d63253退出0：保留227旧路径，共228，CSS解析。
- web完整`tsc --noEmit --incremental false`首轮a19d49发现旧局部变量移除和参数重名，已修；4b46a6退出0。最新含笔记和导航修改38d123/b1acb1退出0。
- web6目标ESLint b755f6退出0，已确认笔记旧img性能建议1项。无测试、浏览器、构建、业务调用、迁移或生产。

## 2026-10-23 外观与账户源码静态核查（没有测试）

- 最终7文件AST 9c7d92退出0；14目标ESLint ad5357退出0，保留reader-shell既有img建议。14 CSS与2 JS仅解析385791退出0，包括交互HTML内脚本，不执行页面。45路径白名单git diff --check cf37c7退出0（换行提示不影响结果）。
- web完整 TypeScript `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：24665/a4ddf3、56164/7488b9均退出0；无构建产物。
- 7个Python源码文件仅 ast.parse，2a0394退出0；不import应用，不连接数据库。
- 14目标ESLint首轮a09105发现旧ReaderCenter直接赋值window.location.href，改为校验mailto并location.assign。后续4目标744d9d退出0。reader-shell原img性能建议仍待正式验收时评估，不隐藏。
- 参考PDF本单元实际查看10/18/183/185/189。3张imagegen扩展示意与纯HTML交互文件不作为像素对照结果。未运行浏览器或交互文件。
- 用户禁止本轮测试：没有单元/E2E/业务运行/视觉回归/检索测评、构建、迁移或生产操作。当前仅静态证据，不能称验收通过。

## 2026-10-23 知识历史静态记录（不代表验收）

- `.venv/Scripts/python.exe tmp/stl4-knowledge-history-static-20261023.py`：最终86c87c退出0，5文件AST、20次SQLite/PostgreSQL SQL编译，数据库连接被禁止、0连接；九类型可编辑字段均有中文标题。spectacular 0错误/10条既有类型提示。
- `node tmp/stl4-knowledge-history-contracts-20261023.mjs`：776910退出0，226旧路径保持、227总路径；生成schema.json/schema.ts，新增CSS解析通过。
- web全量`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：首轮11477/945dde退出0；后续42037在新输入后无法取得最终状态，不记通过。最后增量涉及文案/回执清除与上下文入口，待静态收口。
- web10目标ESLint c28481退出0无警告。初轮35540/3713b2发现reload手动依赖4项，补稳定setter依赖后4目标3ed63c及10目标c28481通过，没有忽略规则。
- 7后端函数（首函数6类型，共12参数案例）及6浏览器场景只定义，涵盖只读、原回执、恢复编辑、草稿保护、分页/对象归属、owner权限、取消/确认/移动内容。没有执行测试、浏览器、构建、迁移、真实服务或生产。

## 2026-10-23 知识M17四区工作台静态检查

- `.venv/Scripts/python.exe tmp/stl4-knowledge-review-static-20261023.py`（PYTHONIOENCODING=utf-8），e64eb9退出0：3文件AST、18次SQLite/PostgreSQL SQL编译，ensure_connection禁止连接，0数据库连接。只导入检查服务，不执行预检业务。脚本内spectacular生成/验证0错误、10条既有提示。
- `node tmp/stl4-knowledge-review-contracts-20261023.mjs`，e74d38退出0；226路径保留，review可选参数加入原GET；生成schema.json/schema.ts同步，未新增API路径。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web），最终28088/da8aa1退出0，包含embedded样式参数；前次64459/1351f2、71837/6bc04d亦退出0。
- 9目标ESLint（knowledge-publication-review、knowledge-publish-control、knowledge-page-preview、knowledge-visual-editor、knowledge-object-context-panel、knowledge-legacy-redirect、admin-shell、原预览route、knowledge-publication-atlas），9413bd退出0、无警告。前次dbdfb8的内部window.location.assign建议已改为useRouter.push，未忽略规则。复用原issue-publication.module.css，本次未改CSS。
- 最终3 Python AST文件920650退出0；25路径记录脚本只更新明确文档和M17三行说明。209行22列及全部身份/来源/状态保持，96/26/87不变。目标git diff --check adea35退出0，只有已有CRLF换行提示。
- 新增8后端函数（首函数6类型参数），浏览器文件扩充到11场景，仅定义未运行。覆盖只读无写入、版本/权限/原撤回、人物资格、图片不可变元数据、四区/设备、frame失败与伪造消息、旧链接准确返回。没有正式测试/E2E/浏览器/服务/构建/迁移/检索测评/生产操作。
- 最后两组件ESLint62566/d347d7退出0；旧跳转明确选择优先列表筛选的修正及对应定义，d3ad62退出0。上述均无警告。

## 2026-10-23 知识预览保存版本静态检查

- `.venv/Scripts/python.exe tmp/stl4-knowledge-preview-static-20261023.py`（PYTHONIOENCODING=utf-8），bd0c77退出0：3文件AST、16次SQLite/PostgreSQL SQL编译，ensure_connection禁止连接，0连接。脚本内spectacular生成与验证0错误/10既有警告；未运行测试。
- `node tmp/stl4-knowledge-preview-contracts-20261023.mjs`，2c67d4退出0。保留226路径，仅知识预览GET/POST新增edit_version参数及409响应；api/openapi/schema.json与生成schema.ts同步。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web），最终49661/4ca627退出0，前次92613/defda6也退出0。
- 四目标ESLint（knowledge-page-preview、knowledge-publish-control、knowledge-visual-editor、knowledge-publication-atlas），bfb464退出0。后续链接/验收定义两目标992b06及错误返回入口一目标1ecd67退出0，均无警告。曾从仓库根目录调用ESLint产生pages路径提示；改在web目录按原配置执行，未忽略规则。
- 新增4后端函数（首函数6类型参数）、2浏览器场景只定义；浏览器文件共7场景。覆盖版本公式保持、保存后过期、生成期间变化、只读选择不写库、失败重读清空、账户变化及绑定链接。未运行正式测试/E2E/浏览器/服务/构建/迁移/模型/索引/检索测评/生产操作。图集状态与96/26/87不变。

## 2026-10-23 知识对象发布状态与恢复静态检查

- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web），最终47850/ed2103退出0；前次31566/8e90ff也退出0。仅类型检查，无构建。
- `node node_modules/eslint/bin/eslint.js components/admin/knowledge/knowledge-publish-control.tsx components/admin/knowledge/knowledge-visual-editor.tsx components/admin/knowledge/knowledge-object-context-panel.tsx components/theory-system-admin.tsx tests/knowledge-publication-atlas.spec.ts`，24265/0e35a5退出0、无警告。末次错误提示和验收配置补充后，control与playwright.auth.config.ts两目标ed71a4退出0。
- Python AST检查api/common/permissions.py及api/tests/test_knowledge_publish_owner_20261023.py，9a9425退出0；不import、不连接数据库、不运行测试。本批不改SQL、schema或CSS，无需重复生成契约或编译SQL。
- 新增4个后端函数（首函数对6类编辑器参数化）和5个浏览器场景，只定义未运行；auth配置登记本批与原issue-publication/publication-ledger/publication-review定义。没有正式测试/E2E/浏览器/服务/构建/迁移/模型/检索测评/生产操作。
- 保存前白名单审计只核对18条路径、空暂存区、图集索引和生成契约未改。首次原字节比较因工作区CRLF与Git LF不同而触发断言；改按换行归一化核对文本内容，不修改索引文件或放宽业务检查。该审计不是功能测试。

## 2026-10-23 NEW-A16静态检查

- `.venv/Scripts/python.exe tmp/stl4-review-static-20261023.py`，最终dc9f18退出0：5文件AST、14次SQLite/PostgreSQL SQL编译；ensure_connection禁止连接，0数据库连接，无测试运行。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web），最终56958/afdcc2退出0，前次46223/f8f47d亦退出0。前序74571/af934d因旧验收fixture缺review字段失败；已补review:null，再完整检查通过，不隐瞒前序失败。
- 10目标ESLint（review、entry、ledger、work-page-preview、workflow-editor、admin-shell、两路由页、两个publication验收定义），b04132退出0；1项既有img及2项既有window.location.assign建议，无错误。末次预览视口高度修正后两目标a0dd16退出0。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-publication-review-schema-20261023.json --validate`（DATABASE_URL=sqlite:///:memory:，PUBLIC_DEPLOYMENT_MODE=false，DJANGO_DEBUG=true），dc9f18退出0；0错误/10既有警告，不是fail-on-warn通过。`node tmp/stl4-review-contracts-20261023.mjs`最终b50ecb退出0，保留226路径、生成双方类型、CSS84顶层节点可解析。一次重复生成曾遇Windows UNKNOWN写文件错误；随后重新执行成功，未删除或替换原件绕过。
- 7后端函数和4浏览器场景只定义。覆盖草稿/公开出版信息分离、纯书目、历史跨页、关联增删、owner/权限、预览版本冲突、旧收件ID解析、真实命令参数、预览失败门槛。浏览器用例中的iframe只模拟消息确认，不能证明真实WorkDetailView视觉；真实iframe呈现、版式与全部状态待统一验收。无测试/E2E/浏览器/构建/迁移/模型/检索测评/生产操作。

## 2026-10-22 M18出版历史工作台静态检查

- `.venv/Scripts/python.exe tmp/stl4-publication-desk-static.py`（PYTHONIOENCODING=utf-8），c90621退出0：6文件AST、SQLite/PostgreSQL共10次SQL编译，ensure_connection阻断，0连接。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`，最终13816/dceee7退出0；前序76882/3028b0、83509/9e3c4b亦退出0。
- `node node_modules/eslint/bin/eslint.js components/admin/workflow/publication-ledger.tsx components/admin/workflow/publication-diff.tsx components/admin/workflow/publication-retry-control.tsx components/publication-desk.tsx tests/publication-ledger-atlas.spec.ts`，e4f1b3退出0，1项img优化建议保留。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-publication-desk-schema.json --validate`（SQLite内存URL、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true），81abbe退出0，0错误/10项既有serializer警告；严格fail-on-warn未记通过。`node tmp/stl4-publication-desk-contracts.mjs`，03e7a9退出0，226路径全部保留，CSS65顶层节点可解析。
- 7后端函数和4浏览器场景只定义；包含只读分页、跨对象/权限、撤回状态、旧版恢复CAS与回执、准确请求、断线重开、撤回独立能力。未运行正式测试/E2E/浏览器/构建/迁移/模型或检索测评/生产操作。

## 2026-10-22 M17发布检查静态记录

- `.venv/Scripts/python.exe tmp/stl4-publish-review-static.py`（PYTHONIOENCODING=utf-8），efe16f退出0：7文件AST、两数据库共8次SQL编译；ensure_connection阻断，0连接。没有运行功能测试。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`，最终35540会话退出0；此前70565/7b1139、41714/f40087亦退出0。
- 10目标ESLint：`node node_modules/eslint/bin/eslint.js components/admin/curation/issue-publication-review.tsx components/admin/curation/issue-preview-frame.tsx components/admin/recommendation-issue-editor.tsx components/admin-shell.tsx components/admin/curation/use-issue-draft.ts components/admin/curation/inline-media-picker.tsx components/admin/curation/article-body-fields.tsx components/admin/curation/article-metadata-fields.tsx 'app/admin/recommendations/issues/[issueId]/preview/page.tsx' tests/issue-publication-atlas.spec.ts`，d64a0a退出0，3处既有img建议。追加放弃修改后复查review/hook/浏览器定义，20532d退出0。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-publish-review-schema.json --validate`（SQLite内存URL、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true），d444d0退出0，0错误/10项既有serializer警告；未标严格fail-on-warn通过。
- `node tmp/stl4-publish-review-contracts.mjs`，fdb976退出0，原225路径全保留、补已有preview覆盖共226，IssuePublicationReview存在；CSS68顶层节点可解析。此前仅225路径生成不含preview，已修正覆盖，不能用旧结果证明review契约存在。
- 新增8后端函数、7浏览器场景只定义。未运行正式测试/E2E、浏览器、构建、迁移、OCR、模型/检索评测、索引任务或生产操作。

## 2026-10-22 关联材料与人工审阅

- `.venv/Scripts/python.exe tmp/stl4-related-static.py`（PYTHONIOENCODING=utf-8），88144e退出0：7文件AST、两数据库共10次查询编译；ensure_connection阻断，0数据库连接，未执行功能测试。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：40533/a9820b及最终61377/46da8a退出0。
- `node node_modules/eslint/bin/eslint.js components/admin/curation/issue-related-materials.tsx components/admin/curation/issue-assistance-review.tsx components/admin/curation/issue-selection-workbench.tsx components/admin/curation/article-body-fields.tsx components/public/issue-block-view.tsx components/public/recommendation-issue-view.tsx lib/api/curation-workspace.client.ts lib/api/recommendation-issues.types.ts components/admin/curation/use-issue-draft.ts tests/issue-selection-atlas.spec.ts`，8d2295退出0，1项既有img建议。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-related-schema.json --validate`（SQLite内存URL、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true），0f42cb退出0；0错误、10项既有serializer类型警告。未将严格--fail-on-warn记为通过。`node tmp/stl4-related-contracts.mjs` a2599f退出0，保留225路径，重生契约，两CSS77/196顶层节点可解析。
- `git diff --check`限定本批源码路径，569acd退出0。新增6后端函数+3浏览器场景仅定义（选材文件共9场景）；未运行正式测试、E2E、浏览器、构建、迁移、OCR、模型、检索质量评测或生产操作。


## 2026-10-22 来源信息与真实缩略图接入

- `tmp/stl4-source-details-static.py`：80e427、最终0087e6退出0。4文件AST、SQLite/PostgreSQL共6次SQL编译，ensure_connection阻断且连接0；不运行测试或解析真实馆藏。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：6424/11c19a退出0；后续11405会话恢复时不可查，未作为通过记录；最终67526/15b29d退出0。
- `node node_modules/eslint/bin/eslint.js components/admin/curation/issue-source-summary.tsx components/admin/curation/article-body-fields.tsx components/admin/curation/issue-source-picker.tsx components/admin/curation/issue-selection-workbench.tsx lib/api/recommendation-issues.types.ts tests/issue-editor-atlas.spec.ts`，09bf48退出0，1处既有img建议。PostCSS 5e979b退出0，两CSS202/68顶层节点可解析。
- 新test_issue_source_details_20261022.py四函数与编辑器新增一场景、来源断言更新仅定义，未执行；18浏览器场景不是通过数量。source扩展位于既有DictField内，225契约不变。
- 未执行正式测试/E2E/浏览器/构建/迁移/OCR/模型/检索质量评测/索引重建/生产操作。

## 2026-10-22 PDF128–130选材与助手第一批（部分接入）

- 记录辅助d57914因旧索引使用多种“已接入”状态措辞，按单一前缀统计而退出1；未涉及业务运行。仅续写白名单与校验的3b7146退出0，保留CSV原BOM及209组身份/哈希/验收状态，只改M16三行，重新核对为96接入/19部分/94待实施。暂存区为空、30路径白名单差异检查通过；未重复执行文档插入。
- Python AST与安全SQL编译：`$env:PYTHONIOENCODING='utf-8'; .venv/Scripts/python.exe tmp/stl4-selection-static.py`，93bb41、8e4553及范围修订后重跑退出0。7文件AST、SQLite/PostgreSQL各5查询，共10编译；ensure_connection阻断，连接0。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：初次e742b3因JSX缺失空分支退出1，修复后96160/d8cb32、41295/79a198、最终84124/4615a6退出0。
- 8目标ESLint：`node node_modules/eslint/bin/eslint.js components/admin/recommendation-issue-editor.tsx components/admin/curation/use-issue-draft.ts components/admin/curation/issue-selection-workbench.tsx components/admin/curation/issue-assistance-review.tsx components/admin/curation/issue-discovery-materials.tsx lib/api/recommendation-issues.types.ts lib/api/curation-workspace.client.ts tests/issue-selection-atlas.spec.ts`。最终fb47d6退出0，仅1处既有img提示；初次轮询依赖提示已修正。
- PostCSS解析7148d8退出0：67顶层节点、20直接引用类齐全。未执行页面渲染。
- 隔离DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8；`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-selection-schema.json --validate`，e9a5c4退出0，0错误/10项既有HomeScholar/Topic类型提示；32e348同步225路径及TS，原225全保留。
- 新`api/tests/test_issue_selection_20261022.py`10个函数，`web/tests/issue-selection-atlas.spec.ts`6场景，仅定义未运行。无正式测试/E2E/浏览器/构建/迁移/OCR/模型调用/检索质量评测/索引/生产。

## 2026-10-22 富文本第三批静态记录

完整 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：57312/014c6d、65605/3f0d02退出0；最终57499/e767ca退出0。目标ESLint a85c5f退出0但多一项composing依赖提示，去除无用依赖后aca4ab退出0，仅保留2处既有img提示。PostCSS 568bcc退出0，185顶层节点可解析。新增4浏览器场景、现17场景仅定义，未运行正式测试/浏览器/构建/模型/检索质量评测/生产。

## 2026-10-22 PDF127第二批静态记录

- Python ast.parse 9个源码/测试文件：69214d、最终fb0a39退出0；测试定义未执行。新9个后端函数、6个浏览器场景仅定义，现issue-editor-atlas共13场景。
- `tmp/stl4-issue-editor-details-static.py` 7e010f退出0：公开作品/学者/概念查询、准确版本、JSON放弃回执、当前可用账号，共6组SQLite/PostgreSQL编译12次。ensure_connection明确阻断、连接0；仅在编译时stub词表返回ID，不执行查询或检索评测。
- 完整 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：79226/2c0171、57006/78a3f5、最终19654/5fdb13均退出0。
- 目标ESLint初次7f1908因渲染回调里递增offset退出1，改为渲染前计算行偏移；11目标ec47a0退出0（3项img建议）。素材图片后改为复用EditorialImage缺失/失败处理，最终3目标e13647退出0、无提示，其他2项原img建议保留。无禁用检查规则。
- PostCSS e13647退出0：176个顶层节点、本批48个直接类引用均存在。CSS不证明实际像素或交互。
- 隔离进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8；`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-issue-editor-details-schema.json --validate` d8cee1退出0，0错误/10项既有Home Scholar/Topic类型提示。dbbdbf生成225路径、原223全保留及TS同步。
- ATLAS辅助首次983b81因CSV头BOM未剥离退出1，改为utf-8-sig后fb0a39退出0：209行、仅M15四行细节修改，page/id/hash/source_page及实施/验收状态不变；空暂存区、34路径白名单diff检查0（既有CRLF提示）。
- 未正式测试、浏览器、E2E、构建、迁移、OCR/模型调用、检索质量测评、索引重建、生产发布或清理。

## 2026-10-22 专题编辑器第一批静态记录

- Python ast.parse 8个源码/测试文件：a148f8退出0。未执行测试模块。
- tmp/stl4-issue-editor-static.py：b10485退出0，历史/概念/回执6组SQLite/PostgreSQL SQL仅编译；ensure_connection明确阻断，连接0。
- 全量TypeScript首次0ce913/fdb131退出0；加入比较回调后52585/9ad8c1出现泛型unknown，显式IssueDraft修复；最终 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false` 88029/f661cf退出0。
- 目标ESLint首次6feb5b报state对象潜在修改，改用不可变command；eaa43e 8目标退出0（2项img建议），后补owner/API清除等5目标b66e17退出0（1项img建议）。
- schema用DATABASE_URL=sqlite:///:memory:等隔离进程环境，`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-issue-editor-schema.json --validate` eb6021退出0，0错误/10项原Home Scholar/Topic提示。生成223路径保留原221及TS。首次CSS核对ad0a3c发现blocks类未定义，补齐后b66e17 123节点/45直接引用全存在。
- git diff --check 67ba5c退出0（既有CRLF提示）。10个新后端测试函数、7个浏览器场景及auth runner登记仅定义，未运行。未浏览器/构建/迁移/检索测评/生产。


## 2026-10-22 今日工作第一批静态记录

- `tmp/stl4-today-static.py`（本机辅助）：SQL12组SQLite/PostgreSQL仅编译，数据库连接明确阻断为0；最终6bfe48退出0。初始7c0780混合Text/Char失败已修正，不作为通过记录。
- Python ast.parse 10源码/测试文件：6bfe48退出0，不运行测试。
- 完整`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：session66778/6e517e及9441/f4b280退出0。
- 8文件目标ESLint：160714退出0、0错误5提示（4img、1既有location.assign）。4CSS PostCSS parse：c56f15退出0，62/38/16/82顶层节点，22个直接模块类引用齐全。
- 进程DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-today-schema-20261022.json --validate`，113b6a退出0，10既有提示/0错误；02264e生成219路径与TS类型，原218均保留。
- ATLAS语义比较a8d25c退出0，仅80/81变更，209行22字段及来源身份保留；两视图标部分接入。
- 后端10新函数14参数案例、浏览器6场景仅定义。继承OCR提醒2用例、旧认证用例适配保留。正式测试/浏览器/构建/迁移/检索质量测评/生产均未运行。

## 2026-10-21 PDF73–78专题文章/微展览静态记录

- 白名单tmp/stl4-editorial-checkpoint.json为62路径。22个Python逐个ast.parse通过，0faa23退出0；其中新16个后端函数21参数案例仅AST统计，未执行。旧v307书单与privacy样例、11个浏览器场景同步定义，未运行。
- web下按白名单筛选23个TS/TSX（排除generated）运行node node_modules/eslint/bin/eslint.js，最终86877/ba1234退出0，0错误/4个图片优化建议。第一次reader修改曾报effect内setState，改为用户选择与默认偏好的派生状态后通过。
- web下node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false，最终63771/a6d2b4退出0。455ddf曾报会话user可空和privacy测试计数缺article_comments；修正后通过。早期结构化来源nullable字段、schema循环导入分别修复后通过，不删除检查项。
- PostCSS解析editorial.module.css 191顶层节点、stl4-reader.css 180节点，67个直接styles类引用没有缺失，682ba0退出0。实际图片/布局/焦点/移动状态尚未验收。
- 环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，运行.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-curation-schema-20261021.json --validate，ff954f退出0：0错误/10个既有Home/Scholar/Topic类型提示。openapi-typescript/astToString同步，a87ec4退出0，218路径，原213全部保留；新五路径为评论公开/本人/回执/删除/管理。
- 0faa23退出0：禁用BaseDatabaseWrapper.ensure_connection，目录类型/主题JSON/署名关键词/图片UUID及评论公开/本人六组SQL分别SQLite/PostgreSQL仅编译12次，参数数一致，数据库连接0。
- MigrationLoader(None)+MigrationAutodetector仅内存比较模型/迁移，8495dc退出0、数据库连接0：reading/catalog没有差异；contenttypes/sessions/admin/auth/accounts报告既有options/字段状态差异，保留待统一环境核验，没有生成、应用或删除任何迁移。0021及此前迁移均未应用。
- 不运行正式API/数据库/并发/功能测试、浏览器、E2E、构建、实际PDF/OCR/模型、检索质量测评、索引重建或生产操作。96/209仅源码接入，全部视觉与B01–B06仍待全量完成后统一验收。

## 2026-10-21 PDF68–71主题静态记录

- 精确白名单tmp/stl4-topics-checkpoint.json共74路径；.venv/Scripts/python.exe tmp/topic-checkpoint-20261021.py逐个ast.parse 28个Python文件，1b1764退出0；同批git diff --check退出0。未执行测试函数。
- web下node node_modules/eslint/bin/eslint.js <30目标TS/TSX路径>，70fc53退出0，0错误/8提示（7图片优化、1既有导航）。node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false最终52383/690e4f退出0；早期缺失legacy预览字段导致失败，已补完整默认字段后通过。
- PostCSS解析topic.module.css 240顶层节点、82直接class引用无缺失，85df8b退出0；不证明实际视觉。两照片裁片元数据保留sources.json。
- 进程DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8运行.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-topics-schema-20261021.json --validate。最终8c3a1a退出0，0错误/10既有Home/Scholar/Topic提示；早期枚举嵌套导入提示已改为准确choices。openapi-typescript同步49e8ff退出0，213路径，原205全部保留。
- 6776a7退出0：在阻止BaseDatabaseWrapper.ensure_connection的条件下，公开主题基础/slug/版本/规范条目/学者/双理论关系共6组查询分别SQLite与PostgreSQL编译12次；参数数一致，数据库连接0。此前私人10AST/8导入/16SQL的f8a04d及2组轻量slug SQL的47bc34退出0，未运行数据库查询。
- 后端公共9函数9案例、私人11函数19案例，合计20函数28案例；既有test_admin_configuration收藏场景同步。公共/管理预览10场景、私人4场景只定义。fixture接local_cataloging_e2e_api但未运行；统计脚本最初ast.literal_eval遇uuid4调用退出1，改为仅计AST列表长度后b268a1退出0，未执行测试定义。
- catalog0074/reading0020仅编写未应用；无正式功能测试、浏览器、构建、实际迁移、模型/OCR、检索质量测评、索引重建或生产操作。逐图、并发、真实设备和B01–B06仍待全量开发后验收。

## 2026-10-21 PDF62–66学者静态记录

- 最终冻结后全量TypeScript会话95875/04cd3e退出0，覆盖新增两条预览浏览器定义；110路径精确暂存cd9abd退出0，ingestion/views.py仅3行责任范围保留，其他历史改动仍留工作区。
- 最终冻结后新增管理预览4函数/8案例，合计40个新后端函数70参数案例；公共/预览浏览器13场景加私人4场景共17场景，均未运行。新增预览测试纳入后110路径白名单、62 Python AST为408c57退出0；预览3目标ESLint ec8d4b退出0无警告。精确白名单不含tmp、原PDF和其他继承脏改。
- 最终补充：完整109路径白名单中的61个Python文件AST，dce509退出0。检索收口90749a退出0，19文件AST/17模块导入，SQLite/PostgreSQL九种prefix分别按内部None、匿名公开、显式空授权编译，36组SQL及18组EmptyResultSet，实际数据库操作0。独立只读复核确认当前来源门槛、6处session与3处context筛选以及文献回执接线。
- 管理预览新增只读选择覆盖后，spectacular同上述内存配置cea227退出0，205路径/0错误/10既有提示；e7a0b9同步生成并确认204旧路径全部保留。全量TypeScript最终91501/8e422c退出0。此前204路径与67765结果保留为过程记录，不能代替正式运行验收。
- 唯一PDF62/63/64/65/66及两张纯照片裁片均实际读取；68–71只作为下一组预审。源码白名单tmp/stl4-scholars-checkpoint.json，Python采用ast.parse，不执行测试函数。
- 42 Python AST初次21944a退出0。检索13文件最终AST与inspect.signature.bind为4c2c9e退出0，确认allowed_access_statuses关键字一致；完整61文件最终检查另附下方记录。公开学者SQLite/PostgreSQL各7条SQL仅编译；检索12模块导入、两种数据库8条表达式SQL编译e5bfe1退出0，实际查询0，参数数吻合。首次检查误将manager参数假定为1，修正检查程序后通过，未运行数据库查询。
- web目录node node_modules/eslint/bin/eslint.js对白名单32个TS/TSX：c207c5退出0，0错误/12提示（9条图片优化、3条既有导航）。CSS PostCSS解析288顶层节点、91个直接引用class无缺失（fb4461）；不证明实际视觉。
- node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false最终会话67765/c57909退出0，较早87917/afdc9d也退出0。未运行build或浏览器。
- 进程内DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8执行.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-scholars-schema-20261021.json --validate：56d82a退出0，204路径，0错误/10既有Home/Scholar/Topic类型提示。openapi-typescript openapiTS/astToString同步schema/生成类型，724aa5退出0，原203路径保留。
- 新后端学者8函数10参数案例、scope10函数22案例、关注6函数10案例、检索12函数20案例，管理预览补充定义见后续记录，仅定义。新浏览器11公共/管理预览加4私人关注场景，仅定义；旧source-updates场景同步命令信封。合成fixture接入本地启动器，未执行。
- 61文件包含既有首推Discovery adapter依赖；api/ingestion/views.py仅部分暂存3行，旧处理中心改动留在工作区。catalog0073/reading0019仅编写未应用，没有测试、服务、模型、OCR、迁移、索引更新、检索质量测评或生产操作。旧索引id能力、真实环境和209视图/B01–B06待全量开发后统一验收。

## 2026-10-21 PDF58–60阅读路径静态记录

- `ast.parse`精确白名单29个Python文件，3b4135退出0。公共代理另编译10个序列化声明和有界版本历史SQL，私人代理导入模块并分别编译SQLite/PostgreSQL三组owner/计划/回执SQL，均0实际查询、连接为None；没有运行功能用例。
- `node node_modules/eslint/bin/eslint.js <白名单26个TS/TSX文件>`（web）：34b66d退出0，0错误/11条动态图片优化建议。首次根目录运行未发现配置，改用web目录；新hook参数命名和render读取ref的错误已修，26文件最终结果如上。
- PostCSS parse `reading-path.module.css`：c920eb退出0，202顶层节点、四个直接引用组件无缺失class；代理额外复核五组件通过。不证明实际视觉。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：初次98678退出1，修改过程中的替代书目类型与三个旧字段不同步；统一PathSubstitute后，最终5427退出0（92fe95），私人代理87761也退出0。必要后续新修改检查追加记录，不运行正式用例。
- 进程内`DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false`、`DJANGO_DEBUG=true`、`PYTHONIOENCODING=utf-8`运行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-reading-path-schema-20261021.json --validate`。首次8329e5为201路径0错误/11提示；纳入管理两路径后90291f揭示集合继承方法及枚举冲突，修复后9fba86退出0，203路径、0错误/10既有Home/Scholar/Topic类型提示。
- 用openapi-typescript `openapiTS/astToString`同步schema和生成类型，b3cd95退出0，明确断言原194路径无丢失。只使用内存SQLite设置，没有真实库、迁移或队列操作。
- 后端18函数、24参数案例；公共浏览器8场景、私人4场景，均只定义未运行。隔离reading_path_e2e_fixtures与既有启动器接线，未执行夹具。全部正式功能、浏览器、逐图、迁移、资源及生产仍待全量实施后验收。
- 精确源码白名单位于本地tmp/stl4-reading-path-checkpoint.json，共72路径（含文档/契约/装饰照片）。PDF、tmp、真实数据和继承业务脏文件不纳入。

## 2026-10-21 PDF52/53/55图谱静态收口

- 唯一PDF52/53/55及53纯照片裁片实际读取；原图58–60也已逐张读取，仅作为下一组审计，不计本单元完成。49路径白名单见tmp/stl4-graph-checkpoint.py，19 Python文件逐个ast.parse退出0（12f772）；只解析未执行业务代码。
- web下使用白名单过滤15个非generated TS/TSX路径，执行node node_modules/eslint/bin/eslint.js，909d96退出0，0错误/8条img优化建议。PostCSS解析theory-graph.module.css共256顶层节点，5个直接引用该样式的组件类名核对通过。
- web下node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false，43817和最终51834均退出0（bbda3e、498e56）。最终检查包括私人保存、saved_view恢复和两份新浏览器spec。
- 后端图谱SQLite/PostgreSQL共74条ORM SQL仅编译，执行器明确阻止连接/查询；包括四种快照实体、八类边、准确原文StrIndex和当前修订哈希。私人模型/0017声明和owner/回执SQL静态核对通过，未运行迁移。
- 本进程DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，执行.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-graph-schema-20261021.json --validate，7e4983退出0，0错误/10既有Home/Scholar/Topic提示。新增enum命名碰撞已修，未隐藏旧提示。
- openapi-typescript openapiTS/astToString同步api/openapi/schema.json与web/lib/api/generated/schema.ts，2c2472退出0；194路径保留原191。
- 后端18函数48参数案例、7公共图谱和7私人保存浏览器场景，以及真实隔离图谱fixture均只编写未运行。覆盖准确来源、三层/同名身份、真实分页、候选双权限、回执丢失/重试、owner变化、已删除回执防复活。没有正式测试、服务、浏览器、构建、实际迁移、检索质量评测或生产操作。实际PDF/OCR环境仍待核实。

## 2026-10-21 PDF56/57时间线静态收口

- 唯一PDF56/57及纯照片hero已实际读取。按tmp/stl4-timeline-checkpoint.py精确55路径取25个Python文件，ast.parse退出0（278567）；13个测试函数34参数案例只计AST、未运行。
- web下node node_modules/eslint/bin/eslint.js检查四时间线路由、theory-system-admin、theory-timeline-public-view/page/workspace、timeline-event-details/picker、timeline.types/server、knowledge.types及两spec，共15文件，退出0（9ebf35，0错误/3 img建议）。同一工具调用中的白名单脚本因web工作目录找不到Python未执行，随后已在根目录278567单独成功，不影响ESLint结果。
- PostCSS解析theory-timeline.module.css为215顶层节点；样式引用核对退出0。全量node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false最终66497退出0（87633a）；前一轮类型检查修复节点子页timeline参数、空筛选类型和关系数组交叉类型后80010退出0。
- SQLite/PostgreSQL各5条ORM SQL仅编译，覆盖作者快照、准确版本/相关作品、作者关联、year/type聚合和排序。占位符与参数数一致，ensure_connection明确拒绝连接，未查询数据库。
- 完整spectacular首轮45abab退出1，Windows应用控制阻止PyMuPDF原生DLL。11模块fitz延迟到21个实际使用函数，25 Python AST包含这些改动；单独对11模块剔除导入后业务AST与HEAD一致，静态导入不载入fitz/pymupdf并禁止DB连接。未执行PDF。
- 本进程DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，执行.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-timeline-schema-20261021.json --validate，最终93213e退出0，0错误/10既有Home/Scholar/Topic提示。中间18提示的5旧字段和3列表方法冲突均已修。
- openapi-typescript openapiTS/astToString同步api/openapi/schema.json与web/lib/api/generated/schema.ts，0fbe8c退出0；191路径，原188无删除。
- 13公共浏览器与2管理场景、合成隔离fixture已编写，未运行；公开/隐藏次版、来源变化、日期精度/0年、筛选统计、键盘、移动和发布分离均待统一功能验收。0071未应用。没有正式测试、浏览器、构建、检索质量评测或生产操作。

## 2026-10-20 PDF50/51/54子学科与目录静态收口

- 实际读取唯一final-r2 PDF50/51/54及下一单元52/53/55–57原图；13张装饰裁片逐项查看，仅纯照片，不是实施页截图。
- `ast.parse`检查本单元白名单15个Python源码/用例/夹具，最终退出0（d82d58）。最初计数辅助脚本对`"x"*241`做literal_eval报错，源码AST本身已全部通过；改为只数AST列表成员后c32465及最终检查通过。没有执行测试函数。
- `node node_modules/eslint/bin/eslint.js app/subdisciplines/page.tsx "app/subdisciplines/[slug]/page.tsx" app/theories/directory/page.tsx components/public/subdiscipline-public-view.tsx components/theory/theory-directory.tsx components/admin/preview/knowledge-page-preview.tsx lib/api/taxonomy.server.ts lib/api/taxonomy.types.ts lib/api/theory-directory.server.ts lib/api/theory-directory.types.ts lib/api/knowledge.types.ts tests/theory-directory-v306.spec.ts tests/theory-overview-v306.spec.ts tests/subdiscipline-v306.spec.ts`（web）：最终f5c25d退出0，14文件、0错误/4条动态图片优化建议。
- PostCSS parse两CSS最终95ec97退出0，subdiscipline.module.css135节点、theory-directory.module.css102节点。只验证语法，不证明实际布局。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：初次44169退出1，因目录status将两个判别值写在同一union成员，导致收窄失败；拆为两个成员后84244退出0。补轻量列表、真实文献分页并生成最终契约后75884退出0（1dc355）。
- 本进程`DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false`、`DJANGO_DEBUG=true`、`PYTHONIOENCODING=utf-8`执行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-subdiscipline-schema-20261020.json --validate`：最终ed08cd退出0，0错误/10条既有Home/Scholar/Topic类型提示。原185路径全部保留，增3条至188。
- 使用openapi-typescript的openapiTS/astToString同步api/openapi/schema.json与web/lib/api/generated/schema.ts，最终eebb32退出0。没有连接真实数据库或运行迁移。
- 新增目录10函数/18参数案例、子学科17函数/27参数案例，合计27函数/45案例；目录8个真实隔离API浏览器场景、子学科20个，共28个，只编写未运行。既有理论总览用例同步目录新标题，夹具启动器接seed_subdisciplines但未执行。
- 交叉审查修复轻量列表、文献48项真实分页、次版证据独立身份、直属条目展开关键词、手机抽屉同条目重开与公开来源收严。ATLAS只标记50/51/54源码接入，正式验收仍待核实。
- 没有正式测试、浏览器、构建、迁移、真实OCR/模型/NAS、检索质量评测、生产清理或部署。检查点只保存本单元57路径，其他继承修改保留。

## 2026-10-20 PDF45–49理论条目静态记录

- 从本单元精确白名单取27个Python文件，`ast.parse`全部退出0；包括0016、两隔离启动/夹具脚本和三份新后端用例。未执行Python业务或测试。
- web下 `node node_modules/eslint/bin/eslint.js` 检查20个理论/历史兼容/隐私客户端、组件、路由与spec，退出0，9条img优化建议，无其他错误/警告。PostCSS解析四份CSS，节点14/12/265/48，退出0。
- web下 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false` 最终52436退出0。此前66525因旧隐私夹具三处缺saved_knowledge失败，修复后66166、2164及最终52436退出0；最终包含旧入口strict、隐私固定owner和新增spec。
- SQLite内存配置下 `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-theory-schema-20261020.json --validate` 最终bb3ada退出0，0错误/10既有Home/Scholar/Topic提示；185路径，原175全部保留，openapi-typescript同步。初版新增字段/枚举提示已修，未将失败写通过。
- 后端新34函数/60参数场景、理论18真实隔离API浏览器场景、隐私新增8合成状态机场景只编写未运行。隔离夹具从并读测试PDF实际提取原文、正式发布，合成人物/释义不作学术事实；初始化真实写请求带CSRF。没有运行服务、浏览器、构建、迁移、检索质量评测或生产操作。
- PDF45–49已实际读原图并实现源码，仍未正式截图对照。旧子栏目完整视觉与独立旧图谱/时间轴、下一组50–57及全站209视图/B01–B06继续实施，检查点不是验收。

## 2026-10-20 PDF40 OCR补齐静态记录

- ast.parse新OCR服务/view/serializer、distribution urls、新后端用例、config schema_urls/settings共7路径退出0；未执行业务。PostCSS解析原Reader CSS143、新OCR CSS49节点退出0。
- web下`node node_modules/eslint/bin/eslint.js components/reader-shell.tsx components/reader/reader-page-thumbnail.tsx components/reader/reader-ocr-status.tsx components/reader/use-reader-ocr-status.ts lib/api/reader-ocr.client.ts tests/reader-ocr-v306.spec.ts`退出0，1条既有头像img提示。
- 全量`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`，39434及最终32523退出0；后者含同owner降权与失效版本入口修改。
- SQLite内存配置spectacular生成tmp/stl4-reader-ocr-schema-20261020.json退出0，0错误/10既有Home/Scholar/Topic提示；openapi-typescript同步175路径，旧174全部保留。
- 新后端19函数39场景、新前端15合成OCR契约场景均未运行，后者自动由现*v306.spec.ts配置收录并依赖隔离真实PDF。未运行测试、浏览器、构建、迁移、OCR/模型/NAS、生产操作或检索质量测评。

## 2026-10-20 PDF41–43静态记录

- 22路径Python ast.parse退出0，31测试函数只解析未执行；PostCSS解析并读CSS120/管理CSS18节点退出0。
- web下node node_modules/eslint/bin/eslint.js检查并读4组件hooks、两client、管理组件/路由/入口、隐私组件/client、reader-failure/reader路由/ReaderShell、两spec和playwright.v306共17路径，退出0，3条img提示。最终6个并读路径复查退出0、1img提示。
- 全量`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`初次空值错误修复后78664退出0，最终49952在schema与恢复修复后退出0。
- SQLite内存配置运行spectacular生成tmp/stl4-parallel-schema-20261020.json，退出0、0错误/10条既有Home/Scholar/Topic提示。首次16提示中的6个新项已修，最终仅旧10项。openapi-typescript同步174路径，原158无删除。
- 来源10、私人15、隐私6个后端函数；8真实API并读及9管理契约浏览器场景，均未运行。真实PDF隔离夹具与启动器、配置已接线但未执行。没有正式测试、浏览器、构建、迁移、OCR/模型/NAS或生产操作。

## 2026-10-20 PDF36–40静态记录

- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-reader-schema-20261020.json --validate`，SQLite内存配置，退出0；0错误/10既有提示，158路径，原151全部保留。openapi-typescript同步成功，首次Windows文件写入失败后重试成功。
- Python ast.parse共10文件退出0，另有serializer构造/三分支SQL编译零查询；PostCSS解析Reader CSS142节点退出0。
- web下node node_modules/eslint/bin/eslint.js检查Reader/8hooks与类型/Viewer/Header/session/适配器/路由/两spec/两MJS共20路径，退出0、1真实头像提示，精确列表见本轮工具执行及READER_20261020。
- web下`node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`，65482及最终57106退出0（后者在最终schema及标签草稿保护后）。无输出，不等于功能验收。
- 新后端13函数26参数案例及7函数11参数案例、前端加载/回执4例和旋转4例，更新8浏览器场景，均只编写未运行。没有正式测试、浏览器、构建、迁移、真实服务或生产操作。

## 2026-10-20 PDF33–35静态记录

7文件AST、5条SQL编译（无DB查询）、10目标ESLint（3个img提示）、CSS146节点均退出0。spectacular以内存SQLite配置生成tmp/stl4-work-detail-schema-20261020.json，0错误/10条既有提示，151路径；openapi-typescript同步。TS首轮40209语言可空错误已修，59028及最终45429退出0。21后端参数案例和3适配器案例仅编写，未运行。未执行正式功能/视觉、浏览器、构建、迁移或生产操作；准确范围见WORK_DETAIL_20261020。

## 2026-10-20 PDF32状态静态记录

Python ast.parse八路径退出0；web下目标ESLint五路径退出0（两个img提示）；PostCSS观点CSS257节点；全量TypeScript session88120退出0。spectacular使用SQLite内存配置生成tmp/stl4-documents-20261020-schema.json，0错误/10条既有提示，151paths，openapi-typescript同步。7后端函数/9参数案例及2浏览器场景未运行。过程中的ESLint时间读取位置错误已修复重跑，不把旧失败记通过。详细文件与命令见单元记录及Git差异。未运行正式验收或部署。

## 2026-10-20 检索单元静态收口

- web下 `node node_modules/typescript/bin/tsc --noEmit --incremental false`，session37376，退出0。
- web下 `node node_modules/eslint/bin/eslint.js` 检查opinion入口/client/hook/route/spec、save/add-list/read-all-pages及所有私人分页调用者，共16路径，退出0。两处新增useEffect依赖提示随后按真实user依赖修正；img提示仍待正式性能验收。此前14路径目录/原文检索ESLint退出0（2条img提示）。
- Python ast.parse 本人历史、services/serializers/views/research_views及两新回归文件，共7路径，退出0；此前catalog/Discovery/提取脚本12路径AST退出0。
- PostCSS parse四份CSS退出0，节点84/235/191/31。仅语法，不证明排版一致。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-search-20261019-schema.json --validate` 使用SQLite内存配置，0 schema errors/10条既有Home/Scholar/Topic提示，150paths；openapi-typescript同步生成。未连接生产、未应用迁移。
- 已编写catalog后端11函数、收藏6函数/9案例、Discovery呈现7函数、控制6函数/8案例、观点历史4函数/6案例、私人边界3函数/16案例；浏览器catalog7、evidence8、opinion5及private分页4案例。均未运行。

补充：两处Hook依赖修正后，目标ESLint无提示退出0；全量TS session64546退出0。85路径严格白名单、全部暂存Python AST、git diff --cached --check退出0，150路径保持全部原接口。

完整功能、PostgreSQL/权限/并发、真实任务与资源、浏览器/逐图验收留待全量实施后；没有构建、检索质量评测、模型/OCR/NAS或生产操作。最终差异白名单与静态补充见本检查点及单元记录。

## 2026-10-19 公共交互检查点

- 各单元目标ESLint、Python AST、CSS解析记录见HOME_SUPPORT_IMPLEMENTATION_20261018、PUBLIC_FEEDBACK_20261018、SOURCE_UPDATES_20261019、SHARED_CITATION_20261019，均只静态检查。合成后端/浏览器用例仅编写，未执行。
- 本进程DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8；`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/public-interactions-openapi.json --validate`最终退出0，0错误/10条旧Home/Scholar/Topic类型提示。新增枚举和列表ID碰撞已消除；第一次类内枚举路径解析失败，改为明确模块常量后重跑成功，未忽略错误。
- `openapi-typescript`的openapiTS/astToString同步schema.json和generated/schema.ts，退出0。原141 paths全部保留，新增7 paths至148；原研究/隐私组件按本单元扩展。
- 全量TS最后运行退出1，包含并行观点入口/证据新文件未完成诊断；不能标为本轮全量通过。冻结的共享引用单元原nullable与fixture错误已修，继续开发后集中重跑。
- tmp/checkpoint-public-interactions.py只将四文档白名单、共享入口、契约与全局记录暂存；读取暂存Python AST和whitespace检查，不运行测试/浏览器/构建/迁移/真实服务/生产操作。ATLAS保持209行22列及原始身份列。

当前阶段：功能开发。全站正式功能、视觉、权限、迁移、性能验收全部待核实；未部署。

## 2026-10-18 公共导航静态收口

- `node node_modules/eslint/bin/eslint.js components/site-header.tsx components/ui/dialog.tsx components/reader-center.tsx components/public/site-footer-view.tsx lib/public-navigation-return.ts tests/public-navigation.spec.ts`（web）：退出0，6文件，0警告。
- PostCSS解析styles/layout/site-menu.css与public-responsive.css：退出0，32/5节点，仅语法。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：退出0。上一在途检查被会话中断后进程不可读取，没有把它当作通过；本次重新取得明确退出0。较早检索新文件曾报4条可空类型错误，修正后本次通过。
- 5个导航合成用例仅编写，未运行。最终PDF18已实际读取，不曾浏览器截图或正式视觉比对。检查点只纳导航白名单与ReaderCenter的section段，不含正在开发的检索/来源/反馈；所有生产操作未执行。

## 2026-10-18 文件、OCR与DOCX静态收口

- 唯一终稿PDF95–98、109–111及209实际读图。没有浏览器/实施页截图/正式逐图回归。本单元为源码接入，实际服务及全站验收尚未执行。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：生成契约后的最终检查退出0。此前并行修改阶段，先因版权说明types未同步、后因OCR/文件fixture新增字段缺失退出1，均补齐后重新检查通过；没有忽略错误。
- `node node_modules/eslint/bin/eslint.js components/admin/library/work-files-workspace.tsx components/admin/library/work-file-actions.tsx components/admin/library/work-file-preview.tsx components/admin/library/work-file-rights.tsx components/admin/library/work-file-public-preparation.tsx components/admin/library/work-library.tsx components/admin/workflow/workflow-editor.tsx components/pdf-canvas.tsx components/research/citation-docx-preview.tsx components/research/citation-manuscript-preview.tsx components/research/citation-audit-parse.tsx components/admin/library/ocr-workspace.tsx lib/api/work-files.client.ts lib/api/work-files.types.ts lib/api/citation-preview.client.ts lib/api/ocr-workspace.client.ts lib/api.ts tests/work-files.spec.ts tests/citation-docx-preview.spec.ts tests/ocr-workspace.spec.ts app/admin/library/works/[workId]/files/page.tsx app/admin/library/assets/[assetId]/ocr/page.tsx`（web）：22路径退出0，0错误/4警告（OCR真实封面/缩略图2条no-img，旧WorkflowEditor2条导航规则提示）。
- `.venv/Scripts/python.exe tmp/checkpoint-files-ocr-docx.py --stage`：68条已复核源码/契约/单元记录精确暂存，补10条全局记录后78路径提交为e310536，63整文件+5按hunk。脚本对暂存Python逐项`ast.parse(git show :path)`及cached whitespace检查退出0。另标准库AST汇总37个暂存Python文件、PyYAML对可选compose overlay仅语法解析退出0；不导入应用或访问数据库。脚本禁止在已有暂存或HEAD变化时重跑，不能作为下一轮通用git add脚本。
- PostCSS解析work-files.module.css和ocr-workspace.module.css退出0，顶层节点164/79。所有语法结果不证明实际布局。
- 仅本进程环境`DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false`、`DJANGO_DEBUG=true`，执行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/files-ocr-docx-openapi.json --validate`最终退出0，0errors/10条原Home/Scholar/Topic类型提示。首次因文件采用动态get_permissions读取schema缺失kwargs失败，增加swagger_fake_view静态路径修复，真实权限未放宽。新增mode枚举碰撞通过共用DocumentRevisionApplyModeEnum命名消除。
- openapi-typescript的openapiTS/astToString同步schema.json与前端生成类型，退出0。结构化对比原126 paths全部保留、内容未变，新增15 paths至141；原MappingPreviewModeEnum改为页码/人工文字共用枚举，没有删减业务契约。
- DOCX交叉审查修复过期请求仍运行/晚到回写、解密前后未重验稿件/预览身份两项问题；12函数/22案例。文件34函数/37案例、OCR18函数/23案例；后端合计64函数/82案例，前端22场景仅编写，未运行。迁移0069/0012仅编写，未应用。
- ATLAS_INDEX更新95–98、109–111和209共8行，仍209行×22列，page/id/image_path/image_sha256逐项不变。全部为源码接入和正式验收待核实。
- 检查点保留必要OCR来源/取消/几何继承实现，排除旧备份、处理中心筛选/仪表盘、旧主流程OCR统计及下一单元帮助/导航/反馈/来源关注。未运行正式测试、浏览器、构建、真实OCR/转换器/模型/NAS、检索质量评测、迁移、生产清理或部署。

## 2026-10-18 反证、隐私和页码映射静态收口

- 最终PDF198–200、223–225、116–118均已实际渲染读取；没有实施页截图或浏览器操作。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：最终退出0。先前一次退出1仅为并行DOCX新文件缺PdfCanvas回调，补实际页数回调后本次重跑退出0；DOCX新单元尚未纳本检查点。
- `node node_modules/eslint/bin/eslint.js components/research/counter-evidence-workspace.tsx components/research/counter-evidence-editor.tsx components/research/counter-evidence-actions.tsx lib/api/counter-evidence.client.ts app/account/research/[id]/counter-evidence/page.tsx tests/counter-evidence.spec.ts components/research/research-session-detail.tsx lib/api/research.client.ts components/admin/library/page-mapping-workspace.tsx components/admin/library/page-mapping-thumbnails.ts components/admin/library/outline-pdf-preview.tsx components/admin/library/work-library.tsx lib/api/page-mapping.client.ts app/admin/library/assets/[assetId]/page-mapping/page.tsx components/reader-center.tsx components/research/privacy-workspace.tsx lib/api/privacy.client.ts tests/privacy-workspace.spec.ts app/account/settings/privacy/page.tsx app/account/settings/privacy/export/page.tsx playwright.auth.config.ts tests/page-mapping-workspace.spec.ts`（web）：退出0，22文件、0 errors/1条隐私封面no-img-element提示。
- `.venv/Scripts/python.exe -m compileall -q api/catalog/models.py api/catalog/migrations/0068_page_mapping_revision.py api/catalog/page_mapping_views.py api/catalog/services/page_mapping.py api/catalog/services/page_label_metadata.py api/catalog/services/knowledge_publication.py api/catalog/urls.py api/catalog/views.py api/catalog/public_response_serializers.py api/catalog/serializers.py api/catalog/services/search_geometry.py api/catalog/services/evidence_envelope.py api/catalog/services/document_intelligence.py api/distribution/serializers.py api/distribution/services.py api/ingestion/tasks.py api/reading/research.py api/reading/research_serializers.py api/reading/research_views.py api/reading/tasks.py api/reading/citation_audit.py api/tests/test_counter_evidence_atlas_20261018.py api/tests/test_page_mapping_20261018.py api/tests/test_resilient_publication_v260.py api/config/settings.py api/config/schema_urls.py api/reading/privacy.py api/reading/privacy_views.py api/reading/privacy_serializers.py api/reading/research_models.py api/reading/models.py api/reading/urls.py api/reading/views.py api/reading/serializers.py api/reading/migrations/0011_reader_privacy_operations.py api/catalog/services/discovery_sessions.py api/tests/test_privacy_atlas_20261018.py`：退出0，37文件；另单独编译api/distribution/views.py退出0，总38文件仅语法。
- PostCSS对counter-evidence.css、privacy.module.css、page-mapping.module.css执行parse：退出0，顶层节点分别122/141/96。
- 使用仅本进程的DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true执行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/counter-privacy-pages-20261018.openapi.json --validate`：最终退出0、10条既有serializer类型提示、0 errors；初次多1条export/erase枚举碰撞，命名ReaderPrivacyOperationKindEnum后消除。更新双页历史来源和可空条件后重新生成，结果相同。
- 用openapi-typescript的openapiTS/astToString同步api/openapi/schema.json及web/lib/api/generated/schema.ts，退出0。全量TypeScript最终检查在此生成之后。
- ATLAS_INDEX记录9个视图，仍为209行×22列，逐项核对page/id/image_path/image_sha256未变。索引只记录源码接入，视觉正式验收仍待核实。
- 新增后端43函数/46参数案例与前端24合成场景仅编写；旧页码73案例保持并适配新流程。没有运行pytest/Playwright/构建/正式E2E/视觉回归、数据库迁移、真实OCR/模型/NAS、检索质量测评或生产动作。静态结果不证明运行行为。
- 提交前核对79个明确路径（78整文件、distribution/views仅Reader相关hunk）；限定git diff --check退出0，来源身份与209×22结构不变，选定私钥/GitHub Token/OpenAI Key模式未命中。继承备份dispatch修改留在工作区，不纳入本单元；该有限模式扫描不等于全仓安全审计。暂存后再次核对79路径、整文件内容及cached diff --check退出0；检查点9a7c68c成功，备份hunk仍保留未暂存。


## 开发期检查

只记录实际完成的命令、退出码和范围。静态成功不能证明服务、数据库、NAS、Provider或公网可用。历史测试报告不覆盖本轮修改。

### 2026-10-16 视觉驱动检索接入静态检查

| 命令 | 结果 | 范围与限制 |
|---|---|---|
| `python -m compileall -q api/catalog/services/retrieval/deep_pipeline.py api/catalog/services/discovery_sessions.py api/catalog/discovery_tasks.py api/catalog/tasks.py api/catalog/discovery_views.py api/catalog/services/discovery_inference.py api/config/settings.py` | 退出0 | 仅语法编译；未启动 Django、Celery、Meilisearch 或推理服务 |
| `git diff --check` | 退出0 | 当前工作区差异；不代表业务行为通过 |
| `node node_modules/eslint/bin/eslint.js components/discovery-search-workspace.tsx lib/api/discovery.types.ts` | 退出0，1条既有警告 | 目标前端文件；`no-img-element` 警告未扩大为错误 |
| `.venv/Scripts/python.exe api/manage.py spectacular ... --validate` | 0 schema errors，10条既有 serializer 类型提示 | 生成并更新 OpenAPI；`--fail-on-warn` 仍会因既有警告退出失败 |
| `node node_modules/typescript/bin/tsc --noEmit --pretty false` | 退出1 | 仅报告三个既有 live 测试 TS7022；未定位到本轮深度检索文件 |

第三步检索质量评测按用户要求未运行；正式 E2E、全量功能、浏览器逐图回归、生产迁移和部署仍为待核实。

## 最终验收矩阵

| 门槛 | 核验内容 | 状态 |
|---|---|---|
| B01 | 计划规则/解释、时间估计、完成项和手动调整 | 待核实 |
| B02 | 授权笔记集合持久化、研究/计划隔离、撤销删除失效 | 待核实 |
| B03 | 体检/OCR容量、并发、NAS CPU/内存、取消/部分报告 | 待核实 |
| B04 | 所有者隔离与匿名公开搜索/阅读/下载/复制/引用 | 待核实 |
| B05 | 真实空库、错误/部分结果，无示例学术数据 | 待核实 |
| B06 | 209视图路由/API/移动/桌面/无障碍/性能逐图检查 | 待核实 |
| 接口 | OpenAPI/前端类型/错误/分页/筛选一致性 | 待核实 |
| 数据 | 迁移、保账号清理预演/恢复/真实登录 | 待核实 |
| 发布 | 上传→去重→编目→OCR→预览→发布→撤回→恢复 | 待核实 |
| 检索 | QueryLexicon、活动索引、真实多来源原文、页码 | 待核实 |
| Reader | 连续滚动、目录、书内搜索、选中、批注、引用 | 待核实 |
| 任务 | 持久状态、幂等、迟到结果、重试、取消、部分成功 | 待核实 |
| 运维 | 备份隔离恢复、NAS资源与生产切换/回退 | 待核实 |

最终视觉记录应逐行对应ATLAS_INDEX中的PDF页码、route和state，保存参考区域与实现截图位置、差异及复测结果，不以页面可打开算通过。

### 2026-10-18 阅读计划开发期静态记录

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`：退出0。
- 目标 ESLint（reading-plan-detail/form/plans、reader-collection-list、research-session-list、use-persistent-workspace、private-owner、research.client、reading-plan-workspace.spec）：退出0，1条no-img-element警告。
- `.venv/Scripts/python.exe -m compileall -q api/reading/research.py api/reading/plan_rules.py api/reading/research_serializers.py api/reading/tasks.py api/reading/local_analysis.py api/tests/test_reading_plan_atlas_20261018.py`：退出0。
- 以进程环境 `DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false` 运行 `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-plan-schema-20261018.json --validate`：退出0，0 schema errors、10条既有类型提示。随后openapi-typescript生成成功。未连接生产库。
- Git依赖静态导入清单与45文件恢复检查点见CHECKPOINT_DEPENDENCIES；`git diff --check`与该批`--cached --check`退出0。
- 后端 `test_reading_plan_atlas_20261018.py`、前端 `reading-plan-workspace.spec.ts` 与auth-bootstrap新增用例均只编写，未执行。B01/B02/B04新增行为与B06逐图对照仍待正式验收。

### 2026-10-18 引文体检开发期静态记录

实际参考：仅由最终PDF渲染并读取第208–215页。实现页未打开浏览器、未截图、未与PDF做正式视觉回归。

| 命令/操作 | 结果 | 范围与限制 |
|---|---|---|
| `node node_modules/typescript/bin/tsc --noEmit --pretty false`（web目录） | 退出0 | 全量类型静态检查；最终含打印与上传源码 |
| `node node_modules/eslint/bin/eslint.js 'components/research/citation-*.tsx' components/research/reader-collection-list.tsx lib/api/research.client.ts 'app/account/citation-audits/**/page.tsx' 'tests/citation-audit-*.spec.ts' playwright.auth.config.ts`（web目录） | 退出0，0警告 | 新页面/组件/API/回归用例与配置，只做静态检查 |
| `.venv/Scripts/python.exe -m compileall -q api/reading/citation_audit.py api/reading/research.py api/reading/research_serializers.py api/reading/research_views.py api/reading/tasks.py api/tests/test_citation_atlas_20261018.py api/tests/test_private_research.py` | 退出0 | 不执行数据库、任务、OCR或模型 |
| Node/PostCSS `parse` 读取citation-audit.css、citation-audit-upload.css、citation-source-preview.css | 退出0，123/84/40个顶层节点 | 语法可解析，不代表排版或打印效果通过 |
| `.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-citation-schema-20261018.json --validate` | 退出0；0 errors，10条既有serializer类型提示 | 进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true；未连接生产库。openapi-typescript随后同步成功 |
| `git diff --check -- <本单元明确文件清单>` | 退出0 | 仅换行提示，没有空白错误；检查点不包含其他继承改动 |
| 限定检查点文件的private-key/provider-token/credential-url模式扫描 | 无命中 | 有限模式静态检查，不能代表所有秘密类型都已证明不存在 |

新增后端test_citation_atlas_20261018.py共11项，前端citation-audit-workspace.spec.ts共6项、citation-audit-upload.spec.ts共3项；旧扫描用例按显式scan_ocr/旧记录兼容更新。均仅编写，未执行。重点覆盖批量原子性/owner、检查项、同请求指纹、失败恢复容量、人工历史、撤回来源、409输入保留和打印快照清理。真实锁并发、NAS负载、OCR/Provider、打印、路由与209视图仍待统一验收。第三步检索质量评测、迁移、部署和清理未运行。

本单元37文件提交前的 `git diff --cached --check` 退出0；ATLAS_INDEX静态比对确认仅208–215八行语义变更、仍为209行22列，来源身份及其他行保留。源码检查点50cf8ed；后续仅补记提交号。

### 2026-10-18 稿件版本与目录校准静态记录

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`，web目录：最终退出0。
- `node node_modules/eslint/bin/eslint.js components/admin/library/document-outline-workspace.tsx components/admin/library/outline-edit-state.ts components/admin/library/outline-pdf-preview.tsx components/admin/library/work-library.tsx components/pdf-canvas.tsx lib/api/document-outline.ts lib/api/curation-workspace.client.ts components/research/citation-audit-versions.tsx components/research/citation-audit-report.tsx components/research/citation-audit-issue.tsx lib/api/research.client.ts tests/citation-audit-versions.spec.ts tests/document-outline-workspace.spec.ts playwright.auth.config.ts 'app/admin/library/assets/[assetId]/outline/page.tsx'`：发现并修正函数名被识别为hook、props重新赋值和memo依赖规则后，目标文件检查最终0错误/0警告，退出0。
- `.venv/Scripts/python.exe -m compileall -q api/reading/citation_audit.py api/reading/research.py api/reading/research_views.py api/reading/research_serializers.py api/catalog/outline_views.py api/catalog/services/document_outline.py api/tests/test_citation_versions_20261018.py api/tests/test_outline_atlas_20261018.py api/tests/test_document_outline_20261013.py`：退出0；仅语法编译。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-versions-outline-schema.json --validate`：使用.venv Python及进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true；退出0，0 errors/10条既有类型提示。随后openapi-typescript/astToString同步api/openapi/schema.json和web/lib/api/generated/schema.ts，退出0。
- PostCSS解析document-outline.module.css与citation-audit.css：退出0。限定本轮文件`git diff --check`退出0，仅已有换行提示。
- ATLAS_INDEX静态比较：209行/22列、UTF8 BOM保留，仅112–115/211/212/215七行语义改变，图片身份/哈希/来源页及其他行均保留。211打印缺口按已存在的实际实现修正，不表示打印运行通过。

新增citation版本13个测试函数/14参数案例、outline12个单例及3个clear_position参数案例，共29个后端场景；前端版本3项、目录6项，共9项。仅编写，未执行。沿用并保留旧目录测试，原明确采用输入补充confirmed。新spec已加入playwright.auth.config.ts。不存在本轮正式测试通过、浏览器通过、真实OCR/Provider/NAS可用或像素一致的结论。未运行迁移、部署、数据清理和检索质量评测。

稿件版本12文件检查点45c669a、目录校准18文件检查点0fe3a8e分别保存。两批提交前的`git diff --cached --check`均退出0；明确文件清单之外的历史未提交成果保留，未做reset/clean。

### 2026-10-18 笔记授权、私人来源与解析工作台静态记录

仅实际读取final-r2的205–210页及此前已读取的211–215页。没有打开实现浏览器或进行正式逐图对比。

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`（web）：退出0，含新页面、客户端和全部新增回归源码；生成契约同步后再次检查退出0。
- 目标ESLint覆盖confirmed-notes-workspace、research-memory-reminders、research-session-detail、memory.client、research.client、confirmed-notes路由、citation组件/路由、两项新spec/旧upload spec及playwright.auth.config：退出0，1条真实封面no-img-element警告。
- `.venv/Scripts/python.exe -m compileall -q`覆盖config/settings、reading的citation_audit/citation_sources/research/research_models/research_serializers/research_views/urls/tasks、0010，以及test_citation_private_sources_20261018/test_citation_atlas_20261018/test_citation_versions_20261018/test_confirmed_memory_atlas_20261018/test_private_research/test_private_research_completion_20261014，16文件退出0。
- Node/PostCSS parse：confirmed-notes.module.css 103个顶层节点、research.css 230、citation-audit.css 245，全部退出0。仅语法证据。
- 进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，执行`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-memory-private-schema-20261018.json --validate`，最终退出0、10条既有serializer提示/0 errors。新增kind/action枚举歧义用明确Enum名称修正，openapi-typescript同步成功。
- 新后端笔记14函数/17参数案例、私人来源13函数/18参数案例；新前端笔记6场景、解析/来源11场景，仅编写。旧private_research/citation/version/upload用例保留并适配明确授权、purpose与实际依据契约。

未执行正式测试、浏览器、构建、视觉回归、OCR/模型/NAS、检索质量评测、迁移、部署或清理。静态检查和检查点不等于B01–B06或209视图验收通过。

本单元51文件准确白名单核验及`git diff --cached --check`退出0；限定private-key/provider-token/credential-url模式扫描无命中。ATLAS_INDEX保持209行22字段，仅205–215记录更新，图像来源身份字段与其他行不变。检查点1d19dd5。

- 2026-10-21阅读路径最终预览补查：8文件ESLint e5869a退出0（2个既有img建议）；全量TS session56556最终205061退出0；差异检查b3e533退出0。阶段和材料双向选择按稳定ID同步，新增两条管理场景后本单元浏览器定义14条，均未运行。

## 2026-10-22 搜索与提醒静态检查

- `.venv/Scripts/python.exe tmp/stl4-today-static.py`：24组SQLite/PostgreSQL SQL编译，ensure_connection强制阻断，0连接；6改动Python文件ast.parse。未执行接口或数据库功能。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-admin-search-schema.json --validate`，DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true：50bdba退出0，0错误/10既有Home/Scholar/Topic类型提示。按已有openapi-typescript生成法同步，221路径保留原219。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：38293/61b156退出0。
- ESLint目标admin-dashboard/admin-shell/admin-work-notices/search/page/today-work-atlas与auth-bootstrap：a6b0ee/fac9a7退出0，1img提示。postcss解析stl4-admin.css54、today-work.module.css62顶层节点。git diff --check 945234退出0。
- 后端新增5函数、前端新增3场景仅定义，所有正式测试/E2E/浏览器/构建/迁移/生产均未运行。PDF124–127为只读源图，未截图实现或宣称逐图通过。
