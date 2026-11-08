# 公网视效遗漏清点与统一候选

## 当前结论

本轮从用户的组织新制度主义截图追溯实际页面，确认两类源码遗漏：公开页面与管理预览使用不同渲染分支；统一样式依赖路由白名单，未覆盖部分二级入口。已完成源码修正、本机构建、NAS 内网候选和代表状态实看。**公网仍为 readable-r4，本轮候选尚未替换正式 Web。**

候选入口为 `http://192.168.5.6:18084`，共用现有 API、数据库和权限。没有新建业务副本、改写知识内容、提交策展表单或执行数据迁移。浏览器曾临时切换大字号检查分享页，随后恢复舒适、白昼、无衬线。受保护预览继续保留鉴权、草稿版本核对、inert 和静态读者操作。

## 根因与实际修正

| 编号 | 直接证据、触发条件及影响 | 最小修正与状态 |
| --- | --- | --- |
| VIS-01 | `KnowledgeNodePublicView` 默认 `publicDesign=false`；正式理论路由传 true，`PreviewSurface` 未传。公网管理预览可重现用户截图的灰色几何图、旧信息表及重复卡片，正式理论页已经采用新版。 | 删除旧渲染分支，管理预览和正式总览/二级页共用 `TheoryDetailPublicView`。恢复理论栏目的定位标记；预览不挂载真实收藏/分享状态读取。开发 D，真实总览、证据及时间线预览已实看。 |
| VIS-02 | `RouteTransition` 的 `atlasRoute` 白名单漏掉学科详情、旧 theory-schools 路径、部分账号页及激活入口。新增页面需要人为补名单，容易继续遗漏。 | 全部路由统一 `data-ui-scope="stl4"`，保留各组件自己的主题与交互。152 个页面模板及一个未来二级路径的行为检查通过。开发 D；不是152页逐状态视觉验收。 |
| VIS-03 | 三个学科详情仍由 v307 旧布局渲染。公网社会学页实际出现重复配图、较重卡片和标题/内容密度不一致。 | 学科页采用统一白色内容层、细线导航和内容分组，保留查询参数、真实计数、公开条目和自定义媒体。缺图时复用已授权的 20261030 配图，不重绘品牌或伪造人物照片。桌面/390px 已实看，三学科入口 HTTP 正常。开发 D。 |
| VIS-04 | `/theory-schools/graph` 和旧实体二级页仍沿旧展示；空图谱保留大幅空画布。 | 图谱共用 `KnowledgeMapHero`，二级内容使用统一容器和页脚；真实无数据时呈现空状态。保留旧实体数据与规范映射，不猜测重定向。390px 空图谱已实看；无真实旧实体详情保留 B。 |
| VIS-05 | 独立预览 `SiteHeader preview` 一律按首页呈现，不能反映对象页面的导航与标题区。 | 预览传入仅用于展示的逻辑路径，继续复用 `BrandImage`。页头/页脚沿用批准的黑金符号与中英文名称。开发 D。 |

本轮没有发现需要重新设计 Logo 的证据。现有共享品牌使用 `/brand/stl-symbol-20261027.svg#mark`。此次修复的是漏接组件和旧渲染入口。

另一个实际入口 `PreviewViewport` 在 `fixed-page-editor.tsx` 的 srcDoc 中写死 editorial-v2，外层路由无法影响 iframe 内部。已将该根容器统一为 stl4/expressive。实际读回又证实iframe缺少 `data-typeset` / `data-typeface` 和 `#main-content`，字体规则无法命中；补齐排版标记的复制/监听及语义容器，并增加直接检查隔离文档的渲染测试。最终浏览器读回iframe内部为 stl4/expressive、typeset=A、typeface=balanced，正文计算字体为 STL Text Sans，旧几何图为0；1120px实际画面已保存。未被任何页面引用的 `RandomRecommendation`/`ArchitecturalImage` 保留为历史代码，不把它计为已上线遗漏。

## 清点范围与计数

- `VISUAL_ROUTE_COVERAGE_20261108.csv`：152 个 `page.tsx` 模板，管理77、读者24、其他51。逐项保存路径、源码、路由行为检查、实际发现的地址及剩余验证边界。
- `VISUAL_RUNTIME_COVERAGE_20261108.csv`：由静态入口与实际渲染链接发现137个地址。基线及候选均133个200，4个404。4个均为 `/layout-preview` 指向的 `layout-example-*` 示例详情，不是已发布策划或馆藏。
- 基线133个正常地址中122个 stl4、11个 editorial-v2；候选133个均 stl4。11个包含欢迎与演示入口，**旧 scope 本身不等于11个可见缺陷**；必须修复项以本表的直接源码和画面证据为准。
- 基线3个学科页存在 `architectural-image` 几何兜底；候选发现数0。该检测覆盖返回的 HTML，不代表所有私人记录和懒加载状态均已检查。
- 批量只读 GET 使用同部署的 NAS 18084：工具直接请求公网 HTTPS 被入口返回403；真实公网 HTTPS 的理论页、截图对应管理预览和学科页由已登录 Edge 实看。二者不混报。
- 管理、读者、阅读器、分享令牌等受保护或记录相关地址不伪造ID抓取；源码入口覆盖，按现有登录和真实记录补充代表状态。政策研究继续排除。

## 视觉依据与证据

遵循最终图集、20261027品牌板及后续文字可读性决定。实际读取理论详情参考 `output/visual-review-20261013/01-reader/R15/R15-sub02.png` 和学科相关参考 `output/visual-revisions-20261015/NEW-T02-v6.png`，与真实页面对照。

截图均保存在本机忽略目录 `tmp/stl4-visual-coverage-20261108/`，不提交账号或私人页面截图：

| 画面 | 文件与范围 |
| --- | --- |
| 公网学科页旧版 | `public-discipline-before.png` |
| 学科页最终候选 | `final-discipline-desktop.png`；`discipline-390.png`（r1，r2仅修正桌面首图高度） |
| 理论管理预览总览 | `final-theory-preview-desktop.png`；`candidate-theory-preview-390.png` |
| 编辑器内嵌预览 | `final-embedded-preview.png`（布局初核）；最终字体复核另存 `final-embedded-preview-type.png` |
| 理论管理预览证据页 | `final-theory-evidence-preview.png`，真实无公开定位原文状态 |
| 理论时间线预览 | `timeline-preview-390.png`，真实空态 |
| 旧图谱入口 | `final-legacy-graph-390.png`，空态 |
| 欢迎入口 | `final-welcome-desktop.png` |
| 分享入口 | `sharing-320.png`、`final-sharing-320-large.png`，真实空记录，320px大号未再被750px容器裁切 |

已实现待验收 B：没有真实记录的旧实体详情、私人研究结果、分享详情、全部弹窗/权限/分页状态，以及未逐页截图的管理页面。它们不因本轮入口清点而宣称通过，也不据此重复开发。上一轮 r9 的策展导语计数等未复核状态继续保留原记录。

## 检查与候选运行

- `node --import tsx --test tests/public-visual-coverage-20261108.test.mjs tests/brand-config-20261027.test.mjs`：退出0，5项通过。验证路由统一、预览/正式数据一致、预览不挂载真实账号操作、品牌及缺图行为。
- 工作区 `node node_modules/typescript/bin/tsc --noEmit --incremental false`：退出0。隔离快照单独 tsc 曾因历史快照缺少 `c-preview/bridge.mjs` 失败，随后使用完整工作区核验；不将该失败隐去。
- 独立快照 `node node_modules/vinext/dist/cli.js build`：r1至最终r4均退出0。构建在本机执行，不在 NAS 执行 npm/Vinext/Docker 构建。
- 修改范围 `git diff --check`：退出0。Impeccable `detect --json` 对首批18份修改源文件执行一次，返回空发现数组。机械检查不作为设计获奖或全站验收证明。
- 沿用 r9 已准备的字体/工作区 CSS 基线，加本轮19份源码；没有带入同工作区其他未完成后端、读取器或媒体任务修改。原有暂存文件保持。
- 最终归档 `tmp/stl4-visual-coverage-20261108/visual-coverage-r4.tar.gz`，46,075,142字节，SHA256 `04c522c2389948323bb019ce63bc5fd2f3bf2166c06ccb63f68dc700de016dd9`。
- NAS 候选 `stl-visual-coverage-r4-20261108` / `b5524b44b049`，使用正式 Web 基础镜像和只读编译产物，768MiB内存上限、restart=no。r1/r2/r3已停止，失败启动容器保留退出状态。1,841运行文件与本地产物一致，唯一差异为沿用正式环境的 `client/runtime-config.js`。
- 137地址批量读回针对r1；r2仅增加桌面首图尺寸和两处图谱空态，r3补齐iframe根样式、r4同步字体作用域；针对更改的真实页面再复核，不重复全站抓取。

## 发布与恢复边界

公网仍为 `social-theory-library-web:4.0.0-20261107-readable-r4`，Web `016743aff243`；默认 upstream 仍 `web:3000`。仅 LAN Host 映射至候选。r4启动后核对15个既有运行服务的容器ID和启动时间均未变化。

候选目录 `/volume2/library/stl-previews/visual-coverage-20261108/r4`；r1目录的 `edge-recovery` 保留候选前正式路由，r2/r3/r4的 `edge-recovery` 分别保留上一候选路由。恢复时仅对照并恢复这一条 LAN Host 映射，经 `nginx -t` 后 reload，再停止本轮候选；不能覆盖随后发生的其他配置变化，也不用重建数据库或重启API。

正式发布需要按 AGENTS.md 的“生产、DNS和隧道切换仍须最终批准”取得针对本候选的最终确认。批准后只更新 Web 编译产物/正式服务和相应代理目标，保留当前正式 Web 镜像及配置恢复入口，继续核对其他服务不变并实看公网。不要使用旧 r9 在NAS构建脚本或全量 compose up。
