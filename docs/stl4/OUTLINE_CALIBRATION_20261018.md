# 自动目录与跳转校准接入

状态：源码已接入，统一功能和视觉验收待核实。唯一视觉依据为最终PDF第112–115页，已用Poppler直接渲染并实际读取四页图像。

## 页面与继承关系

`/admin/library/assets/[assetId]/outline`从馆藏版本的当前阅读文件进入，沿用管理会话与权限。桌面由目录树、节点详情、当前PDF预览三栏组成，下方提供真实候选来源对照；移动端可在目录、详情、预览间切换。另有修订历史、读者入口和提取任务状态。

复用既有DocumentOutlineRevision、ProcessingJob、目录提取及PdfCanvas，不建立平行目录服务。支持层级调整、同页多节点、子树顺序、印刷页码、物理页、目录来源页、页内落点、逐项/批量确认、保存候选、明确采用、恢复历史、重建/取消/重试。所有书目和页数均由实际API返回；无目录、未发布和文件不可用显示真实状态。

## API与安全边界

- `GET /api/catalog/admin/assets/{id}/outline/`返回active/latest/history/jobs及实际asset摘要；`revision_id`读取完整历史修订，`history_page`分页。后台PDF沿既有`/distribution/admin/assets/{id}/preview/`读取，owner前后核对，退出或换账号清理blob。公开Reader入口只在来源正式可读时返回。
- `POST action=edit`携带`request_id`、全局`expected_revision`、实际编辑基准`base_revision_id`与nodes。保存仅新增候选修订，不直接采用。单节点改变不得把其他节点自动标为人工确认。
- `calibration_status=confirmed`表示本人本次明确核对。更改标题、父级、页码或位置时前端撤回旧确认；后端不允许人工伪造native/matched/generated。未修改节点保留真实来源和定位。
- `clear_position=true`清除旧PDF点坐标及来源locator，不再暗中继承；本次明确提供的normalized_position仍可保留。印刷页码允许罗马数字与分段标签，不猜全书统一偏移。
- `adopt/restore`要求非空目录、范围内物理页以及每项confirmed/native，均新增修订。原历史和文件保留；已采用人工目录不会被自动重建覆盖。此操作只更新目录，不发布尚未公开书目。
- 候选仅来自实际书签、印刷目录及正文标题。每节点最多返回50条，count标示实际总数，不编造置信度。候选字段只供后台，公开目录剥离这些尚未采用的观察。
- 后台读取需CanAccessBackOffice；编辑/采用/恢复需can_edit_metadata；重建及任务动作需can_retry_jobs。API仍是权限与来源资格的最终判定者。
- 409保留输入，支持核对差异后另存新修订，继续使用原base_revision_id与确认时固定的最新expected_revision；并发修订及active目录均保留。复用已有未保存导航保护，不将目录草稿写入localStorage。

## 验证与继承测试

新增`test_outline_atlas_20261018.py`覆盖来源、人工确认、基准修订、公开边界与坐标清除，`document-outline-workspace.spec.ts`覆盖编辑、冲突另存、候选、独立采用、同页节点与账号变化；均仅编写未运行。原先未提交的`test_document_outline_20261013.py`保留全部场景，只给原本明确采用的测试输入补上confirmed，纳入本单元检查点，避免遗失早期成果。

TypeScript、目标ESLint、Python语法、CSS解析与接口生成结果见VALIDATION.md。严格像素/移动布局、键盘焦点、真实PDF和任务运行效果仍待统一验收。本单元不迁移数据库、不部署、不清理生产数据。
