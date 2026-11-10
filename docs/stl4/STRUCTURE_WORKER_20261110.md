# 内网正文结构执行器

仅用于当前内网候选，不改变正式数据库、DNS、Cloudflare Tunnel 或公网路由。结构解析不使用生成模型，不替代 Intelligence 的 OpenAI-compatible Provider 配置。

## 当前运行方式

- 候选 API：NAS `192.168.5.6:18091`，数据库 `stl_intelligence_demo_20261109`。
- 执行器入口：`https://192.168.5.6:18491/api/capability-worker`。Nginx 仅绑定该内网 IP，仅代理此路由，其他路径返回404；配置见 `deploy/nginx/knowledge-worker-demo.conf`。
- Windows 节点：`stl-demo-windows-structure`，仅声明 `document_parse` / `document_structure`，并发1。模型目录使用已安装的 Docling 本地工件，OCR关闭，标题层级明确开启。依赖固定 Docling2.149.0；API/beat 不加载解析模型。
- HTTPS 信任文件通过既有 SSH 传输并核对 SHA256。客户端使用标准证书及主机名校验，没有关闭验证或向系统信任库安装证书。当前自签证书有效90天，替换时同步服务端证书与执行器的信任文件。
- 执行器令牌来自候选原配置体系，保存在被忽略的本地权限受限文件。它不等于读者身份、MCP权限或模型密钥。不要复制到聊天、Git 或日志。

```powershell
./scripts/start_knowledge_structure_demo.ps1 `
  -PythonPath './tmp/worker-env/Scripts/python.exe' `
  -ModelsPath './tmp/docling-models' `
  -WorkerTokenFile './tmp/structure-worker/executor-token.txt' `
  -ServerCertificate './tmp/structure-worker/server.crt' `
  -ParserPackageRoot 'C:/Users/12297/.cache/stl-structure-worker'
```

`ParserPackageRoot` 是本机原生解析器的路径兼容选项，不是新依赖来源。当前中文工作区中的 docling_parse 无法打开字体资源；英文路径副本与已安装包506个文件逐一哈希相同。英文路径安装的完整worker环境可省略此参数。启动脚本只读取凭据，隐藏启动进程，记录PID及标准输出/错误；重复启动前拒绝覆盖仍存活的PID。尚未配置 Windows 开机自启。

## 失败与恢复

领取、文件传输、租约续期、来源修订核对和完成回执复用原远程协议。解析失败同步到ProcessingJob，保留错误及旧任务；暂时性失败最多自动尝试3次，非重试错误立即失败。管理台“恢复这一范围”调用原处理任务服务，确定性创建替代任务，重复恢复复用同一任务。人工校正段落受保护，旧锚点不改绑。

本次实际暴露并修复了：Windows中文资源路径；租约失败但ProcessingJob仍显示运行；来源工作区恢复按钮传错旧任务source值。回归覆盖失败、重试上限、HTTP恢复、幂等、TLS验证及远程完成。没有把失败记录清除后重新标成成功。

## 真实操作记录

- 书籍《以利为利》，Edition `da2580bc-09e2-4306-ba0f-7be09852afc4`，DocumentRevision `ff54d2c0-3cf2-4a3b-8057-d284a72ef412`，PDF15–16。
- 浏览器创建失败任务 `4781d024-5ab2-4c7e-ab75-9c04feed0af7`。修复环境及状态同步后，浏览器恢复为 `92690347-3850-4142-9895-623535bec6c0`。
- 任务05:09:43 UTC创建、05:10:04领取、05:10:58完成；节点报告解析44,063ms，生成模型调用0。结束后Windows进程RSS采样约1642MiB，非峰值。
- 新结构 `0f3f4bd6-461a-498e-8b5e-65c7da17a31e`。PDF13–14的人工段落新结构副本保留 `human_corrected`，原内容哈希 `2d54b5a3028693e193282e6cf40812addab3fc6ec0f42625081f24a3c711d4ce` 不变；原节点与锚点保留。
- 解析累计34个映射条目，6个对齐缺口（本范围4个、之前2个），两个目录标题尚未唯一匹配。缺口原文保留，未制造坐标或推断整本结构已经可靠。
- 浏览器实际显示“最近范围 PDF15—16 · 结构已保存”。更新自动派发关键词任务 `626b4c17-d330-4e15-916b-28fed92f0bde`；此任务完成情况按最新进度记录。
- 上一人工结构关键词任务 `92f0b694-1fdb-4408-9f57-69b4256344e2` 已成功，1355投影/277正文单元，最后一次执行区间361.90秒（包含让出与排队，不代表完整首次总耗时）；生成/嵌入调用0。关键词与语义状态分开。

## 恢复安排

候选API前一容器 `stl-intelligence-demo-api-before-structure-20261110` 和 `demo.env.before-structure-20261110` 保留。前一索引worker `stl-intelligence-demo-worker-before-index-20261110` 保留。恢复旧API前先停止本任务Windows执行器和候选TLS代理，再在候选目录恢复原环境与容器名；不得影响正式容器、正式卷或全量清空Redis。证书、令牌、模型及运行日志均不入Git。
