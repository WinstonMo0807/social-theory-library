# 2026-10-27 内网候选收尾验证

当前工作继续至公网切换前。只有本记录明确列出的运行行为经过验证，不能将其推广为206视图全部验收。生产未更改。

## 已确认并修复

- PAGE-LABEL-01：`ingestion/services/extract._explicit_page_labels`把扫描器默认PDF 1…N视为可靠印刷标签。样书Reader在PDF34显示印刷34，而原目录/正文应为21。仅排除默认单段连续物理编号，明确分段/罗马标签保留；人工页码映射优先。12项聚焦检查通过，包括映射历史与发布契约。
- OUTLINE-PREVIEW-01：`DocumentOutlineWorkspace`首选目录节点PDF14但原稿预览保持PDF1。根据当前节点ID和物理页同步预览；手动翻页仍保留。Web类型与构建通过。
- PRIVACY-EDIT-01：`parallel_reading.update_task`额外要求新笔记保存开关，违反现有隐私界面和PRIVACY_OPERATIONS明确的“已有内容仍可编辑”。只移除已有任务编辑的该条件；新建、本人归属、事务锁、版本和回执校验保留。两份早期测试对此互相冲突，按现有产品规则修正旧断言。
- PRIVACY-INPUT-01：`PrivacyRequestStopInput.to_internal_value`在多余owner字段时抛字符串错误，DRF封装errors时ValueError，实际返回500。改为标准non_field_errors，仍拒绝多余字段及他人归属，接口回归返回400。
- PUBLICATION-DISCOVERY-01：实际校准发布事件115d819c在rag/semantic消费者重试8次后dead_letter。读者检索与LibraryRetrievalService已消费Discovery，但`projection_refresh._semantic_projection`仍启动旧SemanticIndexJob，因无旧active SemanticIndexVersion失败。启用Discovery时沿同一任务账本验证当前公开文件、CatalogRevision、source_revision、generation及完整写入记录；等待现有索引调度完成，失败仍保留，未启用Discovery的旧路径保持。延迟完成复用原投影租约和版本检查，不新建索引架构或隐藏失败。

## 本轮真实样书

《社会学方法的准则》170页，整书cd28e58a成功；目录页7–13定向d23d9390成功。前6页保留旧OCR来源，其余新引擎；另两书未OCR。期间预览PostgreSQL256MiB出现一次OOM，已保存117页；上限调512MiB后沿同一任务恢复至170。不是零中断，也不等同逐字准确率。

v8真实目录任务e5cfece5生成10项。逐项查看原PDF章节起页，人工补引言34，实际管理端保存、采用、书签导出成功。导出资产95d9f651的170页PDF实际读回10书签，落点14/18/34/36/48/79/106/119/151/165。原始资产SHA仍dd72348c885b6f80843891dfe4064071e98c5e5fe5e3431d3b07cd729080eccc。

页码修订49012719（候选2）经过原界面影响预览并采用，0补页，五段：1–3无编号、4–5为1–2、6无编号、7–13为1–7、14–170为1–157。实际原件页眉逐页核对；章节起页数字省略时依据印刷目录和相邻页，不伪称OCR自动确认。新阅读资产5bc8a288、正式快照e0ec49b2，沿用10个已采用目录；Reader实际PDF34显示印刷21。公开阅读已切换，派生消费者此前失败，需以修复后事件状态另记。

管理OCR服务检查按钮成功保存新回执，历史失败未删除。批注台已验证原PDF读取、画线/文字/视口保存和刷新回读。样书内容及原文不提交Git。

## 验证与运行边界

- `precutover-contracts-final-r2.log`：108项读者计划、确认笔记、本人隐私、并读、私人引文及备份回归退出0。初轮失败与修复依据保留。备份测试模拟入口改到已有capture_backup_snapshot，未削弱原件缺失、归档失败和幂等断言。
- `discovery-publication-contracts.log`：16项通过，包括新增7项准确修订/旧来源拒绝/延迟完成/真实失败保留和原9项投影流程。
- `page-label-regression-final.log`：12项通过。`outline-v8-final.log`：26项通过，含实书170页隔离重放。不是检索质量评测。
- Web类型、构建退出0；实际r80策划页读取新品牌和副标题/描述字号。只读PDF73及当前截图，实际内容数量保持1，未填造PDF示例数据或人物肖像。
- API49 d695df3c1ff3/Web80 958185f55582已更新内网；API50 e60e7518c1c0准备应用发布消费者修复。更新仅空闲服务，索引worker仍有任务保留旧镜像；beat在finally恢复。最终版本/重试/恢复演练结果继续补充。

## 仍需读回

发布消费者修复部署后重试同一事件，核对实际Discovery来源与发布状态；候选备份的隔离恢复；r80目录初选原页。账户身份/生产环境保持，公网批准仍待用户最终确认。其余206视图的B验收不改记为开发缺项，已有功能不重复开发。模型质量和全NAS长期稳定性未由上述检查证明。
