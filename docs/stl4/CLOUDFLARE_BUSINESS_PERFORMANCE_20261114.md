# Cloudflare 与业务读取优化 · 2026-11-14

## 本轮目标与基线

用户要求解释202份字体，检查其已登录Cloudflare配置，在保证安全下直接调整网络，并采用高星项目的方法优化业务层，保持内容与架构联动。延续本会话已授权修改、验证、Git及公网发布范围；不购买服务、不暴露NAS公网端口、不改变鉴权或内容发布边界。

共享工作区HEAD仍f29ddb22，远端main为上一轮2803b7c7，原暂存两文件保持。当前Web network-web-r2，源站文件/代理协议上一轮已验证。使用Ponytail full与应用开发规则；不加载研究/写作规则。没有Cloudflare专用连接器，沿用户现有Edge登录会话的独立检查标签页操作。

## 已核实

- 202份为两个现有字体族的子集：STL Text Sans 101份、STL Display Serif 101份；每份保留unicode-range与swap。不是202种新字体或首页必下202份。
- Cloudflare Free；速度页已启用HTTP/2、HTTP/2 to Origin、HTTP/3、0-RTT、Early Hints、Speed Brain、TLS1.3、Always Use HTTPS及既有RUM。Cloudflare Fonts、Rocket Loader、Shared Dictionary为关闭。不把已开启功能重复计作本轮修改。
- RUM过去7天730次访问均为books.winstonmo.com，地区显示中国大陆632、香港92、日本5、新加坡1。这是所见统计快照，不单独证明网络瓶颈位置。
- 必须保留2026-11-07 PDF缓存修复：受保护文件曾因强制Edge TTL缓存而对未登录者返回200。当前规则及实际401需继续核对，禁止为速度重新开启强制PDF缓存。
- 首页前端只取/catalog/home/，服务端按现有公开边界组合8个区域。后续先测量SQL与序列化成本，再实施可保持响应内容的读取优化。

## Cloudflare 与测速结果

实际规则列表仅1条，受保护PDF为Bypass cache且Active。Smart Shield免费包已启用Smart Tiered Cache和Connection Reuse；Argo关闭、需升级。标准缓存模式、Browser TTL 4小时，开发模式关闭。没有强制缓存业务页、改DNS、降低TLS、开放NAS端口或购买套餐。已启用的设置没有再次操作，不把核查算作提速改动。

cloudflared实际协议为HTTP/2，重启次数0；近一小时24条错误均含context canceled，未出现origin unreachable、timeout或连接关闭匹配。该样本不足以证明全时段稳定，也不足以支持强制切QUIC。保留既有容器独立tcp_retries2设置。

用户截图对应2026-11-14 11:54、Iowa USA桌面测试：78分，TTFB4183ms、FCP888ms、LCP2268ms、TBT0、CLS0。不同指标的统计口径没有混为同一请求计时。

另运行完整PageSpeed移动报告：https://pagespeed.web.dev/analysis/https-books-winstonmo-com/hn3uapjov6?form_factor=mobile 。本次模拟低速4G得64分，LCP12.8秒、TBT50ms、CLS0；无CrUX现场数据。建议具体指向公共CSS、两个初始化脚本、公开策划图及小头像/书封。缓存警告主要为需撤回检查的API图片及Cloudflare统计脚本，不将其一概改成长缓存。SEO noindex为项目既有决定，没有为得分移除。

## 本轮实现与前后对照

| 部分 | 修改前 | 修改后 | 内容保护 |
| --- | --- | --- | --- |
| 版本序列化 | 同一版本多个字段重复核对公开分类 | 每次版本序列化只读取一次，结束立即丢弃 | 后续序列化仍重新检查撤回 |
| 首页与学者/主题嵌套卡片 | 相同作品重复生成完整公开卡片 | 仅该次首页请求内复用同类公开卡片 | 不存用户、跨请求缓存或修改发布规则 |
| 显示偏好 | 一个额外阻塞脚本请求 | 从原初始化源码生成相同内联代码 | 本地存储拒绝、系统主题、URL试用逻辑一致 |
| 欢迎页小头像与书封 | 即使已有小尺寸仍只指定主图 | 传递现有版本清单，以srcset/sizes选择 | 原图、裁切、尺寸版本与高密度选项保持 |

在生产API的独立Python进程内，READ ONLY、REPEATABLE READ事务和15秒单SQL超时下，先旧代码再内存加载候选，各3次。全部6次完整JSON规范化SHA为c4e207825d1a0b1d01df106cb4d98a7267adc358136667656a5527733c7d6a45，262401字节，内容及数组顺序一致。查询782→422（减少46.0%）；耗时中位数3802.32→2818.31ms（减少25.9%）。这是源站短样本，非公网LCP或并发压测。最初预取学者关系改变了未显式排序的条目顺序，等价检查发现后已撤除，未发布。

桌面与390px窗口（有效内容375px）实际预览选择已有320w头像，图片成功解码，页面无水平溢出；示例320w11004字节、640w58362字节。没有重编码原图，没有修改PDF。没有声称实际覆盖所有高DPI硬件。内联主题在刷新前后保持dark，检查后恢复light。

类型、构建、CSS预算及1048份压缩副本验证通过；2项静态网络行为测试通过。原首页3项与元数据发布可见性10项通过；新增两项撤回/版本读取边界通过。新增测试的第一次夹具错误地尝试覆盖不可变修订、第二次使用旧关系夹具，均已修正为发布前建立正式关系；未改生产不可变修订规则。

## 持续增长与投入顺序

现有媒体库按6条分页，默认API分页24条；旧媒体入口最多60条。书封和肖像选择服务已经生成320/640/1280请求宽度版本，实际宽度不超过原图。现有媒体variant_key按用途、裁切/焦点、元数据和宽度复用，不按页面无限复制。本轮前端按接口清单选择，未来图片自动适用。特别策划目前样例只有1280版本、部分旧封面无尺寸清单，仍保持原图；不能把所有图片优化都写成完成。

NAS读取快照：4核，MemTotal7998336kB、可用2091812kB，Swap总8191976kB/空闲2249856kB，两网口均2500Mbps且up；负载0.63/0.90/0.84，API约284MiB、Web241MiB。交换占用不等于正在持续交换，不能仅凭此要求购买内存；双2.5G不等于公网5G上行。未做占满家庭带宽的测试。

优先核实公网实际上行及忙时排队，备份/同步错峰并按实际路由器能力采用SQM；持续换页时再评估内存，数据库磁盘等待明显时评估SSD。原架构下可选Smart Shield+Argo改善回源路由；公开不可撤回的构建资产可评估R2/CDN，私有PDF与可撤回媒体不直接公开托管。大陆专网Cloudflare China Network需Enterprise另购及ICP条件，普通Pro升级不等价。没有购买、迁移、清理历史或更改存储策略。

## 方法来源

2026-11-14 GitHub API核对：django/django91730星、encode/django-rest-framework30232星、cloudflare/cloudflared16583星；保存于output/cloudflare-business-20261114/github-projects.json。沿已有框架使用官方剖析、复用和关联读取方法，未增加框架或生产调试工具。

- https://docs.djangoproject.com/en/5.2/topics/db/optimization/
- https://www.django-rest-framework.org/api-guide/generic-views/#avoiding-n1-queries
- https://developers.cloudflare.com/cache/how-to/tiered-cache/
- https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/
- https://developers.cloudflare.com/speed/optimization/content/rocket-loader/
- https://developers.cloudflare.com/smart-shield/get-started/
- https://developers.cloudflare.com/tunnel/reference/run-parameters/
- https://developers.cloudflare.com/china-network/
- https://developers.cloudflare.com/r2/pricing/
- https://openwrt.org/docs/guide-user/network/traffic-shaping/sqm

## 发布状态

候选API003be31e4455与Web29a4a355ce50已暂存，仅2份API源码和3184份Web运行文件。尚未切换；准备精确API/Web配置差分、镜像回退和既有完整备份核验。worker、数据库、索引、任务、媒体原件、隧道保持。
