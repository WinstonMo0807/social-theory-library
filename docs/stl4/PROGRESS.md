# STL 4.0 当前执行状态

## 2026-10-15 U01 首页静态复核（当前接续）

- 已补充当前入口契约 [`docs/stl4/API_CONTRACT.md`](API_CONTRACT.md)，锁定 `GET /api/catalog/home/` 的公开资格、空/部分故障/全故障状态、区域来源和前端私密继续阅读边界。
- 已修正首页两个故障状态的原生 `<a href="/">`，改用 Next `Link`，避免绕过应用路由；目标前端文件 ESLint 不再有该规则错误（图片优化提示仍为警告）。
- `python -m compileall -q api/catalog/home_views.py api/catalog/urls.py api/catalog/serializers.py api/catalog/services/recommendations.py` 已退出 0。
- 全量 `web` TypeScript 静态检查仍被既有 `web/tests/admin-collections-v306-live.spec.ts` 与 `web/tests/relation-timeline-v306-live.spec.ts` 的 3 个 TS7022 阻断；这些错误不在 U01 文件调用链内，未擅自修改旧测试。
- 尚未运行正式 Django/前端测试、构建、浏览器或视觉验收；U01 仍是“已实现、静态部分通过、正式验收待核实”，不计为完成。
- U01 局部 Git 检查点为 `4dbe776`。工作区其余改动没有被清理或重置。

更新于2026-10-15。阶段：全量功能开发，未进入统一验收。

## 恢复基线

- 工作区 `F:/agent skills/书库开发3`。开始时main，HEAD `14a41a11d567a9ed52b2403eab9e5fe4014a3573`，本地远端跟踪显示落后74提交；未fetch/pull，不据此覆盖当前修改。
- 原工作区有221条Git状态项（目录项可能包含多个文件），包括已有后端、Reader、视觉整理等。已保留。当前分支 `codex/stl4-unified`。
- 本轮前状态和tracked补丁保存在忽略目录 `output/stl4-baseline/`，不是完整备份，未追踪文件仍在工作区。不得reset/clean。
- 旧前后端分工取消。历史docs/stl-4.0保留但停止作为当前任务队列。

## 正在实施

U01：首页公共发现及真实空态。涉及 `/`、公共页头、`GET /api/catalog/home/`、站点默认文案；复用已有公开模型，不新增schema。参考R01-main/sub01/states。页面代码、聚合接口、分区状态与安全读取正在协调。尚未标记视觉完成。

U00：完整视觉索引、持续恢复文件和保账户清理命令安全边界。本轮未执行数据库迁移/清理或生产连接。

## 下一个业务单元

完成U01静态检查及Git检查点后，按首页模块其余帮助/关于/菜单视图收口，再进入探索统一检索→原文证据→Reader。管理端与私人研究按共享身份和业务依赖逐个接入，不能只换皮。

## 尚未完成与风险

- 全部209视图尚未最终验收，旧页面不能批量算作4.0实现。
- 历史实现有未提交依赖，检查点需保存必要源码，不能只提交前端孤立变化。
- PDF示例内容不得导入生产；精确装饰图/媒体资产与参考差异需登记。
- 生产清空仅有历史文档记载；现状、备份、账号登录待最终阶段复核，不重复执行。
- 尚未启动正式E2E/功能/视觉验收、构建部署或推送。
