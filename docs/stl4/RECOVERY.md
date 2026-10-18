# 中断恢复最短路径

1. 完整读根AGENTS及Ponytail，再读CURRENT_PROGRESS顶部与本目录PROGRESS；读本轮实际需要的开发规则。
2. `git status --short --branch`、`git log -3 --oneline`；先保留所有未提交内容。不能pull/reset覆盖当前单主线。
3. 以MASTER_SPEC和最终PDF为目标；ATLAS_INDEX是209有效视图索引，旧审核标记不是完成证据。只按CSV的最终页码渲染唯一终稿PDF；不读取历史独立图作为视觉替代。
4. 只核对PROGRESS最后未完成单元的真实代码、API_CONTRACT和DECISIONS，不重复审计全部历史。分别记录实现/静态检查/正式验收/上线。
5. 完成业务单元时更新契约、索引、PROGRESS及CURRENT_PROGRESS，执行允许的静态检查并形成Git检查点。不要仅把工作写在回复中。
6. 全量实施前不运行正式验收或部署。生产不可逆操作必须按DATA_RESET_PLAN形成新鲜影响范围、备份恢复证据并取得最终确认。

本地PDF/原图/output备份被.gitignore排除，不进入源码提交。恢复到另一台机器时必须一并提供这一份最终PDF；源码仓库不能代替这些外部视觉原件。

## 2026-10-18 接续点

阅读计划四页参考已实际读取，源码位于web/components/research/reading-plan-*与api/reading/{research,plan_rules,tasks}.py；本轮静态结果见VALIDATION。先核对Git最新两批检查点（依赖a77be7a及阅读计划批），无需重复本次全量读取。引文体检上传与报告详情仍是下一未闭合单元。继续只读取终稿PDF对应页，禁止启动第三步检索质量测评或提前正式全站验收。原有未提交工作保留。
