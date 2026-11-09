# STL 当前状态

**截至2026-11-09，当前审计基准为公网STL 4.0。** 旧main的3.0.9.1与实际运行环境已不同；本轮依据运行源码整理Git基线和文档，没有再次发布生产。

| 对象 | 已确认状态 |
| --- | --- |
| API / Web | `4.0.0-20261109-curation-publish-r1`；镜像digest见审计基线 |
| API源码 | 791份应用与根运行文件LF规范化摘要核对一致 |
| OCR源码 | 已配置RapidOCR容器5份源码核对一致，观察时停止；未运行识别 |
| Web产物 | 1847项清单与既有发布产物核对，环境注入runtime-config单列 |
| 数据库就绪 | 公网ready返回database=true、pending_migrations=0；不包含全部应用功能/外部能力验收 |
| Git源码整合 | `f5406339cd9c263e9ee58f6ea73d9f09881ab6d9`，25份差异补齐；后续文档另有生成schema更新 |
| 版本对应限制 | 不能倒推原生产镜像来自本轮新commit；以后发布应固定源SHA与manifest |
| 浏览器范围 | 代表性公开/授权管理页面只读检查，6张无私人信息截图；不是79入口全部交互验收 |
| 定向检查 | TypeScript、契约复查和7项Web测试通过；API41例中39通过、2项旧夹具失败 |

完整证据：[审计基线](architecture/AUDIT_BASELINE.md) · [验证记录](architecture/VALIDATION.md) · [公网观察](architecture/PUBLIC_SITE_VERIFICATION.md)。

当前问题按证据强度记录在[审计报告](architecture/15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md)。手机手工编目拥挤已复现；旧证据修订追溯与方法使用映射由源码确认；并发写入/发布恢复、共享网站草稿及OCR后私人锚点仍需隔离环境测试。不要把待测项直接称为生产故障。

本轮未读取、整理或并入首期PDF项目正在进行的知识策展内容，未改生产业务数据、模型、权限或配置。原工作区及既有暂存内容保留。

历史记录见 [原 CURRENT_STATE 快照](https://github.com/WinstonMo0807/social-theory-library/blob/315a3c48442afc9cafc79718c152e5e70352b13f/docs/CURRENT_STATE.md)、[PROGRESS](PROGRESS.md)与[根进度](../CURRENT_PROGRESS.md)。旧发布记录按日期解释，不能覆盖上表当前证据。
