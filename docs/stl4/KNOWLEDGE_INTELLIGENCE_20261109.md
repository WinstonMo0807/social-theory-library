# Knowledge Core / Intelligence 内网候选

本轮用户要求以真实业务实现六阶段，并先交付内网 demo。公网、DNS、隧道和正式数据库切换未授权。当前正式内网 192.168.5.6:18084 与公网共用实例，不能作为隔离候选写入目标。

## 基线与恢复

- 2026-11-09 已 fetch origin/main，最新提交 `2f151a8617b33886f046a7ccc3325d7a2deca3ae`，与用户审计基线相同。
- 原工作区 `F:/agent skills/书库开发3` 的已暂存、未暂存及两次肖像提交保持。新工作树 `C:/Users/12297/.codex/worktrees/stl-knowledge-intelligence/书库开发3`，任务分支 `codex/stl-knowledge-intelligence`。
- 最新任务明确允许逐阶段真实验证，覆盖旧文档“全部实现后才验证”的顺序；保留数据、权限、来源、备份及最终公网批准要求。
- NAS 连接已验证。现有正式服务和原预览均不重建；OCR 暂停保持。
- 运行配置实际读回：curation_reasoning、claim_extraction 均 enabled=false / provider=none，未配置模型。已请用户指定既有模型配置；不默认外呼，不把模拟结果记为章节分析。

## 开发状态

|阶段|状态|下一项实际工作|
|---|---|---|
|Knowledge Core|A 尚未实现|正文不可变快照、结构与跨页锚点，身份与来源陈述，复用修订|
|统一检索|A 尚未实现|关键词与向量解耦、迁移消费者、统一 locator|
|Intelligence|A 尚未实现|严格输入预算、固定 DocETL 适配、阶段产物与 ChangeSet|
|管理端|A 尚未实现|AdminShell 工作台、证据与局部审核|
|公开消费者/退役|A 尚未实现|旧 ID 回填与读写切换后才能停止旧生成器|
|MCP|A 尚未实现|复用领域服务和审核权限|

## 验证日志

- NAS 最近15分钟 API/edge 日志未发现502；这不证明用户报告已消失。需复现相同查询与管理员状态读取，取得对应日志。
- 版本元数据已从 PyPI 读取：DocETL 0.3.0、LiteLLM 1.108.3、Docling 2.149.0、MCP 2.3.0，均声明 MIT。尚未完成安装及兼容核验，不计已接入。

实现、实测和内网部署分别记录。没有运行的代表性业务不标通过，旧正式写入在消费者完整迁移前保留并明确登记。
