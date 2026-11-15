# 学者关系原文资格修复

2026-11-10，赵鼎新与韦伯的影响关系已绑定《东周战争与儒法国家的诞生》PDF 第38页，管理台仍报“准确原文尚未公开”。原因是关系发布校验使用匿名可读条件，把已经上架但仅供登录读者阅读的 registered 原文排除。

`api/catalog/relation_source_anchor.py` 现在分别核对发布资格和访客读取资格。管理流程允许 registered 原文作为关系依据；匿名响应继续不返回该原文，restricted/private 及失效定位仍不能发布。未改数据库完成标志。

三个关系来源测试文件共22项通过，包括 registered 可发布、匿名不泄露原文、restricted 不可发布与原有关系行为。启动检查通过。

2026-11-10 13:24:42（北京时间）API-only 切换完成。镜像 `social-theory-library-api:4.0.0-20261110-relation-reader-access-r1`，新文件哈希 `95dafcb475d1c3da7216c8faa78062e18fb76d39cba1cbaa61823f63be93ab0f`。其余四文件保留已部署的原文策展权限修复。本机打包，NAS 仅加载；无迁移、无完整 compose up。其他容器身份、启动时间及状态保持，API readiness 200，内存事件和 OOM 均0。

代码回滚信息已留在 NAS 发布目录。复核既有恢复备份238460564字节，SHA256 `9b190f71d450c1852e7a19a12813966063b7a8996bede336dfe1ac25a9cdb7d0`；该代码发布不恢复数据库，以保留后续策展。部署脚本与结果位于 `tmp/relation-reader-access-20261110/`。真实管理台关系发布与公开回读继续进行。
