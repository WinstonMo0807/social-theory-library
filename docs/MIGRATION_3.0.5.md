# 3.0.5 迁移记录（开发中）

未在生产执行。所有 schema 必须先经过隔离 PostgreSQL 恢复演练，不能用 SQLite 成绩代替。

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

EntityResolutionCandidate 新增可空 cataloging_session FK，旧 upload_item 改为可空但保留，数据库要求至少一个真实上下文。增加 session/type/status 索引。没有删除、自动接受或批量改写旧候选。新研究写入 session，旧上传候选在确认来源一致的持久化操作中关联会话；保持 ID、旧状态、证据和审计。

首次服务回归 24 passed，包含无上传采用/撤销与跨会话隔离。PostgreSQL 锁与生产回填仍待演练。回退旧应用时保留新增 schema，旧应用不支持新 session-only 候选，必须停止相关写入并使用新版只读诊断，不能删除这些候选来回退。

候选上下文、安全历史映射、纯书目公开模式、统一标识符与媒体 schema、正式发布约束、生产 pre/post-check 和还原演练。不要把本文件当作最终迁移清单。
