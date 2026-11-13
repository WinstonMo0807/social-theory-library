# PostgreSQL、检索引擎与恢复演练

2026-11-14。用户要求继续底层开发和迁移准备，明确公网先不切换，保护11月15日随机观点检索演示。本轮使用本机独立PostgreSQL 16.15、Meilisearch 1.37.0；只监听127.0.0.1，使用临时数据目录和独立凭据。不连接NAS，不重启候选worker/beat，不调用生成、向量或重排模型。Intelligence工作台不恢复，MCP不动。

## 本轮修复

- `knowledge_compilation.reconcile_pending`：两个接续任务或人工编辑同时占用订阅时，原逐项锁等待可能使一条来源阻塞后续来源。真实PostgreSQL双连接测试复现锁超时后整批退出；改为`select_for_update(skip_locked=True)`，占用项保留待处理状态，未占用项继续。不是吞掉失败或清除任务。
- `knowledge_source_updates`：`logical_structure`原先未进入ProcessingJob恢复扫描。队列断开或执行器中断后，正文结构、关键词与编纂通知可能停留在失败/运行状态。现在复用已有声明、任务ID、心跳、最大尝试次数和恢复调度；重复消息只允许一个执行者，旧task_id不能覆盖新任务状态。正文锁在下游索引/订阅事务前释放，关键词和编纂继续调用同一服务。
- `ingestion.services.processing`与原Celery路由增加该任务类型，队列存在性检查能识别intelligence队列。不建立第二套任务表/调度器，不默认启动全馆维护，不恢复人工暂停。
- 两处旧PostgreSQL夹具更新：移除已退役的旧理论生成器mock，改为隔离当前结构任务发送；OCR下载测试从实际测试PDF取得geometry。保留几何校验，未放宽生产代码以通过测试。

## 已执行的检查

| 检查 | 实际结果 | 范围 |
|---|---|---|
| PostgreSQL底层组合检查 | 75项通过 | 检索等待预算、公开来源/图、逻辑索引、窗口计划、空产物缓存、远程结果、自动编纂；外部模型/部分索引调用为故障注入 |
| 恢复与原入库检查 | 首轮30项通过、3项夹具失败；夹具修正后原入库10项通过 | 两项缺PDF几何、一项mock已删除的旧入口；没有隐藏这些初始失败 |
| 最终PostgreSQL + 实际Meilisearch | 21项通过，127.20秒含87.29秒空测试库迁移准备 | 新恢复、并发占用、迁移保留、源更新、原文联动及真实索引；与前轮有重叠，不相加冒充独立测试数量 |
| 0102→0104已有数据升级 | 最终小夹具1.394秒 | 10行来源/任务/空回执/拒绝决定/人工正文/订阅及目标页关联逐字段保持；旧run仍plan_version=1，新退避字段为空/0；无模型调用 |
| PostgreSQL备份/恢复 | 242表、1384行测试及初始化记录、15序列全部一致 | 使用真实pg_dump自定义格式与pg_restore，逐表内容摘要及序列值一致；dump约1.36MB，5.205秒导出、5.718秒恢复；运行检查schema_current |
| 图权限查询 | 同一24陈述夹具29→7次SQL | 在PostgreSQL复核原来的批量查询收益，继续验证撤回与归并；不是全馆吞吐指标 |
| 模型不可用时真实关键词 | 两段中英文/Unicode夹具写入1.740秒；3次完整retrieve_channel分别2.323/2.345/2.427秒 | 推理端明确设为不可用的本机端口，每次只尝试一次；真实Meili读写和来源校验，无向量就绪。两段夹具不是长书或NAS速度 |

备份恢复使用的均为隔离测试记录，没有正式馆藏、账号或私人资料。该结果证明工具链和schema恢复，不能替代正式备份的完整恢复验证。Windows/Python3.14.6测试也不能替代Docker Python3.12、ARM依赖和Mac本地模型验证。

Meilisearch使用与仓库配置同系列的[官方v1.37.0发行版](https://github.com/meilisearch/meilisearch/releases/tag/v1.37.0)，Windows二进制SHA-256为`b358c98162d4d857e26753b44a5e954c5ed650b5bd654d3c817d09995e6c514f`，下载后核对一致；无额外RAG服务、数据库或框架依赖。

## 可复跑入口

在`api`目录执行。`DATABASE_URL`必须指向独立PostgreSQL，pytest创建自己的test数据库。`STL_TEST_MEILI_URL`只接受显式指定的本机临时引擎，测试只创建/删除自己的随机索引；不要指向正式索引服务。凭据通过环境安全配置，不能提交Git或回显。

```sh
python -m pytest tests/test_knowledge_postgres_recovery.py \
  tests/test_knowledge_source_updates.py tests/test_knowledge_runtime_optimization.py \
  tests/test_knowledge_meilisearch_integration.py \
  tests/test_ingestion_postgres_integration.py::test_postgres_processing_job_claim_crash_recovery_and_duplicate_retry \
  tests/test_ingestion_postgres_integration.py::test_postgres_processing_recovery_skip_locked_uses_independent_connections \
  -o addopts='' -q --tb=short --durations=8 -s
```

未提供独立Meilisearch时，其integration测试明确跳过；不能将跳过写成通过。上述本轮运行提供了真实引擎，21项没有跳过。生成模型仍未配置，未称无人值守Wiki生成已验收。

## 迁移交接

1. GitHub任务分支包含代码、Django迁移和上述检查。NAS候选仍为0102，新代码依赖0103/0104，不能只覆盖Python文件。
2. 后续在隔离恢复环境安全转移正式库备份与候选库备份，分别恢复；候选保存三书待审成果，不能覆盖正式库。先执行`inspect_knowledge_runtime`、`migrate --plan`、`makemigrations --check --dry-run --noinput`。
3. 为迁移会话设置明确的PostgreSQL `lock_timeout`与`statement_timeout`。例如隔离演练可用`PGOPTIONS='-c lock_timeout=5s -c statement_timeout=120s' python manage.py migrate --noinput`。实际锁超时应停止并检查占用，不能取消保护后反复强推。短schema迁移与后台模型/索引回填分开。
4. 先确认旧引用、来源权限、原文文件和旧有效索引，再有限接续新投影。0103/0104不会自动触发全馆重建；已完成三书产物不强制升级为v2。
5. 回退以源码及停用新执行器为主，保留新增列、历史和人工决定；旧执行器不消费v2任务。恢复测试库成功不授权还原正式库或切换公网。

正式备份恢复、真实NAS新代码时延、新结构索引补齐、配置Provider后的持续编纂及Mac运行仍待各自环境验证。11月15日演示前保持正式版本与活动索引，不准备固定问题答案或演示专用缓存。
