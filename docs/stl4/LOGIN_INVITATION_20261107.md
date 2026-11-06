## 2026-11-07 试用说明文案修订已上线

按用户最终措辞，标题为“欢迎试读社会理论书库”，署名“由 WinstonMo 开发”，正文“欢迎尝试”改“欢迎试用”。仅改AuthSessionDialog文案，已读标记不变，不重新邀请已看过的读者。源码c4928c9f；正式Web4.0.0-20261107-r3（6754dfc05f9e）。独立构建排除另外进行中的4个上传前端文件改动，不覆盖工作区。构建退出0，2074个运行文件读回一致（既有启动注入runtime-config除外），已从内网实际JS资源核对三处文字；本轮未另跑界面/功能测试。仅Web重建、edge平滑reload，其余24个运行容器未重启。NAS回退点/volume2/library/stl-releases/20261107-r1/login-copy-web-r3-recovery保留Web r2与准确配置。日志tmp/stl4-login-copy-r3/，公网及内网仍同一正式服务。

# 进入书库后的登录邀请与试用说明

## 用户确认的范围

- 欢迎页不自动弹出登录。点击“进入书库”后，未登录读者可登录、注册或暂不登录。
- 右侧用连续演示说明观点检索、PDF 阅读/下载、保存材料与连续研究；沿用欢迎页的纸白、砂金和卡片语言，不触发真实检索或写入。
- 登录邀请之后显示简短试用说明。按用户提供的文案说明现有策展为测试示例、57 本书进入内容策划与观点检索。本条数字是用户指定的发布文案，不是本轮馆藏/索引验收结果。
- 两个提示记住本浏览器的选择，不因刷新或返回首页反复弹出。浏览器标签图标统一为既有黑金 STL 图形。

## 证据与最小修改

LOGIN-INVITE-01：`api.ts` 在刷新返回 400/401 且 `library_session_active` 仍在时派发 `stl:auth-required`；原 `AuthSessionDialog` 把 `/`、`/welcome` 纳入自动处理，因此旧会话失效会在欢迎页出现“会话已过期”。纯首次访客没有该标记，不是所有首次访问都会触发。

保留原会话校验、权限和表单，仅限制落地页自动提示，两个欢迎入口记录进入意图。`/home` 等待共享会话结果，已登录跳过邀请；未登录才邀请。暂时无法验证会话不冒充会话失效。邀请状态和试用说明使用独立的版本化本机标记，与账户权限无关。

LOGIN-LAYOUT-01：原右栏是返回目的地和本机记录，底部“暂不登录”弱化。现改为三段轻量 CSS 卡片演示、可暂停/手动切换、后台暂停及减少动态效果支持。跳过按钮紧接登录主按钮。原本机记录转存仍需明确勾选，只在有记录时出现；找回申请和未提交输入确认保留。原表单接口和隐私授权未改。

FAVICON-01：原 SVG 已为 STL，但 `favicon.ico` 为旧图标。现用已批准 `stl-symbol-20261027.svg` 的原路径生成同源 SVG、16/32/48/64 ICO 与 Apple 图标；不重新设计品牌。metadata 使用版本化 URL，旧默认地址同步替换。

## 本机核对

- TypeScript `node web/node_modules/typescript/bin/tsc --noEmit --project web/tsconfig.json`，退出 0。
- 现有 19 项会话检查退出 0，覆盖 Cookie 恢复、失效标记、403/5xx、并发刷新及跨标签同步。本轮不修改这些测试。
- Vinext 正式构建退出 0，日志 `tmp/stl4-login-20261107/web-build.log`。
- 实际浏览器：欢迎页无对话框，进入后邀请，跳过后试用说明，关闭后刷新无提示，再次欢迎→首页无提示；主动点击读者登录可重新打开，关闭不会再出现试用说明。
- 1280、768、390、320 宽度已实看。手机跳过按钮在首屏，dialog 无横向溢出。连续研究卡片首次发现被裁切，已缩减示意行修正。截图 `output/playwright/login-invitation-20261107/`。
- 登录/注册成功提交、本机记录真实转存、真实设备 Safari 与长期运行未在本轮实测；不宣称全站验收通过。减少动态效果分支已实现，运行验收待补。

## 发布状态

LOGIN-INVITE-01、LOGIN-LAYOUT-01、FAVICON-01 为 D（本轮实现及下列定向运行核对完成；不代表全站验收）。代码检查点 `8b3d8cbb`。正式 Web 已更新为 `social-theory-library-web:4.0.0-20261107-r2`，镜像 `dea2f146adce0baedb6027303767223b9ac7e0b23531c148d15e51d4262f1391`，容器 `9cfbab1af328`。

2074 个前端构建/图标文件逐项 hash 一致，仅排除启动时按正式环境注入的 runtime-config.js。公网实际核对欢迎无自动弹窗、进入后邀请、右栏切换/暂停、跳过后说明、刷新及再次进入不再提示；真实页面 head 已引用新版 SVG/ICO/Apple 图标。截图 `public-invitation.png`、`public-notice.png`。内网首页和新图标 HTTP 200，与公网同一正式 Web。

NAS 恢复点 `/volume2/library/stl-releases/20261107-r1/login-web-r2-recovery` 保存更新前环境、完整组合命令、解析配置、容器摘要和操作日志。上一版 Web r1 镜像保留。仅 Web 重建，edge 执行 `nginx -t` 通过后的平滑 reload；其余 24 个当时正在运行的容器 ID/StartedAt 均未变化。API/四 worker/beat 仍 r1，所有具有健康检查的正式服务 healthy。数据库、任务、原件、私人资料未改。

还原本次前端：由恢复点 `.env` 恢复 public/.env（0600），用既有完整 compose 命令 `up -d --no-build --pull never --no-deps web`，Web 就绪后 `docker exec social-science-library-edge-1 nginx -s reload`。不执行全栈 down/up 或旧预览启动。

范围限制：本轮实看首页仍显示“暂无公开馆藏”，不能据用户提供的 57 本说明声称这些书已完成公开或检索验收；未擅自发布、清理、重跑 OCR 或索引。此差异留待对应入库批次/公开状态核对，不据推测新增后台修改。
