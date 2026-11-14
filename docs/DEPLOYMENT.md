## 2026-11-14 Cloudflare业务性能版本

2026-11-14T04:24:06Z只替换API/Web。API镜像social-theory-library-api:4.0.0-20261114-cloudflare-business-api-r1（sha256:003be31e445555fe7c0d3e30ab967317705675931d25dcd3ee510806acb700f0）；Web为social-theory-library-web:4.0.0-20261114-cloudflare-business-web-r1（sha256:29a4a355ce500f523ffad433acb5750f6e64676244fe49fdca9aa848882d5163）。2份API源码与3184运行文件哈希一致，105其他容器保持。无schema迁移、媒体改写、worker更新、DNS或Cloudflare配置变更。

活动入口仍/volume2/library/stl-releases/20261107-r1/public/compose-command.json，追加/volume2/library/stl-releases/20261114-cloudflare-business-r1/release.compose.json。该目录recovery/rollback.py有活动版本保护，恢复旧API/Web并保留当前数据。当天完整备份重新验SHA。显示偏好内联源码由prepare-performance-assets.mjs生成，generated.ts不进Git；runtime-config保持no-store。公网/内网匿名PDF各3种URL均401/private/no-store，公网DYNAMIC；API不强制缓存。源码12f0cd09，最终Git回执与详细限制见stl4/CLOUDFLARE_BUSINESS_PERFORMANCE_20261114.md。

## 2026-11-14 Web性能发布与代理协议

现用Web镜像social-theory-library-web:4.0.0-20261114-network-web-r2（sha256:10a38bf0337d5828530363cd92c36698a15b6e628d6f2ce8eca7f2a77e80aa68）。构建会生成静态br/gzip、响应图片、字体内容哈希副本及派生字体CSS；运行配置不预压缩。源文件及许可证保留，生成产物不进Git。正常使用package.json的prebuild/build流程，不跳过prepare-performance-assets。

compose.public.yaml为Web设置VINEXT_TRUSTED_HOSTS=${LIBRARY_DOMAIN}。生产Web无宿主机发布端口，仅在既有backend网络由edge访问；edge按公网/内网入口设置X-Forwarded-Proto。该白名单让Vinext保持公网HTTPS登录跳转，拒绝外国X-Forwarded-Host；内网HTTP仍正常。若改变Web暴露方式，必须重新审查代理信任，不能把这一设置复制到不受控直连服务。

本次替换Web，随后补单一代理环境变量和edge转给Web的一行协议头；API所用library_forwarded_proto规则保持，API、worker、数据、DNS与隧道未变。完整备份SHA复核，两个代码发布及配置发布各自保留受保护的旧compose命令和回退脚本。活动配置入口仍为既有20261107-r1/public/compose-command.json。具体回执见stl4/FRONTEND_NETWORK_RELEASE_20261114.md。

## 2026-11-14 S4 公网发布

最终Web：`social-theory-library-web:4.0.0-20261114-s4-web-r9`，`sha256:796503b4b14a690668c282182f76c7ddf6eab0244c15421b912a73f11b3b2b9e`，时间 `2026-11-14T03:59:27+08:00`。API为`200d52cae66c`，普通worker为`d1711e519d36`。只更新这三角色，未迁移数据库；Web最终校验1891文件及106个受保护服务。回退入口 `/volume2/library/stl-releases/20261114-s4-research-r1/recovery-web-r9/rollback-web.py` 恢复r8；此前r8/r7/r6/r5到r2、首次三角色恢复链保留。完整备份与详细验证见 `docs/stl4/S4_RESEARCH_RELEASE_20261114.md`。

## 2026-11-13 最终公网与 main 回读

本轮阅读器与加载修复已于13:59:59 +0800上线。同期检索追加读取预算后，14:11:21 +0800最终Web为viewpoint-web-r4（sha256:8810070bb92af9e6dcf0b97e5960c8b1d91fc42bc8f88fe10f8e031dfcfdf73c），以本轮reader-b-loading-r1为底层，保留本轮全部13份源码。独立回读1866个构建文件哈希一致，runtime-config由启动入口生成；五入口200、106其他容器保持。API未被本轮改写。main已推送bfb55957并核对远端相同SHA，本条为其最终回执补记。原两项暂存、共享HEAD及其他未提交内容保持。Mac架构迁移未开始。详docs/stl4/READER_B_LOADING_20261113.md。

## 2026-11-13 B 版阅读控件与等比随机加载已上线

B 版短把手、整块标题拖动、双页码同排、上方复位及账户本机位置记忆已实现；L5/L6/L7每次加载随机，首屏HTML即带动效，Logo与双线/书签使用同一SVG按容器等比缩放。定向检查、类型与构建、本机真实PDF、刷新/返回记忆和复位、1280/390px布局均通过。13:59:59 +0800发布reader-b-loading-r1，1867运行文件一致，106其他容器保持；外网首页/账户/检索200。公网阅读会话已退出，未声称本轮登录后的公网操作复测。main合并树类型检查通过，Git推送收尾中。详docs/stl4/READER_B_LOADING_20261113.md。

## 2026-11-13 brand-annotations-r1 当前公网Web

NAS回执 2026-11-13T03:57:17Z 完成Web-only更新，镜像 sha256:015d463fd71bfe4e681d66d217c88777178effa3082020968eaf330ed79b2626。API继续使用reader-unified-r3，未迁移数据库或重启任务服务。1866运行文件哈希一致，runtime-config原样保留；ready/home/admin/explore/original/account均200，106其他容器身份、配置和启动时间不变。

发布目录/volume2/library/stl-releases/20261113-brand-annotations-r1；活动compose-command追加web.compose.json。恢复脚本recovery/rollback-web.py只切回先前Web，带活动版本保护，不回灌数据库。沿用reader-unified-r1已完整读验的252637363字节数据库备份并重新核对SHA256。详stl4/BRAND_LOADING_ANNOTATIONS_20261113.md。

# STL 部署与运行入口

当前运行说明在[架构文档第13章](architecture/13_DEPLOYMENT_AND_OPERATIONS.md)，当前镜像与版本证据在[审计基线](architecture/AUDIT_BASELINE.md)。本页保持既有文档链接有效，不再复制第二份会漂移的部署手册。

- [本地运行：环境、Compose、依赖与启动边界](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#本地开发入口)
- [生产拓扑：Cloudflare、Nginx、NAS与同一业务环境](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#生产部署拓扑)
- [运行架构：网络、容器角色、按需重任务与存储](architecture/02_RUNTIME_ARCHITECTURE.md)
- [OCR与派生索引](architecture/10_ASYNC_TASKS_AND_OCR.md)
- [发布、备份和恢复所需事实](architecture/13_DEPLOYMENT_AND_OPERATIONS.md#发布与恢复必须记录的事实)
- [实际完成的检查与未覆盖范围](architecture/VALIDATION.md)

基础Compose是本地环境入口，不是当前NAS的完整部署清单。生产观察到累计27层配置覆盖；旧tag、目录名或单个文件不能代表实际运行版本。Web、API、worker、OCR、模型与索引必须分别核对。

本轮只提交代码整合和文档。生产切换、数据迁移、密钥配置与恢复操作不在本轮范围，不能直接把README示例命令用于已有生产库。

早期Paddle离线依赖、旧部署形态及历史操作说明仍可在 [Git 历史快照](https://github.com/WinstonMo0807/social-theory-library/blob/315a3c48442afc9cafc79718c152e5e70352b13f/docs/DEPLOYMENT.md) 中查看。使用前须按当前源码和实际环境复核。
