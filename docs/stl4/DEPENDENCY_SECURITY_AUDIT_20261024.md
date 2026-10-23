# STL 4.0 依赖安全排查 — 2026-10-24

本轮为用户要求的只读排查。没有安装/更新依赖、修改业务源码、运行漏洞利用、测试或构建，没有连接生产、迁移或重启服务。开发检查点为bac772f；当前结论不是全站安全验收。

## 结论与证据范围

未在项目源码、依赖声明、Dockerfile及代理配置中发现PHP解释器/服务、Composer、PHP-FPM或FastCGI执行链路。源码中的Wikidata api.php是对外HTTP请求，不能据此判定本项目运行PHP。浏览器上传进度由web/lib/api.ts:342–354的XMLHttpRequest实现，不使用PHP session.upload_progress，无需因PHP公告删除进度条。

但这不能推出全栈没有近期漏洞。npm官方Bulk Advisory API对锁文件617个包名查询，9个包名返回命中；OSV对本地API虚拟环境76项安装版本以及OCR/推理服务7项明确固定版本查询，11个本地包命中。已读取137份去重GHSA记录，查询无失败、没有withdrawn记录。命中数量是依赖包数量，不是已证实可利用漏洞数量；未运行利用验证。

OSV批量结果没有列全Django最新10月公告，因此额外以框架维护者公告补齐。数据库未返回命中也不能证明包无漏洞。OCR/推理容器中的完整间接依赖、基础系统包、实际生产镜像及NAS其他应用未获取，不在本次完整覆盖范围。

## 需要优先处理的版本与发布缺口

| 项目 | 实际证据 | 处理基线与限制 |
|---|---|---|
| Next.js | package.json、package-lock与本机node_modules均为16.3.5 | 官方10月14日修复基线16.4.1；当前包命中严重/高危公告。项目启动用Vinext，不能直接把原Next服务的每条漏洞都算作已可触发。 |
| sharp | 当前锁定/安装0.35.4，且overrides强制0.35.4 | 修复基线0.35.5，涉及librsvg/CVE-2026-96889。Web镜像使用Debian/glibc；未证明当前Vinext图片路由会执行受影响转换。只升级Next而保留旧override不够。 |
| Node.js | 本轮命令工具使用本机24.19.0；Dockerfile只声明node:24-bookworm-slim | 官方10月21日24.x修复基线24.22.1。工具自带Node不等于生产版本；需独立核对运行容器，不能以浮动镜像标签代表已经修补。 |
| Django | 本地API环境5.2.16；requirements允许5.2任意补丁 | 官方10月6日修复基线5.2.18。存在HTTP头/语言解析DoS等公告；GIS专属漏洞尚未证明本项目可触发。 |
| Django REST framework | 本地3.16.1；requirements限制<3.17 | 公告涉及请求体限制绕过、请求头解析、JSON编码处理等；修复需跨过旧上限。已核对3.18.2相关安全公告，PyPI现有3.18.3；具体升级需兼容复核。不能只升级Django。 |
| Python图片/证书依赖 | Pillow12.3.0、cryptography45.0.7，requirements分别限制<13和<46 | 当前公告修复集合已超出旧上限；PyPI现有Pillow13.0.0、cryptography50.0.2。先核对实际使用的解码器/证书API，再同步容器与锁定版本。Pillow确有媒体和TIFF导入调用。 |
| Vite | 声明/锁定/安装8.2.0 | 8.2.4修复10月披露的相关问题；多项限定开发服务器/编辑器入口，不能混称为生产RCE。 |
| Nginx | compose.yaml和compose.public.yaml默认nginx:1.27-alpine | 应更新到维护中的修复版本；10月14日官方基线为1.30.6/1.31.7。模板有aio threads，但未发现SSI开启、HTTP/3或相关rewrite组合，不把仅版本匹配当作可利用证明。生产实际小版本/补丁未知。 |
| FastAPI/Starlette | 推理服务固定FastAPI0.115.14，其PyPI元数据要求starlette>=0.40,<0.47 | 旧上限会阻止较新Starlette修复。推理服务源码是JSON接口，无已发现的文件上传处理；完整容器安装版本/漏洞触发条件待核对，不能把主包无OSV命中当整套服务安全。 |

## 离线包与安装漂移

offline/web.Dockerfile直接复制offline/web-runtime-node-modules-2.5.0-linux-x64.tar.gz，而不按当前锁文件安装依赖。本轮只流式读取归档内package.json，没有解包或执行。归档结果如下；这是现存构建输入，不代表当前线上已部署它。

| 包 | 离线归档 | 当前npm锁文件 |
|---|---|---|
| vite | 8.2.0 | 8.2.0 |
| vinext | 0.0.50 | 0.0.50 |
| sharp | 0.35.3 | 0.35.4 |
| react-server-dom-webpack | 19.2.8 | 19.2.8 |
| react-dom | 19.2.8 | 19.2.8 |
| react | 19.2.8 | 19.2.8 |
| postcss | 8.5.25 | 8.5.25 |
| pdfjs-dist | 5.4.530 | 5.4.530 |
| next | 16.2.12 | 16.3.5 |
| image-size | 2.0.2 | 2.0.2 |

尤其离线Next16.2.12和sharp0.35.3仍处于已披露问题的版本范围。安全更新必须同步重制归档和最终镜像，不能只改package.json。另有本机pdfjs-dist安装5.7.284而锁文件5.4.530的漂移；本次未据此声称其存在漏洞，但本机检查不能替代npm ci后的实际构建证据。

## 前端公告命中清单

依赖角色以顶层package.json及锁文件dev标记区分，不以hoist到根node_modules就误判为直接依赖。

| 包 | 锁文件中的版本 | 角色 | 公告等级 |
|---|---|---|---|
| esbuild | 0.18.20, 0.25.12, 0.28.1 | 间接依赖，含运行项 | moderate |
| brace-expansion | 1.1.18, 2.1.4, 5.0.9 | 间接开发依赖 | high, moderate |
| fast-uri | 3.1.7 | 间接依赖，含运行项 | moderate |
| image-size | 2.0.2 | 间接依赖，含运行项 | high |
| next | 16.3.5 | 直接生产依赖 | critical, high, low, moderate |
| sharp | 0.35.4 | 间接依赖，含运行项 | high |
| source-map-js | 1.2.1 | 间接依赖，含运行项 | high |
| undici | 7.29.0 | 间接开发依赖 | high, low, moderate |
| vite | 8.2.0 | 直接生产依赖 | high, low, moderate |

同名包的多个安装版本不一定全部受影响，以下按公告范围保留，不用包级命中替代具体版本判断。

### esbuild

- [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) — moderate；范围 `<=0.24.2`；esbuild enables any website to send any requests to the development server and read the response

### brace-expansion

- [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7) — high；范围 `>=4.0.0 <5.0.11`；brace-expansion: DoS via uncontrolled recursion on nested brace groups causing stack exhaustion
- [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p) — high；范围 `<1.1.19`；brace-expansion: DoS via uncontrolled recursion in parseCommaParts causing stack exhaustion
- [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p) — high；范围 `>=2.0.0 <2.1.5`；brace-expansion: DoS via uncontrolled recursion in parseCommaParts causing stack exhaustion
- [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p) — high；范围 `>=4.0.0 <5.0.10`；brace-expansion: DoS via uncontrolled recursion in parseCommaParts causing stack exhaustion
- [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) — moderate；范围 `<1.1.21`；brace-expansion: Quadratic-time expansion of the `{a},b}` rewrite causes CPU denial of service
- [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) — moderate；范围 `>=2.0.0 <2.1.7`；brace-expansion: Quadratic-time expansion of the `{a},b}` rewrite causes CPU denial of service
- [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) — moderate；范围 `>=4.0.0 <5.0.12`；brace-expansion: Quadratic-time expansion of the `{a},b}` rewrite causes CPU denial of service
- [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7) — high；范围 `<1.1.20`；brace-expansion: DoS via uncontrolled recursion on nested brace groups causing stack exhaustion
- [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7) — high；范围 `>=2.0.0 <2.1.6`；brace-expansion: DoS via uncontrolled recursion on nested brace groups causing stack exhaustion

### fast-uri

- [GHSA-hrr3-gc8f-f4qj](https://github.com/advisories/GHSA-hrr3-gc8f-f4qj) — moderate；范围 `>=3.0.0 <3.1.8`；fast-uri vulnerable to inconsistent host case normalization via percent-encoded octets

### image-size

- [GHSA-5p2g-fcmc-qvqq](https://github.com/advisories/GHSA-5p2g-fcmc-qvqq) — high；范围 `>=1.2.0 <=2.0.2`；image-size: JXL and HEIF parsers allow denial of service through infinite loops
- [GHSA-w3rx-r6r6-pgpr](https://github.com/advisories/GHSA-w3rx-r6r6-pgpr) — high；范围 `>=0.6.3 <=2.0.2`；image-size: ICNS parser allows denial of service through an infinite loop

### next

- [GHSA-cjq9-62q9-8jv4](https://github.com/advisories/GHSA-cjq9-62q9-8jv4) — high；范围 `>=16.0.0 <16.3.8`；Next.js has Server-Side Request Forgery in Image Optimization
- [GHSA-vcvr-r3jv-pc5j](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j) — critical；范围 `>=16.2.0 <16.3.6`；Next.js: Remote Code Execution in next/og ImageResponse
- [GHSA-f87g-xv8r-7p7x](https://github.com/advisories/GHSA-f87g-xv8r-7p7x) — moderate；范围 `>=16.0.0 <16.3.8`；Next.js has information disclosure in App Router metadata image routes via dynamicParams bypass
- [GHSA-mcj8-r9mp-w47p](https://github.com/advisories/GHSA-mcj8-r9mp-w47p) — moderate；范围 `>=16.0.0 <16.3.8`；Next.js has cache poisoning in SSG/ISR rendering that leads to cross-user content substitution and persistent denial of service
- [GHSA-3w37-wq28-93x7](https://github.com/advisories/GHSA-3w37-wq28-93x7) — moderate；范围 `>=16.3.0 <16.3.8`；Next.js: Pending `use cache` fill can leak Draft Mode content into regular responses and persisted pages
- [GHSA-4jqv-mc3x-m676](https://github.com/advisories/GHSA-4jqv-mc3x-m676) — moderate；范围 `>=16.0.0 <16.3.8`；Next.js has cache poisoning of SSG and ISR pages in self-hosted applications
- [GHSA-39w2-rjm5-chcv](https://github.com/advisories/GHSA-39w2-rjm5-chcv) — low；范围 `>=16.0.0 <16.3.8`；Next.js has information disclosure in development server's Model Context Protocol endpoint
- [GHSA-h694-7cp9-m8p3](https://github.com/advisories/GHSA-h694-7cp9-m8p3) — moderate；范围 `>=16.3.0 <16.3.8`；next.js cache leak across root param values in nested 'use cache' functions
- [GHSA-p3m5-59mp-jv5r](https://github.com/advisories/GHSA-p3m5-59mp-jv5r) — high；范围 `>=16.0.0 <=16.4.0`；Next.js: Denial of Service in App Router using Server Actions
- [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw) — critical；范围 `>=16.0.0 <=16.4.0`；Next.js: Unauthenticated Remote Code Execution in Image Optimization API when SVG files are used
- [GHSA-673q-mjm6-r5xr](https://github.com/advisories/GHSA-673q-mjm6-r5xr) — critical；范围 `>=16.0.0 <=16.4.0`；Next.js: Unauthenticated Remote Code Execution in `use cache` functions returning typed arrays

### sharp

- [GHSA-wq5f-xc86-pv6w](https://github.com/advisories/GHSA-wq5f-xc86-pv6w) — high；范围 `<0.35.5`；sharp : Vulnerability in librsvg dependency CVE-2026-96889

### source-map-js

- [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) — high；范围 `>=1.0.0 <1.2.2`；source-map-js allows event-loop denial of service through indexed source-map section offsets

### undici

- [GHSA-3wwx-pv8p-q78v](https://github.com/advisories/GHSA-3wwx-pv8p-q78v) — moderate；范围 `>=7.28.0 <7.29.1`；undici vulnerable to Denial of Service via unhandled error in WebSocket permessage-deflate decompression
- [GHSA-pmjh-fq2x-6v4x](https://github.com/advisories/GHSA-pmjh-fq2x-6v4x) — moderate；范围 `>=7.11.0 <7.29.1`；undici vulnerable to Denial of Service via orphaned RetryHandler response body
- [GHSA-r53p-7pc4-xj5r](https://github.com/advisories/GHSA-r53p-7pc4-xj5r) — low；范围 `>=7.0.0 <7.29.1`；undici vulnerable to downstream response splitting via retry interceptor
- [GHSA-rfgv-xxqx-mfg5](https://github.com/advisories/GHSA-rfgv-xxqx-mfg5) — high；范围 `>=7.0.0 <7.29.1`；undici vulnerable to Denial of Service via unrequested WebSocket subprotocol
- [GHSA-3xpg-4rpp-hhhm](https://github.com/advisories/GHSA-3xpg-4rpp-hhhm) — moderate；范围 `>=7.15.0 <7.29.1`；undici vulnerable to Denial of Service via unbounded decompression of compressed responses
- [GHSA-2jfj-6hjv-fm6j](https://github.com/advisories/GHSA-2jfj-6hjv-fm6j) — moderate；范围 `>=7.0.0 <7.29.1`；undici vulnerable to cross-user cookie disclosure via Set-Cookie caching in shared caches
- [GHSA-2gqq-gqf2-x968](https://github.com/advisories/GHSA-2gqq-gqf2-x968) — low；范围 `>=7.1.0 <7.29.1`；undici vulnerable to response truncation via oversized chunked responses in the dump interceptor
- [GHSA-w293-vg96-wgc3](https://github.com/advisories/GHSA-w293-vg96-wgc3) — high；范围 `>=7.24.1 <7.29.1`；undici vulnerable to TLS certificate validation bypass via dropped connect options in BalancedPool
- [GHSA-8436-99hf-9mmv](https://github.com/advisories/GHSA-8436-99hf-9mmv) — low；范围 `>=7.0.0 <7.29.1`；undici vulnerable to caching and replay of unsafe HTTP method responses
- [GHSA-rx4f-c7p8-82vq](https://github.com/advisories/GHSA-rx4f-c7p8-82vq) — moderate；范围 `>=7.0.0 <7.29.1`；undici vulnerable to Denial of Service via WebSocketStream unclean close

### vite

- [GHSA-9jrq-w75r-8gcw](https://github.com/advisories/GHSA-9jrq-w75r-8gcw) — low；范围 `>=8.2.0 <=8.2.3`；Vite: Cross origin script execution through Vite custom middleware
- [GHSA-rq7h-c2jc-7f22](https://github.com/advisories/GHSA-rq7h-c2jc-7f22) — moderate；范围 `>=8.2.0 <=8.2.3`；Vite: Files outside `server.fs.allow` could be served when project paths match system paths on non-Windows machine
- [GHSA-698v-4r3x-3vcv](https://github.com/advisories/GHSA-698v-4r3x-3vcv) — moderate；范围 `>=8.2.0 <=8.2.3`；launch-editor: escapeCmdArgs() omits % escaping on Windows
- [GHSA-r825-w8mm-5pxw](https://github.com/advisories/GHSA-r825-w8mm-5pxw) — moderate；范围 `>=8.2.0 <=8.2.3`；launch-editor: Editor CLI flag misinterpretation causing arbitrary command execution for some editors
- [GHSA-587h-7wmj-h5pm](https://github.com/advisories/GHSA-587h-7wmj-h5pm) — high；范围 `>=8.2.0 <=8.2.3`；launch-editor: `fs.existsSync()` existence check can be bypassed on Windows
- [GHSA-vfpm-58rq-9qcg](https://github.com/advisories/GHSA-vfpm-58rq-9qcg) — moderate；范围 `>=8.2.0 <=8.2.3`；Vite: First 4 bytes of files outside of `server.fs` setting is exposed by `?vite-wasm-instance`

## 后端本地环境公告命中清单

| 包 | 本地安装 | 去重GHSA数 | 查询所得修复版本集合（不是一律升级目标） |
|---|---|---|---|
| certifi | 2026.7.22 | 1 | 2026.10.19 |
| cryptography | 45.0.7 | 7 | 46.0.5, 46.0.6, 46.0.7, 48.0.1, 49.0.0, 50.0.0 |
| Django | 5.2.16 | 2 | 5.2.17, 6.0.8, 6.1.1 |
| djangorestframework | 3.16.1 | 5 | 3.17.2, 3.18.2 |
| pillow | 12.3.0 | 39 | 13.0.0 |
| pip | 26.1.2 | 1 | 26.2.0 |
| PyJWT | 2.13.0 | 15 | 2.14.0, 2.15.0 |
| pypdf | 6.14.2 | 22 | 6.15.0, 6.16.0, 6.16.1, 6.17.0, 6.18.0, 6.18.1, 6.19.0, 6.20.0, 6.20.1, 6.21.0, 6.21.1 |
| pytest | 8.4.2 | 1 | 9.0.3 |
| sqlparse | 0.5.5 | 5 | 0.6.0 |
| urllib3 | 2.7.0 | 3 | 2.8.0 |

Pillow解码在api/catalog/services/media.py、edition_file_intake.py存在真实调用。DRF处理API输入，需优先处理请求解析相关公告。PyJWT通过SimpleJWT进入登录体系，但部分公告限定JWK/外部JWKS或特定选项，应分别复核；不能把15条公告都说成当前账号鉴权绕过。

pypdf、sqlparse等安装命中也应清理，但本轮未找到业务源码直接使用sqlparse.format生成Python/PHP代码、PyJWKClient或verify_signature=False的证据。sqlparse公告GHSA-3496-9g83-7v6x确实涉及生成Python/PHP代码片段，这是跨语言工具能力，不等于本项目有PHP服务。pip/pytest主要属于安装/开发工具风险。

## PHP上传进度评估

[PHP 10月23日公告](https://www.php.net/archive/2026.php#2026-10-23-1)针对session.upload_progress及特定运行时切换session.serialize_handler组合；建议在PHP运行环境关闭该功能。10月21日的两项严重PHP漏洞需要升级对应PHP版本，仅关闭上传进度不能完整修复。当前项目没有发现PHP服务，所以无需添加无效php.ini或删除浏览器上传进度；NAS上其他PHP应用若存在，需单独核对。

## 修复与验收顺序

1. 先升级与公网请求/身份/图像解析相关的实际依赖，调整会阻止补丁的上限或override；保留既有技术架构、账号数据和权限规则。
2. 同步npm锁文件、本地安装、Python部署约束、离线依赖归档及容器基础版本。不要直接运行强制自动升级或复用旧离线归档。
3. 核对真实生产容器的版本、镜像摘要及系统包，确认NAS其他应用是否有PHP；当前没有连接生产，不能代填结果。
4. 按项目约定在统一验收阶段验证登录/刷新/权限、JSON和multipart解析、媒体转换、Reader与PDF、异步任务及部署回滚。安全公告匹配和静态检查不替代运行验证。

## 主要官方依据

- [Next.js 2026-10-14安全更新](https://nextjs.org/blog/nextjs-security-update-october-14-2026)
- [sharp/librsvg公告](https://github.com/lovell/sharp/security/advisories/GHSA-wq5f-xc86-pv6w)
- [Node.js 2026-10-21安全更新](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)
- [Django 2026-10-06安全更新](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/)
- [DRF请求体限制公告](https://github.com/encode/django-rest-framework/security/advisories/GHSA-2m8g-3cmr-wg3w)
- [DRF请求头解析公告](https://github.com/encode/django-rest-framework/security/advisories/GHSA-33wh-fxxf-88vv)
- [Vite开发服务公告](https://github.com/vitejs/vite/security/advisories/GHSA-vfpm-58rq-9qcg)
- [Nginx安全公告](https://nginx.org/en/security_advisories.html)与[发布记录](https://nginx.org/news.html)
- [sqlparse代码生成公告](https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-3496-9g83-7v6x)

## 本机原始证据与复查方式

原始只读元数据保存在tmp/stl4-security-npm-advisories-20261024.json、stl4-security-python-inventory-20261024.json、stl4-security-python-advisories-20261024.json、stl4-security-advisory-details-20261024.json、stl4-security-offline-inventory-20261024.json。它们未提交，属于可重新查询的运行产物，不能作为长期不可变的漏洞数据库。

执行了tmp/stl4-dependency-advisory-audit-20261024.py（npm/OSV批量查询）、tmp/stl4-advisory-details-20261024.py（137条GHSA详情）和tmp/stl4-offline-package-inventory-20261024.py（归档元数据读取），退出码均0。工具安装、应用测试、漏洞利用、浏览器验收、数据库访问和生产操作均未执行。
