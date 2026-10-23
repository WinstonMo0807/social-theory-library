# M23 时间线事件编辑源码接入

2026-10-23，前置 ba115c6。唯一视觉依据 final-r2 PDF 149–151 页，实际读取嵌入图；缓存仅来自该 PDF：tmp/pdfs/stl4-final-m23-20261023。图集标注和示例学术内容不进入产品数据。

## 已接源码

沿原 TheoryTimelineEvent、TimelineEventRelation、EditorialRevision、AuditEvent、Asset/Edition 实施。事件三栏编辑包括基本信息、关联对象/准确版本、主要及补充出处、分歧说明、内部备注、人工核对和真实关联时间线预览。目录收折保留原筛选/分页/切换；窄屏按单栏排列，现有公共预览组件沿用。

新增人物出生、去世、任职类型；开始/结束日期及月份/日期精度与年份严格一致，原年份、约年、时间区间和文字说明继续有效。公开序列化与事件详情显示保留明确精度，不将所有历史时间推成具体日期。月份内部日期编码首日，显示时仅呈现年月。

私有 editorial_details 保存最多20条稳定UUID出处，含书目、类型、定位、摘录、采用/存疑/相关研究、可选原Asset及页序，附时间/分歧/编辑/独立事件说明。选择原文沿原材料选择器，文件必须是有效阅读文件且页序有效。公开接口未添加该私有字段，主要出处沿既有阅读文件权限过滤。

出版/译介事件发布须指向明确Edition；人物生平须指向Scholar；正式发布前要求实际来源、事件说明和人工核对，存疑来源须填写分歧说明。草稿可分步保存。来源或内容变化清除前端已核对勾选；正式发布仍沿原版本冲突校验与发布权限。

新保存包装复用ScholarCommandMixin，原User锁内检查active/token_version/编辑或创建能力，固定请求UUID/HMAC/If-Match；重放返回原结果，不覆盖后续编辑。查回/停止仅限本人；停止与原保存共用锁，迟到请求不得重新写入。会话切换卸载/中断，浏览器仅保存请求UUID，不保存证据正文。相似事件只读查询按对象、类型、邻近年份，最多50条结果，不自动归并；编辑可记录保留独立事件的说明。

## 契约与数据

新增 POST /catalog/admin/theory-timeline/similar/、GET/POST /catalog/admin/theory-timeline/commands/{request_id}/。原事件list/detail保存地址保留，新建必需X-Editor-Owner和Idempotency-Key，更新原If-Match继续必需。生成287条契约，原285全部保留。

catalog0076仅声明editorial_details、start_date、end_date、source长度及精度/事件类型，不回填或改动已有账号。尚未执行；catalog0075及reading0022/23/24亦未执行。

## 静态核对及限制

- dacd04：12份AST、8次SQLite/PostgreSQL SQL编译、6项模型/迁移声明比较，强制禁止数据库连接。OpenAPI 0错误，10项原有警告。
- cd4413：285旧路径保留、2新路径，287契约；CSS仅解析。
- 最终5b5b57→cb4c37 TypeScript noEmit及目标ESLint退出0，3项img提示。中间e31300发现精度标签及图片URL工具未同步，已修复；7d19a8在根目录误调用TypeScript路径报MODULE_NOT_FOUND，修正目录后执行。没有测试、构建、浏览器、业务请求、迁移、生产操作。

M23三视图记部分接入：同一事件归并尚未接入正式双对象预览/迁移/回退，不能把相似提示当作归并完成；多角色人物卡、来源图片替换与完整移动页签/折叠及精确几何仍需补齐。未做页面截图比较，不能称逐图验收通过。全站96源码/60部分/53待实施，继续M24及其余全站工作。
