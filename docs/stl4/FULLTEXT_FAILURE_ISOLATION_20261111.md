# 正文检索失败隔离

2026-11-11 22:32:33（NAS 北京时间），普通 Worker-only 已切换到 `social-theory-library-api:4.0.0-20261111-fulltext-failure-isolation-r1`。

实测故障是 Meilisearch 连接拒绝从 `index_asset` 直接抛出，导致协调器把尚未执行的公开页、知识关系等投影一并标为失败。`_fulltext_projection` 现在接住该索引服务既有的 HTTP、任务失败和超时异常，记录正文投影的真实失败，再继续其他处理。没有把全文或语义索引改成成功，没有改权限、发布校验、数据库或原件。

本机 SQLite 内存库运行三个定向文件，共 26 项通过。新增覆盖连接拒绝、读取超时、索引任务失败和超时：全文保持失败；公开和知识关系真正执行完成；恢复检索后原任务能够完成。隔离镜像 `manage.py check` 通过。仅将 `app/catalog/services/projection_refresh.py` 替入当前普通 Worker 准确基线，运行哈希为 `3190db555b7dacc659d59428adc3d5fbe8a8872118a183978c63205b264009a1`。

首次切换因按需 ingestion 在等待期间自行重启触发严格保护断言，已自动回退。查明容器 ID、镜像和配置未变后，第二次仅允许同一 ingestion 容器的自主启停，其余配置和容器 ID 全部比较。本次成功切换的其他服务身份、启动状态及配置均未变化，Worker OOM 计数为 0。

本机打包，NAS 只加载镜像；温和等待当前任务结束后切换普通 Worker。恢复目录为 `/volume2/library/stl-releases/20261111-fulltext-failure-isolation-r1/recovery-code-only-attempt2`，保留旧镜像与 Compose；核验既有完整备份的 238460564 字节及哈希。代码回退只还原 Worker，不能恢复旧数据库覆盖后续策展。OCR 保持关闭与暂停，未执行完整 compose up。

证据在 `tmp/fulltext-failure-isolation-r1-20261111/`。运行修复完成，待发布书目仍需沿管理员原事件恢复并核验实际读者页，不把本次上线等同于内容公开完成。
