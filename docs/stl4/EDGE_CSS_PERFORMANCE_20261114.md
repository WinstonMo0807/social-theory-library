# 香港回源、公共 CSS、字体与欢迎演示加载

2026-11-14。用户授权验证后直接上线并推送 Git，保持功能架构和内容。此批在远端 `345faac1` 上叠加，保留另一会话已发布的 E 书库、C 首页荐书与 B 读者中心。源码提交与最终文档提交见 `output/edge-css-20261114/final-receipt.json`。

## 发布结果

- 19:34:17 +0800 完成隧道切换。现有 cloudflared 镜像保持 `sha256:41320ce229c5fb52a316a5e3af2e6a1faa32b114aa9e2a5eed0652eff59e8eef`，传输协议改为 QUIC，活动连接由 LAX 变为 4 条 HKG。
- 19:37 完成显式直连回退与恢复香港验证。备用 HTTP/2 连接成功建立 LAX 连接；重新选择香港后，守护程序确认健康并自动停止备用连接，主隧道未重启。
- 19:38:38 +0800 发布 Web `social-theory-library-web:4.0.0-20261114-edge-css-web-r1`，镜像 `sha256:ceae47ee09725e800057485ce50c106f80e916c4216c17ca11b27cdcb8d906c3`。运行的 3,210 个文件与构建产物 SHA256 一致，107 个其他容器的身份、镜像、配置及启动时间保持。
- API 保持 `sha256:17204310147baffc36eb8409314fd0f396d577713380d10d59aeb50842047bea`。未改数据库、任务调度、业务 API、馆藏、读者私人资料或已确认的功能关系。

## 公网绕行的证据和处理

原路径中，访问者一侧 CF-RAY 为 HKG，NAS 的 cloudflared 却连接 LAX；NAS 直接请求 Cloudflare trace 也显示 LAX。未发现强制美国区域配置，NAS 没有可用的公网 IPv6 默认路由。仅将 HTTP/2 改为直连 QUIC，仍然到达 LAX，且有握手超时。因此不把改协议本身当作线路修复。

复用用户已经运行的 `mihomo-gateway` 香港出口。仅新增内部隔离桥 `stl_tunnel_egress`，将 cloudflared 中 Cloudflare Tunnel 官方两个 IPv4 目标网段 `198.41.192.0/24`、`198.41.200.0/24` 经既有网关转发。原 public_front 网络继续访问同一源站。没有修改 NAS 默认路由、DNS、业务容器网络、公开端口、代理 allowlist 或网关选择组；网关未重启。Tunnel 仍使用端到端加密，未关闭证书检查。

实际测试中，香港出口的 TCP 7844 TLS 握手返回 EOF，UDP QUIC 可以建立 HKG 连接；部分临时 QUIC 探测仍出现超时，故保留故障回退。没有固定 Cloudflare 单个 IP、伪造地区参数、开放代理或购买新服务。

守护代码为 `deploy/network/tunnel-egress.py`，每 15 秒检查。只有带协议号 199 的两条任务路由可以被它修改；不覆盖未管理的路由。首次连接保留 60 秒窗口，之后连续三次连接检查不健康或网关失联时切回直连，并启动同镜像、同既有隧道配置的 HTTP/2 备用连接。失败后保持直连，管理员显式 `--retry` 或 NAS 重启才重新尝试香港，避免反复切换。正常时备用容器停止。未做真实 NAS 重启或网关断电测试。

依据：[Cloudflare Tunnel 参数](https://developers.cloudflare.com/tunnel/reference/run-parameters/)、[Tunnel 连接与网络](https://developers.cloudflare.com/tunnel/configuration/)、[Mihomo TUN 配置](https://wiki.metacubex.one/en/config/inbound/tun/)。Cloudflare 的地区参数并不提供任意香港节点选择，实际节点仍须以连接指标核验。

## 同机公网与内网实测

本机 curl，显式禁用系统代理，每次新连接，接受压缩；每个阶段各路径 6 次，四个组合共 24 次。记录 DNS、连接、TLS、TTFB 和完整响应时间。以下为完整响应中位数，单位 ms，全部 HTTP 200。短时 A/B 与最终上线样本分开保留，不选最快一次作为交付结果。

| 路径 | 改前 | 香港短时 A/B | 最终上线后 |
|---|---:|---:|---:|
| 公网 `/api/ready/` | 1,670 | 213 | 490 |
| 内网 `/api/ready/` | 41 | 40 | 44 |
| 公网 `/api/catalog/home/` | 3,299 | 2,343 | 2,746 |
| 内网 `/api/catalog/home/` | 1,883 | 1,952 | 2,087 |

最终公网健康请求约缩短 71%，首页数据约缩短 17%。同期内网首页数据也变慢约 204 ms，说明源站负载/处理时间仍有波动。公网首页与内网的中位差由约 1,416 ms 减到 659 ms。这些是请求指标，不能换算为整页 LCP 同比例改善，也不是所有地区的用户 p75。

## CSS、字体与欢迎演示

1. 从根布局退出两份旧 editorial 样式。其中 904 条旧 editorial-v2 规则和 662 条旧工作区规则要求当前组件不再输出的旧 scope。历史源码保留。将仍有效的 431 条后台规则提取到现有 admin 路由样式，保持声明、条件和顺序，没有新增布局框架。
2. 202 份文件是中文无衬线/衬线字体的 WOFF2 字符子集，不是 202 种字体，也不是每次访问都全量下载。字形、字重、unicode-range、font-display 与所有二进制保持一致。字体定义从主 CSS 分离为独立内容哈希资源，通过原静态资源缓存策略加载；楷体与用户字体、字号偏好保持。
3. 欢迎演示独立为 `welcome-workflow-demo` 异步模块，在接近视口时安排加载；先保留相同高度的品牌画面。完整三版文案、真实馆藏/学者数据、时间线、暂停/重播、离屏与页面隐藏暂停、减少动态效果分支保留。粒子动画由外层 HTML 元素承载 SVG，图形与视觉内容保持。独立演示 JS 原始 13,262 B / Brotli 3,491 B；不把延后加载说成删除这些字节。
4. 实际 CSS 对照发现，拆分后后台规则加载顺序会覆盖确认框说明文字的字重/颜色/间距。给确认框文字选择器增加组件自身作用域，复测恢复原值；未改变确认、取消或删除业务逻辑。

资源比较使用另一会话最新界面版本的构建作为 CSS 基线，包含其新增页面样式：

| 项目 | 改前 | 改后 |
|---|---:|---:|
| 主 CSS 原始字节 | 1,258,345 | 786,353 |
| 主 CSS Brotli | 147,938 | 100,241 |
| 独立字体定义 Brotli | 已包含在主 CSS | 20,942 |
| 主 CSS + 字体定义 Brotli 合计 | 147,938 | 121,183 |

合计减少 26,755 B，约 18.1%；仅主 CSS 减少约 32.2%，不能省略拆出的字体定义后宣称总量下降 32%。公网实际协商 Brotli 后得到相同字节数，两个资源均为 CF HIT、`max-age=31536000, immutable`，解压后哈希与构建一致。gzip 客户端也验证通过。

## 验证范围

- 5 项前端定向测试通过：废弃 scope、431 条 CSS 语义保留、原偏好初始化、字体资源与定义保持、另一会话书库查询契约。6 项网络决策测试通过。
- TypeScript、Vinext 生产构建、1,058 个压缩副本和性能预算均退出 0。源码收尾仅清理两份新组件文件末尾空行；Git diff 检查通过。
- 实际管理页 DOM 的只读样式夹具：作品编辑 1,263 元素在桌面与 390px 下，关闭过渡以固定状态后，全部尺寸和所比较的计算样式一致；馆藏列表前 2,000 元素的窄屏对照一致。夹具保留内容、字体与结构，不运行表单或 API 写入；不当作全站业务验收。
- 候选浏览器三版欢迎文案切换、暂停/重播、离屏暂停、主题刷新通过。演示占位与加载后桌面高度均为 584.4px；390px 视口内容/滚动宽度均 375px（含浏览器滚动条占位），无整体横向溢出。
- 公网真实欢迎页、进入 `/home`、`/library` 的 57 部馆藏、已登录本人读者中心，以及内网实际作品管理页完成只读核对。现有管理页在 1280px 的水平溢出改前已经存在，CSS 拆分没有改变其几何，不声称修复全站历史布局。
- 公网 6 个入口：5 个直接 200，匿名 `/explore/original` 按既有规则 307 到登录页；152 个页面引用的静态资源全部 200 且哈希与候选构建一致。NAS 内网部署检查的 7 个入口正常，包括允许的登录跳转。
- 内外网各三种匿名 PDF 请求全部 401、private/no-store，公网 CF DYNAMIC；没有以公共缓存代替鉴权。
- 部署前复核既有完整备份归档 SHA256、镜像回退和私有配置副本；Web 替换后 Nginx 校验和 reload 完成，配置字节保持。

## PageSpeed 与仍存在的限制

同一公网根页面，移动设备/低速 4G 模拟，Lighthouse 13.6.0。此前同版本两次为 48 / 66 分、LCP 均 12.3s，TBT 590 / 10ms、CLS 0.102 / 0。本批两次如下，不丢弃波动样本：

| 指标 | 19:39 | 19:41 |
|---|---:|---:|
| 性能 | 68 | 69 |
| FCP | 1.5s | 1.5s |
| LCP | 11.8s | 11.7s |
| TBT | 90ms | 90ms |
| CLS | 0 | 0 |
| Speed Index | 6.9s | 6.1s |

[第一次报告](https://pagespeed.web.dev/analysis/https-books-winstonmo-com/4dbqufjx3f?form_factor=mobile)、[第二次报告](https://pagespeed.web.dev/analysis/https-books-winstonmo-com/lchf9v60mx?form_factor=mobile)。没有 CrUX 真实用户数据。LCP 仍偏慢；第一份报告定位到欢迎页介绍段落，记录文档请求与元素渲染延迟，仍有公共 CSS/字体加载及源站响应空间。不能仅凭这一报告断言某一个因素独自造成全部 11.8 秒。

匿名 `/auth/me/` 的 401 与 `/auth/token/refresh/` 的 400 被 Lighthouse 计为控制台错误，现有 noindex 也影响 SEO 分数；本轮未为提高评分取消这些边界。减少动态效果的既有分支保留，但本轮没有改操作系统设置做该偏好的运行测试。NAS 繁忙 OCR/索引/备份并行场景未在本批人为触发；同日早前已验证的并发/CPU取舍见 NETWORK_CONTENTION_PERFORMANCE_20261114.md，不重复声称空闲检查能证明繁忙状态。

## 运行维护与回退

活动 Compose 指针仍为 `/volume2/library/stl-releases/20261107-r1/public/compose-command.json`。本批网络目录 `20261114-edge-egress-r3`，Web 目录 `20261114-edge-css-r1`，各自保留 `recovery/rollback.py`。通常先回退 Web，再回退网络。网络回退仅移除自己的 overlay，保留后来 Web 发布，恢复原 HTTP/2、停止守护与备用连接、断开网关内部桥，不删除业务数据。

网络守护位于 `/volume2/library/stl-network/tunnel-egress.py`，systemd `stl-tunnel-egress.timer`，状态 `/run/stl-tunnel-egress/state.json`。需要即时恢复原路径时运行 `sudo python3 /volume2/library/stl-network/tunnel-egress.py --direct`；修复出口后用 `--retry`，再核验 HKG 活动连接、守护 healthy 与备用已停止。隧道 token 轮换时需沿私有部署流程同步更新主连接与备用连接，不能将凭据写入 Git。

早期发布与另一会话并发，两边保护检查均触发过回退；待其结束后合入最新源码再发布，最终活动指针与镜像一致。临时探测失败和空桥重建记录保留，不能把所有尝试写成成功。共享 HEAD、原暂存和其他未提交修改保留；不提交运行归档、日志、私有夹具、备份或凭据。

证据目录：`output/edge-css-20261114/`。包含三阶段原始计时、静态资源哈希核对、故障回退结果、CSS 比较、浏览器截图和两份 PageSpeed 报告。
