## 2026-11-12 MCP上传桥接

MCP新增准备与入库状态工具，二进制走/mcp/uploads/及本机辅助程序，不进入模型上下文。网关以固定受信账户调用原网站上传视图，原权限、批次归属、文件/策略规则、分片及派发负责结果；本轮按用户要求不另建业务校验或上传测试。上传计划映射沿既有AuditEvent，无新业务表。独立MCP复用当前API镜像并挂载incoming供原上传服务使用，其他文件目录仍只读，文件处理沿原后台队列。详stl4/MCP_UPLOAD_DELIVERY_20261112.md。

## 2026-11-12 MCP动态馆藏草稿范围

可信配置work_scope=catalog替代本人的固定作品清单，按原Work表实时判断存在，不缓存馆藏ID快照或建立同步任务。新Work/Edition自然纳入；领域服务仍校验本次Work与关联对象、账户能力、版本和锁。selected保留为默认有限范围、未知模式拒绝；该配置不进入工具参数。NAS只有桥接/领域两个模块与范围更新，角色/令牌/正式发布/私人资料边界保持。详stl4/PUBLIC_MCP_SECURITY_20261112.md。

## 2026-11-12 公网 MCP 单用户入口

用户最新授权增加受保护Streamable HTTP。tools/stl_mcp/public_server.py经DjangoBridge复用同七工具/领域服务；固定账户能力、token_version、三书写入范围、锁/版本/回执仍在服务端执行。独立NAS容器复用API镜像，Nginx仅代理/mcp，源库/文件系统不分叉。Bearer摘要/到期/Host/Origin在协议前校验，本机DPAPI helper供应认证；NAS journal持久保存计划，原三计划已迁移验证。原stdio仍可备用，下文“无远程监听”为此前本机阶段记录。部署、修复和边界见stl4/PUBLIC_MCP_SECURITY_20261112.md。

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
