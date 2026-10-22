# 读者账户、隐私接口与夜间外观

前置检查点 `8a491d1`。用户要求继续全站开发、不运行测试、不使用浏览器检查，同时核对账户与读者中心的接口关系，并提供夜间模式参考与交互页面。本文件记录源码实施和阅读证据，不代表运行、视觉或生产验收。

## 视觉依据与交付物

唯一依据仍是 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf`。本单元实际查看第 10、18、183、185、189 页提取图，未引入其他设计稿。第 10 页页头搜索和菜单之间加入 40px 月亮/太阳按钮，菜单底部和读者设置共用白昼、夜间、跟随系统选择。夜间使用暖炭黑、暖白正文、砂金强调；默认保持终稿纸白。

三张 imagegen 参考分别展示页头入口、夜间读者中心、菜单完整设置。生成图仅为用户要求的扩展设计示意，图中书封与条目不写入业务库，也不当作 PDF 对照证据。

独立交互文件 `output/preview/stl4-appearance-preview.html` 支持日夜/系统、菜单、390px 左右的手机预览宽度、键盘页签和空资料搜索。纯本地示意，独立 storage key，不接真实账户。已请求在 Codex 打开文件，未使用浏览器运行或截图。该输出不提交到源码检查点。

注意第 189 页实际是会话过期后的登录浮层、返回原页及可选访客记录转存，并非设备会话管理。图像优先于 ATLAS_INDEX 中 `/account/sessions` 路径提示；后续按实际图补齐，不能以新增设备列表代替。

## 实施的外观链路

- RootLayout 加载预绘制外观脚本与 AppearanceProvider。新浏览器默认 light，明确选择 system 时才读取系统外观；媒体查询变化与其他标签页的外观 storage 变化同步生效。
- 原 `library_text_size`、`library_font_family` 保留；新增 `library_theme` 只存非敏感外观选择。存储禁用时明确提示仅当前页面生效。
- 页头、后台页头、认证页、菜单、账户设置和阅读器共用偏好。阅读器不再维护独立 dark 布尔值；不对扫描原页、书封或图像整体反色。
- `PATCH /api/auth/me/` 的原 ReaderProfile JSON 增加 theme=light/dark/system；保留其他隐私/研究键，不迁移表。User 与 ReaderProfile 在事务中按顺序加锁，合并局部字段，避免并发设置覆盖。
- 偏好读取和写入绑定账户，取消过期请求，保存按本标签页顺序发送。失败不宣称同步成功，用户可再次选择重试。网络超时不等于服务端回滚，跨设备同时选择以实际最后保存为准。
- 新 appearance.css 覆盖共用色值。主页、页头、菜单、读者中心/研究/计划/引文体检及三个私人工作台中已读的颜色用夜间变量加原值回退，不改白昼尺寸或原图。仍需逐个剩余模块补齐局部硬编码颜色，不能宣称全站深色视觉通过。

## 账户接口核对

下表的“已连接”是源码中的路由和调用链，不等于本轮实际执行过业务。

| 资料或能力 | 原接口（`/api` 下） | 读者入口与归属核对 |
|---|---|---|
| 身份、显示名称、外观 | `auth/me/` | 读者中心账户设置；只处理 request.user，ID/邮箱/角色只读，不能借此提权。新增可选 X-Reader-Owner、private/no-store、Vary。 |
| 能力与退出 | `auth/capabilities/`、`auth/logout/` | 继续原角色能力表；退出可绑定当前显示账户，避免旧页面退出另一个刚登录的账户。 |
| 阅读进度、文献收藏、主题收藏 | `reading/progress/`、`saved/`、`saved-topics/` | 总览/更多资料；OwnedModelViewSet 过滤 user，创建由服务端写当前 user；主题收藏继续原请求回执。 |
| 高亮、划线、笔记、书签 | `reading/annotations/`、`annotations/note-groups/`、`bookmarks/` | 读者中心、笔记页与原阅读器互通；当前账户限定，原文状态继续由原序列化与阅读权限处理。 |
| 私人书单与条目 | `reading/lists/`、`lists/{id}/add_item/`、`items/{id}/` | 读者中心书单；父书单归属查询，创建强制当前 user，新增文献要求当前公开的主要出版版本。删除增加明确选择，馆藏与笔记保留。 |
| 阅读历史 | `reading/history/` | 原账户阅读历史；user 过滤且遵守 privacy_retention。本轮补统一账户切换及禁止缓存响应。 |
| 研究与轮次 | `reading/research-projects/`、`research-turns/` | `/account/research` 和详情；user 或 project__user 过滤，管理员身份不扩大查询。修正“我的研究”导航原先指回总览的问题。 |
| 阅读计划 | `reading/reading-plans/`、`path-follows/` | `/account/plans`、详情及公开路径加入计划；当前 user 范围，共用原 PersonalReadingPlan。 |
| 引文体检、私人原文与 PDF 预览 | `reading/citation-audits/`、`citation-sources/`、各自 `preview/` | 引文核验工作台；CitationAudit 按 user、purpose、UUID 查询；预览文件继续 nosniff、sandbox 和禁止缓存。 |
| 已确认认识与授权记忆 | `reading/research-memories/`、`research-account/` | 已确认笔记和研究/计划使用设置；候选不会自动成为已确认记忆；原用法仍要求逐项上下文授权。不能把确认计数理解为默认允许全站调用。 |
| 来源关注、图谱保存、并读 | `reading/source-follows/`、`saved-knowledge/{id}/`、`graph-views/`、`parallel-tasks/` | 来源更新、知识页和并读入口；本人查询。公开校准/后台审阅是单独权限路由，不把私人任务列表公开。部分资料仍需完整聚合进 R22 资料表。 |
| 隐私开关、分类导出与删除 | `reading/privacy/`、`privacy/items/`、`privacy/operations/` | 账户设置接 `/account/settings/privacy` 和 `/export`；本人选择、版本核对、先准备影响再确认删除，原任务回执/取消/过期恢复保留。 |
| 兼容完整 JSON 导出 | `reading/export/` | 原导出按钮；只从当前 user 关联取数据。本轮补发起账户验证。大量资料宜走现有分类异步导出；不把此旧同步接口描述为无容量限制。 |
| 个人模型配置、原问答会话与流 | `reading/library-assistant/connection/`、`library-conversations/`、`library-messages/` | 账户设置增加原问答入口 `/explore?mode=ask`。原密钥加密且只返回是否配置；本轮旧问答按 owner 重建，JSON/流请求带 owner，账户切换取消、清空内容与未保存密钥。 |
| 荐书 | `reading/submit/` | 当前账户生成 mailto，用户邮件应用确认发送；不直接上传或自动发信。补身份验证并限制返回链接为 mailto。 |

`common/private_responses.py` 统一可选的 X-Reader-Owner 核对和 `private, no-store`，合并 Vary，保留流接口已有 no-transform。Reading 的原 PrivateResponses 名称作为兼容入口，原 queryset 和权限类仍是实际授权边界。缺少 header 不会获得任何额外数据范围；新前端操作均主动发送 header。

## 本轮修复的缺口

1. 原显示偏好直接 PATCH、没有发起账户校验或取消保护，且晚到读取可能覆盖手动选择。改为共用 provider、变更序号保护和串行保存。
2. 原 ReaderCenter 写操作没有与发起账户绑定。新增统一 privateRequest，并按账户 key 卸载旧状态，取消请求；原 readAllPages owner 过滤继续复用。
3. 原阅读历史、身份、个人模型和旧问答等私人响应没有统一缓存边界。接共用保护；模型/会话仍用原服务，不建立第二套账户或问答库。
4. 原问答 bootstrap 依赖角色，两个同角色账户切换可能保留旧组件内容。改为按账户 ID 重建工作区，并保护包括流读取在内的请求。
5. 读者中心缺少清楚的分类数据操作入口，“我的研究”导航未进入真实列表，现已接好。

## 权限结论与未完成事项

访客仍可使用公开搜索、阅读、下载、复制和引用。登录 reader 获得自己的资料持久化能力，不自动获得后台。editor、admin、System Owner 的业务能力沿原 capability_snapshot；管理员管理账户权限不等于读取他人的私人研究正文。

这次未执行登录切换、实际导出/删除、模型请求、浏览器点击或全站业务验收，也没有连接生产。不能据此宣称全部接口无漏洞。剩余 R22 跨类型资料表、分页/筛选/批量流程、PDF185 访客记录显式转存、PDF189 重新登录浮层、其他 R28–R31 页面和全站局部夜间颜色继续按图实施。旧兼容导出的容量、撤回文献在旧历史摘要中的展示边界仍需继续核查。209 图统计不因按钮完成而变化。

## 恢复与验证

不要重新运行本单元的一次性颜色替换或代码替换片段。原 `web/styles/tokens/design.css`、`web/styles/features/admin/workspace-v307.css` 及其他继承脏改未暂存。

只做源码静态检查：7 Python 文件 AST、TypeScript noEmit、目标 ESLint。详细执行结果记录在 VALIDATION。没有运行测试、构建、浏览器、模型/检索质量评测、数据库迁移或生产操作。交互 HTML 与 imagegen 输出保留在本地，源码检查点只纳入明确代码和文档白名单。

## R22接口接续

详见READER_OVERVIEW_20261023与READER_MATERIALS_20261023。读者总览真实七类owner聚合；所选导出/删除复用原隐私任务；作品收藏纳入数据管理；本机研究显式转存复用原import并补删除后最小回执。reading0022迁移尚未执行，运行边界待统一验收。


## R29书单补充

2026-10-23：/account/collections直接使用本人原书单，directory/workspace/command/receipt/export必需owner；笔记/进度导出默认不勾选，原来源授权复核。书单移除只影响关联、30天内可恢复，整单删除不删独立计划/笔记。新的0023未执行；复制私人入口不公开，显式分享仍待。见BOOKLIST_WORKSPACE_20261023，未测试或运行验收。
