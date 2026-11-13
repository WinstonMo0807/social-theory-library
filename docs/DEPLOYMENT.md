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
