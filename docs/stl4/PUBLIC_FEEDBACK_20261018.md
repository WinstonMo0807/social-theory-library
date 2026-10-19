# 公众反馈与管理员处理（2026-10-18）

唯一视觉依据为 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf`，已实际读取第 16 页反馈表单和第 17 页相关状态。反馈后台是为这条业务链补充的管理界面，采用现有纸白、暖灰、炭黑、砂金管理语言。第 170–172 页是检索质量评审，不属于本单元，也没有执行该评测。

## 已接入的业务

- 复用 `PublicFeedback`，新增使用咨询、改进建议并兼容旧引用/无障碍分类。原始正文、联系信息和提交时间不可通过处理接口修改；旧 5000 字正文保留，新提交限制 4–500 字，联系邮箱可选且最长 254 字。
- 匿名与登录读者均可提交。必须明确同意处理用途；记录用途版本和时间。公开回执仅包含真实 ID、原请求 ID、状态、时间和接收说明，不回显正文、邮箱或账户。
- 提交使用 UUID 幂等键及绑定规范化正文、类别、路径、邮箱、提交者和同意的 HMAC。首次 201、相同请求重放 200、同键不同内容或提交者 409。未知响应保留原稿和请求；前台写入不自动刷新并重放认证请求。
- 相关页面只保留站内公开路径和可核对的 Reader 物理页，剥离其他查询参数与片段；拒绝账户、后台、外部地址、反斜线、控制字符、点路径、异常编码和编码逃逸。前后端采用相同规范化规则，重复页码不保留。独立来源单元提供权威公开书目和状态，不接受浏览器传入的题名或封面作为来源事实。
- 表单的相关页面卡已接来源单元 `FeedbackSourceCard`，显示权威题名、封面、作者/版本、物理页和状态；加载/错误可见，保留更换、移除及错误重试。后台详情也复用同一 resolver。
- 提交端有独立每分钟 6 次/每日 30 次预算，以账户或连接来源形成不可逆缓存键，外部转发与内部调用标头不绕过预算。没有记录原始 IP 到反馈表。
- `/admin/support/feedback` 接入真实列表、关键词、类别、状态、全量计数、分页、详情和处理历史。仅实际管理员/系统所有者能读写，前端使用 `can_manage_users` 显示门槛，API 以 `IsLibraryAdmin` 独立核验。
- 处理采用行锁、`expected_revision` 和 UUID 幂等键，复用 `AuditEvent` 保存处理前后状态。解决或重新打开需要说明；只有明确同意且留有邮箱的未解决反馈可标记人工回复。标记不发送邮件，处理说明不公开。
- 后台草稿在冲突时保留并展示新修订，需显式核对后继续。响应未知及 408/429 保留同一修改键重试；401 不自动重放写入。会话变更清除私有读取和草稿，历史及详情响应均 `private, no-store`。

## API 契约

- `POST /catalog/feedback/` 输入 `{request_id,category,body,contact?,path?,consent:true}`，返回 `{id,request_id,status,created_at,message}`。
- `GET /catalog/admin/public-feedback/?q=&category=&status=&page=` 返回 `{count,page,page_size:20,counts:{total,submitted,reviewing,resolved},results}`。状态计数在关键词与类型过滤后、状态过滤前计算，不从当页凑总数。
- `GET /catalog/admin/public-feedback/{id}/?history_page=` 返回原始反馈、用途、处理状态/修订、公开来源 resolver 结果及每页 10 条处理历史。历史不回传幂等摘要。
- `PATCH /catalog/admin/public-feedback/{id}/` 输入 `{request_id,expected_revision,status,note,follow_up}`，返回 `{request_id,accepted_revision,record}`。原请求在后续修订后重放仍返回已接受的修订及当前记录。

## 迁移与保存边界

`catalog/models.py` 的 PublicFeedback 两项类别及八项字段共 10 行已先进入 `e310536` 文件/OCR检查点。本单元配齐 `0070_public_feedback_workflow.py`，依赖 `0069_page_text_revision`，不重写旧 Git 历史。新增字段可空或有明确默认值；没有回填历史用途同意、删除旧反馈或更改旧正文。迁移只编写，未执行。

反馈详情依赖同批来源单元的 `reading.source_follow.resolve_public_source`。必须与来源 resolver 及其正式发布资格守卫一起保存后才能部署，不将未提交依赖视为已发布能力。

## 文件白名单

1. `api/catalog/feedback_serializers.py`
2. `api/catalog/feedback_views.py`
3. `api/catalog/services/public_feedback.py`
4. `api/catalog/migrations/0070_public_feedback_workflow.py`
5. `api/catalog/urls.py`（仅反馈导入及两条管理路由）
6. `api/tests/test_public_feedback_20261018.py`
7. `web/lib/api/admin-feedback.client.ts`
8. `web/components/admin/support/feedback-workspace.tsx`
9. `web/components/admin/support/feedback.module.css`
10. `web/app/admin/support/feedback/page.tsx`
11. `web/tests/admin-feedback.spec.ts`
12. `web/lib/api/feedback.client.ts`（与首页帮助单元共用）
13. `web/components/public/feedback-form.tsx`（与首页帮助单元共用）
14. `web/tests/support-feedback.spec.ts`（与首页帮助单元共用）
15. 本记录。

后台菜单与管理路由权限由主线负责，来源卡及公开来源 resolver 由来源单元负责。未修改全局进度、ATLAS、生成契约、reading/views.py 或 reading/serializers.py。

## 静态检查与尚未验收事项

- `node node_modules/eslint/bin/eslint.js components/admin/support/feedback-workspace.tsx lib/api/admin-feedback.client.ts lib/api/feedback.client.ts tests/admin-feedback.spec.ts tests/support-feedback.spec.ts app/admin/support/feedback/page.tsx components/public/feedback-form.tsx`：退出 0，0 错误、0 警告。
- `.venv/Scripts/python.exe` 使用 `ast.parse` 读取上述五个反馈 Python 新/改文件（serializer、view、service、0070、用例）：退出 0。
- `postcss.parse` 解析 `web/components/admin/support/feedback.module.css`：退出 0，97 个根节点。
- 回归用例已编写，涵盖幂等、权限、计数、状态说明、历史、旧数据、限流、路径、冲突、会话、未知保存、408/429 和 401 不重放。**未执行**。
- 未运行浏览器、正式测试、构建、逐图视觉回归、生产操作或迁移。真实数据库并发、代理部署下的限流范围、最终字体/尺寸/移动布局及隐私会话行为留待统一验收。静态通过不证明这些行为通过。
