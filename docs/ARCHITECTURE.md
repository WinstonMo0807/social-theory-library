## 2026-11-14 书库浏览与私人工作台

新增/library为现有公开WorkList API的独立前端视图，作品级created_at/title排序、服务端分页；搜索与探索继续使用原服务。/account全部次级路由统一ReaderWorkspace外框，导航/查找/新建只调度已有路由，子模块仍负责本人鉴权、数据、写入与任务。不建立第二套馆藏、私人资料库或身份体系。首页只调整最近入库至荐书区域，根入口/与/home职责保持。

## 2026-11-14 检索页内连续研究与原版页面

S4检索复用既有发现/书目检索接口；SearchResearchDock在同页复用私人研究接口。每轮context_refs与scope独立快照，选段仍由服务端核对原文偏移；不新增私人资料库。SourceExcerpt清洗仅影响显示，引用继续使用原始来源。DiscoverySourcePage在读者展开时先校验来源及版本，再沿既有distribution access/PdfCanvas显示单页PDF，关闭自动预取；不新增检索任务、OCR或模型调用。结构提示是本地展示规则，不能视为结构识别的准确性保证，所有段落均保留原页入口。

## 2026-11-12 本机 Codex MCP 策展

tools/stl_mcp 是本机stdio接口，通过现有严格主机校验的SSH通道在原API容器内启动固定Django命令分派，复用原编目、编辑修订、规范实体、EvidenceCuration与AuditEvent。没有远程MCP监听、第二套馆藏或数据库schema变更。模型仅可调用白名单读取/草稿命令；固定账户、token_version、作品范围、对象关联、人工锁、版本与逐项回执在服务端重核。独立本机SQLite仅存不可变计划、原请求编号及耗时，不承担正式业务状态；机器待审与人工确认/正式发布分开。三书6项维护增补已真实保存并跨进程回放验证。边界与实测见 `stl4/LOCAL_MCP_CURATION_20261112.md`。

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
