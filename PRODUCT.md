# Social Theory Library 产品事实

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

公开访客浏览已发布网页。登录读者阅读原文、维护本人笔记、书单、计划及连续研究。编辑、管理员、馆长按现行权限管理馆藏与内容；馆长专属配置不向普通管理员开放。

## Product Purpose

以真实作品、版本、可定位原文支持阅读和研究。本轮只调整当前公网管理台与读者中心的主体排版，禁止把未确认 Knowledge Core / Intelligence Demo 纳入。

## Operating Context

已核实公网 Web work-session-r2、API catalog-session-r1；worker semantic-status-r2 的差异独立登记。源码还原基线 7b8963fe；视觉实施前检查点 7c4e4a0d。完整页面、接口、字段、状态与角色盘点位于 docs/stl4/public-visual-20261110/。

## Capabilities and Constraints

现有 Django、Next/Vinext、PostgreSQL、Redis、Celery、Meilisearch、PaddleOCR 架构不变。现有 URL、API、角色、状态、字段、控件、交互和内容不变。只允许 CSS 排版调整，以及必要的样式引入与作用域包装。

管理台与读者中心的任务分类栏整体保留。登录页及登录弹窗、所有弹窗和抽屉、已有加载动画、公开页、独立阅读器和公开展示预览原样保留。公网部署、DNS、隧道及切换没有授权。

## Brand Commitments

复用已有黑金书页／人物 SVG：web/public/brand/stl-symbol-20261027.svg。名称 Social Theory Library / 社会理论书库保持。字体、字号、字重、行高、字色及外观偏好按现网级联保留，不采用生成图中的替代品牌、字体、导航或业务文案。不参考 Elicit。

## Evidence on Hand

唯一覆盖清单 COVERAGE.csv 保留 157 条全站记录，本轮 80 个管理／读者入口，77 个保留项；入口中的公开预览正文依然保留。76 张桌面图提供允许范围内的布局参考，图片生成记录和历史版本可追溯。手机不再生成图片，直接通过响应式代码适配。

独立预览 http://127.0.0.1:18110，隔离 API 18111，均使用临时 SQLite、合成账号、合成 PDF 与测试对象，禁止出站。界面截图中的测试书目和任务结果不是学术事实。未实际运行模型、OCR 或邮件任务，不将其未配置状态美化为成功。

## Product Principles

- 现有功能、数据、权限、内容及任务分类保持。
- 图片仅指导允许修改的空间关系，不替代真实组件。
- 保存草稿、发布、回执核对和失败恢复沿用真实业务入口。
- 本轮发现的无关功能缺陷只记录，部署必须等最终授权。

## Accessibility & Inclusion

沿用键盘与焦点、减少动态效果、外观与字体偏好。实际核对 1536、768、390、320px；大号宋体和夜间模式检查单独记录。原文使用原有 PDF 渲染，不更换其字体或内容。
