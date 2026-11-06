# 欢迎入口与首页衔接

2026-11-06，WELCOME-ENTRY-01，D 已实现关闭本开发项；公网与完整视觉验收不在此次通过范围。

用户最新确定 books.winstonmo.com 的入口为欢迎页。候选根路径直接渲染现有欢迎组件，原首页移到 `/home`，`/welcome` 继续可用。没有新增欢迎内容、修改品牌或替换首页布局。

## 实现

- `web/app/page.tsx` 复用原欢迎页；`web/app/home/page.tsx` 保留原首页数据与组件。
- 两处进入按钮是 `/home` 普通链接，保留回车、新标签和无JS导航。页面局部 `LibraryEntryTransition` 使用浏览器跨文档过渡；不会先隐藏页面再等待请求。正文淡出180ms，淡入280ms并从8px下方回到原位；页头独立保持，不等待演示结束。
- `prefers-reduced-motion` 关闭过渡；不支持原生跨文档过渡的浏览器正常直接导航。共享原140ms路由淡入跳过这三个入口，避免叠加。
- 现有全站首页/Logo/返回链接指向 `/home`；读者注销后的返回、后台返回前台、首页重试及移动导航同步。没有放宽登录、阅读、下载或探索权限。
- 反馈选页器区分欢迎页/首页，前后端只允许对应公开路径，仍剔除私人查询参数；视觉批注台默认与PDF首页映射指向 `/home`。旧批注数据、保存时的历史路径和旧实现证据保持，不做数据库改写。
- 共享页头旧访客说明改为“登录后可检索、阅读和下载”，与已确认的访客权限相符。

## 当前候选与恢复

内网 `http://192.168.5.6:18084/`，Web131镜像 `a0e2508d0a61c17e55a478edf8fd477d755a077ee2466d1733b827ea60a6f85e`；API64镜像 `f9ef984539c2ee0b35b826856ba53e48ff48a7f8c772ec4ff01baf2c37c8147b`，四worker/beat同步64。原RapidOCR/DOCX、数据与模型保持。

NAS `/volume2/library/stl-previews/20261026-r1/welcome-entry-web-r131-recovery` 保存前Web130；同级 `welcome-entry-api-r64-recovery` 保存前API63、受限环境/日志及更新前数据库包。新数据库包未独立恢复，不能据此称恢复验证通过。更新先停beat并等待队列/在途为零；未丢弃任务。脚本逐项断言生产/政策容器身份、挂载及启动时间不变。恢复应只调整本次对应镜像键，不能整份覆盖.env或清空数据。

## 核对记录

| 范围 | 结果与证据 |
|---|---|
| TypeScript | `node node_modules/typescript/bin/tsc --noEmit` 退出0，entry-typecheck.log |
| Web最终构建 | `node node_modules/vinext/dist/cli.js build` 退出0，entry-web-build-r131-final.log。早一轮构建期间补了欢迎页样式范围，成品未发布，最终重建后再打包；不是产品失败 |
| 公开页面过滤 | 28项参数用例通过，包括新公开路径与拒绝其私人子路径；`pytest -q api/tests/test_public_feedback_20261018.py -k test_context_never_keeps_private_routes_or_tokens`，entry-feedback-check.log。未连接业务数据库；旧pytest缓存目录警告保留 |
| 匿名HTTP | `/`、`/home`、`/welcome`均200、标题区域匹配且包含过渡CSS；entry-public-http.json |
| 实际浏览器 | 根路径显示欢迎页；首屏点击进入/home；理论流派→首页直接回/home；/welcome可访问，回车进入与浏览器返回正常；本人继续阅读内容随后正常显示。未提交表单或创建数据 |
| 实际页面范围 | `/home` 为stl4，根欢迎页为editorial-v2，与各自原页面一致；默认浏览器宽度未见横向溢出，页头过渡名已实际读回。只核对端点与样式，不声称逐帧动画或跨浏览器验收 |
| 源码/成品一致 | 788个后端文件、3008个前端构建/静态文件与活动容器哈希一致；launch-inventory-r131.log / launch-file-diff-r131.json |

上述日志位于 `tmp/stl4-copy-20261104/`；截图 `output/welcome-entry-20261106/welcome-r131.png`、`home-r131.png`。均为本地运行证据，不提交仓库。一次浏览器读取超时后重新读取并继续正常，未据此新增产品缺陷。浏览器CSSOM读取未暴露style.sheet，不能把该工具结果当作浏览器不支持过渡的证据。

## 保留边界

这次只更新内网候选，没有修改公网、DNS、隧道、生产数据库，未运行全站测试/OCR/检索质量评测。实际动画节奏、不同浏览器与手机效果继续由用户批注；现有全站B不重开开发。邮件真实配置、最终发布环境与一致备份/恢复、生产账号私人增量、外围网络核实及最终批准仍沿原清单。
