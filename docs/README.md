# 文档导航与事实优先级

准备重新设计整体架构或后台时，从下面的当前入口开始。文档中的“当前”只对其写明的日期成立，真实服务检查与源码证据各有范围。

## 当前入口

1. [GPT实际架构与场景](GPT_ARCHITECTURE_CONTEXT.md)，理解用户、运行结构、数据职责和代码位置。
2. [管理端架构与功能画像](ADMIN_ARCHITECTURE_PROFILE.md)，六组任务、各种保存范围、智能填写、时间线、封面/OCR、公开位置、权限和修改地图，可直接交给其他AI。
3. [上架与发布过程](INGESTION_AND_PUBLICATION.md)，理解真实保存、复核、发布、撤回、正文和任务状态。
4. [重设计任务说明](REDESIGN_BRIEF.md)，区分用户已经确定的要求与待选择方案。
5. [当前状态](CURRENT_STATE.md)，查看3.0.6线上与Git/镜像的关系及未验证范围。
6. [根目录当前进度](../CURRENT_PROGRESS.md)，核对最新Git与正在进行的动作。

## 按领域深入

| 文档 | 用途 |
| --- | --- |
| [3.0.6 后台能力清单](V3.0.6_ADMIN_CAPABILITY_INVENTORY.md) | 43入口的唯一完整路由/能力交付索引；历史基线列与当前摘要分开 |
| [3.0.6 编辑—公开读取对照](V3.0.6_PUBLIC_CONTROL_MATRIX.md) | 对应源码单一public_knowledge_control登记，不是第二套运行配置 |
| [3.0.6 最终交付](V3.0.6_COMPLETION_RELEASE.md) | 本轮补漏/封面、最小测试、备份恢复、公网及未实测边界 |
| [3.0.6 分阶段验证](V3.0.6_VERIFICATION.md) | 开发过程的准确命令和不同源码时点，不累加为最终全量通过 |
| [ARCHITECTURE](ARCHITECTURE.md) | 实现结构与架构演变；旧版本段落按历史阅读 |
| [UI_3.0.5](UI_3.0.5.md) | 历史共享组件、CSS分层和当时UI验证；3.0.6以当前组件/样式为准 |
| [V3.0.5_API_CONTRACT](V3.0.5_API_CONTRACT.md) | 实际生成契约范围、旧接口覆盖边界及依赖检查 |
| [V3.0.5_PUBLICATION](V3.0.5_PUBLICATION.md) | 发布命令、历史恢复及当时专项验证 |
| [V3.0.5_MEDIA](V3.0.5_MEDIA.md) | 媒体、草稿和历史引用保护 |
| [V3.0.5_PERSON_RESOLUTION](V3.0.5_PERSON_RESOLUTION.md) | 人物查重和有边界的合并/撤回 |
| [MIGRATION_3.0.5](MIGRATION_3.0.5.md) | 完整增量迁移、恢复演练和回退限制 |
| [DEPLOYMENT](DEPLOYMENT.md) | NAS部署事实与操作边界，不等同每次Git push自动部署 |
| [V3.0.5_VERIFICATION](V3.0.5_VERIFICATION.md) | 准确命令、源码时间点、通过/失败/未核实范围 |
| [ISSUES](ISSUES.md)、[PROGRESS](PROGRESS.md) | 最新摘要加历史过程，按时间区分 |

## 历史与设计资料

[GPT-HANDOFF](GPT-HANDOFF.md)是2.9.2快照，[V3.0.5_ARCHITECTURE_AUDIT](V3.0.5_ARCHITECTURE_AUDIT.md)是3.0.5实施前的基线审计。更早版本的升级、需求矩阵和验证报告保留以解释决策，但不要把其中“尚未实现”的描述自动当作今天仍未完成。

`REDESIGN_BRIEF`中的问题和新方案属于设计输入，不能写成已经部署的事实。遇到文档相互矛盾时，先核对当前源码，再确认最近运行证据，不删除真实错误或默认为已验证。

维护入口资料后可运行`node scripts/verify-ai-handoff.mjs`，只读核对本地链接、明确源码路径和43入口清单覆盖，并统计当前public control声明；它不启动服务、不写数据库，也不证明页面行为或外部服务通过。
