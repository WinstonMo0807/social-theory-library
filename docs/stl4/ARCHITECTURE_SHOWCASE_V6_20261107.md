# 架构演示 v6：域名接入与响应式布局

2026-11-07。范围仅为 `web/architecture-showcase/` 独立展示。公开入口 https://preview.winstonmo.com/ 。用户指定公开脱敏版，并追加桌面铺满、手机和平板适配。

## 改动与依据

原界面固定 1600×900，再按窗口宽高整体缩放。实际 988×942 浏览器中出现明显上下留白，移动端文字随画布一同缩小。

- 外层改为填满窗口的 CSS Grid，使用动态视口高度和安全边距。桌面保留侧栏；1180px 以下改用顶部导航，640px 以下采用手机排版。主区域滚动，控制栏固定在布局底部。
- 总览节点依实际图形容器宽高定位；窄屏采用品牌在上、六个模块分双列的布局，连线走中间空隙。保持平滑聚焦，不加入模拟鼠标。窄屏详情改为纵向内容并自动带入视野。
- 网站页面在桌面四列、平板双列、手机单列，当前卡片依次突出并自动滚入可见区域。
- 三条使用演示保留 38 步和模拟指针。窄屏重排检索范围、结果、阅读、引用、入库与研究画面。滚动容器会显示当前操作，弹窗重新锚定到可见演示区域，防止继承旧阅读位置造成按钮遮挡。
- 自动循环、点击延时、暂停、键盘、减少动态效果、全屏与导出保留。页面不再锁定 16:9；PPT 图片继续导出 3840×2160，导出前固定实际网格和字号，避免 4K 视口重新计算布局造成裁切。
- 沿用既有品牌和 Noto 字体，未改架构数据、业务页面、数据库、访问权限或 npm 依赖。文案维持此前 STC 修订结果。

## 运行验证

| 检查 | 结果 |
| --- | --- |
| `node web/architecture-showcase/build.mjs` 及 `--public` | 退出 0；公开构建内部路径扫描通过 |
| `node web/architecture-showcase/verify-auto.mjs` | 退出 0，129 项自动循环、点击延时、暂停、返回、减少动态及公开边界检查 |
| `node web/architecture-showcase/verify-responsive.mjs` | 退出 0，197 条检查记录，9 种尺寸、5 幕与 4 种宽度下的全部 38 步；无浏览器异常、页面横向溢出或当前可见操作遮挡 |
| 尺寸 | 1920×1080、1440×900、1280×720、980×950、1024×1366、768×1024、390×844、320×568、844×390 |
| 最小手机指针 | 320×568 实时检查范围、上下文、引用格式、下载、目录修订和研究备注 6 个步骤，指针均在可见演示区域 |
| 公网独立浏览器 | 1920×1080、768×1024、390×844 页面 HTTP 200、布局铺满、无横向溢出或控制台异常 |
| 公网资源 | app.js、app.css、architecture.json HTTP 200，SHA-256 与本机最终公开构建相同 |
| 公网受限路径 | evidence-index.csv、admin、serve.mjs HTTP 404 |
| 全屏 | 独立 Edge 浏览器进入/退出 API 通过；受控后台标签页有一次拒绝提示，未降低浏览器权限 |
| Impeccable | context 与 detect 各一次；机械检测输出 []，人工查看桌面、平板、手机及导出画面 |
| 导出 | 14 张 3840×2160 PNG 和独立 SVG，实际打开检查节点与卡片边界 |

首次窄屏检查发现弹窗高度与滚动位置问题，修复后复测。完成状态中已被弹窗替换或移除的旧操作目标单独记为结果替换，不当作需要点击的可见按钮。最终 JSON 保留该区分。

验证范围是 Chromium/Edge 的真实页面与设备尺寸模拟，未使用实体手机或平板，未做 iOS Safari 实机验收。演示继续使用标注的示例文献和状态，不构成书库业务功能验收。本轮未重新审计 11 月 6 日的架构内容快照。

## 域名与部署

通过已登录的 Cloudflare 控制台，在现有 social-theory-library-nas 隧道新增 preview.winstonmo.com → http://stl-architecture-showcase:5196，HTTP Host Header 为 preview.winstonmo.com。控制台确认路由与 CNAME 创建成功，原 books.winstonmo.com → http://edge:80 保持。

最终发布目录 `/volume2/library/stl-previews/architecture-showcase-v6-r2-20261107`，镜像 `stl-architecture-showcase:v6-r2-20261107`，镜像摘要 `sha256:fbe81dce0f90345bfef322e3689ca1c20092d5ce1eed6760f214cd67d64bb074`。216 个运行文件哈希一致，容器 healthy，隧道网络源站 HTTP 200。非 root、只读、无业务挂载、无宿主端口。原 edge/cloudflared 的容器 ID、镜像、启动时间与重启次数保持。

v5-smooth 和此前版本的目录、镜像及离线包均保留。v6 初次发布也保留；v6-r2 的 rollback.json 指向它。回到本轮前版本时，在 v5-smooth 发布目录执行原 Compose 启动命令即可，域名服务名不变。具体维护见 `web/architecture-showcase/DOMAIN_SETUP.md`。

早期 Python 公网 HTTP 探测为 403，保留原失败记录；之后正常 Edge 和独立浏览器均返回正常页面，最终浏览器资源探测为 200。未为此修改 Cloudflare 安全策略。

## 产物

目录 `output/playwright/architecture-showcase-v6/`：

- `public-1920.png`、`public-768.png`、`public-390.png` 与 `public-mobile-citation.png` 为最终公网截图。
- `responsive-verification.json`、`mobile-pointer-check.json`、`auto-verification.json`、`public-verification.json`、`deployment-proof.json` 保留验证结果。
- `4k/` 是 PPT 图片；`video/STL-architecture-v6-1080p.webm` 是完整自动循环视频。
- `STL-architecture-v6-local-20261107.zip` 为内部离线包，包含源码索引，不应上传公开站点；公网只部署 public 允许清单中的静态成品。

仅形成本项 Git 检查点，不推送，不覆盖其他工作区修改。
