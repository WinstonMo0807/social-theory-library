# 已确认笔记与明确使用范围

状态：源码已接入，正式功能/视觉验收待核实。唯一视觉依据为final-r2最终PDF205–207页，本轮直接渲染并实际读取。界面数据全部来自本人实际记录；图中书目、笔记和计数未作为种子。

## 页面与操作

- `/account/confirmed-notes`替换原仅confirmed只读列表。纸白外层、白色内容区、左侧类型/状态/来源筛选、右侧真实列表、移动筛选与状态导航承接最终图；封面仅来自当前公开来源，否则显示文档空态。
- 从本人Annotation选择原笔记，编辑自己的认识后先保存为proposed；详情中明确选择confirmed/proposed/ignored。原始笔记、当前认识、来源与历史分开显示，确认不自动授权。
- 列表支持服务器搜索/筛选/排序/分页及真实状态计数。来源变化区分updated/unavailable/no_source，保留私人正文；原文变化后须明确核对并更新来源关联。
- 来源编辑复用现有研究选材选择器；移除失效来源或选择真实原文后保留尚未提交的正文草稿。refresh_origin只替换原笔记对应来源，其他人工关联来源和历史保留。
- 每条笔记可以选择具体研究或阅读计划、撤销单一范围或全部范围。最多40条明确ID用于一个范围。列表开关打开范围选择，不默认把全部笔记交给所有研究。
- 编辑保存与删除按已核对revision提交；409保留输入，明确选择最新保存基准后再提交。窗口关闭、站内链接和页面离开保留未保存提醒；账户变化清除列表、弹窗、草稿与下载结果。
- 所选笔记JSON从owner导出接口重读后生成。删除仅删除确认笔记、历史及派生数据并撤销关联授权，独立原始Annotation保留。

## 服务、契约和权限

沿用ResearchMemory、ResearchProject、PersonalReadingPlan加密payload，不新增表或迁移。kind扩充concept/method/observation，兼容understanding/question/contradiction。

- `GET /reading/research-memories/`：q/state/kind/source_status/order（updated_at/newest）筛选，分页响应含counts.total/confirmed/proposed/ignored。计数基于owner和q/kind/source条件，state筛选前统计，不把一页结果当全量。
- `POST`同路径：request_id/body/kind/annotation_id，保存proposed。原Annotation和当前公开来源在服务端核对，原件身份由服务端取得。
- `PATCH /reading/research-memories/{id}/`：expected_revision，body/kind/state/sources及显式refresh_origin。编辑未显式确认时回到proposed并撤销范围，旧修订留在加密历史。
- 实际正文/类型/来源变化均撤销旧授权，即使同请求state=confirmed也只确认新版；纯同文同类型确认不误撤范围。确认和授权分别执行。
- `GET /reading/research-memories/{id}/usage/`：memory_id/revision/本人targets(kind,id,title,revision,enabled,selected)。
- `POST usage/`：expected_revision/action(grant/revoke/revoke_all)/targets(kind,id,expected_revision)。只允许confirmed本人笔记和本人目标，事务内核对双方版本。作用域权威字段沿用use_confirmed_memories和confirmed_memory_ids；暂停范围重新授权时不会复活旧名单。
- `DELETE`按expected_revision检查，先撤销作用域再删除。普通管理员身份不会扩大私人访问范围。
- `search_memories`不传明确allowed_ids或授权context时返回空；只在本人confirmed与明确范围交集中检索。模型编码前后再检查授权及版本。
- 研究turn保存笔记ID/修订快照，读回只提供仍有有效授权的同版memory_reminders；授权变化时收起旧提醒。提醒与公开检索/证据分开，不把私人正文加入Discovery查询。计划继续复用既有白名单并在模型调用前复核当前修订。
- 旧research_personalization的未设置默认值改为false；显式关闭撤销全部范围。本人仍可随后重新授权具体范围，管理笔记本身不依赖全局开关。

## 验证及边界

开发期只做静态检查，具体最终命令见VALIDATION.md。新增前端6个合成回归场景，后端14函数/17参数案例仅编写；旧检索测试改为明确allowed_ids，原安全断言保留。全量TypeScript、目标ESLint、Python编译、CSS解析均退出0；真实封面img有1条lint警告，不是视觉验收。

同一用户的加密列表和使用范围采用现有owner范围扫描；未引入第二套索引。真实大账户量、并发事务、浏览器/移动布局、来源更新、全部209视图和B01–B06仍须统一验收。未运行检索质量评测、生产清理、迁移或部署。
