# 3.0.5迁移与回退记录

2026-09-12已在生产执行catalog0043至0054及ingestion0015/0016。先在同一生产备份恢复的隔离PostgreSQL16中完成迁移，再切生产。生产pending_migrations为0。没有手工DDL、反向迁移、馆藏清理或活动索引重建。

| 迁移 | 变化 | 保护范围 |
| --- | --- | --- |
| catalog0043 | CatalogingSession、上下文FK、开放会话唯一约束 | 不伪造上传、不改旧人工数据 |
| catalog0044 | Edition.publication_mode及合法值约束 | 旧行保留document，纯书目显式bibliographic |
| catalog0045 | MediaAsset、MediaRendition | 新表，不移动旧图片 |
| catalog0046 | 媒体来源类型 | 不批量确认历史来源 |
| catalog0047 | Work封面rendition FK | 可空，旧cover保留 |
| catalog0048 | CatalogPublicationMedia | 正式修订图片引用保护 |
| catalog0049 | 媒体元数据快照 | 尺寸、说明和来源随修订固定 |
| catalog0050 | Work推荐图片rendition FK | 可空，保留历史图例 |
| catalog0051 | PersonMergeRecord | 不可变操作记录及回滚依据 |
| catalog0052 | Person肖像rendition、EditorialRevisionMedia | 草稿和历史图片引用保护 |
| catalog0053 | KnowledgeNode/ReadingPath封面rendition FK | 可空，无自动发布或旧图批量迁入 |
| catalog0054 | publication_mode数据库默认值document | 旧ORM可省略新列插入，既有值不变 |
| ingestion0015 | 人物候选session FK、索引、上下文约束 | 旧upload FK、候选身份和决定保留 |
| ingestion0016 | 元数据候选session FK、索引、上下文约束 | 证据和审核历史保留 |

BackupJob为780098c8-17c1-4090-a52e-4e00cb14090d，归档SHA256为11b20085f2eb84f0e386a14d3e5c0ed913f44289240e9407d630037cc8d3f000。隔离恢复库stl_v305_rehearsal仅接内部网络，生产文件只读挂载。候选迁移、Django检查、书目恢复、原件及页身份比对通过。旧3.0.4镜像在新schema下实际创建Work/Edition后整笔事务回滚，readiness正常、行数不变。此检查不代表旧版支持新媒体和session-only候选写入。

回退记录在storage/backups/pre-v305-20260912-2148/deploy-record，保留源码、环境、Compose、镜像、数据库备份及rollback-v305.sh。新功能投入使用后优先回到已验证3.0.5。必要时回3.0.4必须暂停旧版无法理解的新媒体与session-only候选写入，不删除这些记录。停止Worker前先停Beat并确认真实任务结束。API/Web替换后刷新Edge，不改cloudflared。

2026-09-13恢复副本另行重现发布完成时可空关联的FOR UPDATE异常。补丁只锁事件主行，Edition和revision仍由激活服务分别加锁，完成及租约释放已在副本事务内验证后回滚。此补丁上线状态以CURRENT_PROGRESS为准。

## 以下为实施时历史记录

本次部署目标为catalog0043至0053与ingestion0015/0016。0045/0046创建媒体及来源类型，0047Work封面FK，0048公开修订图片保护，0049衍生图元数据快照，0050推荐图例FK，0051人物合并记录，0052肖像与编辑图片保护，0053理论/阅读路径图片FK。既有列默认保留旧文档模式，不回填或删除原件、关系和私人记录。应用回退保留所有新增schema，不用反向迁移删表。

2026-09-12生产BackupJob780098c8-17c1-4090-a52e-4e00cb14090d完成，归档SHA256为11b20085f2eb84f0e386a14d3e5c0ed913f44289240e9407d630037cc8d3f000。独立内部网络的PG16副本stl_v305_rehearsal已实际恢复，dump SHA和pg_restore目录校验通过，尚在候选迁移验证阶段。生产没有应用3.0.5迁移。

媒体增量 0045–0050 的职责和验证见 `V3.0.5_MEDIA.md`。当前 migration 尚未应用生产，不执行 down migration 或覆盖旧文件。

未在生产执行。所有 schema 必须先经过隔离 PostgreSQL 恢复演练，不能用 SQLite 成绩代替。

0050 为 Work 增加可空的 recommendation_rendition PROTECT FK。新选图使用 MediaAsset/Rendition 与现有 CatalogPublicationMedia；旧图例路径保持原样，无批量确认、图片重建或删除。回退旧应用需保留 schema 并禁用旧推荐图写入口，或保留本修复，避免旧代码物理删除托管衍生图；只读兼容不受影响。

## catalog 0043

新增 CatalogingSession。来源与编目状态独立，nullable upload_item、edition、base_public_revision 均使用真实 FK。Work 从 edition.work 推导，避免双写作品身份。对 Edition 和 UploadItem 分别限制最多一个开放会话，用户请求键唯一，必须有上下文，上传来源必须引用真实上传记录。

- Preflight 核对 0042 与 ingestion 0014 已应用、备份和还原可用。新表为空，不扫描或改写既有人工数据。
- Migration 只新增表、索引与约束。没有自动采用候选、创建权威实体、OCR 或索引任务。
- Post-check migration drift、来源/FK/唯一约束与 12 个会话专项已在 SQLite 验证，PostgreSQL 待核实。
- Rollback 恢复旧应用并保留新增表。会话投入使用后不 down migrate，避免丢失过程记录。

## 仍待完成

## catalog 0044

Edition 新增 publication_mode，默认 document 保留旧馆藏文件门槛。手工会话创建新 Edition 时显式选择 bibliographic，旧行不批量改为纯书目。纯书目只有在没有任何 Asset 时允许无文档发布；已有异常或不可读文件仍阻断。恢复旧应用时保留字段，不 down migrate。SQLite 纯书目公开、损坏文件、旧模式、字段与会话专项通过，PostgreSQL 演练待核实。

## ingestion 0015

## ingestion 0016

MetadataCandidate 增加可空 cataloging_session FK、会话字段状态索引与至少一个上下文约束，旧 upload FK 保留。手工来源导入只建立 PROPOSED 候选和 Evidence，正式字段由显式人工采用写入。旧候选决定、身份和来源保持不变。兼容读取、拒绝幂等、隔离不同会话、审计和旧 backfill 已回归。应用回退仍保留新增字段/表，新会话-only 候选不交给旧应用写入。

EntityResolutionCandidate 新增可空 cataloging_session FK，旧 upload_item 改为可空但保留，数据库要求至少一个真实上下文。增加 session/type/status 索引。没有删除、自动接受或批量改写旧候选。新研究写入 session，旧上传候选在确认来源一致的持久化操作中关联会话；保持 ID、旧状态、证据和审计。

首次服务回归 24 passed，包含无上传采用/撤销与跨会话隔离。PostgreSQL 锁与生产回填仍待演练。回退旧应用时保留新增 schema，旧应用不支持新 session-only 候选，必须停止相关写入并使用新版只读诊断，不能删除这些候选来回退。

候选上下文、安全历史映射、纯书目公开模式、统一标识符与媒体 schema、正式发布约束、生产 pre/post-check 和还原演练。不要把本文件当作最终迁移清单。
