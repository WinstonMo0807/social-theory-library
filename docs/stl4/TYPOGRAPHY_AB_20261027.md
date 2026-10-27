# 全站排版 A/B 比较

## 范围与边界

本轮为用户明确新增的 B 版排版工作。最终 PDF 仍决定品牌色彩、图像与设计语言；页面主体允许重新组织文字与图文比例。Logo、品牌资源、页头品牌区与导航结构冻结。现有文案、API、权限、搜索及数据库不变。未提交的历史开发修改保留，不纳入本轮检查点。

## A 版保存

- 代码基线 `92742cc4b49ce5a09ae7645ca94c038c1e9b53a0`；标签 `codex/stl4-typography-a-20261027`。
- 活动 Web87 镜像 `sha256:f15845a667f1a41c2216e1c648df4ac3e44c8bccb569aff316214c434c31edfc`。
- NAS 增加指向该镜像的标签 `social-theory-library-web:stl4-typography-a-20261027`，受限环境快照位于预览目录 `typography-a-20261027/`。
- 本机忽略目录 `output/visual-review-20261027-typography/A/` 保存完整前端源码归档、当时 Git 状态与补丁、414 个冻结文件 hash、镜像清单、实际页面截图和几何/字体读回。源码归档 21,963,392 字节、1652 文件，包含当时前端未提交修改。
- `01/10/11-loaded.png` 是馆藏/后台馆藏/后台理论实际载入后画面；最初同编号图中的载入态保留，不冒充业务结果。
- A 保存的是代码与视觉结果。实时页面数据随原系统变化，A 链接不是数据库历史快照。

## 现状证据与决定

| 现有实际情况 | B 实施范围 |
| --- | --- |
| 未发现字体文件和 @font-face，声明的 Noto 依赖系统回退；不同页面直接指定宋体/Arial/ui-serif | 本站自托管 Noto Serif SC 与 Noto Sans SC 的可变 WOFF2 字符分片，独立别名，统一主体字体 |
| 学者/主题首页标题实测 72px、馆藏46px、后台馆藏44px，操作页面层级接近编辑大标题 | 编辑标题32–48px、首页36–60px；操作标题24–32px，后台22–28px |
| 单篇首页策划跨整行，短标题与长摘要缺少层次；卡片元数据偏小 | 单篇无图策划左右两列编排，移动单列；人物/书名宋体，摘要及元数据黑体 |
| 检索结果出版列占40%，正文摘要列相对窄，字号混杂 | 出版列26%、保留书封，正文/元数据/按钮各自有层级，窄屏出版信息回流 |
| 多套目录正文与卡片字号/留白独立漂移 | 复用现有组件、样式模块和4px间距体系；目录卡片与章节间距按页面职责分别调整 |
| 文章已有正文与目录/相关材料分栏 | 保留功能，正文限制约40个中文字宽，17–19px、1.85行高，标题/引文宋体 |
| 管理端表单及说明混用展示字体 | 仅 `.admin-content` 使用紧凑黑体层级，标签14px、正文约16px、说明13px；导航/Logo不动 |

完整源码路由覆盖清单为 `TYPOGRAPHY_ROUTE_COVERAGE_20261027.csv`，145行，含重定向及动态对象路由。代码覆盖不等于145路由的每个状态都完成视觉验收。PDF阅读器原页画布、文字层与阅读器导航保持原样。

## 字体与规则

`type-fonts.css` 引入两个新别名 `STL Display Serif`、`STL Text Sans`，未注册覆盖品牌原有的 Noto 名称。共202个 unicode-range WOFF2 文件，10,531,532字节，为完整字符库总量，浏览器只按页面字符请求分片。400–700为可变字重，不重复下载各字号或字重。字体采用 OFL 1.1，字体目录保留许可、来源URL及逐文件SHA256；运行时不访问第三方字体服务。

主体共享规则接入现有 `styles/tokens/typography.css`，路由仅增加表达用途的 `data-type-mode` 和 `data-type-section`。不引入组件库、字体依赖或第二套业务组件。旧样式保留作为A；所有B规则由 `html[data-typeset="B"]` 限定。用户已有宋体偏好和文字大小变量继续参与B规则。

## 对照入口

同一页面加 `#typography=A` 或 `#typography=B` 可以切换。使用fragment不进入服务器的业务查询参数。选择只存当前标签页的 sessionStorage，不写账户设置；同标签继续导航维持版本。默认B。恢复完整A仍可使用保存的Web87镜像和源码，不依赖B样式开关。

现有 `/admin/visual-review` 保留绘图、批注与保存，视口选择增加320×740。未更改批注接口或已有记录。

## 方法参考

- [Carbon Type sets](https://www.carbondesignsystem.com/building-blocks/foundations/typography/type-sets)：区分操作密度与编辑展示的字号用途。
- [Spectrum 2 Typography system](https://spectrum.adobe.com/foundations/typography/typography-system)：CJK行高、文字角色及控件字重。
- [USWDS measure](https://designsystem.digital.gov/design-tokens/typesetting/measure/)：阅读行宽与页面容器分离。
- [WCAG 2.2 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)：窄屏回流及缩放后内容可获取。
- [MIT Press Reader](https://thereader.mitpress.mit.edu/) 与 [Kinfolk](https://www.kinfolk.com/)：编辑目录、题名/摘要/署名组织方法；没有复制其品牌、素材或组件。

## 验证与交接状态

2026-10-27 18:42：B 已部署内网 Web90，镜像 `sha256:f1a7350eef6b37efbe72779d15ac507961801d10fa3c98d06adca46b7b7be478`，HTTP 200。仅更新预览 Web/edge，API/四worker、数据及模型容器ID保持，生产未动。此版本是实际可交互候选。

| 实际核对 | 结果与证据 |
| --- | --- |
| 1440px，12个首批页面 | 首页、原文检索、学者、理论、主题、策划目录、策划文章、书籍详情、读者中心、研究目录、后台馆藏、后台理论均有实际截图与DOM读回。`B/desktop-readback.json`及对应PNG；对象详情只代表当前样本 |
| 1440px，8个补充页面 | 探索入口、观点入口、证据入口、引文体检、隐私、帮助、后台编排、处理中心，`B/final-extra-0..7.json/png`。后台编排/处理中心等首次截图含载入态，不算其所有数据状态验收；引文体检在r90补充可用检查项及0任务空态读回 |
| 768/390/320px，7类页面共21组合 | 使用现有批注台真实iframe： 首页、原文检索、主题、书籍详情、策划文章、研究目录、后台理论。`B/final-{width}-{0..6}.json/png`。320/390的页面scrollWidth与clientWidth相同；768文章有1px舍入差，其余相同；扫描h1/h2/button未发现超过3px的内部溢出。代表截图已实看，不等同全站逐像素验收 |
| r90最后调整 | 探索入口卡片标题降为约21px、操作副标题16.5px黑体、主体段落字体统一、精选主题摘要14px。`explore/citation/topics-final-r90.png`；主题与引文体检另核对320px，宽度305=scrollWidth305、标题及按钮无扫描溢出 |
| 已有文字大小设置 | 策划文章实际从舒适18.5px/34.225px行高切换至大号20.5px/37.925px，文档无横向溢出，随后恢复舒适。`B/large-text-r89.json/png`。浏览器200%缩放未成功应用，不计通过 |
| 字体实际加载 | r90首页FontFaceSet共202条，status loaded；两字体中文样本check为true，实际标题600 60px/78px STL Display Serif。`B/final-r90-home.json` |
| 品牌与导航冻结 | 414文件SHA全部未变，`B/frozen-check-r90.json`。同页A/B实测页头66px、品牌与六导航字体和几何位置相同，`B/ab-chrome-r90.json`（6个品牌元素及六导航逐项相同；旧readback的brand空数组不作为品牌证据）。页头、侧栏、PDF原页/文字层没有排版改写 |
| 静态与发布 | `node node_modules/typescript/bin/tsc --noEmit`退出0；r90 `node node_modules/vinext/dist/cli.js build`完成；镜像/内网部署退出0。日志在`tmp/stl4-rapidocr-20261027/type-b-final-tsc.log`及`type-b-r90-{build,image,deploy}.log`。未运行全量功能/E2E、OCR或模型评测 |

`mobile-home-390*.png`是早期截图裁切工具实验，不能作为手机布局证据；正式窄屏证据使用上表final系列。旧载入态、截图实验与中间版本证据保留，未删除。

### 分类与下一步

- **D 已实现，关闭开发项 TYPE-B-01**：A独立保存、主体字体/层级/行宽/栅格、页面类型差异、窄屏修正、A/B入口及内网B部署完成。可进行用户主观比较，无需因此再建业务功能。
- **B 已实现，待验收**：145个源码路由不等于145个全部数据/权限/弹层状态实际验收。真实样本仅如上；私人研究详情、动态对象的其他长文/错误状态、其他浏览器及200%浏览器缩放未验证，原206视图最终验收不因此关闭。
- **C 后续优化**：只在本次比较反馈指向具体阅读问题时继续微调；不将更换更多字体、额外素材或新组件作为当前阻塞。
- 本轮未创建/上传稿件、运行查询任务、保存业务表单、改账号或批注。夜间与动作规则沿用Web87；本轮主要在白昼/舒适设置下比较。主题图像复用既有素材，没有替换内容资源；无图数据仍如实呈现。
- 原 PUBLIC-CONFIG-01邮件凭据及公网最终批准继续按原清单，不是本次排版缺项，不据此自动部署生产。自动接续任务保持删除。

### 恢复

NAS预览根`/volume2/library/stl-previews/20261026-r1/`下，`typography-b-r88-recovery`保存本批前Web87，`typography-b-r89-recovery`保存Web88，`typography-b-r90-recovery`保存Web89。恢复只取对应受限环境中的原`LIBRARY_WEB_IMAGE`，沿既有预览Compose更新Web/edge；不整份覆盖其他环境、不重启后端。A独立保存在`typography-a-20261027/`及其镜像标签。

B源码和字体许可入Git；截图、NAS环境、源码归档、构建结果、日志与私人页面读回仅保存在忽略目录。对照标签页保留B首页，临时检查标签已关闭。
