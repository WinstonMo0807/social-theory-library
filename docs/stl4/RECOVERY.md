# 中断恢复最短路径

1. 完整读根AGENTS及Ponytail，再读CURRENT_PROGRESS顶部与本目录PROGRESS；读本轮实际需要的开发规则。
2. `git status --short --branch`、`git log -3 --oneline`；先保留所有未提交内容。不能pull/reset覆盖当前单主线。
3. 以MASTER_SPEC和最终PDF为目标；ATLAS_INDEX是209有效视图索引，旧审核标记不是完成证据。只按CSV的最终页码渲染唯一终稿PDF；不读取历史独立图作为视觉替代。
4. 只核对PROGRESS最后未完成单元的真实代码、API_CONTRACT和DECISIONS，不重复审计全部历史。分别记录实现/静态检查/正式验收/上线。
5. 完成业务单元时更新契约、索引、PROGRESS及CURRENT_PROGRESS，执行允许的静态检查并形成Git检查点。不要仅把工作写在回复中。
6. 全量实施前不运行正式验收或部署。生产不可逆操作必须按DATA_RESET_PLAN形成新鲜影响范围、备份恢复证据并取得最终确认。

本地PDF/原图/output备份被.gitignore排除，不进入源码提交。恢复到另一台机器时必须一并提供这一份最终PDF；源码仓库不能代替这些外部视觉原件。

## 2026-10-18 接续点

前置检查点a77be7a、15f6252、50cf8ed和b0cbf28保留。最新业务单元为稿件版本与目录校准，恢复时先读CURRENT_PROGRESS顶部及CITATION_VERSIONS_20261018.md、OUTLINE_CALIBRATION_20261018.md；Git检查点提交号见当前进度。新API、前端、生成类型和测试须一并恢复。

本轮已把PDF212新版本/增量比较和112–115目录工作区接入源码。下一步继续私人证据材料、PDF209三栏解析工作台及已确认笔记/隐私等剩余视图。不要把新版本局部重查或目录静态检查写成正式验收。正式测试/逐图回归留待全量实施结束；生产数据未再清理，不运行第三步检索质量评测。其他历史未提交成果继续保留。
