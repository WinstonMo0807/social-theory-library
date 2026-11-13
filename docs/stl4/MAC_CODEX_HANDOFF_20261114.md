# Mac mini / Codex 知识底层接续入口

用户决定先完成知识底层，再从GitHub任务分支接续到Mac mini；大部分服务最终由Mac运行，NAS保存原件、派生文件和备份。本文是可执行交接，不是已经迁移或性能通过的证明。当前新计划优化的验证和部署状态先读CURRENT_PROGRESS顶部。

## 取代码与恢复上下文

```sh
git clone --branch codex/stl-knowledge-intelligence https://github.com/WinstonMo0807/social-theory-library.git
cd social-theory-library
git status --short --branch
git log -5 --oneline
```

读本仓库AGENTS.md、CURRENT_PROGRESS.md顶部、本文件，再按任务读ARCHITECTURE/DEPLOYMENT最新段落。用户级Windows技能路径在Mac可能不存在：先查Mac已有的同名技能，不把Windows盘符当作源码或运行依赖。应用代码没有依赖Windows的tmp脚本。

使用当前任务分支，不把main自动当作知识底层交付版本。正式镜像可能含其他已上线改动；正式API在2026-11-14只读核查为20261113-viewpoint-api-r3，不能凭Git分支名推断线上版本。迁移前比较当前正式源码差异，保护MCP和其他已上线修复。

## 必须保留的运行边界

- 用户最新明确停止Codex暂代生成模型。不要继续人工生成章节/全书/Wiki产物；未配置Provider时保持等待，旧三书产物与决定不改写。原文、缓存、索引和迁移验证可继续。
- NAS正式服务优先。隔离候选重型worker/beat已停止，不因克隆代码、恢复数据库或接续本任务而自动启动。
- 只允许迁移准备、隔离恢复和内网验证；公网、正式数据库写入端、DNS和Cloudflare Tunnel切换仍等用户授权。
- Intelligence独立工作台不恢复，审核使用/admin/knowledge/review。MCP不开发、不重建、不部署。
- 保留账号ID/密码哈希/角色、私人笔记和研究、原文件及人工成果。不得以候选库覆盖当前正式数据库，也不得清空Redis/活动索引来省迁移步骤。
- 三书完整可用原文已完成旧计划产物：245窗口、884947字符、589项待审。不要重新OCR或重新调用模型来重建这些已保存成果。

## GitHub不包含的材料

源码不是可恢复的完整书库。以下内容通过用户已有的安全渠道转移，不提交Git、不在聊天回显凭据：

| 材料 | 用途与处理 |
|---|---|
| 当前正式PostgreSQL备份及版本 | 正式馆藏、账户、私人资料和人工成果的权威来源；在Mac独立恢复，先核验再讨论切换 |
| 隔离候选数据库备份 | 保留新知识模型、三书产物、589项待审和旧ID映射；先恢复为隔离候选。它不是可直接覆盖正式库的新生产库 |
| NAS文件树与相对路径 | 保持archive/public/private/incoming/backups等实际路径及权限；先核验挂载和代表性原文件哈希 |
| 有效Meilisearch备份/代际信息 | 与对应数据库及引擎版本核对；优先恢复有效索引，再有限接续新版投影，禁止启动后立即全馆重建 |
| 安全运行配置及原加密配置 | 保留Provider凭据加密材料和账号签名配置，避免盲目更换导致凭据不可解密或会话混乱；预览与正式会话继续隔离 |
| 已有模型工件及清单 | 明确实际版本与本机可用性；未启用的生成/向量/重排能力保持关闭，不隐式下载或外呼 |

目前候选位于NAS `/volume2/library/stl-previews/intelligence-20261109`，数据库`stl_intelligence_demo_20261109`，API容器`stl-intelligence-demo-api`。源码、数据备份及回退包的现有位置见DEPLOYMENT；备份清单核验不等于完整恢复成功。

三书待审ID：以利518a104d-ab7e-4b7c-a11a-268bc75d08c3；治理9fa8c249-0159-4a7d-b510-9ba6000763c6；规训a30cb2e4-967e-43a1-8f9a-bc65b09d74aa。完整run/revision及业务证据见RAG_WIKI_THREE_BOOKS_20261113.md。

## 先检查，再运行

1. 记录Mac芯片、物理内存、可用磁盘、macOS、Docker/原生Python和Node版本。活动PostgreSQL、Redis、Meilisearch数据与模型缓存放Mac本地磁盘；NAS文件挂载断开时应停止文件操作，不能误用同名空目录。
2. API环境沿api/Dockerfile和api/requirements.txt构建。当前Dockerfile为Python3.12；Windows本轮验证环境为Python3.14.6，不能据此称ARM镜像或Mac依赖安装通过。Web沿package.json和锁文件，不能直接拷贝Windows的node_modules或.venv。
3. 先恢复一个隔离数据库，绑定隔离队列/索引和内网端口；API未就绪前不开beat/重型worker。明确当前使用哪一个数据库，不使用省略连接配置的默认SQLite冒充恢复验证。
4. 在配置到该隔离数据库的API容器或虚拟环境中执行：

```sh
python manage.py inspect_knowledge_runtime
python manage.py migrate --plan
python manage.py makemigrations --check --dry-run --noinput
```

`inspect_knowledge_runtime`只读取迁移、依赖和运行元数据，不显示密钥/原文，不调用模型、不调度任务。它会区分缺迁移、缺worker依赖和当前产物回执；不能代替网络、文件或模型实测。API不必安装DocETL/Docling；缺少它们只说明相应计算环境尚未就绪。

5. 有隔离恢复点后，再在该隔离库执行`python manage.py migrate --noinput`，设置明确的PostgreSQL锁/语句超时。0103给run增加plan_version，历史记录为1，新建任务为2；0104给订阅增加next_refresh_at/refresh_failures，支持接续退避。不批量分析、不删除旧产物。已在本机隔离PostgreSQL 16.15验证旧记录保留与实际备份恢复，见POSTGRES_REHEARSAL_20261114.md；正式备份与Mac/ARM仍须各自核验。
6. 运行单run只读报告，例如：

```sh
python manage.py inspect_knowledge_runtime --run-id c8e1f792-68e4-42f0-8527-28045f535b63
```

报告中的已知模型调用、未知调用次数、代理响应、复用产物、已记录耗时分别统计。回执当前值不是历史全部尝试账单，代理未采集时间不能计为0。

## 本轮执行计划优化

plan_version=1保留旧窗口fold与单patch协议；新建run采用2。相同原文窗口的分析仍可复用，不改变全局分析prompt来强制清缓存。新增计划：

- 按实际章节节点ID归组，完整窗口产物在真实输入预算内合批，顺序及全部源产物哈希保存。同名章标题不是身份键。
- 章内产物不依赖前文全书综合，修改前章时可复用未变化后章；全书fold仍按顺序读取，保留前序结果哈希。长章仍按预算切分，绝不以抽样代替完整阅读。
- 同一目标页面一批可返回最多8个局部patch，完整陈述覆盖清单和每项证据仍校验，重复修改同一块拒绝。人工保护、基准哈希、ChangeSet和发布路径不变。
- Provider、代理提交和远程完成使用同一覆盖/证据校验。预算共用AIClient的严格请求构造，包含系统指令、JSON/schema、UTF-8上界及预留输出，未调用模型前即拒绝超限。
- 当前仍一个重型执行名额，不为了减少耗时直接打开跨进程并发。后续并发调整须根据实际Provider容量、在线体验和Mac测量。
- v2新增stage1/windows范围计划，包含偏移/节点身份而不重复保存整书正文；部分分析恢复也复用原切窗，仍逐次验证快照。已有三书v1产物不强制转换。
- 在线推理共享预算DISCOVERY_QUERY_INFERENCE_BUDGET_SECONDS默认8秒；这是可选模型准入和请求超时预算，不能当全搜索耗时保证。图权限批量检查、原检索会话诊断、0104自动接续及实际测试见RUNTIME_OPTIMIZATION_20261114.md。
- 后续增加订阅skip_locked和正文结构任务的原ProcessingJob恢复接入。部署时同步更新恢复worker与源任务worker；消息携带原job/task_id，队列暂停不会被此源码提交自行解除。真实数据库/引擎检查见POSTGRES_REHEARSAL_20261114.md。
- 索引每次任务/代际/来源归属检查合并为带Exists查询，仍实时核对出版版本及权限；每次4→2条SQL。两书缓存原文的索引与定位记录只证明本机限定关键词路径，不是任意观点质量或全馆时延承诺。

Gunicorn配置新增worker_abort调用栈诊断，只打印线程栈，不打印请求正文或局部变量。启动API时须沿`--config python:config.gunicorn`加载；旧候选命令未加载此配置，不能宣称已经捕获旧超时根因。

## 到货后的最小验证与剩余事项

- 先验证旧URL/账号权限/原PDF/历史跨页锚点/关键词检索；随后打开三书原待审记录核对数量与固定修订。
- 用同一短章分别测已配置本地模型的完整输入、输出、耗时、错误和资源；再测一部真实长书的新计划。单元测试证明预算、恢复和权限规则，不证明解释质量或本地模型足够准确。
- 分别记录OCR、索引写入、生成、数据库等待及排队。当前NAS候选RAG曾48.923秒且出现Gunicorn超时；新结构索引未补齐，未宣称性能问题已解决。
- 新版计划的实际语义质量须与旧三书分析对照；禁止只按调用次数减少判定优化成功。
- 正式数据与候选成果先独立保留。最终知识成果迁入正式库须核对作品/版本/修订身份与原文哈希，沿原映射和审核服务迁入，不盲目导入候选整表覆盖正式人工变更。
- 统一管理应用可复用现有应用服务和此只读报告，未来可增加运行参数及受控操作；不建立第二套任务、知识写入或密钥数据库。新增架构需明确任务与性能依据，当前不预装未经确定的系统。

本机定向检查入口（在api目录，使用隔离测试配置）：

```sh
DATABASE_URL='sqlite:///:memory:' DJANGO_DEBUG=true python -m pytest \
  tests/test_compilation_plan.py tests/test_continuous_wiki.py \
  tests/test_intelligence_evolution.py tests/test_intelligence_remote.py \
  tests/test_ai_client.py -q --tb=short
```

继续开发前先核对CURRENT_PROGRESS最新状态，保护未提交修改；部署、验证与实现分别记录，不把本文件当作已经完成Mac迁移的证明。
