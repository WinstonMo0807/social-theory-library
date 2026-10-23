# 读者中心无引导使用复核

2026-10-24。按用户要求使用已读取的grilling规则自行追问，读者45图作为一个一级分类，未逐张另开问答。唯一依据为final-r2 PDF；181–225全部原始图像实际逐张读取。以下是原图和静态调用链证据，未测试、浏览器操作或确认像素一致。

## 普通读者的操作分支

| 自问 | 已查源码事实与处理 | 尚待统一运行核实 |
|---|---|---|
| 首次注册后还能回原页吗？ | AuthPageFrame/AuthForm使用safeAuthDestination；Reader登录/注册保留同一完整返回位置。账户恢复单次验证码与重发限制；本机记录仅明确选择后转存。 | 邮件服务、验证码过期、实际账号恢复；未配置的第三方登录明确未开放，不能当作可用。 |
| 研究取消或改问法是否会丢掉已有材料？ | useResearchProject通过readAllPages读取本账户全部轮次；cancel_turn只取消活动任务并提升generation，不删除已有结果；扩展/重试另建轮次。 | 任务超时、撤回来源、跨设备冲突。 |
| 从某一轮原文回来还能找回该轮吗？ | R02：原链接只用reader_url，缺少项目/轮次/return_to。已给研究原文链接接原Reader上下文，返回页恢复明确轮次且仅从本人已读取轮次匹配。 | 旧轮次删除、当前原文修订变更、实际滚动定位。 |
| 比较、反证会把系统建议当本人判断吗？ | 比较单元格分别保存原文身份和我的笔记，缺证据单独显示；并发编辑另存一条。CounterEvidence区分规则/模型建议与本人分类，明确未找到反例不证明命题成立。 | 真实混合来源、部分模型结果与编辑并发；不宣称推理正确。 |
| 计划能找到已确认笔记吗？ | R01：原PlanMemoryPicker分页后筛confirmed，可能出现假空页。改用现有state=confirmed服务端过滤，原分页和40项限制保留，增加确认笔记入口及刷新。 | 跨页选取、在另一标签确认后刷新、授权撤销。 |
| 计划读完原文能回哪里？ | R03：沿共享readerContextHref附本人计划地址，公开路径保留公开修订/阶段/材料锚点，返回按钮按来源命名。完成项保护不变。 | 路径改版、来源撤回、阅读计划材料换版。 |
| 确认笔记等于全局授权吗？ | confirmed-notes与MemoryUsageDialog把本人确认、grant/revoke/revoke_all分开；PlanSettingsForm默认不使用个人笔记，公开路径副本不借用笔记生成。接口按本人/修订锁定，删笔记撤销原上下文。 | 授权正在使用时撤销、任务迟到结果及真实多账户。 |
| 上传的稿件是否变成公开馆藏？ | citation-audit-upload仅私人体检端点；真实capabilities决定检查项、大小、scope。选定私人来源必须显式选择，文件与选项绑定固定请求。解析界面允许部分结果、手工核对，原稿下载与公开馆藏分开。 | 实际PDF/DOCX解析、OCR资源占用与取消；此前能力接入不作为本轮实测。 |
| 书单删错或重复点击能恢复吗？ | ReaderBooklists复用版本/固定请求/原回执，sessionStorage仅保存list_id/request_id，按owner隔离；已有回收、恢复、导出和计划转换。 | 重排、重复追加、删后旧请求重放、会话变化真实行为。 |
| 隐私导出与删除会处理别人的或公开资料吗？ | privacy_views查询只按当前user；privacy.rows和owned复核归属；逐项版本/子记录检查，删除先预览再确认，任务有generation和逐项事务。下载时再次核对版本与来源，输出部分失败与准备后变化；不包含PDF/DOCX原件及凭据。 | 实际大任务、重试剩余、跨账户隔离、备份保留期；源码不能证明运行部署安全。 |

## 小范围修正

R01–R03不改视觉构图。研究问题输入新增沿用useUnsavedForm的站内离开提醒；多个锚点的Reader优先使用服务端既有reference_id，避免HTTP内网重新计算摘要导致定位报错，不以弱摘要替换。研究/计划/主题/公共路径仍通过原Reader访问原文件，不建第二套阅读器或私人数据表。

## 逐图阅读登记

下列45行均只表示已读取PDF原图。各状态的对应源码以上述整类分支为证据，实施页面渲染、触屏、键盘、视觉几何及真实操作仍待核实。

| PDF页 | ID | 原图标题 | 实际入口 |
|---|---|---|---|
| 181 | R34-sub02 | 加入研究与导出 | 共享浮层 |
| 182 | R34-sub03 | 分享或提交策划的内容范围 | 共享浮层 |
| 183 | R22-main | 读者中心：阅读、研究与私人资料 | /account |
| 184 | NEW-R04 | 研究会话总览 | /account/research |
| 185 | R22-states | 我的资料与研究档案 · 状态 | /account |
| 186 | R31-main | 登录、注册与账户恢复 | /login |
| 187 | R31-sub01 | 注册 | /register |
| 188 | R31-sub02 | 账户恢复 | /reset-password |
| 189 | R31-sub03 | 会话过期与重新登录浮层 | /login |
| 190 | R31-states | 登录、注册与账户恢复 · 状态 | /login |
| 191 | R05-main | 持续研究工作区 | /account/research/[id] |
| 192 | R05-sub01 | 研究轮次与分支 | /account/research/[id] |
| 193 | R05-sub02 | 范围变更与新增证据 | /account/research/[id] |
| 194 | R05-states | 持续研究工作区 · 状态 | /account/research/[id] |
| 195 | R06-main | 选材比较与证据矩阵 | /account/research/[id]/compare |
| 196 | R06-sub01 | 单维度对照与缺失证据 | /account/research/[id]/compare |
| 197 | R06-states | 选材比较与证据矩阵 · 状态 | /account/research/[id]/compare |
| 198 | R07-main | 学术反证：检验一个判断 | /account/research/[id]/counter-evidence |
| 199 | R07-sub01 | 反证候选的分类纠正与归属复核 | /account/research/[id]/counter-evidence |
| 200 | R07-states | 学术反证：检验一个判断 · 状态 | /account/research/[id]/counter-evidence |
| 201 | R21-main | 我的阅读计划：可解释规则与手动调整 | /account/plans/[id] |
| 202 | R21-sub01 | 生成计划的目标与时间 | /account/plans/[id] |
| 203 | R21-sub02 | 调整顺序与先修冲突 | /account/plans/[id] |
| 204 | R21-states | 我的智能阅读计划 · 状态 | /account/plans/[id] |
| 205 | R23-main | 已确认笔记与使用范围 | /account/confirmed-notes |
| 206 | R23-sub01 | 从笔记形成记忆的主动确认 | /account/confirmed-notes |
| 207 | R23-states | 个人学术记忆列表 · 状态 | /account/confirmed-notes |
| 208 | R25-main | 论文引文体检：提交与任务 | /account/citation-audits |
| 209 | R25-sub01 | 上传解析与局部失败 | /account/citation-audits/[id]/parse |
| 210 | R25-states | 论文引文体检：提交与任务 · 状态 | /account/citation-audits |
| 211 | R26-main | 论文体检报告总览 | /account/citation-audits/[id] |
| 212 | R26-states | 论文体检报告总览 · 状态 | /account/citation-audits/[id] |
| 213 | R27-main | 引文问题详情与原文核验 | /account/citation-audits/[id]/issues/[issueId] |
| 214 | R27-sub01 | 译本匹配与人工决定 | /account/citation-audits/[id]/issues/[issueId] |
| 215 | R27-states | 引文问题详情与原文核验 · 状态 | /account/citation-audits/[id]/issues/[issueId] |
| 216 | R28-main | 笔记、摘录与书签 | /account/notes |
| 217 | R28-states | 笔记、摘录与书签 · 状态 | /account/notes |
| 218 | R29-main | 书单与材料集合 | /account/collections/[id] |
| 219 | R29-sub01 | 集合详情与排序 | /account/collections/[id] |
| 220 | R29-states | 书单与材料集合 · 状态 | /account/collections/[id] |
| 221 | R30-main | 研究过程回放 | /account/research/[id]/history |
| 222 | R30-states | 研究过程回放 · 状态 | /account/research/[id]/history |
| 223 | R32-main | 隐私与资料：选定笔记使用默认关闭 | /account/settings/privacy |
| 224 | R32-sub01 | 导出与删除资料 | /account/settings/privacy/export |
| 225 | R32-states | 隐私、记忆偏好与资料导出 · 状态 | /account/settings/privacy |

## 2026-10-24 读者资料原请求恢复与迟到提交隔离

前置a9d8099。按读者整类grill-me自问，沿唯一PDF183/185重新核对总览，实际重读223/225。原读者中心只清本机恢复信息不能停止迟到请求；隐私页原编号只留内存。现两个入口共用本人/原UUID的会话恢复记录与服务端查回、停止操作；User行锁串行创建与停止，已有任务返回原详情，未创建写最少停止回执。身份核验、权限及404不清编号，409保留等待查回；已创建删除仍须独立预览和确认。原偏好/准备/任务命令写入重新核对账户启用和token版本，无新表。

总览空列表仍保留任务和恢复入口；切换筛选/分页提醒清除本页选择，未决请求刷新后可继续查回。复用原Dialog/ReaderDataOperation/Celery，不建立第二套私人任务。恢复记录只有编号、类别与对象版本，不保存正文。补录R22已有批量导出、删除预览和本机研究转存，删除索引中过时的未接入描述；重命名/归档及账户浮层等仍按原缺项继续。

30eae6禁连DB契约0错误10既有警告；7988b2同步345路径；670d14六AST与6条SQLite/PostgreSQL静态SQL编译；839336目标ESLint0错误1既有img提示；b91522→3d11d9 TypeScript noEmit0。迟到请求阻断、已执行预览不取消、所有者隔离和凭证变化用例仅编写未运行。没有测试、浏览器、真实资料请求、迁移或部署。PDF中的ZIP/单独文件夹/CSV导出尚未全部接齐，继续实施；不将原图阅读计为页面视觉通过。
