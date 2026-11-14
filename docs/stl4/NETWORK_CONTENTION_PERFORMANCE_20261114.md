# 公网链路、NAS争用与剩余资源（2026-11-14）

用户要求按公网差距、NAS任务争用、前端资源的顺序继续，验证后直接上线和推送Git；保留功能架构、内容和已有安全边界。基线为c5e73504，API 17204310147b、Web 545f77342732。工作区原HEAD f29ddb22、原暂存区及其他修改保留。

## 公网差距定位

对同一配置文件、健康检查、首页JSON和主CSS分别测内外网、identity与gzip/br、连接建立与首字节/完整响应，交替各3次。证据 `output/network-contention-20261114/network-before-r2.json`。这是本机和NAS当前线路样本，不代表所有访客地区或真实用户p75。

- 78字节runtime-config内网约2–3ms；公网复用连接仍有约420–1100ms等待，初次连接还涉及DNS/TLS。说明小文件也受公网/回源路径影响，不能全部归因业务查询。
- 本机CF-Ray为HKG，NAS隧道指标中4条当前活动连接分别为lax01/lax07/lax13/lax09，`cloudflared_tunnel_server_locations=1`，不是仅用旧日志推断。存在香港入口至洛杉矶隧道节点的跨区域路径。隧道有4条活动HTTP2连接，未发现本批测量中的源站不可达；历史累计错误不等于当前错误率。
- 主CSS公网命中HIT，压缩后约170KB，复用连接首字节约88–109ms。静态缓存已生效，不能把全站Cache Everything当成修复。
- 首页JSON源站未压缩，即使请求接受gzip/br也返回256292字节；Cloudflare到浏览器虽有Brotli约54KB，NAS到隧道的响应仍有可减少的传输量。
- NAS自身以curl HTTP/2、不使用环境代理访问公网也有明显连接与传输波动，证据`tunnel-before.json`；与本机暖连接测试条件不同，不将两者直接算成前后提速。

不修改DNS、固定Cloudflare边缘IP、强制QUIC、降低证书校验或暴露NAS端口。Cloudflare官方region参数只支持限制到美国或默认全球，不能据此配置香港。跨境路由仍是外部限制，未承诺本批消除。

## 实施

1. Nginx只为`/api/catalog/home/`开启源站gzip level 3。HomeView显式关闭鉴权并对所有角色返回同一公开投影，适合此范围；其no-store、当前发布/撤回校验、限流和代理身份头沿用。其他私有API、登录和PDF策略保持。独立临时Nginx候选实际读取：256292→70153字节，减少72.6%；解压SHA完全一致。初次候选检查发现嵌套location需要显式proxy_pass，修正后检查通过，未将失败候选上线。
2. 容器入口将已校验的apiBase同时交给服务端内联初始化，生产HTML无需再阻塞请求runtime-config.js。仍保留原文件；非容器/未设置新变量时沿旧脚本路径，现有开发和浏览器夹具兼容。URL校验继续在出口前执行，JSON内联转义`<`及行分隔符。
3. 静态文本Brotli构建质量9→11，压缩CPU由本机构建承担，NAS不实时重压缩。主CSS原始1253685字节及SHA完全不变，Brotli169873→147376字节，减少13.2%；全部524份压缩资源Brotli合计2569728→2376936字节，减少约7.5%。CSS/静态资源使用assets/r2命名空间，让CDN取得新编码；旧URL继续保留，不做全站缓存清空。字体、图像、CSS声明和内容均未删减。
4. 主CSS压缩预算180000→160000字节。额外试验再次minify只减少907原始字节，Brotli反而略大，未采用。

## NAS任务争用结论

只读查看队列和任务名称，不读取任务参数。样本中ingestion/discovery_query/discovery_index排队均0，普通队列3，1个运行中的例行健康巡检。既有单并发、prefetch=1、读者查询优先、重任务按需模式继续保留，不另建调度器、不清队列、不强停任务。

30秒采样，换入5页、换出0，末尾内存PSI约0.12%、I/O约0.28%；API cgroup没有OOM，API约348MB。CPU限额曾触发等待，但低并发对照不足以证明增配收益。

保留同一API代码，2路并发、各3轮，CPU额度1核与2核的完整请求中位分别3098.88/3095.93ms，约0.1%，未显示稳定改善。全部12次响应SHA一致，内存约286MB，无新增OOM。测试后原CPU额度及HostConfig已准确恢复，因此不保留无实测收益的资源调整。

较早CPU shares试验中Docker update传0没有清除已有非零值，恢复检查及时发现；随后从未修改的活动compose重建同一API镜像，恢复原资源配置并检查ready，未更换源码/数据。正式1核/2核对照只改变CPU额度，结束后HostConfig与开始完全一致。具体回执`probe-restore.json`和`resource-ab.json`。不将这次重建省略成“所有容器始终未重启”。

## 验证与上线记录

候选类型、生产构建、1048份压缩副本解码/原文等价与体积预算通过；4项初始化/静态资源定向测试通过。实际Linux入口检查有效地址内联、无网络启动、非法API地址拒绝；独立Nginx候选语法和真实gzip往返通过。

Edge原有页的调试连接不可用，改用内置浏览器成功核对。候选1280px首页正常，390px无横向溢出，菜单打开/Escape关闭、夜间主题刷新保持，API配置在HTML内联，页面无外部runtime-config脚本。共享主CSS前后SHA完全相同，截图用于呈现检查，不把登录状态不同的页面称作逐像素相同。前后图在`output/network-contention-20261114/`。

13:32:21 +0800正式发布Web bebeb7feca02，3185份运行文件哈希一致。Nginx宿主机持久化模板与容器生成配置同时更新，候选envsubst结果与实测配置逐字一致，语法检查后平滑重载。5个入口及gzip首页200，106个其他容器的ID、镜像、配置和启动时间保持。代码中两处媒体限流burst=40/status=429只是与发布前已在线配置对齐，不是本次放宽生产限流。完整备份再次核验SHA，发布目录`/volume2/library/stl-releases/20261114-network-contention-r1`保留配置/镜像备份及带版本保护的rollback.py。

前后96次HTTP请求全部200，四类响应解码后的SHA前后一致。采用相同客户端、每组各3次交替内外网，`Accept-Encoding: gzip, br`的中位数如下。当前线路样本并非页面LCP或全站提速比例。

| 项目 | 修改前 | 修改后 | 解释 |
| --- | ---: | ---: | --- |
| 内网首页JSON完整响应 | 1976ms | 1941ms | 业务查询仍约2秒 |
| 公网首页JSON完整响应 | 3306ms | 3306ms | 本轮未测出端到端提速 |
| 公网首页JSON首字节 | 2617ms | 2914ms | 路由/负载波动仍在 |
| 公网主CSS完整响应 | 552ms | 537ms | 两组均HIT，体积下降可靠，耗时差异仅样本 |
| 源站首页JSON传输 | 256292B | 70153B | 减少72.6%，解压内容不变 |
| 浏览器首页JSON传输 | 约53841B Brotli | 70153B gzip | 多约16KB，不能称两段都变小 |

Cloudflare官方说明：浏览器支持源站压缩格式时，通常保留原编码。因此保留此次gzip是为了减少NAS上行传输，并非宣称浏览器侧体积更小；没有为此启用Rocket Loader、修改私有接口缓存、安装运行依赖或购买服务。原理见[Cloudflare内容压缩](https://developers.cloudflare.com/speed/optimization/content/compression/)。若后续设置专门Compression Rule，应再测源站与浏览器两段，不把Argo或压缩开关当必然提速。

上线后内置浏览器实看公网`/home`，主内容、私人继续阅读、栏目与导航正常，生产HTML内联初始化、没有外部runtime-config脚本，引用r2样式；1280px无横向溢出。内外网匿名PDF三种URL共6次均401、private/no-store/no-transform，公网DYNAMIC。照片、字体、CSS原文、权限及数据没有改写。

13:37生成本批PageSpeed移动报告：[um7bic3ft1](https://pagespeed.web.dev/analysis/https-books-winstonmo-com/um7bic3ft1?form_factor=mobile)。性能66，无障碍96，最佳做法96，SEO66；FCP1.7s、LCP12.7s、TBT0ms、CLS0、Speed Index8.7s。低速4G模拟、单次Lighthouse13.6，不存在真实用户CrUX数据。报告中的LCP元素是欢迎页介绍段落，不是图片；文档响应、公共CSS和首屏内容呈现仍是限制。SEO中的noindex是现有明确配置，不能为分数擅自开放索引。匿名auth/me 401和缺失刷新Cookie的400保留真实鉴权结果，不改200掩盖。

## PageSpeed发现的预取争用补修

该新报告记录欢迎页自动请求`/scholars.rsc`并超时。主导航已禁用预取，但`home-feature-story.tsx`中的14处链接仍采用默认预取，包含可见栏目入口及演示/内容链接。现在统一增加`prefetch={false}`，保留href、全部内容、样式、点击导航和无JavaScript时的原生链接。不改路由/API/数据库/任务架构。

候选初始停留18.9秒，应用代理记录0个`.rsc`请求；点击欢迎页“学者”后才发起该路径并实际显示学者目录。后续同路径刷新也记入原始日志，未称点击只有1次请求。补修类型、构建、1048压缩副本和预算通过，仍524份文本资源，Brotli合计2376788B。源码a10d154c；13:43:05 +0800补修已发布，当前Web774699aaabd4。3185份运行文件SHA一致，6个入口200，106其他容器保持；Nginx配置不变。发布目录`/volume2/library/stl-releases/20261114-welcome-prefetch-r1`保留前一Web镜像和带版本保护的回退，按需可先回退本补修再回退前一网络版本，数据保持。

补修后实际取得两份新报告，完整保留较差样本，不择优报告：

| 移动端同一线上版本 | 性能 | FCP | LCP | TBT | CLS | Speed Index |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [13:43样本](https://pagespeed.web.dev/analysis/https-books-winstonmo-com/oowe5sbmhw?form_factor=mobile) | 48 | 1.7s | 12.3s | 590ms | 0.102 | 8.3s |
| [13:45复核](https://pagespeed.web.dev/analysis/https-books-winstonmo-com/8p27qgbwwv?form_factor=mobile) | 66 | 1.7s | 12.3s | 10ms | 0 | 8.1s |

13:43报告的控制台中已没有学者页面预取超时，匿名401/400仍在；资源总量2771→2734KiB只是当次测量。较低分样本把CLS定位在演示grain SVG所在区域并列出字体，长任务涉及原框架与主CSS。不能仅据单次评分断言根因或回归；复测表明TBT/CLS并非稳定复现，LCP仍持续偏慢。欢迎文案按既定规则随机，测试运行阶段和线路负载也有差异，未声称受控的整体分数提升。最终公网首屏正常；曾出现一次外链SVG未绘出的观察，品牌文件公网200且SHA与原件一致，页面重载后恢复，未据此改写品牌资产，作为资源加载偶发项保留。

剩余项明确列为C：跨区域公网路径；按路由拆公共CSS的级联依赖；首屏字体/演示区域的加载波动；繁忙时OCR/索引/备份共同运行的争用测量。当前没有重任务积压，不能从空闲样本推出繁忙时无争用。公共CSS中本页未用的样式服务其他页面，未按单页覆盖报告直接删除；实际精确重复规则仅412B/9条，不值得凭此重排全局级联。如做进一步拆分，需要覆盖跨页导航和对应页面视觉。未进行全站230页图集验收，不将本批核对写成全站无问题。

本批源码ce7bde20/a10d154c与最终部署记录沿隔离Git索引提交；原工作区HEAD和暂存区SHA保持。最终文档提交和远端main/工作分支验证回执位于`output/network-contention-20261114/final-receipt.json`。本报告的截图与原始测量在同目录，仅源码和文档进入Git。

依据：[Cloudflare隧道参数](https://developers.cloudflare.com/tunnel/reference/run-parameters/)、[Cloudflare配置](https://developers.cloudflare.com/tunnel/configuration/)、[Nginx gzip](https://nginx.org/en/docs/http/ngx_http_gzip_module.html)、[Docker资源约束](https://docs.docker.com/engine/containers/resource_constraints/)、[Celery优化](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)。沿现有平台能力实施，无新增运行依赖或付费服务。
