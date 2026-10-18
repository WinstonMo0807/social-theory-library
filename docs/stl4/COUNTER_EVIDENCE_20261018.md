# 学术反证与本人分类决定

状态：源码已接入，统一验收待核实。唯一视觉依据为final-r2最终PDF198–200页，直接渲染并实际读取。页面按原命题/条件、真实证据行、分类纠正侧栏及移动流程实施，不使用图中的学术书目或统计数。

## 复用与真实流程

- `/account/research/[id]/counter-evidence`复用同一ResearchProject/ResearchTurn、Discovery、Reader和加密笔记，不新建公开反证库。
- 原命题、研究对象、地区、时间、限定条件进入当前检索语境及本地关系比较；条件不会被伪装成出版年份筛选。总查询超过1200字符时报错保留输入，不默默截断。明确条件的后续反证轮次不再由追问改写覆盖。
- 每次重新检索或子命题检验生成独立轮次；原命题、条件、分析、人工决定与旧材料保留。只读检索候选不等于支持或反证，未找到不同结论也不证明原判断成立。
- 真实来源卡、书目信息、原文/上下文、当前研究选材、个人笔记和阅读计划使用现有API。封面/出版年只来自可访问的当前公开快照；失效来源移除旧片段和模型线索，保留本人历史判断。
- 分类与归属纠正属于本人记录；公开DerivedClaim和原文不被改写。纠正须填写理由，可另存来源范围差异；明确选择时才同时创建待确认笔记，不自动授予研究或计划使用。

## 接口

- `GET /reading/research-projects/{id}/turns/?mode=counterargument&order=newest&page=N`在本人项目内过滤后分页，count为真实过滤结果数；无参数沿用旧时间正序。mode=all/search/counterargument，order=oldest/newest。
- 现有创建turn接口保持question、statement、scope、subclaims和active_subclaim_id。query_plan含实际query、explicit_conditions/original_proposition方法和条件说明。
- `POST /reading/research-turns/{id}/decision/`接受expected_revision/id，action=confirm|clear（默认confirm）、request_id、relation、note、attribution、scope_note、save_as_note。
- relation为support/different_conclusion/qualification/reframe/insufficient_evidence/unrelated；确认必须填本人note。attribution沿现有作者主张/引述/转述/被批评观点/历史描述/不确定枚举。原始系统候选不因决定被覆盖。
- request_id提供幂等重放；同标识异内容409。save_as_note=true要求request_id，在同一事务中保存分类与state=proposed的ResearchMemory。失败全部回滚；确认新版笔记及使用范围仍按笔记工作台单独执行。
- `decision_history`保存前次relation/decision/修订/时间与替换动作；clear允许在来源失效后撤回本人决定，保留系统候选、历史及独立笔记。隐私内部幂等收据不从序列化/导出返回。
- 当前公开引用额外提供真实cover_url/publication_year；结构化双页映射通过printed_labels/printed_label_precision区分，不据同一扫描页推断左右印刷页。

## 验证边界

后端新增12函数/14参数案例仅编写，覆盖实际检索条件、后续轮次不改写、长度拒绝、关系/归属历史、明确存笔记/幂等/事务回滚、权限/修订、来源撤回与真实历史分页。前端11个合成回归场景仅编写。可选文本条件可留空或明确清空；新版API字段不再拒绝默认表单。静态结果见VALIDATION。

无正式测试、浏览器、逐图回归、检索质量测评或生产操作。运行中的模型/Discovery/Reader、事务并发、移动布局和209视图须统一验收。
