# 作品详情登录阅读入口修复

2026-11-09 23:25:29，按用户持续授权，Web-only 发布 work-session-r1。当前镜像 sha256:ebb16d7b14b773cf52470b19415b2b073ff56b8b09917018427015e0ef71141f，1860 个构建文件及运行配置哈希一致，其他服务容器身份与启动时间不变。

触发条件是正式出版版本关联 registered 阅读文件。作品详情 SSR 原来不转发会话，CatalogEditionSerializer 按匿名读者过滤 readable_asset；同一已登录管理员可在 Reader 打开，却在作品页看到“暂无可在线阅读的公开文件”，页数也为空。定县版本 d62aa49d 的真实后台已发布状态、842 页阅读文件以及 Reader PDF79/印刷14画布共同验证该差异。

Web部分让作品路由的页面和元数据调用 loadWork(slug, true)，复用已有 serverRequest forwardSession，只转发既定访问 cookie；其他 catalog loader 默认保持匿名。未修改文件权限或 API 鉴权。采用 scholar-portraits-r1 的隔离源码基线，保留最新肖像和预览修复。

2 项定向检查通过，覆盖登录详情选择、其他目录调用不带会话、编码路径及404/503区别。本机构建退出0。一起运行旧 api-domain-boundaries 测试时，其“全部适配器只能有type import”的旧断言失败，原因是此前已有 mediaAllows 纯函数运行时导入；与正式上线的 scholar-portraits 基线一致，此次未修改该文件，也未放宽旧断言。其余3项通过。

发布回滚入口 /volume2/library/stl-releases/20261109-work-session-r1/web-recovery，保存发布前完整活动 Compose、Web inspect、解析配置与保护容器身份。异常分支只回滚 Web，不回滚数据库或策展。未在 NAS 构建镜像，未重启 API/OCR/worker，未完整 compose up。原文件及人工记录保持。

部署证据 tmp/work-session-20261109/verification.json；实际页面发布后核验继续进行，不以构建或HTTP200替代浏览器阅读入口检查。

## API补充根因与发布核验

Web上线后的真实浏览器仍显示无全文，进一步核对发现CatalogEditionSerializer另有硬编码public/inherit过滤，未使用传入会话。新增catalog_reader_access_statuses只对已登录读者增加registered，private/restricted不进入公开书目阅读链接；目录采用同一判断，保持活跃修订、归属及文件就绪校验。

新增20项本机SQLite检查全部通过，覆盖匿名/读者/管理员与五类文件权限、失效文件、修订身份不符及目录一致性。与旧关系测试一同运行共26通过、1失败；旧例重复使用空幂等键，在SQLite创建第二条EditorialRevision时违反唯一约束，尚未到达关系断言，与本次两文件代码无关，保留记录未放宽。隔离Linux启动检查通过。

API-only catalog-session-r1于NAS时间2026-11-09 23:55:47上线，镜像afd499c441869b30f819063d904eef217d597823005ba231a2ea26338a85fa1d；两文件哈希一致，保护服务身份和启动时间不变，memory.events全0。

## 2026-11-10 实际核验与会话过期补充

公网登录《定县社会概况调查》作品页现显示842页、开始阅读和章节链接。目录仍有重复页眉及表格数字误识别，属于待人工校准内容，不是此次阅读权限故障。《国家的视角》正式修订3及Reader的PDF17画布也已核验，相关学者正确链接斯科特。

Web work-session-r2只增加会话401后的匿名书目信息回退，503仍抛出，不改变阅读授权。两项定向检查通过，本机构建退出0。NAS时间00:05:04只切Web，镜像9cfdae7bfc736e61f1b32c9e76e8aabb2db6b043695ddac26625280d99673976，1860文件哈希一致，运行配置c69aff4f5436954e5bc19cdb01b9bcbe47e133a06a0d1a771b0cc7a4ec1be3a1。详tmp/work-session-refresh-20261109/verification.json。

API首轮新pg_dump受NAS磁盘读取限制超过10分钟，实际核对进程命令后只终止本轮pg_dump PID3104890，发生在API重启之前。该尝试的recovery/library-before.dump是不完整归档，不可恢复。成功代码发布复用 /volume2/library/stl-releases/20261109-scholar-preview-r1/recovery/library-before.dump，238460564字节，SHA256 9b190f71d450c1852e7a19a12813966063b7a8996bede336dfe1ac25a9cdb7d0，13:39:56Z已完整读取验证，本轮再次哈希一致。没有执行数据库恢复。

恢复入口：API /volume2/library/stl-releases/20261109-catalog-session-r1/recovery-code-only；Web /volume2/library/stl-releases/20261109-work-session-r2/web-recovery。只回滚对应镜像，保留后续策展数据。没有在NAS构建、没有完整compose up、没有恢复OCR或闲置模型。
