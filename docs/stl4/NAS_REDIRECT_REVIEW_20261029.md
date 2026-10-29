# 2026-10-29 NAS登录页误跳转与网络边界核对

## 结论与范围

18:38已修复预览Web反向代理丢失Host端口的问题。不是书库需要NAS登录，也不是发现NAS已被入侵。修复前实际跳转均在同一内网IP；没有新开放端口或新建公网转发。但同IP跨端口Cookie和检索词进入NAS请求的可能影响不能忽略。主机已有管理端口及IPv6监听，尚无路由器/WAN证据，不能宣称公网无法访问或网络安全已全部验证。

本次网络、主机与Cloudflare核对为只读；没有输入NAS用户名/密码，没有抓取Cookie值，没有改变NAS防火墙、路由器、DNS、隧道或生产配置。已授权的预览修复仅改Web代理Host一行及注释，并热加载现有edge。

## 可复现的跳转和截图

1. 在书库带问题进入`/explore/opinions?q=...`。应用`web/app/explore/opinions/page.tsx`保留参数并执行相对路径`redirect('/explore/evidence?...')`。
2. 修复前`http://192.168.5.6:18084/explore/opinions?q=...`返回307，Location为`http://192.168.5.6/explore/evidence?q=...`，遗漏18084。
3. 浏览器请求同IP默认80端口，NAS返回307到`http://192.168.5.6:9999`。
4. 9999返回307到`/desktop/?os=ugospro`，页面落在`#/login/account`。

实际截图`output/visual-review-20261029-interaction/nas-redirect-before.jpg`：蓝紫色背景、中央半透明登录框、设备名称、空用户名/密码框、禁用登录按钮和保持登录选项。没有书库导航或检索结果。没有提交NAS登录。

证据`tmp/stl4-interaction-20261029/redirect-before.json`为不跟随跳转的HTTP读回；截图由实际浏览器取得，没有重制。

## A项最小修复与验证

REDIRECT-PORT-01：`deploy/nginx/default.conf.template`的Web `location /`原来`proxy_set_header Host $host`，使上游收到不含预览端口的Host。仅此处改成`$http_host`保留原请求Host。其他API、鉴权、资产代理规则不改，不用前端绕行掩盖代理错误。

- NAS仅修改`/volume2/library/stl-previews/20261026-r1/deploy/nginx/default.conf.template`。确认真实路径位于预览根且与生产模板不是同一文件。
- 原模板、容器ID、操作日志及结果保存到`interaction-redirect-recovery`，目录0700/文件0600。
- envsubst、既有预览iframe补丁、`nginx -t`、`nginx -s reload`均退出0。没有重建容器，前后所有运行容器ID相同；生产模板hash未变。
- 修复后同一HTTP请求返回307，Location准确保留`http://192.168.5.6:18084/explore/evidence?...`，证据`redirect-after.json`。
- 实际浏览器观点问题框Shift+Enter保留换行且不跳页；Enter提交进入18084原文证据页，未再经过NAS管理页。检索请求与结果状态按页面实际读回记录，不将此检查当作模型质量评测。

REDIRECT-PORT-01为D已实现并在该实际路径验证。其它尚未读取的跳转不宣称全部验证。

## 已读取的网络事实

| 层次 | 实际证据 | 能得出的结论 |
|---|---|---|
| 预览入口 | edge仅映射192.168.5.6:18084到容器80 | 本轮没有改成0.0.0.0或新增IPv6发布；若路由器另有转发，仅此绑定不能排除WAN访问 |
| 预览内部服务 | Web/API/PostgreSQL/Redis/Meilisearch/OCR没有主机发布端口 | 未发现本轮把数据库、任务/检索服务直接发布到宿主端口 |
| 既有Cloudflare | 活动cloudflared只在生产public_front网络；日志中最后可读取的下发配置为2026-10-21，books.winstonmo.com指向http://edge:80，兜底404 | 此配置未指向18084或9999；未登录Cloudflare控制台审计所有账号/隧道 |
| NAS管理服务 | 80、443、9999同时监听0.0.0.0和[::] | 内网其它可达设备存在访问管理登录入口的路径；并非限定127.0.0.1 |
| IPv6地址 | virbr0/virbr1/virbr2有2000::/3全局单播范围地址，非ULA/链路本地/站点本地 | 不能以IPv4私网地址直接推断IPv6也无公网路由；地址存在不证明外部可达 |
| 主机规则 | iptables/ip6tables INPUT为ACCEPT；读取LIBVIRT_INP、UG_SSH_INPUT、UG_INPUT，SSH有来源限制，未看到针对80/443/9999的阻断 | 已读取规则没有提供这些端口的拒绝证据；未替代路由器/其他过滤层核对 |
| 其它既有应用 | 部分应用包含0.0.0.0与IPv6宿主发布，如Firefox5888/5999、数据库5431、Jellyfin8899 | 属于已有主机监听面，不由此次书库改动新建；未操作这些应用或认定它们公网已可达 |

原始非凭据日志在`tmp/stl4-interaction-20261029/exposure-containers.json`、`tunnel-boundary.log`、`host-boundary.log`、`ipv6-classification.log`。全部忽略，不将详细设备配置或运行资料提交Git。报告不记录公网IP、凭据或隧道Token。

## 数据影响与未验证边界

- 检索词随错误目标URL发送到NAS默认HTTP入口，可能进入NAS访问日志；未检查或删除NAS业务日志，未发现此跳转发送至外部第三方站点。
- `api/accounts/cookies.py`的访问Cookie为Host-only、Path=/、HttpOnly、SameSite=Lax；可信HTTP内网会话允许非Secure。Cookie不按端口隔离，所以若浏览器持有该Cookie，它可能随同IP80/9999请求被发送给NAS HTTP服务。HttpOnly只限制脚本读取，不能阻止浏览器自动附带。没有读取/记录实际Cookie请求值，因此不称已证实外泄；书库令牌也不因此等于NAS密码或NAS权限。
- 修复中没有改变登录、刷新令牌、授权或Cookie策略。共享IP不同端口本身不构成Cookie隔离，此处修复停止已证实的错误跳转，不能宣称消除一切跨服务Cookie风险。
- **待核实B（不新增猜测性开发）**：路由器端口转发、UPnP、DMZ及IPv6入站规则；从独立外网对管理端口的实际可达性；其它远程访问产品的授权与转发配置。当前未访问路由器管理台、未外网扫描、未进行入侵取证，所以不能判定已有外部入侵或保证完全无暴露。
- 公网切换前已有安全配置核对中应落实上述边界。若需收紧管理入口或隔离主机名，先明确范围与恢复方式，不在此次只读诊断中擅自更改设备网络设置。

官方依据（本轮读取）：[Nginx Host转发](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)、[RFC6265第8.5节Cookie端口隔离限制](https://httpwg.org/specs/rfc6265.html#weak-confidentiality)。

## 恢复

当前Web98不因代理修复改变镜像。恢复时从NAS受限`interaction-redirect-recovery/default.conf.template.before`恢复**该预览模板**原内容，沿既有envsubst/预览iframe补丁重新生成，再`nginx -t`后reload。不要拷入生产模板，不覆盖整个.env，不重启后端；恢复旧模板会重新引入此误跳转，仅作为故障回退入口。源代码与完整恢复记录保留。
