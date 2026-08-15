# 后台重构迁移指南

更新日期：2026-08-14
适用范围：当前源码快照中的 `ingestion.0008`、`ingestion.0009`、`catalog.0019` 至 `catalog.0023` 及 `backfill_admin_foundation`

## 1. 证据边界

- [SOURCE] 本指南根据当前工作区中的 Django 模型、迁移、管理命令和环境变量模板编写。
- [USER] 本轮只交付可审查、可迁移、可测试和可回滚的代码与文档，不自动部署生产环境。
- [UNKNOWN] NAS 数据库是否已经应用这些迁移、当前表行数、可用维护时段、实际备份位置和恢复耗时均未在本轮验证。
- [UNKNOWN] 当前公网是否运行这一份源码。迁移文件存在不能证明生产数据库已经迁移。

生产操作前应同时阅读 `docs/admin-redesign-audit.md`、`docs/ingestion-pipeline.md` 和 `docs/metadata-provenance-model.md`。

## 2. 迁移内容

| 迁移 | 已实现内容 | 数据动作 | 主要风险 |
| --- | --- | --- | --- |
| `ingestion.0008_admin_redesign_foundation` | 新增来源记录、候选证据、实体消歧候选、审核任务、决定日志；扩展批次策略、上架状态、候选生命周期和任务幂等字段 | 把旧 `UploadItem.status` 映射到 `workflow_state`；把 `selected=true` 的候选标为 `accepted` | 新表和新字段本身为增量变更，但状态映射会更新既有行。反向数据函数是 noop |
| `ingestion.0009_decision_reversal` | 为实体消歧决定增加撤销关系、撤销人、撤销时间和原因 | 无批量数据回填 | 撤销记录使用保护外键。旧决定仍保留，不能通过删除旧日志实现撤销 |
| `catalog.0019_authority_bibliographic_foundation` | 扩展 Work、Edition、Asset、Person 和 KnowledgeNode；保留旧字段 | 无批量数据回填 | 约束会禁止作品自我翻译和知识节点自我引用。上线前要先检查脏数据 |
| `catalog.0020_semantic_chunk_stability_and_search_evaluation` | 增加稳定 `document_id`、反馈关联键和检索评估表 | 遍历全部 `SemanticChunk` 生成稳定 ID，并回填反馈记录 | 可能形成较长事务和表锁。随后把 `document_id` 改为非空唯一字段，这是本组迁移的最高风险步骤 |
| `catalog.0021_asset_registered_access` | 为 Asset 的访问范围增加 `registered` | 无批量数据回填 | 需要新代码与迁移同时生效，否则旧代码无法正确解释新枚举值 |
| `catalog.0022_organization_authority` | 增加机构权威和机构对具体版本的责任关系 | 无批量数据回填 | 新对象默认为草稿或未批准，迁移后不得把机构候选自动公开 |
| `catalog.0023_search_evaluation_task_tracking` | 为检索评估运行增加 Celery 任务 ID 和已完成查询数 | 既有运行记录以空任务 ID 和 0 条完成数开始 | 新旧 worker 混用时进度字段可能暂时不更新，需确保 API 与 worker 使用同一代码版本 |

依赖关系如下。

```text
catalog.0018
  ├─ ingestion.0008 → ingestion.0009
  └─ catalog.0019 → catalog.0020 → catalog.0021 → catalog.0022 → catalog.0023
```

不要手工伪造迁移记录或跳过 `0020`。应由 Django 根据依赖图生成执行计划。

## 3. 上线前只读检查

以下命令只展示状态，不修改数据库。

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations ingestion catalog
python manage.py migrate --plan
```

还应记录当前数据规模。命令只输出计数，不打印馆藏正文或凭据。

```bash
python manage.py shell -c "from catalog.models import SemanticChunk,SemanticSearchFeedback,Asset; from ingestion.models import UploadItem,MetadataCandidate; print({'semantic_chunks':SemanticChunk.objects.count(),'semantic_feedback':SemanticSearchFeedback.objects.count(),'assets':Asset.objects.count(),'upload_items':UploadItem.objects.count(),'metadata_candidates':MetadataCandidate.objects.count()})"
```

生产预检至少保存以下证据。

1. 当前运行镜像、Compose 文件和环境变量键名清单。不要把变量值写入报告。
2. PostgreSQL 备份的路径、校验值和恢复演练结果。
3. 原始 PDF、派生 PDF、模型目录、Meilisearch 数据和媒体卷的独立备份入口。
4. 当前 active `SemanticIndexVersion` 的 ID、UID、模型、revision 和文档数。
5. `SemanticChunk` 行数、唯一键冲突预检结果和 `0020` 预计执行时长。
6. 当前 API、worker、OCR、Meilisearch 容器的健康状态与队列深度。
7. 一个可回退的旧代码镜像或只读归档。

## 4. 迁移前数据检查

### 4.1 自引用约束

`0019` 新增 `translation_of` 和 `parent` 两个可空字段，随后增加自引用检查约束。旧 schema 中没有这两列，因此既有数据不会直接触发约束。不要在尚未迁移的生产数据库上用新模型查询这两列，否则会因列不存在而失败。

应在隔离副本完成 `0019` 后运行只读核对。

```bash
python manage.py shell -c "from django.db.models import F; from catalog.models import Work,KnowledgeNode; print({'self_translation':Work.objects.filter(translation_of_id=F('id')).count(),'self_parent':KnowledgeNode.objects.filter(parent_id=F('id')).count()})"
```

预期两个结果均为 0。若分阶段迁移或人工写入导致结果不为 0，应停止后续步骤并人工修正，不要直接删除冲突行。

### 4.2 稳定语义文档 ID

`0020` 根据资产、parser version、chunk version、页码范围、首个定位信息和同位置出现顺序计算 SHA-256。文本内容和 embedding 模型不进入该键。迁移会先允许空值，再回填，最后增加唯一且非空的字段约束。

生产表较大时，先在生产备份的隔离副本上执行完整迁移并记录耗时、锁等待和磁盘增量。没有这份结果时，不应直接在公网高峰期运行 `0020`。

## 5. 推荐迁移顺序

以下是待执行步骤，不是本轮已经完成的生产操作。

### 5.1 冻结写入并建立备份

1. 暂停新的上传、元数据保存、发布、下架、OCR 和语义索引写入。
2. 等待正在运行的数据库事务完成。
3. 备份 PostgreSQL 和所有持久卷。
4. 验证备份可读取，并在隔离环境完成一次恢复演练。
5. 保存当前 active 语义索引指针和旧镜像标签。

### 5.2 在隔离副本演练

```bash
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py check
python manage.py showmigrations ingestion catalog
```

演练必须覆盖完整生产数据副本。空 SQLite 或测试 fixture 只能证明迁移语法可运行，不能证明生产耗时和锁影响可接受。

### 5.3 生产迁移

确认维护时段、备份和演练结果后，使用生产编排中现有的 API 容器执行一次迁移。

```bash
python manage.py migrate --noinput
```

不要同时在多个 API 或 worker 容器中运行 `migrate`。迁移完成前不要启动消费新字段的 worker。

### 5.4 基础回填预览

`backfill_admin_foundation` 默认 dry-run。建议先限制范围并输出 JSON 报告。

```bash
python manage.py backfill_admin_foundation \
  --dry-run \
  --limit 100 \
  --format json \
  --output /safe/report/admin-foundation-dry-run.json
```

也可重复提供指定对象。

```bash
python manage.py backfill_admin_foundation \
  --dry-run \
  --item-id <upload-item-uuid> \
  --person-id <person-uuid> \
  --format json
```

命令会规划以下增量动作。

- 把有消歧信号的人物从 `draft` 标为 `needs_review`。
- 为疑似重复人物、旧候选冲突和来源不清的记录创建 `ReviewTask`。
- 为作者文本生成实体消歧候选。
- 补充候选的规范值、冲突组和评分因素。
- 在旧来源可解析时创建标明 `legacy-record` 的 `SourceRecord`。
- 把旧 evidence JSON 转成 `CandidateEvidence`。
- 仅在已有 `FieldLock` 与候选值一致时，将该候选补为已接受、已锁定，并写 `DecisionLog`。

它不会合并人物、发布馆藏、删除旧字段，也不会伪造历史网络响应。

### 5.5 审核后应用回填

先对少量明确对象执行。

```bash
python manage.py backfill_admin_foundation \
  --apply \
  --item-id <upload-item-uuid> \
  --format json \
  --output /safe/report/admin-foundation-apply-one.json
```

核对数据库结果和后台页面后，再分批扩大范围。

```bash
python manage.py backfill_admin_foundation \
  --apply \
  --limit 100 \
  --format json \
  --output /safe/report/admin-foundation-apply-100.json
```

当前命令没有 `batch-size`、`resume-from` 或 migration batch ID。`apply_admin_foundation_backfill` 把一次传入的动作放在同一数据库事务中。生产环境不要使用 `--limit 0` 做首次全量执行。每批均应保存 dry-run 和 apply 报告，并在下一批前检查 ReviewTask 数量和事务耗时。

## 6. 模型与语义索引迁移

数据库迁移不会下载 PaddleOCR 或 Hugging Face 模型，也不会自动切换新的生产语义索引。

1. 在受控模型卷预置完整模型文件和精确 revision。
2. 设置离线参数后重启相关服务。
3. 运行轻量健康检查，确认本地文件和模型配置完整。
4. 继续使用现有 active 索引提供查询。
5. 建立新的 `SemanticIndexVersion` 候选快照。
6. 分批建立并验证候选索引的任务数、文档数和模型配置。
7. 只有状态为 `ready` 且验证通过的候选索引才允许人工激活。
8. 保留旧 revision，直到新的社会理论中英文测试查询通过验收。

`catalog.0020` 创建评估数据结构，`catalog.0023` 补充异步任务追踪。当前源码已有管理员 API、人工判断编辑、同步和 Celery 异步执行及后台页面。数据库迁移本身仍不会运行评估、下载模型、建立新索引或切换生产索引。

## 7. 迁移后检查

### 7.1 数据库与应用

```bash
python manage.py check
python manage.py showmigrations ingestion catalog
python manage.py backfill_admin_foundation --dry-run --limit 100 --format json
```

预期结果如下。

- 上表七个迁移均显示已应用。
- dry-run 不应持续重复规划已经成功应用的同一动作。
- 旧 `UploadItem.status` 和候选旧字段仍然存在。
- 既有 PDF、字段锁、已审核关系、读者记录和数据库卷没有被删除。

### 7.2 关键业务检查

1. 管理员和编辑能创建上传批次。审核者只能访问其现有权限允许的复核操作。
2. 保存元数据不会发布。最终发布和下架仍只允许管理员执行。
3. 已发布馆藏编辑后，公开元数据更新不改变原始 PDF。
4. `public`、`registered` 和 `restricted` 三种 Asset 访问范围由分发入口实际执行。
5. 扫描件 OCR 失败或停用时仍能读取原始 PDF。
6. 语义模型不可用时查询返回关键词结果，并在诊断数据中记录降级原因。
7. 新馆藏的页码映射、全文索引和语义索引状态能够独立更新。
8. 下架后公开列表与查询不再返回该馆藏，文件、OCR、索引历史和稳定标识仍保留。

### 7.3 生产验收仍待完成

- [待核实] 真实乱码 PDF 的画布、文字层、中文英文数字复制、引用页码和默认下载。
- [待核实] 管理员、编辑、审核者三个角色在公网批量上传和复核流程中的实际权限。
- [待核实] NAS 离线模型在断网条件下的语义写入与查询。
- [待核实] 发布、修改和下架对首页、推荐、探索、主题、学者、搜索和统计的完整影响。

## 8. 回滚

### 8.1 尚未迁移

停止上线即可。当前代码和文档不能证明生产已经改变。

### 8.2 已迁移但尚未写入新对象

优先恢复旧代码镜像，并保留新增表和字段。只有在隔离副本验证过反向迁移和恢复流程后，才考虑 schema reverse。

### 8.3 已开始写入新对象或运行回填

不要直接反向迁移 `ingestion.0008`。其反向数据函数不会重建旧状态，删除新增表会丢失 SourceRecord、证据、审核任务和决定日志。

安全做法是：

1. 停止新写入和 worker。
2. 恢复旧代码读取路径。
3. 保留新表供审计，不删除原字段。
4. 把 active 语义索引指针切回旧 revision。
5. 如果迁移造成无法接受的数据错误，从迁移前 PostgreSQL 备份整体恢复，并同步恢复对应代码和索引指针。

`0020` 的反向函数会清空稳定 ID，随后删除评估结构。生产已经接收基于稳定 ID 的反馈后，不应以反向迁移作为常规回滚手段。

## 9. 停止条件

出现以下任一情况应停止迁移并执行既定回滚方案。

- 备份无法恢复或校验失败。
- `0020` 演练耗时、锁等待或磁盘增长超过维护时段允许范围。
- 迁移计划包含未审计的额外迁移。
- 当前数据库存在自引用、重复稳定 ID或其他约束冲突。
- 新代码启动后不能读取旧馆藏或原始 PDF。
- worker 使用的代码或 schema 与 API 不一致。
- active 语义索引、模型 revision 或回退 UID 无法确定。

在这些检查全部完成前，本指南不构成生产部署授权。
