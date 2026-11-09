# STL 当前架构

当前架构文档已集中在 [docs/architecture](architecture/README.md)。基准为 2026-11-09 公网 STL 4.0 `curation-publish-r1`，包含实际运行文件核对、源码调用关系和只读页面观察。

| 主题 | 当前入口 |
| --- | --- |
| 产品与系统 | [项目概览](architecture/00_PROJECT_OVERVIEW.md) · [C4系统](architecture/01_SYSTEM_ARCHITECTURE.md) · [运行容器](architecture/02_RUNTIME_ARCHITECTURE.md) |
| 前端与管理端 | [前端架构](architecture/03_FRONTEND_ARCHITECTURE.md) · [管理地图](architecture/04_ADMIN_INFORMATION_ARCHITECTURE.md) · [组件](architecture/05_ADMIN_COMPONENT_MAP.md) |
| 数据与策展 | [领域模型](architecture/06_DOMAIN_MODEL.md) · [知识关系](architecture/07_KNOWLEDGE_GRAPH_AND_RELATIONS.md) · [流程](architecture/08_CURATION_WORKFLOW.md) |
| 服务与安全 | [API](architecture/09_API_AND_SERVICE_MAP.md) · [异步/OCR](architecture/10_ASYNC_TASKS_AND_OCR.md) · [权限](architecture/11_PERMISSIONS_AND_SECURITY.md) |
| 维护 | [设计系统](architecture/12_DESIGN_SYSTEM_AND_PAGE_PATTERNS.md) · [部署](architecture/13_DEPLOYMENT_AND_OPERATIONS.md) · [质量](architecture/14_TESTING_AND_QUALITY.md) · [问题](architecture/15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md) |

完整管理端入口、组件/接口清单、模型消费者及生命周期在架构目录中交叉链接。机器生成的引用只证明源码关系，实际语义和权限仍由对应章节说明。

旧增量文档保留在 [Git 历史快照](https://github.com/WinstonMo0807/social-theory-library/blob/315a3c48442afc9cafc79718c152e5e70352b13f/docs/ARCHITECTURE.md)。它是历史记录，不作为4.0当前架构入口。未来架构变更直接维护新目录，并更新[版本与证据](architecture/AUDIT_BASELINE.md)。
