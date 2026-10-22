# M18 出版版本历史、影响和撤回（2026-10-22）

## 依据与范围

唯一final-r2 PDF134–137原图实际读取；本批M18-main/sub01/states部分接入。复用/admin/publication队列，明确selection后的Edition进入对象摘要、版本历史/影响/引用依赖三页签、差异/发布检查、操作状态。桌面表格、窄屏历史条目，纸白/暖灰/炭黑/砂金，无图集示例业务数据。图136 NEW-A16独立发布前检查仍待实现。

## 真实能力

原history增加desk投影，历史20条分页、特定历史摘要对比。准确Edition约束阻止串馆藏。当前公开由state/active pointer/metadata资格判断；撤回仍保留旧指针，但不再冒充公开。恢复按钮只对曾公开的有效状态出现，文件可读性及正式合法性由原rollback再次核对。

原prepare给保存与当前公开差异和阻断，原维护命令负责发布/撤回，原rollback负责新序号恢复，未引入第二套发布机制。新UI对写命令总发expected_version；发布还沿prepared_fingerprint。恢复先检查准确幂等回执（actor/目标/修订/reason），再核对版本。未知命令在sessionStorage绑定owner/edition保存，显式核对/原请求重试，原JSON不改；未确认前禁新命令。公开/已接受请求/后台任务完成分别展示。

影响范围依据已保存与当前正式关联，不生成虚假页面访问量或引用数。依赖复用已有馆藏EvidenceSnippet和私人Annotation/Bookmark/ReadingProgress聚合数，不含私人身份或正文；不是全站文章引用网络。任务列最近20项并说明上限；原PublicationRetryControl接账户绑定请求。后台权限保持发布/撤回分别授权。

## 验证与余项

7后端函数、4浏览器场景已定义未执行。AST/两数据库SQL编译零连接/TypeScript/目标ESLint/OpenAPI及CSS结果见VALIDATION。无迁移、测试运行、模型/检索评测、生产操作。

待继续：图136独立页面及已有itemId的可靠映射、其他知识对象/策划/固定页发布台、完整文章引用依赖与历史PDF视图、真实规模性能、全部状态及逐图正式验收。已撤回Edition不允许通过回滚隐式重新公开；需要明确发布，不能声称所有图示恢复行为已完成。当前96源码/25部分/88待实施，共209。
