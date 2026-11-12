# STL 策展 MCP

最新授权：本人使用的网关已配置`work_scope = "catalog"`，草稿权限覆盖现有及以后入库的Work，不再逐书更新清单。每次操作仍在原库确认作品存在、账户能力、关联目标、人工锁与版本，不能发布或访问私人笔记；获得权限不等于自动启动策展或OCR。保留`selected`模式用于明确的有限试用，未配置时默认`selected`，未知模式拒绝初始化业务适配；`allowed_work_ids`在catalog模式下只保留为回退清单和抽样依据，不限制新书。范围配置只由受信运维修改，不是MCP工具参数。

2026-11-12追加：按用户最新授权，已增加受保护的公网Streamable HTTP方式。本机默认`stl`现连接HTTPS，原stdio配置保留为停用的`stl_local`。两种方式使用同一工具和领域服务。部署、安全审查与实际验证见 [公网交付记录](../../docs/stl4/PUBLIC_MCP_SECURITY_20261112.md)。下文的“不监听HTTP”仅描述原stdio方式。

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

## 受保护的公网方式

`public_server.py`提供单用户`/mcp`，同一七工具经`DjangoBridge`调用API镜像中的现有领域服务；无SSH密钥、任意命令或OAuth身份模拟。认证文件只有随机令牌SHA-256及绝对到期时间，每次请求重读；删除、轮换或到期立即阻断新请求。`actor_id`/`token_version`/作品写入清单取自只读受信配置，不能从工具参数改写。

认证先于MCP解析，检查重复认证头、Host和Origin，限制2MB请求、两路并发；Nginx另设独立速率和连接限制。无Cookie认证，不开放匿名工具发现。没有动态OAuth注册端点；面向多个用户的OAuth授权尚未实现。

NAS镜像的Python为3.12，依赖在电脑下载和解包，不在NAS安装或构建：

```powershell
./.local/stl-mcp/venv/Scripts/python.exe -m pip download --index-url https://pypi.org/simple --only-binary=:all: --no-deps --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --abi cp312 --dest .local/stl-mcp/public-build/wheels -r tools/stl_mcp/linux-requirements.lock
./.local/stl-mcp/venv/Scripts/python.exe -X utf8 tools/stl_mcp/build_public.py
```

构建目录只放对应平台的固定wheel。产物、清单、认证摘要与可信配置放在忽略目录。Windows DPAPI加密随机令牌，不在日志、命令行、仓库或Codex TOML保存明文。`credentials.py`是凭据辅助程序，**不要直接运行到终端**；Codex的`http_headers_helper`通过管道接收它的JSON输出。

上传产物及`deploy/mcp/deploy.py`、`nginx-location.conf`到一个新NAS release后，由现有受信SSH运维执行：

```sh
sudo -n python3 /volume2/library/stl-releases/RELEASE/deploy.py stage /volume2/library/stl-releases/RELEASE
# 先在容器内通过受信stdin令牌做真实HTTP协议只读验证，再接入口。
sudo -n python3 /volume2/library/stl-releases/RELEASE/deploy.py expose /volume2/library/stl-releases/RELEASE
```

脚本核对原镜像和文件哈希，保存现有容器身份及Nginx原模板/编译配置，复用已有API镜像新增`stl-mcp`，无宿主机端口。它只挂载两个只读馆藏目录、只读配置/代码和独立计划目录，无Docker socket、模型、备份或私人文件挂载。API环境中的数据库等凭据只在NAS本地转入受限env文件，不输出、不上传本机。服务限制384MiB/0.5CPU，根文件系统只读、移除capabilities、禁止提权。

`expose`只在原模板增加两个limit zone及`/mcp`两条location，保留绑定文件inode，经`nginx -t`后reload；不重启现有服务，不改DNS、Tunnel、数据库或索引。回退同脚本的`rollback`动作，只在当前模板哈希仍等于本次候选时恢复，避免覆盖后续变更。关闭令牌可先移走认证文件，使新请求返回503，再撤回代理；保留journal与原业务回执。

`verify_http.py`检查匿名/错误令牌、错误来源，两种协议、工具清单和三书上下文，默认从DPAPI取令牌，仅只读。脚本需本次本机三书配置。已迁移的旧计划仍使用相同ID和digest；NAS journal与原本机journal各保留，迁移不执行业务保存。新计划在当前MCP服务的journal中持久化，跨服务端点切换时必须明确迁移，不能盲目重建。
