# PDF 223–225 隐私、导出与删除

2026-10-18。本单元源码已接入，统一功能与视觉验收待核实。

## 视觉依据与范围

唯一依据为 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第 223、224、225 页。使用 Poppler 从该 PDF 直接渲染并实际读取三页，未使用旧图；渲染文件仅在忽略的 `tmp/pdfs/stl4-privacy-20261018/` 内。

新增 `/account/settings/privacy` 与 `/account/settings/privacy/export`。按图接入左侧资料导航、笔记使用范围、保留记录、四类导出选择、真实计数、删除表格、影响预览、任务状态和历史记录；窄屏使用隐私/导出/删除页签与纵向条目。采用当前纸白、白色内容层、炭黑与砂金系统。PDF 224 中的 JSON 导出已接通；没有绘制假 ZIP/CSV 下载，没有使用图中示例馆藏、数字、时间或操作记录。界面不显示“当前接口”等实现用语。

## 数据与权限

- 新增 `ReaderDataOperation`，继承已有 `PrivateResearchRecord` 的本人归属、加密 payload、请求标识与修订。导出任务保存对象清单、修订、子轮次修订和逐项结果，不额外保存可能失效的引文正文。
- 新增 `ReaderSearchRecord`，仅在本人明确开启后，保存后续检索词及筛选条件的加密快照。默认关闭，不追溯复制历史查询。原 Discovery 工作会话继续按原生命周期服务检索与研究，不因删除长期历史而被删除。
- `0011_reader_privacy_operations.py` 新建上述两表，依赖 `0010_citation_private_source`。迁移仅编写，未执行；没有生产数据操作。
- 隐私偏好保存在既有 `ReaderProfile.reading_preferences` 的 `privacy_retention` 与 `privacy_revision`，不改身份、密码哈希、角色、凭据或账户关联。缺 profile 读取按默认值，保存时在 owner 锁内建立 profile。
- 阅读历史默认兼容既有记录行为；关闭后不新增历史，阅读进度保留。个人笔记关闭后拒绝新建 annotation/memory 并明确保留未保存输入，已有内容仍可编辑。关注主题关闭后不新增关注。关闭设置不会删除已存资料。
- 笔记确认仍不等于授权。全局自动使用固定关闭，使用范围通过已有已确认笔记工作台逐条选择研究或阅读计划。没有新增无差别使用笔记的全局开关。
- 所有新响应本人过滤、`private, no-store`。前端使用现有 `usePersistentWorkspace` 与 `withPrivateOwner`，请求前后校验 cookie owner，切换账号清除内容。旧 `/reading/export/` 同步接口继续保留，增加 no-store、真实来源复核及新检索历史/操作结果；旧账户下载入口加入 owner 前后核验。

## 接口

| 方法与路径 | 行为 |
| --- | --- |
| GET `/reading/privacy/` | owner、偏好修订、四项 retention、确认笔记与授权范围计数、各类资料真实总数、最近任务与偏好变更记录 |
| PATCH `/reading/privacy/` | `{expected_revision, retention}`；并发设置修改返回 409 |
| GET `/reading/privacy/items/?category=…&page=…` | 阅读历史、搜索记录、个人笔记、阅读计划、关注主题的本人清单，服务端分页每页 20 项，真实总数和对象修订 |
| GET `/reading/privacy/operations/` | 本人分页操作历史 |
| POST `/reading/privacy/operations/` | 导出 `{request_id,kind:"export",categories:["research","notes","plans","audits"]}`；或删除预览 `{request_id,kind:"erase",targets:[{category,id,revision}]}` |
| GET `/reading/privacy/operations/{id}/` | 实际状态、完成/失败/剩余数量、逐项结果；删除 preview 按当前本人对象提供标题与修订是否变化 |
| POST `/reading/privacy/operations/{id}/command/` | `{expected_revision,action:"confirm"|"cancel"|"retry"}` |
| GET `/reading/privacy/operations/{id}/download/` | 下载已准备项目的 JSON；读前读后核对对象及研究子轮次修订，下载时重新解析来源权限；变化项明确列入 unavailable |

删除条目的叶类别为 `reading_history/search_history/annotations/memories/plans/followed_topics`。研究记录使用整数修订的字符串；旧阅读对象以 `updated_at` 精确值作为修订。导出包含研究及轮次、原笔记与个人认识、阅读计划、引文报告和本人来源信息，不包含 PDF/DOCX 原件、模型向量或凭据。

## 状态、并发与恢复

状态为 `preview → queued → running → completed/partial/failed`，可取消为 `canceled`。Celery 只传 ID、generation 与 task ID。每本人最多 2 个活动任务，单次最多 500 项、导出内容上限 25 MiB；每项独立事务保存结果，失败不抹掉已完成项。超过 10 分钟未更新的活动任务读取时标记中断，允许恢复。

删除必须先预览、明确确认，再逐项处理。确认按钮的勾选绑定预览修订，读取到新的预览修订后必须重新勾选。创建预览、确认与 worker 均复核对象版本与关联影响。取消提升 generation，旧 worker 不再回写。删除重试重新进入影响预览，不能静默采用新内容并立即删除。部分目标已经从其他页面删除时，将其标为不可用失败，其余目标仍可重新预览与继续处理。

锁顺序为本人 → 操作记录 → 相关研究/计划上下文 → 目标记录。旧个人记录 update/destroy 补事务与 `select_for_update(of=("self",))`，避免异步删除后旧 serializer 重建记录，并避免锁到关联公开 Asset 或 PostgreSQL nullable outer join。原 annotation 删除同时撤销关联认识的使用范围，独立认识正文仍保留；删除 memory 则保留原 annotation。删除计划使缺失记录的旧任务失效，不删除公开来源。

可选搜索历史保存放在外层事务提交后的回调，避免研究 turn → user 与 user → turn 的锁序冲突。回调再次复核开关，保存失败仅记录受控错误类型，并给仍存在的工作会话附加 `history_not_saved` 提示，不能回滚检索任务或冒充保存成功。

## 静态检查与待验收

实际执行：

- 13 个 Python 文件 `ast.parse` 退出 0，覆盖新服务、视图、输入/输出 schema、两个模型注册、0011、关联写入边界及新测试。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false` 最后一次退出 0。前一次报告其他并行单元的三个类型错误，随后已由对应单元修复。
- 目标 6 个 TS/TSX 文件 ESLint 退出 0，封面 `<img>` 保留 1 条 `no-img-element` 提示；没有 lint 错误。
- `postcss.parse` 解析 `privacy.module.css` 退出 0。
- 限定文件 `git diff --check` 退出 0，仅既有 CRLF 转换提示。

新增后端 21 个测试函数、22 个参数展开案例，前端 8 个合成浏览器场景，仅编写，未运行。覆盖默认关闭、缺 profile、偏好 CAS、禁新建仍可编辑、历史停写、本人/管理员边界、幂等、预览与确认、逐项 CAS、取消代次、部分失败恢复、原笔记与独立认识保留、授权撤销、来源失效导出、导出过程中子修订变化、资源限制、任务中断、检索任务保留、存储失败提示、锁序、前端 owner 切换与窄屏入口。

未执行正式测试、浏览器、构建、视觉回归、迁移、生产清理或部署。真实 Celery/PostgreSQL 并发、全部 PDF 状态的逐图视觉验收、文件下载运行效果和真实设备表现仍待统一验收。该单元不构成全站或 B01–B06 验收完成。既有备份遵循既有保留期，页面删除不等于立即清除备份。

## 精确源码白名单

新增：

- `api/reading/privacy.py`
- `api/reading/privacy_views.py`
- `api/reading/privacy_serializers.py`
- `api/reading/migrations/0011_reader_privacy_operations.py`
- `api/tests/test_privacy_atlas_20261018.py`
- `web/lib/api/privacy.client.ts`
- `web/components/research/privacy-workspace.tsx`
- `web/components/research/privacy.module.css`
- `web/app/account/settings/privacy/page.tsx`
- `web/app/account/settings/privacy/export/page.tsx`
- `web/tests/privacy-workspace.spec.ts`
- 本文档

修改：

- `api/reading/research_models.py`：只追加两个隐私模型。
- `api/reading/models.py`：只登记新模型。
- `api/reading/urls.py`：只登记新视图与路径。
- `api/reading/tasks.py`：只追加 `run_reader_data_operation` 任务。
- `api/reading/research.py`：只在 `create_memory` 幂等检查后加入保留偏好 guard；其他并行反证改动由主代理负责。
- `api/reading/serializers.py`：只在新 annotation/topic 保存时核对保留偏好。
- `api/reading/views.py`：个人记录事务行锁、annotation 删除撤销关联授权、历史停写、旧导出权限/来源与新增资料兼容。
- `api/catalog/services/discovery_sessions.py`：只追加主动启用的提交后加密历史保存。
- `web/components/reader-center.tsx`：隐私入口、settings 深链接与旧下载 owner 核验。

未修改公共进度、全站契约、Atlas CSV 或 OpenAPI 生成物。未提交 Git；由主代理整合检查点。

## 2026-10-24 按最终PDF补齐隐私导出格式

前置543994b。实际重读唯一PDF223/225后补齐原R32输出格式：ZIP（推荐）、单独文件夹、CSV，同时保留JSON。四种格式共享原ReaderDataOperation与本人选择，不创建新的任务或业务库；切换格式不重新处理资料。ZIP按类别与UUID组织单项JSON和manifest；CSV为UTF-8 BOM、完整记录JSON及失败/下载时变化项目，复用csv_cell阻止表格公式。服务端内存打包，不落盘、不包含馆藏原件或凭据。

ZIP/CSV发送前再核对来源资格和资料修订，比较时仅排除下载时钟及来源关注的本次checked_at，保留真实版本/公开状态/内容变化核对；响应带本人、原任务和数量，前端核对后触发下载。文件夹通过浏览器原生选择器、本人验证与独立新目录逐项保存，manifest记录未完成/完成，中途失败不删除或覆盖已有目录。非安全连接或不支持选择器时明确提示使用ZIP，不能假装已保存文件夹。格式选择沿PDF原输出栏、原日夜变量与窄屏换行。

7de886禁连DB契约0错误10既有警告；b7eb93同步345路径；e17eac五AST，后续两份最终AST；5ce819目标ESLint0错误1既有img提示；3530e3→991ecb TypeScript noEmit0；015c7a CSS解析。ZIP清单、CSV中文/公式、来源时钟与撤回区分、他人隔离和格式化中资料改变用例只编写未运行。未执行测试、浏览器、实际导出、目录写入、迁移或部署，真实交互和像素验收仍待核实。继续其他已登记缺项及内网预览准备。

文件夹兼容边界依据MDN官方文档：[showDirectoryPicker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker)、[createWritable](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemFileHandle/createWritable)，2026-10-24核对；该资料仅用于技术接口，视觉仍只参考最终PDF。
