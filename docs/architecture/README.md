# STL 架构与管理端审计

**基准：2026-11-09 公网 STL 4.0 运行版本。** 本目录解释当前代码怎样工作，并把观察、源码事实、历史证据和设计建议分开。先读[审计版本](AUDIT_BASELINE.md)，再选择下面的入口。旧版 3.0.9.1 文档不能替代这里的当前基线。

| 读者问题 | 文档 |
| --- | --- |
| STL 为谁服务，功能边界是什么？ | [00 项目概览](00_PROJECT_OVERVIEW.md) |
| 系统与外部服务怎样连接？ | [01 系统架构](01_SYSTEM_ARCHITECTURE.md) · [02 运行架构](02_RUNTIME_ARCHITECTURE.md) |
| 页面、组件、请求与状态怎样协作？ | [03 前端架构](03_FRONTEND_ARCHITECTURE.md) |
| 管理员到哪里完成一项工作？ | [04 管理端信息架构](04_ADMIN_INFORMATION_ARCHITECTURE.md) · [完整页面清单](ADMIN_PAGE_INVENTORY.md) |
| 一个按钮背后经过哪些组件与服务？ | [05 管理端组件图](05_ADMIN_COMPONENT_MAP.md) · [管理模块调用链](ADMIN_MODULE_CONTRACTS.md) |
| 数据写在哪里，谁最终读取？ | [06 领域模型](06_DOMAIN_MODEL.md) · [数据与公开消费者](MODEL_PUBLIC_CONSUMERS.md) · [生命周期](OBJECT_LIFECYCLES.md) |
| 社会科学关系与原文证据怎样表达？ | [07 知识实体与关系](07_KNOWLEDGE_GRAPH_AND_RELATIONS.md) |
| 如何入库、确认、预览和发布？ | [08 策展与发布](08_CURATION_WORKFLOW.md) |
| API 和服务实现在哪里？ | [09 API 与服务](09_API_AND_SERVICE_MAP.md) |
| OCR、索引和后台任务怎样运行？ | [10 异步任务与 OCR](10_ASYNC_TASKS_AND_OCR.md) |
| 谁能读、编辑、发布和管理系统？ | [11 权限与安全](11_PERMISSIONS_AND_SECURITY.md) |
| 字体、间距和响应式规则来自哪里？ | [12 设计系统](12_DESIGN_SYSTEM_AND_PAGE_PATTERNS.md) |
| 如何本地启动、部署和恢复？ | [13 部署与运维](13_DEPLOYMENT_AND_OPERATIONS.md) |
| 哪些检查实际做过？ | [14 测试与质量](14_TESTING_AND_QUALITY.md) · [公网核对](PUBLIC_SITE_VERIFICATION.md) |
| 发现什么问题，应该改哪些页面？ | [15 问题与待核项](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md) |

## 证据索引

- [源码整合清单](SOURCE_RECONCILIATION.csv)：25 份运行源码差异的来源与规范化摘要。
- [管理端入口 CSV](inventory/admin-pages.csv)：79 个入口，含 2 个 route handler；入口不是独立业务数量。
- [组件导入边](inventory/component-imports.csv)与[实际 JSX 使用位置](inventory/component-renders.csv)：区分“导入”与“出现于 JSX”，不把 type-only import 当运行依赖。
- [前端 API 表达式](inventory/frontend-api-expressions.csv)与[后端 URL—View—直接服务引用](inventory/api-views-services.csv)。动态拼接、继承和权限须结合模块调用链阅读。
- [模型字段](inventory/model-fields.csv)与[模型直接消费者](inventory/model-consumers.csv)：包含拆分的 `*_models.py`；空 table 表示抽象基类，字段不自动展开继承。表名来自模型声明/默认规则，未查询生产 schema。
- [维护与重新生成方法](inventory/README.md)。机器扫描覆盖 772 个前端模块、632 个后端模块；不等于逐行形式验证或全部业务实测。

## 文档约定

图中实线表示当前源码或运行关系；标有“建议”的图属于未来设计。公开、登录后可见、管理员私有三种边界不混用。“已实现”只代表找到完整实现；“已观察”只代表本轮所列页面状态；“已部署”以镜像及运行文件核对为依据。全文没有把历史测试数累加成新的验收成绩。

本次只整合已上线代码、编写文档及静态索引。进行中的首期 PDF 知识策展内容、私人资料、凭据、馆藏文件和生产变更均不在交付物中。
