# STL 4.0 架构事实与决定

## 2026-10-18 个人阅读计划与身份边界

个人阅读计划沿用加密 PersonalReadingPlan，与同一 Discovery、公开修订与 Reader 共用来源身份。周预算/周期、只读预览和人工调整通过既有 PATCH 协议传递，不新增平行馆藏或业务表。计划级笔记使用默认关闭，显式owner+confirmed名单及版本用于生成前、写回与读时校验；未采纳候选在撤销后失效，已人工采纳结果保留。前端通用私人工作区在读写前后核对cookie owner，避免跨账号响应落到旧工作区。完整行为与迁移/权限验收仍待统一执行。

2026-10-15，本轮仅静态源码核对，未启动服务或连接生产。

- 前端：`web/package.json`，React 19 / Next 16 / Vinext / Vite，App Router入口；PDF.js现有Reader。版本来自本地清单，不代表生产运行版本。
- 后端：Django 5.2、DRF、JWT、drf-spectacular；`api/config/urls.py` 接 accounts/catalog/ingestion/reading/distribution。
- 持久身份：Work → Edition → Asset → Page，正式发布快照、DocumentRevision、EvidenceSpan。私人研究模型在 reading，已有未提交迁移0008/0009。catalog已存在0064/0065/0066、ingestion0020候选迁移。本轮不执行迁移。
- Compose中配置PostgreSQL、Redis/Celery、Meilisearch、PaddleOCR与推理服务。源码存在不代表当前可用；生产启动/数据/资源状况待最终实测。
- Discovery已有generation/模型维度/任务重试身份、QueryLexicon与正式资格过滤。旧同步入口仍为兼容；EG2实验不代表活动生产索引。
- 视觉驱动的观点检索使用同一 Discovery 会话接入可选深度补充：`api/catalog/services/retrieval/deep_pipeline.py` 只读取显式配置的隔离 EG2 索引并调用 allowlist 的 BGE/ConvMemory 服务；`channels.deep`、`passages_deep` 和 `task_progress.deep` 保存真实异步状态。深度结果回填前再次执行来源、权限、EvidenceSpan、页码和修订校验；默认关闭时基础 E5/mMARCO 结果不受影响。该 lane 不代表生产模型或活动索引已经切换。
- 公共与管理共用一套主库、文件、索引与队列。保留可用栈，不为满足视觉建立平行书库。重大结构改造可在明确需要时实施并记录迁移。

## 本单元决定

首页以 `/api/catalog/home/` 公共只读聚合提供同一版式所需的策划、学者、主题、最近馆藏、随机池与热搜。复用正式公开serializer和资格规则，不提供私人数据、不触发发布或重索引。各分区区别 ready / empty / unavailable，失败数量未知而不是0。前端SSR适配后渲染，个别分区失败不抹掉成功内容。

网站默认文字属于系统配置，可在空库存在。真实书目/学者/策划不能用本地demo数据补齐。原站点内容草稿/正式发布继续复用，不直接覆盖管理员已发布配置。

## 调用链阅读入口

首页：`web/app/page.tsx` → `web/lib/api/home.server.ts` → `api/catalog/home_views.py` → 原公开查询/序列化服务。
站点文案：`api/catalog/site_config.py` / `SiteSetting` / `catalog.services.editorial_issues`。
研究：`api/reading/research_models.py`、`research_views.py`、`research.py`、`plan_rules.py`、`citation_audit.py`。
完整旧地图按模块查 `docs/NEXT_DEVELOPMENT_MAP.md`，不重复加载历史全集。
