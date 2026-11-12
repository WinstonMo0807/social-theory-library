# 公网 MCP、安全修复与独立推送

日期：2026-11-12，北京时间。用户最新明确开启公网MCP，覆盖此前只接本机、不开放公网的限制。D：本次单用户公网入口和定向安全验证完成；不代表全站验收或多用户OAuth上线。

## 已部署能力

入口为 `https://books.winstonmo.com/mcp`，Streamable HTTP，必须携带本机加密保管的随机Bearer令牌。无令牌访问返回401是正常保护行为。七工具及原策展清单保持，批量读取、查重、当前正文取证、准备差异、草稿保存、逐项回执与续做均复用原领域服务。MCP不能发布、删除、合并、恢复、改人工锁或启动OCR/索引。写入范围仍限原三部测试文献；查询可读馆藏/规范实体，私人研究笔记不接入，全文只允许当前有效public/registered文件。

本机Codex的`stl`已改为HTTPS和`http_headers_helper`，CLI读取配置确认Streamable HTTP且enabled。原SSH stdio保留为disabled的`stl_local`。令牌仅存在Windows当前用户的DPAPI密文文件，Codex配置无明文；NAS认证文件只存SHA-256和绝对到期时间。初始期限30天，到期须由运维续期或轮换，不自动延期。现有聊天是否热更新工具未观察，需要新聊天或应用重载。本次真实工具连通证据来自SDK HTTP与stdio客户端，不把配置注册当作工具调用证据。

原本机三份不可变计划已校验digest和作品范围后导入NAS journal，保存前NAS journal已备份。公网真实查询确认三份计划、六项原始回执均可恢复；没有调用save、创建重复业务草稿或改写原请求ID。此后公网新计划存NAS持久目录，本机备用服务的journal不自动双向同步。

## 安全审查与已修复问题

在合成数据中先重现失败，再修复并复测：

| 具体问题 | 修复边界 |
| --- | --- |
| Work的bibliography嵌套包装可绕过publisher等字段锁 | 将实际编辑版本和包装字段展开，按正式字段契约检查原锁 |
| Edition编辑传入同Work另一个Edition可借其无锁状态 | 编辑目标、提示版本及包装版本必须相符 |
| Work贡献者包装未与已有作者列表比较，可隐式移除作者 | 使用该版本真实贡献者快照，保存整组时保留原成员 |
| Topic等关系集合遗漏在保留规则外，可清空原关系 | 补入实际集合名，递归检查同一成员下的嵌套集合 |
| 旧ScholarRelation可先换端点再进入授权作品范围 | 旧端点归属和新端点归属分别校验 |
| evidence_curation可引用private/restricted原文并在保存回执回显 | 新引用重核文件访问、正文修订、当前文件哈希及有效定位 |
| 历史策展/回执中的来源撤回后仍可能回显旧文本 | 所有命令输出统一重核EvidenceSpan；保留引用身份，撤回不可访问原文 |

沿用逐项事务、目标行锁、预期版本、请求指纹及AuditEvent原回执；机器操作保留`human_reviewed=false`。固定账户能力和token_version逐次重核。未知命令、正式状态、跨作品目标和隐式集合删除继续拒绝。原文中的指令只作资料。

HTTP认证在协议解析前完成，比较令牌摘要，拒绝重复敏感头、非白名单Host/Origin、过大请求与超额并发。SDK另限制chunked正文，禁用访问日志，Nginx只为MCP增加独立限速/连接限制，清掉Cookie且响应不缓存。令牌读文件即时校验，可不重启撤销或轮换。多用户OAuth、动态客户端注册、ChatGPT网页端接入没有在本轮实现。

独立MCP环境按2026-11-12 OSV版本查询检查30个安装分发包，发现pip 26.1.2的GHSA-qwm4-qh6w-59xr后仅更新MCP虚拟环境的pip到26.3。复查30包无已报告命中。Linux固定28个运行依赖，没有把pip打包到NAS。这是该时点数据库的版本检查，不等于完整供应链证明或既有Django系统全部依赖审计。

## 部署和恢复

NAS新增`stl-mcp`，复用当时API镜像`sha256:0755ac503acf302ec469b142f7c57cdaef64663e8f908056a15e3d33b6b9859f`。电脑准备963文件、约9.3MB压缩包，传输及每文件哈希核对后解包；NAS未构建/安装依赖。代码与配置只读，无宿主端口，只有原backend网络，经现有Cloudflare HTTPS和Nginx代理。384MiB、0.5CPU、96进程、只读根、cap-drop、禁止提权；不挂载Docker socket、模型、备份或私人文件目录，不在进程内加载OCR/模型。

release为 `/volume2/library/stl-releases/20261112-mcp-public-r1`，配置/计划为 `/volume2/library/stl-mcp`。配置和计划目录700，配置文件600；数据库环境仅在NAS转入root受限文件。认证摘要、env、journal、原代理编译配置均不入Git。

原Nginx模板SHA-256：`c55c4fbdd3ff67b3a4ca850e0a4d9ffd21536acd531256bf39fc327aa3e94ade`。增加MCP后：`b28d549510873df2d11ba57ba06f8b6f7ef6f468a53db7095a908117d279834e`。仅原位写入模板、生成配置、`nginx -t`并reload；原21个运行服务的容器ID、镜像及启动时间核对完全一致。DNS/Tunnel未改，数据库未迁移，未运行OCR/索引，也未更换原API/Web/worker。

原模板、编译配置、服务清单和候选哈希保存在该release的受限文件内，原模板备份哈希已核对。回退命令为 `sudo -n python3 /volume2/library/stl-releases/20261112-mcp-public-r1/deploy.py rollback /volume2/library/stl-releases/20261112-mcp-public-r1`。脚本遇并发模板修改将拒绝覆盖。需要快速撤销可先禁用NAS认证文件或令牌，再撤回路径；保留服务与journal调查。没有通过线上回滚演练中断新入口，恢复依据是原文件备份、哈希及脚本检查。

## 实际验证

- 29项Django领域/安全检查通过，其中8项为本轮实际漏洞回归；使用隔离SQLite，不能替代PostgreSQL并发压测。
- 7项HTTP认证/Host/Origin/重复头/请求边界/并发/到期与热轮换检查、1项journal跨进程身份检查通过，共37项。
- 本机原stdio的auto/legacy协议、工具列表和真实馆藏查询复测通过，分别5.394/4.268秒。
- 接公网前，容器内真实HTTP两种协议、七工具及三书上下文通过，10.271秒。
- 公网HTTPS无令牌401、错误令牌401、错误Origin403；两种协议的七工具、三书搜索与批量上下文通过，23.748秒。
- 公网另查三计划六回执、批量人物查重、三书指定页原文；非授权作品及发布状态prepare均拒绝，无计划ID、无业务保存。
- 本轮公网验证没有重新写入六项引用。原三书19.763秒为已有馆藏维护的结构化执行时间，审读在计时前；不能称从零整书策展耗时，也未测得token节省比例。
- 推送用独立worktree从`origin/main`的`2f151a86`建立，仅移入MCP修改；在该干净主线代码上重新建立隔离SQLite，29项领域/安全和8项HTTP/journal检查全部通过。推送差异27个文件另查凭据模式无命中，部署的四个运行源码与本轮提交文件逐字节一致。该模式检查不取代人工审查。

保护目录 `.local/stl-mcp/public-build`保存public-probe、resume-security-probe、deployment-check等原始报告；未提交。Git使用基于当前main的独立 `codex/stl-mcp-security-20261112` 分支，仅含本机MCP和本轮安全/公网交付。没有将工作区其他未提交源码、设计或馆藏资料一并推送，也没有合并main。

## 后续实际边界

B：新聊天中的工具热加载尚未观察；新书从空白全流程策展和视觉Agent同任务对照耗时未测，不能由接口测试替代。C：多用户OAuth及更多作品写入范围按明确使用需求另行配置；本轮入口是本人的受保护单用户接口。没有减少原策展内容，未覆盖的新建文章/版位等仍沿原工作区完成并在清单明确保留，不把保存草稿称为完整学术审核。
