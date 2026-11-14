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

生产变更、最终公网样本、回退与Git回执执行后补记。尚未取得本批PageSpeed或真实用户Core Web Vitals，不将HTTP样本等同于全站验收。

依据：[Cloudflare隧道参数](https://developers.cloudflare.com/tunnel/reference/run-parameters/)、[Cloudflare配置](https://developers.cloudflare.com/tunnel/configuration/)、[Nginx gzip](https://nginx.org/en/docs/http/ngx_http_gzip_module.html)、[Docker资源约束](https://docs.docker.com/engine/containers/resource_constraints/)、[Celery优化](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)。沿现有平台能力实施，无新增运行依赖或付费服务。
