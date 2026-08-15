# 理论流派与知识组织系统实施计划

## 目标

在现有 2.3.1 项目内建立可审核、可追溯和可扩展的理论知识组织功能。前台展示来自同一套规范数据，管理员只在统一节点、关系、证据、事件和阅读路径中维护内容。

## 功能开关

新增 `THEORY_SYSTEM_ENABLED`。默认在本地开发和迁移测试中开启。关闭后：

- 旧 `/theory-schools` 页面继续工作。
- 馆藏、阅读器、全文、观点检索、主题、学者和读者中心不受影响。
- 新 `/theories` 地址返回兼容跳转或维护提示。

## 实施顺序

### 第一阶段  审计与设计

- 完成现状审计、数据模型、迁移方案、接口和回退设计。
- 固定旧数据统计，作为迁移前后核对基线。
- 建立四份持续文档。

验收：文档与当前源码相符，未改变业务数据。

### 第二阶段  规范节点与审核基础

- 新增规范节点、别名、学科关联、理论关系和版本记录。
- 新增 reviewer 角色和知识审核权限。
- 新增节点 CRUD、别名、版本和事务化合并。
- 新增旧对象映射和迁移报告命令。

验收：迁移可升级和回退，旧数据数量不减少，管理员可编辑和发布节点。

### 第三阶段  公开理论页面

- 建立 `/theories` 首页。
- 建立学科详情和统一节点详情。
- 在文献详情加入已确认的理论关联。
- 保留旧地址并建立映射。

验收：统计来自数据库，空模块隐藏，未发布数据不可见。

### 第四阶段  PDF 证据与关系审核

- 新增 evidence snippet 和审核任务。
- 复用现有 OCR、Passage、页码与边界框。
- 在后台审核候选理论、关系角色和原文证据。
- 点击证据进入现有阅读器对应页，坐标存在时定位原文。

验收：自动识别只生成 pending，确认后才进入文献与理论详情。

### 第五阶段  时间轴与阅读路径

- 扩展事件类型和多对象关系。
- 实现时间轴分页、筛选、前后台编辑和发布。
- 实现阅读路径、阶段和项目拖动排序。

验收：公开端只显示 published，路径顺序完全来自后台。

### 第六阶段  局部图谱与响应式

- 服务端按中心节点返回一到两层邻域。
- 默认最多 20 个节点，单次最多 30 个。
- 桌面提供筛选、展开、收起、缩放、平移、小地图和分享参数。
- 手机端显示节点和关系列表。

验收：空库和大库均不读取全图，移动端可阅读。

### 第七阶段  验证与局域网交付

- 运行完整后端测试、前端类型检查、ESLint、构建和端到端流程。
- 在临时 SQLite 执行升级、回退和再次升级。
- 校验 Compose 配置。
- 生成旧数据迁移报告、API 文档、管理说明、部署和回滚说明。

本阶段不执行公网域名、证书或外网开放。

## 新公开路由

| 路由 | 内容 |
|---|---|
| `/theories` | 理论流派探索首页 |
| `/theories/disciplines/[slug]` | 学科详情 |
| `/theories/nodes/[slug]` | 规范节点详情 |
| `/theories/timeline` | 历史时间轴 |
| `/theories/graph` | 局部理论图谱 |
| `/theories/reading-paths/[slug]` | 阅读路径详情 |

旧 `/theory-schools`、`/theory-schools/[slug]`、旧时间轴和图谱地址暂时保留。

## 新后台路由

| 路由 | 内容 |
|---|---|
| `/admin/theory-nodes` | 理论传统、子学科、概念、争论和研究问题 |
| `/admin/theory-nodes?node=<id>` | 独立节点编辑、版本和影响范围 |
| `/admin/theory-relations` | 文献关系审核与理论关系编辑 |
| `/admin/theory-timeline` | 时间轴事件管理 |
| `/admin/reading-paths` | 阅读路径管理 |

旧 `/admin/theory-schools` 保留，并跳转或链接到规范节点管理。

## 新接口概览

公开接口：

- 理论首页聚合数据
- 学科详情
- 节点列表与详情
- 节点文献、证据和关系
- 时间轴分页查询
- 局部图谱查询
- 阅读路径列表与详情
- 理论统一搜索

后台接口：

- 节点、别名和学科关联 CRUD
- 节点版本和合并预览、合并、回滚
- 文献节点关系和理论关系 CRUD
- 审核任务和批量审核
- 时间轴 CRUD
- 阅读路径 CRUD 和排序

所有列表接口支持分页、筛选和排序。

## 预计主要改动文件

- `api/accounts/models.py`
- `api/common/permissions.py`
- `api/catalog/models.py`
- `api/catalog/serializers.py`
- `api/catalog/views.py`
- `api/catalog/knowledge_views.py`
- `api/catalog/urls.py`
- `api/catalog/services/`
- `api/catalog/tasks.py`
- `api/catalog/migrations/`
- `web/lib/server-api.ts`
- `web/lib/api.ts`
- `web/components/admin-shell.tsx`
- `web/components/admin-sections.tsx`
- `web/components/theory-*`
- `web/app/theories/`
- `web/app/admin/theory-nodes/`
- `web/app/admin/theory-relations/`
- `web/app/admin/reading-paths/`
- `web/app/globals.css`
- `web/tests/`
- `api/tests/`

## 回退原则

- 迁移不删除旧表或旧记录。
- 新节点保存旧对象映射。
- 功能开关关闭后继续使用旧页面和旧接口。
- 新关联删除只删除映射和新版本记录，不删除作品、PDF 或学者。
- 合并操作保存来源和目标快照，回滚时按映射恢复。
