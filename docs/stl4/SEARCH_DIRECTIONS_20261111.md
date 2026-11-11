# 检索页排查与三版本地交互预览

日期：2026-11-11。用户明确要求三版比较，并禁止本轮更新公网。

## 范围与状态

- A 必须修复：正式 `/explore?sort=newest` 的封面/书名重叠、标题字号过小、摘要失去截断、操作区分散、筛选与排序区拥挤。已定位证据；正式页面尚未修改。
- B 已实现待用户选择：A 轻盈书房、B 文献目录、C 阅读工作台，均为独立本地交互预览，尚未接入完整业务 API。
- D 本轮排查与定向预览检查完成。D 仅指本轮交付，不代表正式检索页已经修复或全站验收。
- 公网、NAS、生产数据库、正式路由及正式样式均未改变；没有发布、推送或业务写入。

## 直接证据

公开页面 DOM 与实际样式于本轮只读观察。用户截图所示问题可由当前源码解释：

| 位置 | 触发条件及影响 | 后续正式实现最小范围 |
| --- | --- | --- |
| `web/styles/features/explore/stl4-exact.css:306–308` + `web/components/ui.tsx:73–105` | 主网格只留 58px，组件使用 normal 封面，实际 72px；针对 `.small` 的规则未命中，图片超过列宽并挤到文字。标题实际 15px。 | 统一封面列与实际元素尺寸，建立独立标题字号。 |
| `web/styles/components/book-card.css:18–24` + `web/components/ui.tsx:105` | 截断规则定位 `.book-summary`，实际摘要为 `.book-summary-expand > p`，长简介整段展开。 | 按实际 DOM 限制摘要行数，全文留在预览/作品页。 |
| `web/styles/features/explore/stl4-exact.css:311` + `web/components/ui.tsx:107–129` | 最终规则按三列设置，但有预览、阅读、引用、收藏四个操作，且继承 space-between，按钮散落整行。 | 使用随内容排列的操作组，明确主次与交互状态。 |
| `web/app/explore/page.tsx` 的左右侧栏与 explore 样式 | 左侧实际约 176px，复选框、长作者名、计数竞争空间；排序 label 的宽度继承与 flex 覆盖挤窄“应用”。 | 筛选用明确三列和可折叠分组；排序直接生效，无窄小提交按钮。 |
| `web/styles/features/explore/stl4-exact.css:303` | `.result-books` 强制一列，界面网格模式选中时仍单列。 | 让实际列数响应视图状态。 |

另观察到正式收藏控件的请求超时提示。这是业务请求状态问题，当前没有足够证据确认根因，本轮不把本地收藏演示当作其修复，也不触发正式收藏写入。

## 三版设计

| 方案 | 本地入口 | 结构与字体 |
| --- | --- | --- |
| A 轻盈书房 | `http://127.0.0.1:18781/?v=a` | 双栏作品卡片，可切列表；柔和内容层、系统无衬线字体、固定比例封面；1440px 桌面书名 21px，大桌面 24px。 |
| B 文献目录 | `http://127.0.0.1:18781/?v=b` | 单列目录、书名使用本站衬线字体 27px、操作及正文无衬线；摘要限两行和阅读行长，操作紧随内容。 |
| C 阅读工作台 | `http://127.0.0.1:18781/?v=c` | 左筛选、中结果、右预览；结果书名 22px，右侧书名 26px。简介与引用可切换，选作品时保留列表；窄屏转弹层。 |

按用户要求使用 Apple design skill。SwiftUI 是原生界面框架，本轮借鉴其侧栏、分栏、选择状态、弹层和即时反馈，用项目已有 React/CSS/原生控件实现，无技术栈更换，无额外依赖。

正式参考源（本轮已浏览）：

- [Apple Books](https://www.apple.com/apple-books/)：馆藏呈现与清晰视觉层级。
- [Apple HIG Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars) 和 [Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons)：分组、可收起筛选与操作状态。
- [JSTOR Filters and Facets](https://support.jstor.org/hc/en-us/articles/4405598751255-Searching-Using-Filters-and-Facets)：筛选、计数及已选条件。
- [Semantic Scholar Product](https://webflow.semanticscholar.org/product)：结果中的引用与收藏操作。并排阅读面板是本次提案，不称其网站原样布局。

## 数据与操作边界

使用本轮从公开结果页读取的 4 部图书、4 位学者。公开快照保存在忽略目录 `tmp/search-directions-20261111/public-sample.json`，未提交馆藏数据。4/4 是设计样本数量，不是全站数量。封面与肖像复用现有公开图片，不生成或替换真实资产。

搜索、作者/年份筛选、排序、视图切换、收藏状态、弹层和引用面板在本地可操作。收藏仅为当前页面内存状态，刷新后清空。阅读链接指向既有正式阅读器，检查中没有打开阅读器或提交业务请求。引用只提供作者、题名、年份构成的简要书目信息，并明确提示到正式作品页核对完整出版项；没有虚构出版地、出版社或正式引用格式。

源码仅在 `web/design-previews/search-directions-20261111/`。启动：

```powershell
node web/design-previews/search-directions-20261111/serve.mjs
```

依赖本机已读取的公开快照与现有 web 依赖。服务器只监听 `127.0.0.1:18781`，输出在忽略目录 `output/design/search-directions-20261111/`，没有接入发布流程。

## 实际验证

- esbuild 独立构建退出 0。
- `node web/node_modules/typescript/bin/tsc --noEmit --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,es2022 --skipLibCheck --allowSyntheticDefaultImports web/design-previews/search-directions-20261111/main.tsx` 退出 0。
- 使用用户授权的浏览器在本地定向检查：1440×1000 桌面、390×844 手机三版。手机页面实际文档宽度 375px、视口 390px，无横向溢出。桌面四张封面均正常加载。
- 作者筛选“舒尔茨”得到 1 条；2000 年以前得到 1 条；出版年份排序首项为《民族国家与暴力》；无匹配查询显示空结果；清除恢复 4 条。
- 收藏/取消收藏反映为 1/0 条；学者切换显示 4 位；A 列表与网格切换实际列数 1/2。
- C 选中第二部作品时右侧书名与内容同步；引用切换与复制成功提示出现。手机 C 使用预览弹层。
- 原生 dialog 支持 Esc 与关闭按钮。定向检查发现关闭后焦点回到 body，已修复为关闭后回到触发按钮，并复核为 `BUTTON / 预览`。
- 手机筛选年份后“查看 1 条结果”显示并生效；鼠标自动化两次命令超时后改用键盘 Enter 激活，并观察弹层关闭与 1 条结果，不把工具超时记为应用通过。
- 本地页面控制台读取未见 error/warn。未运行全站测试或生产功能验收。

已保存截图：`a-desktop.png`、`b-desktop.png`、`c-desktop.png`、`a-mobile.png`、`c-mobile.png`、`mobile-filter.png`、`preview-dialog.png`。均在上述 output 目录，未提交运行产物。

后续按用户选择把对应方案移入真实检索组件，继续接入既有 API、权限、完整筛选与真实引用/收藏。生产发布仍以新的明确授权为准。
