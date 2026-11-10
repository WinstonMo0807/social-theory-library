## 2026-11-10 学者关系兼容边界

ScholarRelation只保留历史身份、来源、已发布与未发布修订。旧HTTP保存转换到ChangeSet，公开关系及学者消费者统一读取来源独立的Assertion。旧取消回执与请求锁保留；回收站撤回转审核，旧直接发布返回明确替代入口。Django后台WorkKnowledgeRelation/PersonKnowledgeRelation只读。回填命令backfill_knowledge_core --relations --human-pages --batch-size 100按当前公开修订保留来源，数量与备份见CURRENT_PROGRESS；无ScholarRelation真实候选数据，测试夹具不能代替实书迁移。

2026-11-10 专题页可无Work/Entity主对象，以KnowledgePage自身范围提交人工ChangeSet（0098）。正文、标题、范围由同一EditorialRevision管理；公开/knowledge/{slug}仅读取发布投影，来源权限变化继续隐藏受影响区块。关联资料与跨知识页链接由既有resolve_target验证，不另建正文权威。

2026-11-10 身份归并：`knowledge_identity`保存Entity重定向，查询按明确归并展开，原Assertion端点与KnowledgePage不重写。原节点/人物归并命令继续负责权限、预览、事务、幂等和可回退记录；知识修改纳入指纹保护。类型资料里的`prose`只保存与原文完全相符的格式标记，继续作为类型资料功能保留，不与Wiki正文双向同步。

> 2026-11-10 知识架构增量：ChangeSet仍为唯一审核/应用服务；人工知识页可按Work/Entity范围提交，自动与MCP草稿须固定DocumentRevision。AssertionSource的文献出处与EvidenceAnchor精确证据分开；Assertion.supersedes保留历史修订。来源专属学术图谱从Assertion查询投影，已迁移旧关系只作历史兼容。详见[知识核心实现记录](stl4/KNOWLEDGE_INTELLIGENCE_20261109.md)。旧写入入口的剩余迁移明确列在该记录，不宣称已全部退役。

# STL 当前架构

2026-11-10 候选管理设计采用原文与检索、知识编纂、Intelligence三个连通工作区。新增 KnowledgeBlockDependency 仅保存当前知识页区块的依赖投影，EditorialRevision仍是草稿正文来源；人工编辑与外部/模型建议共用ChangeSet。三个管理工作区及公开知识页投影已经接入，0094在隔离内网候选完成；正式环境未迁移。原文窗口与关键词检验共用现有检索服务，正文由不可变RevisionPage与locator提供。官方比较依据及状态见下方候选记录。

2026-11-10 新增[Knowledge Core / Intelligence 内网候选](stl4/KNOWLEDGE_INTELLIGENCE_20261109.md)，记录新模型、服务、locator、配置、隔离部署和未完成项。以下仍描述正式环境，不能将候选能力误作已上线。

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
