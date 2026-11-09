# Knowledge Core / Intelligence 内网候选

本轮用户要求以真实业务实现六阶段，并先交付内网 demo。公网、DNS、隧道和正式数据库切换未授权。当前正式内网 192.168.5.6:18084 与公网共用实例，不能作为隔离候选写入目标。

## 基线与恢复

- 2026-11-09 已 fetch origin/main，最新提交 `2f151a8617b33886f046a7ccc3325d7a2deca3ae`，与用户审计基线相同。
- 原工作区 `F:/agent skills/书库开发3` 的已暂存、未暂存及两次肖像提交保持。新工作树 `C:/Users/12297/.codex/worktrees/stl-knowledge-intelligence/书库开发3`，任务分支 `codex/stl-knowledge-intelligence`。
- 最新任务明确允许逐阶段真实验证，覆盖旧文档“全部实现后才验证”的顺序；保留数据、权限、来源、备份及最终公网批准要求。
- NAS 连接已验证。现有正式服务和原预览均不重建；OCR 暂停保持。
- 运行配置实际读回：curation_reasoning、claim_extraction 均 enabled=false / provider=none，未配置模型。用户明确自行接入OpenAI-compatible API，已提供复用入口；不默认外呼，不把模拟结果记为章节分析。

## 开发状态

|阶段|状态|下一项实际工作|
|---|---|---|
|Knowledge Core|B 来源/身份代码已有契约检查；A 真实馆藏回填和结构补全|快照、节点、跨页锚点、Entity、Assertion、KnowledgePage与EditorialRevision已实现；仍需Docling、完整历史关系迁移|
|统一检索|A 实现中|真实Discovery及读者检索已接共享召回和locator，关键词先写；需真实Meili验证、语义补齐与剩余旧适配器切换|
|Intelligence|B 基础运行/审核契约已验证；A 真实模型、覆盖/恢复及远程验证|八阶段、顺序综合、严格DocETL map、ChangeSet事务与幂等已接服务，模型等待配置|
|管理端|B 源码/类型通过；A 真实工作台验收|列表、启动、审核、身份选择、证据、草稿预览及发布入口，接现有模型管理|
|公开消费者/退役|A 尚未实现|旧 ID 回填与读写切换后才能停止旧生成器|
|MCP|B 官方SDK工具注册通过；A 实际协议及外部草稿验证|stdio绑定现有账户，10个工具复用业务服务，无发布/审核/凭据或租约工具|

## 验证日志

- NAS 最近15分钟 API/edge 日志未发现502；这不证明用户报告已消失。需复现相同查询与管理员状态读取，取得对应日志。
- 版本元数据已从 PyPI 读取：DocETL 0.3.0、LiteLLM 1.108.3、Docling 2.149.0、MCP 2.3.0，均声明 MIT。DocETL/LiteLLM/MCP已安装并验证算子/注册接口；Docling仅固定依赖，尚未安装和业务验证。

实现、实测和内网部署分别记录。没有运行的代表性业务不标通过，旧正式写入在消费者完整迁移前保留并明确登记。

## 当前入口与运行边界

- 管理端 `/admin/intelligence`；兼容API配置 `/admin/intelligence/settings`，仍使用 `/reading/admin/ai-runtime-profiles/`，HTTP页面不录入敏感配置。服务地址、密钥不回显。
- API `/api/intelligence/runs/`、`sources/`、`changesets/`及详情、审核、应用；知识API提供快照、结构、节点上下文、锚点、身份、陈述、知识页/导出。
- 迁移 `python manage.py migrate`。历史回填 `python manage.py backfill_knowledge_core --revision UUID --batch-size 100 --identities --claims`，按来源与批次记录映射；仅在隔离候选执行，正式迁移未授权。
- 计算环境 `pip install -r api/requirements-intelligence.txt`，启动 `celery -A config worker -Q intelligence --pool=solo --concurrency=1`；Redis容量名额用于共用Provider，不依赖单实例semaphore。API/beat不导入DocETL。
- MCP仅可信本地stdio启动 `python manage.py serve_knowledge_mcp --actor EXISTING_ACCOUNT`，账户由启动者绑定，工具不能选择身份。每次调用重新核验账户有效性与服务权限。外部草稿进入相同ChangeSet，尚需补齐无run草稿的工作台列表并实测完整协议。
- 快照文字偏移为Unicode code point，PDF页码1基，end不含。每段独立几何，不可信几何返回文字范围；前端增加code point/UTF-16转换工具和跨页片段入口。历史权限继续要求来源确曾发布且当前版本未撤回。
- 分析结果缓存包含源范围、模型与transport摘要、prompt/schema。未知成本保持null，实际调用数和耗时保存。禁用模型时任务不产生推理产物；短章节和整书均未做真实模型调用。

## 仍须完成

1. 独立候选API/搜索与真实数据就绪；NAS备份恢复操作只针对命名候选，不动正式表/活动索引。
2. 真实跨页/脚注/OCR结构与阅读器校验，Docling按需解析及结构校正失效接入。
3. 关键词可用性及向量补齐业务验证，旧UnifiedRetrievalPipeline与历史消费者完整迁移。
4. 完整人工身份/关系/正文迁移、公开实体/策划消费者切换、旧AI生产者/重复写入退役。当前旧正式写入仍保留，不能宣称单一写入迁移完成。
5. 远程执行协议扩展、长章覆盖、阶段失败产物、恢复/取消实测，真实Provider调用等待用户配置。
6. 管理端真实审核/公开发布/Markdown/原文回看，MCP草稿实际进入相同工作台；代表性耗时/模型调用/资源记录。
