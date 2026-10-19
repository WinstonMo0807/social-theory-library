# 来源状态与私人订阅更新

2026-10-19。源码已接入，静态检查完成项见下；正式功能与视觉验收待核实，0013 迁移未执行。

## 唯一视觉依据与范围

实际读取 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 的第17页第4状态。查看的是此前从该 PDF 提取的 `tmp/pdfs/stl4-home-support-20261018/page-017-visual.jpeg`，未使用旧单图或图集外框作为页面内容。来源信息采用真实封面、题名、类型、公开状态、实际PDF页序/印刷页标签、更新时间与核对时间；恢复/当前版本、订阅更新和来源纠错连接实际业务。颜色服从主约定的炭黑、纸白、暖灰与砂金。

`/account/source-updates` 是为 PDF 中订阅更新动作补齐的本人工作台，沿用当前读者中心与来源卡样式，不声称 PDF 有一张独立订阅管理整页。来源历史记录实际观察时间，既不填图集示例文献，也不将公开发布状态当网络探活结果。

## 调用链与权限

- 匿名 `GET /api/reading/source-status/?path=` 复用既有激活发布修订。仅接受安全站内公开路径。Reader UUID 规范化，订阅身份去除页码与其余查询；展示时保留合法 Reader 页序。无外部请求或邮件。
- 公开元数据只从当前 activated snapshot 读取，旧 Reader 必须有 active/superseded 发布关联。私人、原始、未发布、撤回或不存在来源返回通用不可用，不回泄旧题名/封面。当前文件须同一 Edition、normalized、ready、valid、公开权限且有文件才给阅读入口。新正式文件不能自动换算旧页码。
- 本人 `GET /api/reading/source-follows/?page=&path=`、`POST /api/reading/source-follows/` 和 `GET /api/reading/source-follows/{id}/?history_page=`。管理员不能扩大本人范围。列表/历史每页20，最多500条来源记录。
- POST 明确传 `path/action/request_id/expected_revision`，并要求 `X-Reader-Owner` 与实际 request.user 匹配，不符或缺失403，防止核验后 cookie 更换向另一账户写入。action 为 subscribe/unsubscribe/mark_read；账户锁、唯一 user/path 和 user/request_id、规范输入指纹、修订比较共同保护并发与重试。新增/恢复订阅须仍可核对公开身份。失效的既有订阅仍可取消、读历史或通过隐私流程删除。
- `SourceFollow` / `SourceFollowEvent` 仅保存本人关联、公开来源路径、指纹、状态及动作时间，不复制原文或书目快照。每次读回重新判断当前公开资格。
- Celery `reading.refresh_source_follows` 每15分钟取最早检查的最多200项，逐账户锁复核，仅实际指纹变化写 changed。失败保留旧状态并写 check_error，不能伪造变化。上一批之外的记录按时间轮转，200项并不意味着所有订阅15分钟内全部检查。
- 来源订阅加入既有隐私保留开关、分类导出、逐项删除影响预览和后台任务。关闭保存后拒绝新订阅，并停止记录后续状态变化，保留已有资料，允许取消。导出/下载重核本人、资料修订和当前公开来源；删除级联该来源历史，不删除账户或馆藏。
- 前端复用 `useSessionBootstrap` / `withPrivateOwner` / `usePersistentWorkspace`。身份变化清除本人内容；请求结果未知保留原 request_id 与 expected_revision，锁住相反操作，仅允许重试原请求；409重读，未自动重发操作。重放已处理请求若已有后续变化，以当前状态为准。

## 契约

PublicSourceStatus 状态 available/replaced/unavailable/page；含 path、canonical_path、title、authors、cover_url、source_type、version_label、location、updated_at、checked_at、can_subscribe、reader_url、当前 work/edition/asset/catalog_revision/document_revision ID、notice。无原文正文。

SourceFollow 含 id、owner_id、path、active、revision、created_at、updated_at、last_checked_at、check_error、unread_count、updates_paused、source、notice、分页 history。SourceFollowEvent 仅含 id、action、before_status、after_status、observed_at、revision。

`FeedbackSourceCard({path})` 为反馈表单读取同一匿名公开来源；反馈处理后端也复用相同 resolver。封面使用既有公开资源 URL 规范化。该组件已交反馈单元接入。账户导航入口由主代理接入，未在本单元改写读者中心收藏或主导航。

## 验证与剩余验收

- 11个目标 Python 文件仅 AST parse，退出0，未 import 执行业务或连接数据库。
- 10个目标前端文件 ESLint 退出0，3条既有规则类别的真实封面 img 警告，无错误。
- CSS 静态解析：source-status.module.css 36根节点，source-updates.module.css 41根节点，退出0。
- 全量 TypeScript 首次退出0；新增合成用例后复查退出1，仅并行全局引用单元的 work-citation-panel.tsx 第26/27行 result可能null（TS18047），已通知该单元修复；本单元无TypeScript诊断，最终全量结果由主线记录。
- 新写后端12个测试函数/22个参数案例、前端6个合成场景，仅编写未运行。旧隐私测试夹具增加 source_follows 字段，未改变原断言。
- 未运行测试、浏览器、构建、迁移、模型/转换/真实OCR/NAS、部署、生产清理或检索质量评测。OpenAPI及生成类型由主线集中刷新，不把本单元类型定义当作生成契约已经完成。

静态命令在工作区根目录以 `.venv/Scripts/python.exe` 的 `ast.parse(Path(name).read_text(encoding='utf-8-sig'))` 逐项读取上述11个Python路径；前端在 `web` 运行 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`，以及 `node node_modules/eslint/bin/eslint.js` 加本单元10个TS/TSX路径；CSS采用现有 `postcss.parse` 读取两模块文件。所有测试仅写入，未执行。

## 保存白名单

本单元不自行提交，交主线合并检查点。代码依赖同批反馈单元 `catalog.services.public_feedback.safe_public_path`；0013依赖0012。读取源码入口和后台任务注册不能漏交。

新增文件：

```
api/reading/source_models.py
api/reading/source_follow.py
api/reading/source_follow_views.py
api/reading/migrations/0013_source_follow.py
api/tests/test_source_follows_20261018.py
web/lib/api/source-follows.client.ts
web/components/public/feedback-source-card.tsx
web/components/public/source-follow-control.tsx
web/components/public/support-source-status.tsx
web/components/public/source-status.module.css
web/components/research/source-updates-workspace.tsx
web/components/research/source-updates.module.css
web/app/account/source-updates/page.tsx
web/tests/source-updates.spec.ts
docs/stl4/SOURCE_UPDATES_20261019.md
```

共享修改：

```
api/reading/models.py
api/reading/privacy.py
api/reading/privacy_serializers.py
api/reading/tasks.py
api/reading/urls.py
api/config/settings.py
web/lib/api/privacy.client.ts
web/components/research/privacy-workspace.tsx
web/tests/privacy-workspace.spec.ts
```

`api/reading/urls.py` 同时有另一个全局引用单元的 shared_citation_views 导入及 citation-preview 路径，应按两个单元依赖一起保存或分hunk纳入，不得漏掉它的源码。settings只需本单元 refresh-source-follows beat项；其他继承修改原样保留。
