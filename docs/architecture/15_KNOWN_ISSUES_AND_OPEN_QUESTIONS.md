# 15 · 问题、证据与待核项

[架构目录](README.md) · [测试记录](14_TESTING_AND_QUALITY.md) · [页面观察](PUBLIC_SITE_VERIFICATION.md)

分类按本次审计请求：**A已复现，B源码调用链确认，C有证据但尚未复现，D需要真实管理员测试。** 这与旧开发进度中的A/B/C/D含义不同。D是验收范围，不是断言有缺陷；建议均未作为本轮业务改造执行。

| 编号 | 类别 | 场景 | 本轮状态 |
| --- | --- | --- | --- |
| VN-A01 | A | 390px手工编目控件挤压 | 公网空白表单已复现，未改界面 |
| VN-A02 | A | OpenAPI学者slug规则落后源码 | 已重生成schema，业务实现未改 |
| VN-A03 | A | 两个历史测试夹具不满足当前契约 | 隔离回归已复现，保留失败，未改测试/业务 |
| VN-B01 | B | 运行源码与GitHub main没有完整对应提交 | 已整合源码并记录指纹；原生产构建SHA仍不能倒推 |
| VN-B02 | B | 旧EvidenceSnippet没有固定正文修订 | 模型与serializer已确认，未迁移数据 |
| VN-B03 | B | 方法使用映射为经验应用 | 兼容映射已确认，未变更知识语义 |
| VN-B04 | B | 全书知识审阅分散于多个工作区 | 现有调用链已确认，提出集中审阅设计 |
| VN-C01 | C | 状态页不可用/未探测与按需服务的解释 | 已观察标签；未触发服务需求，不判定服务故障 |
| VN-D01 | D | 并发保存、审核版本与发布恢复 | 需隔离写入/故障注入测试 |
| VN-D02 | D | 共享网站草稿的整份发布范围 | 需多编辑者场景验收 |
| VN-D03 | D | 私人锚点、OCR更新与跨账户残留 | 需合成材料与多账户测试 |

## VN-A01

**空白手工编目在390px发生控件挤压。**

| 项目 | 证据与判断 |
| --- | --- |
| 业务场景/页面 | `/admin/cataloging/new`，手机上选择材料类型及责任角色 |
| 前端 | `ManualCatalogForm` / `PersonField`；[manual-catalog.tsx](../../web/components/admin/workflow/manual-catalog.tsx)、[CSS](../../web/components/admin/workflow/manual-catalog.module.css) |
| API/Service/Model | 保存链为ManualCatalogView→cataloging_sessions/work_editor→Work、Edition、Contribution；本问题发生在提交前，未调用写接口 |
| 实际表现 | 类型文字挤压、责任者角色“作者”换行；[截图](images/admin-cataloging-mobile.jpg) |
| 根因 | 窄屏仍四等分且nowrap，字体可读下限与不足列宽冲突；姓名/角色/删除按钮共同行，select继续收缩 |
| 影响 | 材料类型和角色难辨认，增加误选概率；未证明存在错误保存 |
| 建议 | 仅调整此表单窄屏布局：材料类型两列或等价可访问选择；姓名与角色分行或保证角色宽度；保持底部操作和标签 |
| 验收 | 320/390/768/1440及大字档均完整显示类型/角色，键盘可用，保存栏不遮挡焦点；使用测试数据验证值不改变 |

## VN-A02

**OpenAPI仍限制学者slug为ASCII。**

场景是客户端依接口文档验证中文学者链接。前端入口 `/scholars/[slug]`、`/admin/scholars/[scholarId]`；后端Scholar serializer/模型及迁移0090已经允许Unicode，`api/openapi/schema.json`中两处slug pattern仍为旧ASCII表达式。`npm run api:check`实际退出1。

根因是已部署模型/serializer更新未同步生成契约；影响生成客户端和文档准确性，不证明生产中文路由失效。涉及ScholarProfile、AdminScholarDetailView与公开学者详情；无独立写服务更改。本轮按现有生成器更新schema两处pattern（4行增/4行删），TypeScript生成类型没有变化。验收是api:check退出0、Unicode链接/slug测试保持合法，不能借此修改已有slug。

## VN-A03

**有限回归中两个旧测试的前置数据不合法。**

1. `test_contribution_scope_20261021::test_two_chapters_one_contributor_survive_workflow_save_and_snapshot`复用`test_reading_paths_20261021.source`，直接创建只有title的Work。document_type为空，在`work_editor._refresh_edition_metadata`映射中触发KeyError。涉及Work/Edition/Contribution；真实入口为WorkflowEditor的责任者编辑及WorkMaintenanceSectionView。正常表单/serializer是否可能产生同样空值尚未复现。
2. `test_knowledge_publish_owner_20261023::test_original_revision_owner_and_replay_remain_bound`创建没有公开关联材料的Topic，预期发布200，实际400。诊断响应明确要求至少关联作品、学者、知识条目或策划。调用链为KnowledgePublishControl→AdminEditorialRevisionPublishView→publish_editorial_revision→topic_editor.ensure_topic_publication；模型Topic/EditorialRevision。owner隔离的前置断言通过，不能将此失败写成owner权限失效。

根因是测试夹具没有满足当前领域契约，导致原本要验证的章节保留/幂等重放没有走到目标断言。建议分别补齐合法材料类型、合法公开关联，再保留原目标断言；对真正非法输入另测清楚的失败结果。本轮不擅自改业务兜底或放宽发布条件。验收需这两项恢复到目标断言，同时非法状态测试仍拒绝；并发锁需PostgreSQL测试而非SQLite推断。

## VN-B01

**公网发布与GitHub main版本脱节。**

页面包括全站；前端Web发布文件、API/OCR源码与main不属于同一版本。相关API为health/ready，服务为部署/镜像交付，模型不适用。审计开始时main为7cadf014的3.0.9.1，原本地分支315a3c48另有未提交且已部署代码；health仅报告4.0.0，不能给出完整source SHA。

根因是分次发布与未入Git的源码覆盖。影响可复现部署、审计和维护者判断。已用791份API、5份OCR源码与Web发布清单整合差异，形成f5406339检查点；后续文档与生成schema是本轮新增。建议未来release manifest固定source SHA、digest与环境注入边界，发布包不得默默包含未记录源码。验收应从干净checkout生成清单、与镜像逐项对应，分别核对API/Web/OCR；本轮没有宣称原生产由新commit构建。

## VN-B02

**旧证据片段的document_revision_id是当前推导值。**

| 项目 | 证据与判断 |
| --- | --- |
| 场景/页面 | 理论/作品知识关系的原文证据，`/admin/theories/relations`、作品工作台与公开关系展示 |
| 前端/API | TheoryRelationsAdmin、Workflow知识/证据选择；`theory-system/evidence`、节点/关系读取 |
| Service/Model | EvidenceSnippet、EvidenceSnippetSerializer；与EvidenceSpan/evidence_envelope对照 |
| 源码事实 | [模型](../../api/catalog/models.py#L3235)保存file/page/quote；[get_document_revision_id](../../api/catalog/theory_serializers.py#L467)读取file.edition.active_catalog_revision，而非原证据创建时修订 |
| 根因 | 旧证据协议锚定文件，较新的正文证据协议锚定修订；兼容返回字段相同但证据强度不同 |
| 影响 | 重新OCR/换正文后无法仅凭该字段还原旧quote最初依据的修订；本轮未复现错误引文或错页 |
| 建议 | 编辑器显示来源协议/待核状态；未来迁移前先核对历史数据，不能把当前revision批量回填成历史事实；新证据优先复用EvidenceSpan |
| 验收 | 合成文献在revision A建证据，产生B后仍能看到A或明确待核，不能静默标成B；公开过滤继续生效 |

## VN-B03

**方法使用与经验应用在兼容映射中合并。**

业务为一部著作使用某理论的方法、但不以该理论解释经验对象。入口是WorkflowEditor知识关系及理论关联；前端KnowledgeFields/理论节点关系表；API为工作台knowledge和theory-system/work-relations；服务为[canonical_identity.py](../../api/catalog/services/canonical_identity.py)，模型旧WorkKnowledgeRelation/WorkTheoryRole与新WorkNodeRelation。

源码`LEGACY_WORK_ROLE_MAP['method_use'] = EMPIRICAL_APPLICATION`，新枚举没有独立method_use。影响方法使用与经验应用的细分标签不能靠规范role恢复，不能把它们作为两个已经支持的等价选择介绍给管理员。建议先确定业务语义及历史保留策略，再设计单独role或明确保留原角色的provenance；本轮不迁移。验收要用同一本书的理论发展、方法使用、经验应用、引用/一般提及等不同关系，检查保存与公开标签不混淆。

## VN-B04

**整书建议不能在一个已有队列中完成集中审阅。**

入口横跨Work工作台、学者/人物、理论/主题、独立证据编辑、阅读路径和文章。前端为WorkflowEditor、WorkCurationEditor、FieldAssistantControl、MaterialAssistantProvider、ReadingPathWorkbench、RecommendationIssueEditor；API/Service分别为field-assistant、work curation/claims、theory-system、evidence-curation和editorial_assistance；数据涉及候选、规范实体、关系、EvidenceSpan、CuratedClaim、EditorialRevision。

源码显示字段助手按字段上下文组织，高价值观点最多5个活跃决定，文章助手按1–40个选定来源提供outline/guide/comparison。这些不构成整书各章覆盖、全部实体/关系/冲突的统一知识包。影响是管理员在多对象间核对身份、页码和发布范围；没有实测跨页次数或耗时，不编造负担指标。

建议的具体页面/组件调整见[集中审阅设计](08_CURATION_WORKFLOW.md#建议在现有工作台集中审阅整书建议)。验收应让管理员从一部合成文献完成候选→确认→草稿→影响预览→正式发布，并记录错关联、缺证据、返回位置与重复输入。保留深度规范编辑器和既有正式账本，不新建平行知识库。

## VN-C01

**按需服务与维护页状态需要联合判读。**

页面 `/admin/processing/status`，组件SystemStatusCenter，后端system status/health及common AI runtime、nas_on_demand；数据为ProcessingJob/能力状态/索引配置与Redis需求。已观察部分能力“尚未探测/不可用”，同时query/OCR容器停止且按需管理已配置。

可能原因包括空闲停止、探测缓存、模型/索引未就绪；现有证据不能确定具体哪一种，也不能证明正常查询会失败。影响是管理员可能混淆资源节约状态和真实故障。建议以真实任务/需求/冷启动过程区分“空闲、启动中、不可用、失败”，但先做隔离环境复现；验收需正常需求成功唤起、故意缺模型时明确失败、空闲停止不丢任务。本轮未触发生产需求或修改状态提示。

## VN-D01

**审核版本、并发保存与发布失败恢复。**

场景：两名编辑同时修改并预览，发布请求超时或队列投递失败。入口为WorkflowEditor、KnowledgePublishControl、PublicationDesk；API为workspace edits、knowledge-preview、editorial revision publish、publication history/retry；服务为editorial_revision/publication_commands/knowledge_publication；模型为EditorialRevision、CatalogPublicationRevision、KnowledgePublicationEvent与ProjectionState。

源码已有If-Match、锁、base revision、owner与回执，不据此声称端到端已通过。待验证结果：本地输入保留，旧预览不能发出新草稿；重试不重复发布，当前公开快照继续合法服务；已确认发布而索引未就绪必须分别显示。缺少的是本轮真实写入/网络故障/多连接证据。建议在隔离PostgreSQL与测试账号执行，不在生产注入故障。

## VN-D02

**网站共享草稿的整份发布范围。**

场景：编辑A改欢迎页、编辑B改关于页；A点击发布。入口 `/admin/welcome`、`/admin/about`，组件SiteContentEditor→site-workspace→SitePublicationReview；API为site-content/review/publish；服务editorial_issues/site_publication_review；模型SiteSetting、EditorialRevision。

源码复用共享网站草稿与审核，需真实确认审核界面清楚列出整份变更和版本竞争。不是已复现“暗中发布他人内容”。建议仅在证据证明提示不足时调整审核布局和范围摘要；验收应准确看到两个栏目的修改，旧版本发布遭拒，撤销/恢复不覆盖另一编辑者未审核内容。

## VN-D03

**正文更新、私人锚点与账户切换。**

场景：Reader注释/研究引用建立后重新OCR，或切换账户时旧请求才返回。入口Reader、account研究页、admin OCR/outline；组件use-reader-document、usePersistentWorkspace及私人工作区；API为manifest、reading注释/研究和ingestion处理；服务document修订、reading加密/owner过滤、evidence envelope；模型Annotation、DocumentRevision、ResearchTurn、ReadingProgress。

已有checksum、orphaned、stale与owner清理机制，需合成文件和两测试账户验证真实交互。验收应旧锚点不静默指到新内容，未授权账户看不到旧状态，目录下载生成不修改正文身份；分享只暴露明确范围。此项无当前故障根因，缺少的是允许写入的测试证据，不能凭假设发起业务重构。
