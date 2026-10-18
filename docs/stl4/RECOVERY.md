# 中断恢复最短路径

1. 完整读根AGENTS及Ponytail，再读CURRENT_PROGRESS顶部与本目录PROGRESS；读本轮实际需要的开发规则。
2. `git status --short --branch`、`git log -3 --oneline`；先保留所有未提交内容。不能pull/reset覆盖当前单主线。
3. 以MASTER_SPEC和最终PDF为目标；ATLAS_INDEX是209有效视图索引，旧审核标记不是完成证据。只按CSV的最终页码渲染唯一终稿PDF；不读取历史独立图作为视觉替代。
4. 只核对PROGRESS最后未完成单元的真实代码、API_CONTRACT和DECISIONS，不重复审计全部历史。分别记录实现/静态检查/正式验收/上线。
5. 完成业务单元时更新契约、索引、PROGRESS及CURRENT_PROGRESS，执行允许的静态检查并形成Git检查点。不要仅把工作写在回复中。
6. 全量实施前不运行正式验收或部署。生产不可逆操作必须按DATA_RESET_PLAN形成新鲜影响范围、备份恢复证据并取得最终确认。

本地PDF/原图/output备份被.gitignore排除，不进入源码提交。恢复到另一台机器时必须一并提供这一份最终PDF；源码仓库不能代替这些外部视觉原件。

## 2026-10-18 接续点

阅读计划已保存15f6252（前置依赖a77be7a）。引文体检第208–215页已实际读取，真实接入位于web/components/research/citation-*与api/reading/{citation_audit,research,research_views,research_serializers,tasks}.py；新增路由、schema和测试需与同一检查点恢复。最新检查点见CURRENT_PROGRESS及Git日志，静态证据见VALIDATION。

本单元尚未闭合的新稿件版本增量比较、私人来源文件匹配和PDF209解析三栏优先继续；随后按最终PDF推进已确认笔记/隐私及其余视图。检查/导出/打印控件存在不代表运行验收。不要重新执行旧业务清理，不启动第三步检索质量测评，不提前做正式全站测试或部署。其他历史未提交修改保留。
