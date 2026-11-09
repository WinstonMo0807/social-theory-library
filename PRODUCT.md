# Social Theory Library 产品事实

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

公开访客浏览已发布书目与知识内容；登录读者阅读原文并维护本人笔记、书单、计划与连续研究。编辑、管理员、馆长按现有能力矩阵管理资料、策展、发布、任务与配置。馆长身份不等同于所有管理员。

## Product Purpose

社会理论书库以真实作品、版本与可定位原文支撑浏览、阅读和研究。此次交付是当前公网已有能力的全站视觉与交互更新，不增加未确认的知识架构或 Intelligence Demo。

## Operating Context

业务基线是经运行文件与发布包核实的 Web work-session-r2、API catalog-session-r1，以及单独登记的 worker semantic-status-r2。源码差异、角色、功能开关及唯一覆盖表见 `docs/stl4/public-visual-20261110/`。书目保存、草稿保存、公开发布、文件处理和索引就绪具有不同含义。

## Capabilities and Constraints

保留现有 Django、Next/Vinext、PostgreSQL、Redis、Celery、Meilisearch、PaddleOCR，保留有效 URL、权限与数据。公网探索仅只读；写入验证限本轮隔离临时测试库。独立预览为 127.0.0.1:18110，API 为 18111，后端禁止出站连接。公网部署、DNS、隧道和最终切换仍须用户最终授权。

页面、字段、操作、状态和 API 的事实以本轮覆盖表及源码为准；自动提取候选不视作运行通过。已有 RAG/研究相关能力只按实际公网启用范围处理，不提前并入 Demo。

## Brand Commitments

名称保留 Social Theory Library / 社会理论书库。实现必须复用 `web/public/brand/stl-symbol-20261027.svg` 等精确现有资产。用户指定纸白、白色内容层、炭黑、暖灰及克制砂金；已明确取消 Elicit 参考。此前试稿只提供风格参考，不提供业务事实。

## Evidence on Hand

已核实基线记录、唯一页面覆盖表、接口与 serializer 字段清单、匿名公网响应和隔离角色响应均位于本轮记录目录。测试环境中的书目、PDF、账户及任务明确为合成夹具；不得进入产品正式内容。品牌板与先前 Image Gen 试稿已查看。新一轮正式设计图尚未生成。

## Product Principles

- 页面展示必须追溯到真实接口、来源、版本与权限。
- 管理员应能看清编辑对象、实际展示位置和未保存、草稿、发布的区别。
- 私人数据、来源撤回规则、原件与历史版本不可因视觉改版改变。
- 全站覆盖以逐项证据为准，不以共享组件或代表页面替代其他消费者验证。

## Accessibility & Inclusion

保留用户字体、字号、外观偏好。核对宽屏、平板、390px、320px与放大字号。键盘、焦点、减少动态效果、对比度和模态滚动须实际可用。

## 本轮决定来源

上述范围、方向与工作顺序均来自用户本轮明确要求及已读取源码。用户已要求持续自主完成；不重复询问已明确的产品事实和先出图后实现的流程。尚未核实的业务项仍在唯一覆盖表中保留待闭合状态。
