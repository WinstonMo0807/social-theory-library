---
name: Social Theory Library
description: 既有书库视觉系统与管理台、读者中心主体排版记录
colors:
  stl-surface-paper: "#f7f4ee"
  workbench-paper: "#f7f6f2"
  workbench-sheet: "#fffefa"
  workbench-ink: "#292b28"
  stl-readable-muted: "#5c6267"
  workbench-rule: "#dedfd8"
  workbench-wash: "#eeeee7"
  workbench-accent: "#98702e"
  night-gold: "#aa854d"
typography:
  display:
    fontFamily: '"STL Display Serif", "Noto Serif SC", "Songti SC", SimSun, serif'
  headline:
    fontFamily: '"STL Display Serif", "Noto Serif SC", "Songti SC", SimSun, serif'
    fontSize: "clamp(28px, 2.5vw, 38px)"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0"
  reader-headline:
    fontFamily: '"STL Display Serif", "Noto Serif SC", "Songti SC", SimSun, serif'
    fontSize: "clamp(30px, 3vw, 40px)"
    fontWeight: 500
    lineHeight: 1.3
  body:
    fontFamily: '"STL Text Sans", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "max(15px, var(--stl-readable-meta))"
    lineHeight: 1.6
  ui:
    fontFamily: '"STL Text Sans", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "max(14px, var(--stl-readable-ui))"
  label:
    fontFamily: '"STL Text Sans", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "max(13px, var(--stl-readable-meta))"
rounded:
  center-panel: "3px"
  inherited-control: "6px"
  stl-radius-small: "4px"
spacing:
  stl-space-3: "12px"
  stl-space-4: "16px"
  stl-space-5: "20px"
  stl-space-6: "24px"
  stl-space-7: "28px"
  stl-space-8: "32px"
components:
  button-primary:
    backgroundColor: "{colors.workbench-ink}"
    textColor: "{colors.workbench-sheet}"
    rounded: "{rounded.inherited-control}"
    padding: "9px 16px"
  button-secondary:
    backgroundColor: "{colors.workbench-sheet}"
    textColor: "{colors.workbench-ink}"
    rounded: "{rounded.inherited-control}"
    padding: "9px 16px"
  workspace-field:
    backgroundColor: "{colors.workbench-sheet}"
    textColor: "{colors.workbench-ink}"
    rounded: "{rounded.inherited-control}"
    padding: "10px 12px"
  overview-navigation:
    padding: "10px 12px"
    rounded: "{rounded.inherited-control}"
  evidence-chip:
    backgroundColor: "{colors.workbench-sheet}"
    textColor: "{colors.workbench-ink}"
    padding: "4px 8px"
  reading-card:
    backgroundColor: "{colors.workbench-sheet}"
    textColor: "{colors.workbench-ink}"
    rounded: "{rounded.center-panel}"
    padding: "20px"
---

# Design System: Social Theory Library

## Overview

**Creative North Star: "沿用本站纸白、白色内容层和黑金品牌"**

这是既有系统的源码记录。品牌与类型选择来自现有实现及用户锁定要求；本轮仅调整管理台和读者中心主体的列宽、间距、密度、对齐与内容边界。该说明沿用 [DIRECTION.md](docs/stl4/public-visual-20261110/DIRECTION.md) 的 OWN-WORLD，不命名新的视觉风格，不替换产品身份。

本文 frontmatter 是已核实值的机器可读快照，不新增运行时变量，也不授权把快照覆盖到整站。标为 **inherited** 的内容为本轮沿用规则，标为 **本轮主体排版** 的内容才是此次新增布局约定。现有 CSS 级联、用户外观和字体偏好、[SCOPE.json](docs/stl4/public-visual-20261110/SCOPE.json) 的边界优先；模块中的具体覆盖仍须就地核对。记录依据为本工作区源码，不代表公网发布、全站验收或所有动态状态通过。

**Key Characteristics:**

- 既有黑金书页／人物符号与双语名称保持。
- 标题、字段、真实预览和操作沿用原有组件与业务顺序。
- 主体通过间距与列宽分组，纸面、内容层和细边界继续使用既有变量。
- 窄屏由 CSS 自然换行和已有面板规则适配，不生成手机图片。

权威入口为 [PRODUCT.md](PRODUCT.md)、DIRECTION.md 与 SCOPE.json；实现入口为 [center-layout.css](web/styles/features/center-layout.css)。继承值来源为 [design.css](web/styles/tokens/design.css)、[theme.css](web/styles/tokens/theme.css)、[appearance.css](web/styles/tokens/appearance.css)、[typeface.css](web/styles/tokens/typeface.css) 和 [workbench-editorial.css](web/styles/features/workbench-editorial.css)。根布局按既定顺序载入这些样式；不要排序其 import。

## Colors

**Inherited.** 纸白、暖色内容层、深色文字和少量砂金均为已有配色。本轮没有新增或修改颜色变量。frontmatter 中的中心配色是 `data-workbench="elicit"` 现有作用域的浅色值；这个历史属性名不构成继续参考 Elicit 的授权。

### Primary

- **中心砂金**（`workbench-accent`）用于既有中心的焦点与选中强调，不替换所有按钮背景。
- **既有金色别名**（`night-gold`）继续服务已使用该变量的阅读进度、选中标签等组件。两个金色来源并存，不在文档中合并成一个新品牌色。

### Neutral

- **全站纸白**（`stl-surface-paper`）是全站基础默认；中心纸面使用局部 `workbench-paper` 覆盖。
- **中心内容层**（`workbench-sheet`）与 **中心淡色层**（`workbench-wash`）划分表单、列表和轻背景。
- **中心文字**（`workbench-ink`）与 **可读灰字**（`stl-readable-muted`）继续通过原有 `--ink`、`--muted` 等别名生效。
- **中心细边界**（`workbench-rule`）用于原有分隔线、字段边框和卡片边界。

夜间模式沿用 appearance.css 与 workbench-editorial.css 的局部覆盖。typeface.css 中的可读灰字也有夜间值；不能把浅色快照写成全局常量。错误、成功、警告、异步状态保留各自已存在的颜色和语义，不统一改成砂金。没有合成色阶，sidecar 不把推导色当作已实施变量。

**The Inherited Color Rule.** 本轮主体规则只调整布局，不设置 color、字体颜色别名或新的主题值。

## Typography

**Inherited.** 默认 A 排版使用自托管 `STL Display Serif` 和 `STL Text Sans`；字体文件声明见 [type-fonts.css](web/styles/tokens/type-fonts.css)，默认内容栈、偏好覆盖和可读字号见 typeface.css。frontmatter 记录默认内容栈，不取代品牌专用字体，也不把所有页面强制套成同一字号。

- **Display / Headline**：展示字体栈保持；管理正文 h1 的继承尺寸、字重、行高见 `headline`，读者中心标题见 `reader-headline`。管理标题在已有窄屏规则中降至 28px。模块内既有标题覆盖继续生效。
- **Body**：frontmatter 的 `body` 是现有中心根容器字号与行高。实际正文常使用 `--stl-readable-body` 下限，不能将根字号等同全部正文的最终计算值。
- **UI / Label**：沿用可读下限表达式。`--stl-readable-meta` 为 `.875rem + step`，`--stl-readable-ui` 与 `--stl-readable-body` 为 `1rem + step`，`--stl-readable-prose` 为 `1.0625rem + step`；标准、舒适、大号的 step 分别为 `0rem`、`.0625rem`、`.1875rem`。这些是既有偏好实现，不是新增字号档。
- **品牌**：使用 [BrandImage](web/components/brand-image.tsx) 与 [brand-identity.css](web/styles/layout/brand-identity.css) 的独立组合。英文品牌的既有专用字体不能推广为正文或标题字体；中文和图形布局保持。

字体／字号／字重／行高／字距与字色均不属于本轮修改范围。宋体、黑体、楷体和外观偏好继续由原来入口与 CSS 级联控制。PDF 文本层跟随原有画布和阅读器，不按 UI 字号快照重设。

**The Type Preservation Rule.** 对主体做响应式适配时，改变列宽、换行和间距，不缩小已批准的文字来容纳内容。

## Layout

### 作用域

**本轮主体排版。** 全局候选层仅在 `.admin-content` 与 `[data-stl-page-layout="account"]` 内匹配，读者包装保持 `display: contents`。作用域在导航、aside、dialog、菜单、popover、页头页尾、加载／busy 组件、公开预览、阅读模式、阅读器和 PDF 画布处终止。精确排除选择器以 center-layout.css 为准。

局部 CSS 模块只追加带中心前缀的主体规则。多数管理模块另排除 dialog 后代；分享模块使用独立 `@scope`。不能只看选择器文字是否包含 nav：父级网格或伸展也可能改变被保留导航的几何尺寸，需连同父级布局核对。

### 间距与宽度

**Inherited scale / 本轮复用。** frontmatter 的间距取 design.css 已有第 3 至第 8 级。本轮重复使用 16、20、24px 为组内与组间间距，28、32px 用于较宽研究面板。不是重新生成全站 spacing scale；原有 4、8px 等控件细部继续保留。

| 本轮已实现的主体模式 | 源码数值及范围 |
| --- | --- |
| 标题与动作 | gap 为 `16px 24px`，下间距 `24px`；窄屏 gap `12px`、下间距 `20px` |
| 管理内容面板 | 匹配现有标题／表单条件的面板 padding `24px`；窄屏 `20px 16px` |
| 编辑分组 | 标题 `16px 20px`，正文 `20px`，字段 gap `20px 24px`；窄屏为 `16px` |
| 研究面板／详情 | 面板 `24px 28px 32px`，详情 `24px 28px`；窄屏 `20px 16px` |
| 表格与资料行 | 表格单元格 `14px 16px`；资料行按各模块保留完整字段，长表在自身容器横向滚动 |
| 研究会话列表 | 最大宽度 `1440px`；外层 `28px 32px 48px`，窄屏 `20px 16px 36px` |

`10px` 的局部动作 gap、`14px` 的表格垂直 padding、`22px` 的研究卡片 padding 等是源码已有的具体实现，不强行归入六级统一数列。管理壳与读者壳的外边距沿用原级联；没有为全站新设统一容器宽度。

### 响应式

| 条件 | 本轮源码中的行为 |
| --- | --- |
| `min-width: 1600px` | 研究详情壳最大宽度 `1440px` |
| `min-width: 1201px` | 目录校准主体为 `1fr / 1fr / 1.3fr`；笔记工作区为 `18% / 1fr / 1fr`，使用 `minmax(0, …)` 防止内容撑宽 |
| `max-width: 1200px` | 管理书目资料行转两列，第一项占整行 |
| `min-width: 1100px` | 引文上传主体列比 `1.45fr / 1fr` |
| `max-width: 1100px` | 引文问题主体改为 `28fr / 27fr / 45fr`；已有其他模块断点继续生效 |
| `max-width: 900px` | 读者概览恢复 `display: block`，不让父级 grid 改变任务导航高度；阅读卡片 padding `16px` |
| `max-width: 700px` | 主体面板收敛到 `20px 16px` 或分组 `16px`；标题和动作换行，书目行变单列，隐私选项变单列 |
| `max-width: 640px` | 今日工作模块标题换行、资料行缩小间距；保持原操作与内容 |

桌面读者概览仅将既有阅读／计划主体放入 `1.3fr / 1fr` 双列，其他直接子项占整行，归档视图不套用该双列。OCR 概览正文保持单列并令书目信息可伸缩。导航、原有面板切换与控件交互不因适配重写。

上述断点是本轮相关规则，不是项目全部断点清单。手机不再出图；390px、320px 与大字号为范围文档要求的检查尺寸，本文不把这些要求写成全部状态已通过。

## Elevation & Depth

**本轮主体排版。** 匹配的管理内容面板、编辑分组、知识上下文和研究面板去掉 box-shadow，以既有纸面、内容层、细边界与间距表达层次。这不是“全站禁止阴影”：导航浮层、dialog、toast、原生 picker 与原有 sticky action bar 均保留，且不属于本轮可重做范围。

**Inherited.** design.css 的 sticky、dialog、toast 阴影与 motion token 继续存在，sidecar 仅记录其源值及限定用途。本轮没有新增 animation、transition 或加载行为；已有 reduced-motion 支持沿用原实现。

## Shapes

**本轮主体排版。** 仅明确匹配的主体面板与卡片使用 `center-panel` 小圆角，分享记录的连续列表仍使用直角，不能据此强改所有组件。

**Inherited.** 中心按钮与文本字段沿用 `inherited-control` 圆角；design.css 的 `stl-radius-small` 继续是基础默认。状态圆点、胶囊计数、菜单、dialog 和加载组件保持自己的形状。不得把本轮卡片圆角应用到任务分类栏或品牌。

## Components

### 品牌

复用 `web/public/brand/stl-symbol-20261027.svg#mark` 与 BrandImage 的真实双语名称。紧凑横版、管理侧栏竖版及既有小屏变体继续由 brand-identity.css 控制；本轮不重画、不重新排字、不增加 STL 缩写。

### 按钮与字段

**Inherited.** 复用现有 `.button`、primary／secondary 和已有表单组件。中心主按钮是深色文字变量作为背景、内容层变量作为文字；次按钮沿用内容层、文字和边界变量。两者继续使用既有最小高度、padding、焦点环与按下反馈，不因布局修改交互。

字段保留实际 label、值、校验、placeholder 与保存规则。sidecar 的 workspace field 是现有文本字段的展示片段，不是新增表单组件。原生 select 的独立尺寸和 picker 规则保留，不能用静态片段代替真实控件行为。

### 导航

**Inherited / 本轮保留。** 管理任务栏、读者任务分类栏、名称、图标、顺序、权限、选中态和展开行为全部保持。sidecar 只收录读者概览现有导航链接的静态样式片段，供识别既有材料；不表示该区域允许改版，不复制完整导航或虚构入口。

### 内容卡片与资料行

**本轮主体排版。** 复用阅读卡片、管理内容面板、研究面板和现有资料行。阅读卡片保留真实封面位置、标题、元信息、进度和继续阅读动作，仅采用本轮 padding 与小圆角。图片不能替代组件；sidecar 展示文案明确为样式示例，不是馆藏记录。

### 标签、状态与空态

**Inherited.** evidence chip、status badge、错误／权限／空态继续从现有组件取得。无数据仍显示真实空态，不以新装饰卡片补成有数据。状态颜色、异步过程、禁用与重试均不随空间布局重新解释。

`.impeccable/design.json` 中的组件片段仅展示已核实样式，使用 `ds-` 类名并通过原变量继承主题。它们不是生产组件替代品；业务逻辑、完整响应式导航、动态状态、overlay 与公开预览仍以源码为准。

## Do's and Don'ts

### Do:

- **Do** 先按 SCOPE.json 判断表面是否允许修改，再复用已有组件与变量。
- **Do** 将本轮主体 spacing 与 inherited 品牌、字体、色彩明确分开维护。
- **Do** 使用 min-width: 0、minmax(0, …)、自然换行和局部滚动保留全部内容与操作。
- **Do** 核对祖先布局对任务导航的影响；读者概览在 900px 及以下保持普通文档流。
- **Do** 保持现有主题、字号、字体、焦点、键盘和减少动态效果偏好。
- **Do** 将源码实现、隔离预览结果与公网批准分别记录。

### Don't:

- **Don't** 根据生成图重做品牌、导航、字体、字色、文案、字段或操作。
- **Don't** 将本轮样式扩散到登录、公开页、独立阅读器、公开预览正文、弹窗、抽屉、菜单或加载动画。
- **Don't** 把当前主体的小圆角与去阴影策略提升为所有页面和浮层的通用规则。
- **Don't** 发明新色阶、字体等级、图标、业务状态、数据或新的手机设计稿。
- **Don't** 将历史 data-workbench 属性名、旧对比 B 排版或生成图的替代品牌当成当前设计授权。
- **Don't** 把文档、构建、静态片段或单项复核结论当成全站验收或生产切换批准。
