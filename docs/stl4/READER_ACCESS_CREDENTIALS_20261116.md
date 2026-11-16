# 57 本书阅读访问与长期维护凭据（2026-11-16）

## 授权与根因

用户授权在取消前长期保留 NAS、GitHub、书库 MCP 的维护凭据，并从 Winston 绑定的 MCP 服务开始排查 57 本书无法在线阅读的问题。没有改变文件公开范围、账号权限或执行索引/并发压测。

经真实 MCP initialize、tools/list、stl_get_curation_context 分批核对，57/57 本书均已有 ready、valid 的阅读文件。现网 Web 构建遗漏了源码中已恢复的作品详情登录传递：loadWork 未传 forwardSession，导致注册读者文件按匿名身份序列化，前端又统一提示“暂无公开文件”。部署前实测已复现：同一已登录身份 API 提供文件、PDF 返回 206，但详情页没有阅读按钮。部分已公开文件不受此登录故障影响。

## 实施

- 仅向既有 production Web 基线补入作品详情 page 和 catalog.server 的历史登录传递修复，以及准确的未登录提示。有效登录会话继续使用既定读取权限；过期 401 仍可显示公共书目，服务错误不伪装成无文件。
- 登录续期完成后，WorkReaderSessionRefresh 在确有登录阅读限制时仅刷新一次服务端详情，避免要求读者手动刷新；匿名、临时错误、可读或仅书目的版本不触发额外刷新。
- MCP HTTP 网关支持最多 8 个独立摘要与显式有效期策略；旧单凭据配置兼容。仅 `persistent: true` 加 `expires_at: null` 表示无自动到期，缺失/错误配置拒绝认证。删除单项摘要即可撤销，无需重启。
- 原 MCP 客户端摘要保留并转长期；Mac 新凭据保存在系统钥匙串。Codex HTTP MCP 用本地 header helper 读取，未把明文密钥写入仓库、配置或日志。MCP actor 仍为 Winston，9 个工具和原业务约束保持。
- NAS 复用原 Winston SSH 密钥，并持久保存到用户 SSH 目录；GitHub 新建本仓库专用部署密钥，由用户在 GitHub 页面提交。已确认 Read/write、SSH 身份及仓库读取成功，推送使用专用 SSH host 别名。

## 验证与边界

MCP 9 项检查通过，覆盖旧有效期、逐客户端撤销和无效有效期拒绝。公网 initialize / tools/list / 一项真实 curation context 调用成功；不带凭据返回 401。旧客户端只核对摘要保留及网关规则，没有取得其 Windows 本机加密明文重放。

Web 初版 5 项契约检查、类型检查、生产构建及静态压缩预算通过。实际对 57 本书顺序请求已登录 API、详情 HTML 与 PDF 前 4096 字节：57/57 详情有开始阅读、57/57 PDF 返回 206 且具有 PDF 文件头。匿名注册读者版本显示登录提示，文件仍返回 401。公网该提示 200、no-store、Cloudflare DYNAMIC；ready 200。真实 Edge 打开《反思社会学导引》并看到 PDF 封面、516 页页码及目录。

这是文件与读取链路功能验收，并非逐页内容审读、全站验收、观点索引完成证明或 50 人并发容量结论。

## 发布与回退

首版于 2026-11-16 11:48:54 +08:00 发布，Web image `sha256:e142de99ea8c291adf2ad4914194b93a14b66a8c0c8cf9d46e48d65ce8f85728`，此前 image `sha256:d7603b1b2406a71e88635c9b6c1b3f1fc4d1b5f9434ebfa35d6fcd1b93d9062c`。3195 个构建文件逐字节一致，运行配置另与入口脚本输出核对，合计 3196 个文件。替换 Web 时其余 18 个运行容器保持。

MCP 仅修改既有只读挂载源码的 public_server.py 和认证摘要配置，并重启 stl-mcp。部署中发现新认证文件所有者错误导致进程无法读取，已恢复为服务 UID/GID 100:101、0600；部署脚本也已改为保留原所有者。后续认证与重启稳定性核对通过。

私有证据和脚本在本机 `migration/reader-access-20261116/`，不提交馆藏清单、凭据、运行日志或构建产物。Lima 回退备份位于 `/srv/stl/reader-access-20261116/`：Web 原 overlay 为 release-before-reader.compose.json；MCP 原 auth-before.json 和 public_server-before.py 成对恢复后重启，必须保留服务可读的文件所有者与 0600 权限。无数据库、原件、索引卷或账号迁移。

最终续期补充版本于 11:57:24 +08:00 发布：`social-science-library-web:reader-access-20261116-r2`，image `sha256:baef232d276346987ac75fb5a9171e57ac049e6031be3e34ea4f7f1a23b350a8`。7 项 Web 检查（包括续期后一次刷新、错误/匿名不刷新及防循环）、类型检查、生产构建、压缩预算均通过；3196 个运行文件与构建或入口脚本匹配。其余 18 个运行容器保持。该次回退 overlay 为 release-before-reader-r2.compose.json；完全回到任务前 Web 则用 release-before-reader.compose.json。自动续期分支通过组件和会话契约测试验证，没有为测试去强制修改生产浏览器的登录 Cookie。

最终版再次顺序验证全部 57 本：57/57 已登录详情存在阅读入口，57/57 PDF Range 为 206、4096 字节且文件头有效；匿名注册读者文件仍 401，详情显示登录提示。API healthy，Web/MCP running、重启计数为 0。

源码维护分支：`codex/reader-access-credentials-20261116`。GitHub 已验证同一部署密钥的仓库读取；本轮源码与文档提交通过该密钥推送，main 不做强制覆盖。
