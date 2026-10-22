# PDF136 NEW-A16发布前检查实施记录

日期2026-10-23；前置791bd9b。视觉来源仅output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf第136页，实际查看tmp/pdfs/stl4-publication-history-20261022/page-136-image-0.png（PDF原图抽取，不是其他设计稿）。

## 实际实现

五段检查与右侧桌面1180/移动390同公开组件预览，真实封面、版本差异/其余字段展开、关联增删与全量查看、文件/OCR/页码/索引/权限实际状态、完整阻断/提醒、最近保存与真实历史。预览握手核对源窗口/同源/Edition/version/fingerprint；加载失败、超时、阻断、权限不足、命令未知时不能发起新发布。确认框绑定打开时版本，内容更新后需重新检查。

history?view=review扩展原desk，命令完全复用PublicationLedger及原维护/回滚API。旧路径只表示UploadItem，新Edition入口显式object=edition；view=history可单独进入准确版本历史。工作页进入检查前沿用exit的保存/放弃确认；返回编辑保持同一Edition。

回查发现EditionCompactSerializer在预览时仍用正式快照覆盖保存的出版字段、责任者及阅读文件。本批只在精确preview_edition上下文取当前保存字段、formal_field_values选定的合法阅读文件；纯书目不带PDF/目录，公开序列化不改变。

## 验证与边界

5 AST/14 SQL编译且0连接，完整TS、10目标ESLint、CSS84节点；226路径与强类型review契约。OpenAPI0错误/10既有警告；ESLint3既有建议。详见VALIDATION.md本日期记录。7后端函数、4浏览器场景只定义未运行。无正式验收、浏览器/构建、部署、迁移、数据清理、OCR/模型或检索质量测评。

NEW-A16记部分接入，96/26/87。关联编辑回原编目；保存按钮因只读已保存稿显示禁用的草稿已保存。仍待真实长题名/空库/缺封面/失联/账户变化/移动/逐图验收，其他知识/固定页面发布历史、完整引用网络/历史原PDF与全站余页。生产和继承脏改保留。下一步先按唯一PDF继续M17/M18其他对象发布闭环。
