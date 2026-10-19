# 首页与帮助前端实施记录（2026-10-18）

本记录对应最终视觉 PDF 第 10–17 页的前端收口。唯一图源是 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf`；已从该文件重新渲染并提取各页内嵌图，实际查看第 10–18 页。临时产物在 `tmp/pdfs/stl4-home-support-20261018/`，不进入 Git。第 18 页由主线负责，本单元未修改 SiteHeader、SiteFooter 或共享导航 CSS。

## 继承与本次修改

- 首页继续复用 `/catalog/home/`，保留既有正式公开馆藏、策划、学者、主题、匿名聚合热搜与部分失败/空态。第 11 页主题 3+2 布局和移动单列已有实现，本次没有重写该服务。补充可见搜索等待提示；继续阅读在明确会话变更时立即中止并清除前次记录，请求有 30 秒上限且不在 401 后自动重发；显示实际返回的最近阅读时间和真实封面，缺封面时使用中性占位；统一第二排主题缺图占位高度。
- 帮助首页按第 13 页改为六栏目、三步指南、四快捷主题与反馈入口。手机目录使用原生 `details` 展开。搜索指南直接提交至探索页；阅读操作区为明确标记的界面说明，不展示虚构原文。
- 新增版本化静态帮助内容：搜索、阅读、引用、隐私、来源五篇各四步，以及八条 FAQ。FAQ 可筛选、搜索、展开，空结果有清除筛选与提交问题入口。帮助内容说明现有实际能力，不把检索结果当作者原话，不承诺固定反馈处理时间。
- 第 15 页文章实现编号步骤、桌面锚点目录、移动顺序、返回入口与来源纠错链接。引用示例复用 Reader 的格式类型，明确标记“非真实文献”；切换格式、填写演示页码、复制和导出均可操作，复制内容仍保留示例标识。真实引用继续由 Reader 当前来源生成。
- 第 14 页关于页调整为三说明卡、右下进一步了解、访问边界条。保留已发布 About blocks；已存在的“为什么建设”正文放入展开说明，不修改数据。配置/介绍读取失败会明确提示，静态帮助正文仍可阅读，不拿样例替代已发布资料。
- 第 16 页反馈为桌面说明侧栏与主表单、移动单列；五种分类、4–500 字正文、可选公开路径、可选邮箱、显式用途同意、取消与未保存保护。相关页面可以修改或移除。未接权威来源元数据前，仅显示实际路径，不猜测题名或封面。
- 提交使用稳定 `request_id` 与实际规范化 body 绑定。网络/5xx/超时等结果未知时保留原稿与原请求，并暂时锁定输入，重试取回原回执；明确 4xx 留下可编辑输入；不自动刷新重放写请求。明确会话变化清空正文、邮箱、回执并中止在途请求。成功界面只显示后端回执的真实编号、时间和状态。
- `SupportSourceStatus` 已接 `/help/source?source=/reader/<uuid>?page=N`，复用公有 Reader manifest 读取，显示当次元数据或分类失败、重新读取及纠错入口。该组件已交由 `citation_backend` 接续第 17 页状态 4，不以本单元的初版认定闭环。

## 反馈接口协作契约

`POST /api/catalog/feedback/`：

```json
{
  "request_id": "client-generated UUID",
  "category": "content | function | usage | suggestion | other",
  "body": "trim 后 4–500 字",
  "contact": "可选邮箱，或空字符串",
  "path": "可选站内公开路径，或空字符串",
  "consent": true
}
```

首次 201，同 nonce 与规范化内容重放 200，返回 `{id, request_id, status, created_at, message}`；同 nonce 不同内容为 409。响应不回显正文或邮箱。匿名访客不需要登录。原 `citation/accessibility` 类别由后端兼容保留。后端由 `citation_upload` 实施，本前端不以本地 mock 作为生产成功回执。

路径最长 400 字符，只接受公开栏目相对路径；拒绝账户、管理、登录、外部协议、双斜线、反斜线、控制字符与编码目录逃逸。仅 Reader 保留 1–999999 的正整数 `page`，其他查询与 fragment 不随反馈提交。服务端再次校验。源信息卡、更新时间、订阅及来源失效闭环由独立来源单元补齐。

## 文件白名单

1. `web/components/public/support-hub.tsx`
2. `web/components/public/support-hero.tsx`（新）
3. `web/components/public/support-citation-example.tsx`（新）
4. `web/components/public/support-source-status.tsx`（新，已移交来源单元）
5. `web/components/public/feedback-form.tsx`
6. `web/components/public/about-public-view.tsx`
7. `web/components/public/home-interactions.tsx`
8. `web/lib/support-content.ts`（新）
9. `web/lib/api/feedback.client.ts`（新）
10. `web/app/help/page.tsx`
11. `web/app/help/[slug]/page.tsx`
12. `web/app/feedback/page.tsx`
13. `web/app/about/page.tsx`
14. `web/styles/features/support.css`
15. `web/styles/features/home/home-stl4.css`
16. `web/tests/support-feedback.spec.ts`（新）
17. 本记录。

## 实际检查

在 `web/` 执行：

```text
node node_modules/eslint/bin/eslint.js components/public/support-hub.tsx components/public/support-hero.tsx components/public/support-citation-example.tsx components/public/support-source-status.tsx components/public/feedback-form.tsx components/public/about-public-view.tsx components/public/home-interactions.tsx lib/support-content.ts lib/api/feedback.client.ts app/help/page.tsx "app/help/[slug]/page.tsx" app/feedback/page.tsx app/about/page.tsx tests/support-feedback.spec.ts
```

退出码 0，0 error、3 个 `@next/next/no-img-element` warning（既有首页主题图、公开横幅、当次来源封面）。图片使用现有媒体 URL，不增加外部优化代理。随后补入继续阅读真实封面，对 `home-interactions.tsx` 与 `support-feedback.spec.ts` 再执行目标 ESLint，退出码 0，首页两个 img warning、测试无警告。

`postcss.parse` 解析 `styles/features/support.css` 与 `styles/features/home/home-stl4.css`，退出码 0。此检查只证明 CSS 可解析，不是浏览器几何或视觉验收。

`support-feedback.spec.ts` 写入 10 个合成场景：公开路径过滤、FAQ 搜索/无答案、文章目录/示例复制、手机目录、匿名同意与回执、未知结果原 nonce 重试、关联页面移除、409 留输入、新请求编号、取消留输入、会话清理与 401 不重发（部分场景在同一用例中）。**未执行**，只在后续本地统一验收时运行。没有运行全量 tsc、浏览器、正式测试、构建、服务、迁移或生产操作。统一类型与集成检查由主线记录。

## 仍需后续核实

- 第 17 页状态 4 的真实更新时间、来源状态与订阅更新，以及反馈卡的权威题名/封面/页码由来源单元接续，未把初版视为完成。
- 反馈后端幂等、用途记录、权限与管理处理历史以对应后端单元记录为准；联调尚未执行。
- 第 10 页策划署名头像没有对应的公开人物字段，仍需后端提供明确可公开的关联头像后接入；当前保留真实 public_byline，没有用参考图示例人物填充。第 12 页继续阅读已使用实际返回的封面，缺失时明确中性占位。
- 最终逐图验收尚未执行；字体、实际图像裁切、响应式长文案、窄屏交互、剪贴板权限和慢网重试需在统一验收中验证。
