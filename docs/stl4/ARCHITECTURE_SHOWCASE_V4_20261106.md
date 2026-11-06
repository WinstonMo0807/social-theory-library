# STL 架构演示 v4

ARCHITECTURE-SHOWCASE-05 D（实现关闭）。用户确定全场自动滑动展示，点击页面才刷新当前停留时间；随后选择 `preview.winstonmo.com` 公开访问脱敏版，并决定稍后自行配置 Cloudflare 域名路由。

## 展示行为

打开页面即从全站总览开始。5 个场景依次展开，其中使用演示连续呈现检索与引用 20 步、入库与发布 10 步、私人研究 8 步。末幕回到开场，不再在每条流程末尾停止。移除“播放流程”按钮，保留便于长时间阅读的暂停图标及空格快捷键。

动画进度与停留计时分开。点击重新计算当前步骤的停留时间，不回退输入、指针或模拟操作。悬停、移动鼠标与滚动不延时。详情停留至少 8 秒，期间点击可延时，到时收起并继续。场景与流程以 580ms 横向位移过渡。系统减少动态效果时关闭位移及指针动画，保留自动切换；后台标签页冻结计时。

沿用既有 5 幕、38 步、品牌和架构数据快照。本次没有重新审计或认证整站业务实现。输入、文献、页码及成功状态仍明确标为交互示例。

## 公开版

`build.mjs --public` 在数据打包前去除内部路径、源码索引、接口调用明细及证据下载入口。公开 JS 与 JSON 均不包含源码文件路径或管理入口。本机完整版保留全部溯源记录，继续使用 5196；公开版本机预览使用 5198。

公开版不连接业务 API、数据库或模型服务。构建时检查内部路径，发现残留即失败。公开包单独生成，本机完整版 ZIP 不作为公开下载文件。

NAS 发布目录为 `/volume2/library/stl-previews/architecture-showcase-v4-20261106`。独立容器 `stl-architecture-showcase` 使用只读镜像、非 root 用户，无数据挂载，无宿主机端口，复用现有 tunnel 网络。HTTP 源站为 `http://stl-architecture-showcase:5196`。

初次绑定静态目录时，NAS ACL 使 Node 无法读取文件，HTTP 返回 404。修正为将公开文件封装进镜像，避免依赖宿主目录 ACL。没有放宽书库目录权限。首个可用镜像保留为 `stl-architecture-showcase:v4-first-20261106`，最终镜像为 `sha256:af8350c687ffe0e27230de58143c406cccc4d8c53f442f23482e89f965422efd`。

现有生产 edge 与 cloudflared 的容器 ID、镜像及重启次数在更新前后相同。未修改现有书库路由、业务数据或生产发布候选。域名控制台未登录；用户决定稍后自行接入，DNS 与隧道映射均未更改。不能称 `preview.winstonmo.com` 已经可用。配置值与恢复步骤见 [域名接入说明](../../web/architecture-showcase/DOMAIN_SETUP.md)。

## 验证和产物

所有产物在 `output/playwright/architecture-showcase-v4/`，以下检查均限定独立展示：

| 检查 | 结果 |
| --- | --- |
| `node web/architecture-showcase/build.mjs` 及 `--public` | 退出 0 |
| `node web/architecture-showcase/verify.mjs` | 29 项通过 |
| `node web/architecture-showcase/verify-journeys.mjs` | 250 项通过 |
| `node web/architecture-showcase/verify-auto.mjs` | 62 项通过，含整轮顺序、点击计时、减少动态效果和公开包检查 |
| 公开版全屏 | 实际进入全屏，截图 `public-fullscreen-1920.png` |
| STC 界面复核 | 0 错误、4 警告；相关性排序、状态名称及示例提示均保留理由 |
| NAS 成品检查 | 216 个运行文件 SHA-256 与本机一致，容器 healthy |
| 隧道网络到源站 | 携带 `Host: preview.winstonmo.com` 返回 HTTP 200 |
| 公开静态入口 | 首页、JS、JSON 返回 200；证据 CSV、管理路径和服务器源码返回 404 |
| 图片与视频 | 11 张 3840×2160 PNG，225.8 秒 1920×1080 WebM，视频已解码检查 |

视频记录公开版无人点击的一整轮自动展示。界面检查覆盖布局、全屏、键盘、拖动、38 步反馈与来源，以及暂停续播。这些结果不构成真实检索、入库、发布或私人研究验收。

`STL-architecture-v4-local-20261106.zip` 保存完整版源码、离线成品、图片及视频。`STL-architecture-v4-public-20261106.tar.gz` 只保存公开成品与部署文件。包可通过 `package.py` 或 `package.py --public` 更新。

旧版 `output/playwright/architecture-showcase-v3/STL-architecture-v3-local-20261106.zip` 原样保留，CRC 检查通过，大小 47,662,632 字节。v1/v2 备份也保留。本轮仅提交展示源文件及本项记录，未推送仓库，其他线程的工作区修改继续保留。
