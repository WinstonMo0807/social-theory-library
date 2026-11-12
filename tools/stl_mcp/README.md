# STL 本机策展 MCP

本机 Codex → 本机 stdio MCP → 固定 SSH 主机/密钥 → 现有 API 容器内短生命令分派进程 → 原 Django 领域服务。

不监听 HTTP，不创建公网 `/mcp`，不修改 Nginx、Docker 运行配置、数据库 schema 或生产源码，不重启服务。不加载 OCR/大模型，不启动索引。SSH 提供认证和传输加密，`StrictHostKeyChecking=yes`；此方式使用原有运维通道，未来面向多用户才考虑独立作用域令牌/HTTP。

远端只接受8种固定动作，工具不能传 SQL、Python、shell、URL、actor、权限、发布/删除/合并/恢复/人工锁命令。账户、token_version 和能力每次重查，写入作品清单由本机可信配置限定，跨对象编辑须属于该作品的已有或待发布关联。SSH 端本身仍是高权限运维凭据，必须只由可信本机启动器持有；这不是对不可信本机用户的隔离沙箱。

## 安装与注册

从仓库根目录执行，使用已有 Python 创建独立环境，避免改变应用依赖：

```powershell
./.venv/Scripts/python.exe -m venv .local/stl-mcp/venv
./.local/stl-mcp/venv/Scripts/python.exe -m pip install -r tools/stl_mcp/requirements.txt
```

复制 `config.example.json` 到忽略目录 `.local/stl-mcp/config.json`，填写已授权 SSH 主机、密钥路径、固定账户 ID/token_version 与具体作品 UUID。空作品列表允许查询，拒绝所有写入。不要复制私钥或把 API 密钥写进本文件。

```powershell
codex mcp add stl -- 'F:/path/to/repo/.local/stl-mcp/venv/Scripts/python.exe' '-X' 'utf8' 'F:/path/to/repo/tools/stl_mcp/server.py'
```

Codex 已打开聊天的工具列表未必热更新；新聊天或应用重载后使用 `stl_*` 工具。实际协议连通需用 SDK 客户端调用验证，`mcp add` 本身不是连通证据。

## 策展协议

1. `stl_search_catalog` / `stl_get_curation_context` 批量固定 Work、Edition 及当前版本。非作品对象使用同一 context 工具取得编辑版本及已有草稿。
2. `stl_resolve_entities` 查重；`stl_read_sources` 从现有正文按版本/关键词/PDF页序取证。关键词未命中不等于没有相关论述；不触发重新OCR。
3. `stl_prepare_changes` 保存本机不可变计划并返回差异。`requirements` 必须保留配置中的全部项目，每项标明 retained/changed/pending/not_required 及理由。已有合格内容复用，未核实不得称完成。
4. 使用返回的 `plan_id` 和 `plan_digest` 调 `stl_save_drafts`。每个操作独立事务，逐项成功/失败，不把部分成功称为整批成功。
5. 中断后调用 `stl_get_operation_status(plan_id)`，再使用同一计划续做。远端回执与本机 SQLite 计划分别持久化，服务重启后仍可回查。无回执只表示未观察到；同请求ID重试由原事务锁/回执去重。
6. 发布仍使用原管理端。成功保存不等于公开、索引完成或学术内容已核准。

`editorial` 使用原 `save_workflow_editorial_revision` / `save_object_editorial_patch` / `create_editorial_revision`，包括未上架作品也只产生待审修订，不通过 `confirm_sections` 把机器建议记为人工确认。原有草稿保留合并，别人的草稿或过期版本阻断；集合隐式删成员阻断。`authority_create` 复用原字段助手并固定 `defer_link=True`，人物/出版社/主题/理论传统先建草稿、再显式关联。`node_create` / `knowledge_relation_create` 复用原管理serializer，支持概念等节点及理论关系，强制draft，不自动替换关系语义。

`evidence_curation` 使用原 EvidenceCuration 修订，新增来源只接受当前有效 EvidenceSpan。`scholar_relation` 使用原学者关系修订。`claim_candidate` 只采用已有、有效、带证据的 DerivedClaim 成为 CuratedClaim 草稿，不发布。独立文章/版位仍沿原工作区处理，清单中保留其既有内容或明确pending，不能省略后称完整策展完成；本机首期没有把其他内容工作区全部改造成新的MCP创建接口。

机器来源保存在修订 change_note 和 `mcp.draft.saved` 审计中，明确 `human_reviewed=false`，不设置人工字段决定或锁。原文、正文修订、账号、正式快照和私人材料不作改写。

## 本机记录

`.local/stl-mcp/journal.sqlite3` 保存计划、要求、原请求编号和每次调用耗时；远端使用现有 AuditEvent 回执，不新建业务表。`bridge.stderr.log` 只用于故障诊断。这些文件可能包含书目/原文/草稿，均不入 Git。删除本机 journal 会丢失便捷续做入口，原远端草稿/回执仍保留；不要用新计划盲目重做未知写入。

计时报告必须区分接口耗时、人工/模型核查时间、后台等待，以及首次完整策展或对已有馆藏的维护。复用已完成内容是有效提速，但不能据此宣称从空白完成整书策展的耗时。
