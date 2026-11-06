# STL 架构演示 v5

## 2026-11-07 追加：总览卡片直接进入

ARCHITECTURE-SHOWCASE-07 D。用户要求只取消全站总览的模拟鼠标。已删除该场景专用指针、点击波纹和对应样式。聚焦阶段改为卡片直接缓动移入，550ms 完成位置转换，700ms 后接续详情的 450ms 显现。保留 8 秒详情停留、返回全图、点击延时和手动控制。其他场景不变，三条使用演示的指针、点击、输入及反馈代码与前版一致。

内部/公开构建、129 项自动展示检查均退出 0。额外浏览器检查捕捉到卡片移动前、中、后的不同变换矩阵，证实存在连续过渡。全屏、减少动态效果及三条流程的点击波纹均实际核对。首次点击波纹检查采样早于波纹时段，改为按各步骤真实时长的 40% 取样后通过；产品代码未因此调整。

公开版源站位于 `/volume2/library/stl-previews/architecture-showcase-v5-smooth-20261107`。216 个运行文件哈希与本机一致，容器 healthy，隧道网络 HTTP 200。仅重建独立展示容器，原 edge/cloudflared 的身份、镜像、启动时间和重启次数保持。首轮解包遇到 NAS Python 不支持 `filter` 参数，在写入成品和更新容器前退出；改为检查清单、路径及哈希后逐文件写入，未删除旧目录。初次健康检查尚未就绪，等待实际 healthy 后复核通过。

原 v5 发布目录、镜像和本机 ZIP 保留。当前镜像为 `sha256:dba23b612fa392b157051cc53563770922b6fd9e60816641e8df0bc9dad5ae27`。本轮未更改 DNS、隧道映射或书库业务，未复核公网。当前 5198 预览已刷新。

新产物在 `output/playwright/architecture-showcase-v5-smooth/`，包含总览实际截图、14 张 4K PNG、289.6 秒 1080p 完整循环视频、内部离线包和公开包。新版与原 v5 离线包均通过 CRC 检查。验证记录为 `auto-verification.json`、`motion-verification.json`、`deployment-proof.json`。上一轮其余检查与原成品保持，不重复认定为本轮全站验收。

以下保留 v5 首版记录，其中鼠标点击总览的描述已由本次批注替代。

ARCHITECTURE-SHOWCASE-06 D（实现关闭）。依据用户两张截图，修改独立展示的总览动画、网站页面卡片及底部控制区。沿用此前自动循环、点击延时、公开版去除内部信息的决定。

## 展示变化

全站总览依次呈现发现与检索、知识与策划、阅读与引用、私人研究、馆藏与内容管理、系统与权限。每个模块经历指针点击、聚焦展开、返回全图三个阶段，随后进入下一模块。开场与收尾显示完整架构，共 20 个阶段。展开时显示该模块已有的子模块、一个实际使用入口和权限说明。自动展开不会抢走键盘焦点。

点击刷新当前停留时间，动画继续向前；悬停、移动鼠标与滚动不延时。关闭详情或点击“返回全局”后回到全图，接续下一模块，不跳过余下总览。手动点击节点仍可查看完整详情。

“页面地图”改名为“网站页面”。浏览书库、发现与阅读、私人研究、管理工作区分别放在四张完整边框卡片内。先呈现全部卡片，再逐张以砂金边框、白色背景和轻微上移突出显示，最后回到卡片总览。内部版的路径仍可通过详情和证据索引查看，不再挤占卡片。

底部长进度条、时间读数和短停留条已删除。保留阶段选择、上一阶段、下一阶段、暂停、重播、返回全局和全屏。自动展示与点击延时继续生效。

`overview-tour.json` 独立记录模块顺序、说明和时长。`scenes.ts` 生成阶段，`app.tsx` 负责镜头、指针和详情。未新增依赖。沿用 2026-11-06 架构数据快照及 38 步使用演示，本轮未重新审计或验收 STL 业务。

## 修正与验证

初轮检查发现私人研究和系统详情出现竖向溢出，调整为三列子模块与紧凑说明后通过。网站卡片内的路径文字影响完整边框排版，移回原详情入口。修复“返回全局”跳过后续模块的问题，并验证继续进入下一模块。最终截图等待切场淡入结束后重新截取。

以下命令均在本机独立展示运行，退出码为 0。

| 命令或检查 | 结果 |
| --- | --- |
| `node web/architecture-showcase/build.mjs` 及 `--public` | 内部版与公开版构建完成 |
| `node web/architecture-showcase/verify.mjs` | 29 项通过 |
| `node web/architecture-showcase/verify-journeys.mjs` | 250 项通过 |
| `node web/architecture-showcase/verify-auto.mjs` | 122 项通过 |
| `node web/architecture-showcase/export-assets.mjs` | 14 张 3840×2160 PNG、1 个独立 SVG |
| `node web/architecture-showcase/record.mjs` | 293.92 秒、1920×1080 WebM，解码检查通过 |
| 公开版全屏复核 | 实际进入全屏，无底部进度条 |
| STC 界面复核 | 0 错误、6 个警告，经语义复核保留 |

401 项检查覆盖六个模块的点击、展开、返回和继续，以及详情排版和点击延时。检查也覆盖四卡片依次突出、38 步顺序、减少动态效果、键盘和全屏。四档桌面视口及公开信息边界均已检查。未发现展示脚本异常或外部业务请求。STC 提示的“相关性排序”和“已实现”保留实际名称。“下一部分”指紧随当前步骤的模块；示例说明继续保留。无待处理的文案回声判断。

结果只证明展示应用的行为与布局。本轮未运行真实检索、入库、发布、OCR 或私人资料写入，未重新判定业务完成状态。

## 部署与恢复

仅更新原独立容器 `stl-architecture-showcase`。发布目录为 `/volume2/library/stl-previews/architecture-showcase-v5-20261107`，镜像为 `stl-architecture-showcase:v5-20261107`，镜像 SHA-256 为 `8314811e973672c6031229d78213c5ac6837d7fa116ab522fb135d74cc28e4a8`。

容器健康，无业务挂载或宿主机端口，仍使用只读文件系统和非 root 用户。216 个运行文件的 SHA-256 与本机公开成品一致。隧道网络携带 `Host: preview.winstonmo.com` 访问源站返回 200；首页、JS 和公开 JSON 返回 200，证据 CSV、管理路径和服务器源码返回 404。公开版不包含源码索引、内部路径或接口明细。

原 edge 与 cloudflared 的容器 ID、镜像和重启次数保持。v4 发布目录、镜像及本机原包保留，新目录保存 `rollback.json`。恢复时在 v4 目录运行同一 Compose 项目的启动命令。未修改书库业务、数据库或生产候选。

用户继续自行接入域名。本轮未修改 DNS 或隧道映射，未复核公网 TLS、DNS 或域名访问。源站仍为 `http://stl-architecture-showcase:5196`。详见 [域名接入说明](../../web/architecture-showcase/DOMAIN_SETUP.md)。

## 交付文件

产物均在 `output/playwright/architecture-showcase-v5/`：

- `overview-auto-detail-1920.png`：总览进入模块后的实际画面。
- `website-cards-1920.png`、`public-fullscreen-1920.png`：网站页面卡片与公开版全屏。
- `4k/`：14 张 PPT 图片与 SVG。
- `video/STL-architecture-v5-1080p.webm`：无人点击的一整轮自动展示。
- `verification.json`、`journey-verification.json`、`auto-verification.json`：独立展示检查记录。
- `deployment-proof.json`：源站状态、HTTP 结果与文件一致性记录。
- `STL-architecture-v5-local-20261107.zip`：内部离线成品、源码、图片与视频。
- `STL-architecture-v5-public-20261107.tar.gz`：公开成品与部署文件。

本机公开预览为 `http://127.0.0.1:5198/`，完整溯源版为 `http://127.0.0.1:5196/`。当前预览标签页已刷新。内部 ZIP 不作为公开下载包。新版 ZIP 与 v4 备份的 CRC 检查通过，公开包 219 个文件与清单哈希一致。v4 与更早备份保持，本轮仅形成本项 Git 检查点，不推送，继承修改保留。
