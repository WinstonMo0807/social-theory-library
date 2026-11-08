# Elicit 参考排版与溢出修正 · 2026-11-08

用户反馈上一候选排版仍不足，并要求继续参考 Elicit，修正字体溢出。本轮沿用上轮的公网入口清点，完成理论详情、学科目录和公开编排书目的共享组件重排。用户这次指令是相应布局的新依据；已有黑金品牌资产、数据、身份和发布边界继续保留。

## 参考与实现

实际查看 https://elicit.com/ 当前页面及其展示的 Library、研究问题界面图片，采用紧凑的无衬线层级、细分隔线、目录侧栏与纵向条目组织。不复制 Elicit 品牌、图片或色彩，不改变学术内容。

| 项目 | 直接证据与最终处理 | 状态 |
| --- | --- | --- |
| 理论详情阅读顺序 | 上一候选的大英文副标题、绝对定位操作栏、横向目录和两列空栏目影响阅读。操作移到面包屑旁的正常文档流；身份摘要与导读分列；正文采用左目录、右文档。核心观点置于空人物栏目之前，补齐形成与变化、原文依据、继续研究的目录入口。 | D，真实理论页已查看 |
| 字体与窄屏 | 长标题、按钮与嵌套 Grid/Flex 的固定尺寸存在溢出风险。使用可收缩列、正常换行、限定行宽，手机目录直接换行；译名表仍在自身容器滚动。保留当前浏览器字号/字体选择，不裁切正文。 | D，四档宽度及320px大号核验 |
| 学科目录 | 上一候选仍以较大图片卡片组织少量条目。改为小配图、完整标题、外文名、时期、核心问题的纵向列表；搜索与分类自然换行。共享三学科模板。 | D，社会学桌面/移动实看 |
| 公开编排书目 | 只有一两本书时，三列布局把说明挤在窄列，旁边空置。`PlacementList` 改为封面配纵向条目，来源链接随正文对齐。 | D，真实理论导读/经验研究联系已实看 |
| 子学科分类空列表 | 社会学显示“子学科9”，点开却为空。`TheoryDisciplineDetailView.build_payload` 的数量来自 `Subdiscipline`，列表按 `KnowledgeNode.node_type` 过滤，两者不是同一实体。前端入口改接已有 `/subdisciplines?discipline=...`，旧 `?type=subdiscipline` 地址重定向到该目录。无需增加实体或改生产数据库。 | D，旧地址实际抵达9条目录 |

本轮修改6份源码，未引入依赖。正式、独立预览和嵌入预览继续共用 `TheoryDetailPublicView`；本轮未重新逐态查看所有受保护预览。

## 实际核验

浏览器使用真实内网服务和公开记录。理论页为 `/theories/nodes/organizational-new-institutionalism`，学科页为 `/theories/disciplines/sociology`。

| 检查 | 结果 |
| --- | --- |
| 理论页1440 / 768 / 390 / 320px | 文档宽度分别1425 / 753 / 375 / 305px（滚动条占宽），scrollWidth等于clientWidth；检查的主要标题、段落、链接、按钮没有越出视口。 |
| 学科页同四档宽度 | 同上，无页面横向溢出；完整长英文名称正常换行。 |
| 理论页320px、大号 | 正文19px、主标题29.4px；按钮自动分行、英文名称完整换行，页面无横向溢出。 |
| 舒适字号 | 理论与学科主标题33px（桌面）/27.4px（窄屏），正文17px，计算字体为 STL Text Sans。理论页改前桌面标题44px。 |
| 目录 | 9个目标ID均存在，实际点击原文依据到达 `#sources`，目标顶部约140px，未被页头遮挡。 |
| 子学科兼容地址 | 最终候选访问旧分类地址，落到 `/subdisciplines?discipline=sociology`，实际显示9个公开子学科。 |
| 用户页面 | 已刷新原评审标签至最终候选，516px侧栏宽度下文档501px，无横向溢出。临时字号已恢复原“舒适”，临时尺寸已清除；临时参考/旧检查标签已关闭。 |

截图与运行日志在本机忽略目录 `tmp/stl4-elicit-layout-20261108/`，不提交截图、归档或运行配置。主截图 `theory-desktop.png`、`theory-320-large.png`、`discipline-desktop.png`、`discipline-390.png`、`placements-320-large.png`、`final-review.png`。首张390px理论截图遇到浏览器尺寸切换的截图异常，不用作视觉结论；后续320px和最终516px截图已实际查看。检查中浏览器连接短暂中断，使用新检查标签继续完成，不把中断当页面通过。

- 工作区 `node node_modules/typescript/bin/tsc --noEmit --incremental false`：最终退出0。
- `node --import tsx --test tests/public-visual-coverage-20261108.test.mjs tests/brand-config-20261027.test.mjs`：5项通过，退出0。验证既有品牌、公共/预览组件与隔离预览规则，不能替代全面交互验收。
- 本机隔离快照 `node node_modules/vinext/dist/cli.js build`：完整候选及子学科链接修正版均退出0。
- 任务文件 `git diff --check`：退出0。Impeccable layout/type修改前后扫描为空发现数组，机械扫描不等同设计验收。
- B：概念作者用法弹窗、全部译名表状态、其他学科的逐页截图和全站全部权限状态未在本轮重复验收。上轮152模板/137地址清点范围不扩大为本轮全站逐页视觉通过。

## 候选、发布与恢复

最终内网候选 `stl-elicit-layout-r2-20261108`，容器 `7a720639c62b`。NAS目录 `/volume2/library/stl-previews/elicit-layout-20261108/r2`，基于现有正式Web镜像，只读挂载编译产物，768MiB内存上限、restart=no。旧 visual-coverage-r4 和本轮r1均已停止；不在NAS构建。

本机归档 `tmp/stl4-elicit-layout-20261108/elicit-layout-r2.tar.gz`，46,069,576字节，SHA256 `221a3c69ef9b352d47eff7eb6213d34b54bbf0391e24f0cc9e5bd147f3a3720c`。1,839个运行文件与本地产物核对，唯一差异为复用正式环境的 `client/runtime-config.js`。r2切换时14个既有运行服务容器ID/启动时间不变；r1切换时为15个，按各次实际在运行服务记录，不宣称按需服务始终常驻。

只更新 LAN Host `192.168.5.6:18084` 的候选映射。公网默认upstream仍为 `web:3000`，正式Web仍 `016743aff243` / `social-theory-library-web:4.0.0-20261107-readable-r4`。未修改数据库、业务记录、DNS或隧道。

r2的 `edge-recovery` 保存切换前r1路由，r1的同名目录保存上一轮visual-coverage-r4路由；最初正式LAN路由恢复记录仍在上一轮r1目录。回退先核对当前配置，仅恢复对应LAN映射，确认目标候选在运行，经 `nginx -t` 再reload，不覆盖之后的其他配置变更。公网发布仍遵守AGENTS.md的“生产、DNS和隧道切换仍须最终批准”。本轮用户正在调整设计，不据此执行正式发布。
