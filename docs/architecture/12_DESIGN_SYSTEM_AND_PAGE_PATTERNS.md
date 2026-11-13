# 12 · 设计系统、页面模式与响应式

[架构目录](README.md) · [公网截图与观察](PUBLIC_SITE_VERIFICATION.md)

本轮记录已经上线的视觉实现，没有重新设计界面或把参考图当成真实页面截图。项目期望的高品质需要由实际排版、可读性和操作结果支持，不使用自评分数替代验收。

## 当前视觉来源

`app/layout.tsx`顺序引入globals、editorial、admin workspace、knowledge、home、appearance、brand、typeface、masthead和workspace polish等样式。具体页面另有CSS modules。`scripts/style-source.mjs`按顺序展开本地CSS import供比较；顺序与作用域本身是视觉实现的一部分。

| 维度 | 已核对实现 |
| --- | --- |
| 色彩 | design.css纸白`#f7f4ee`、默认层`#fdfcf9`、墨色`#1b1b18`、暖灰与少量砂金；夜间由appearance/typeface覆盖 |
| 品牌 | 既有黑金图形与中英文品牌资产；公开页紧凑横版，后台侧栏竖版；未新绘Logo |
| 字体 | 本地Noto/展示宋体/正文无衬线等font-face，typeface处理A布局及偏好；B比较规则仍在源码，默认根节点是A |
| 字号 | design基础值不是最终计算值；typeface设置meta .875rem、UI/body 1rem、prose 1.0625rem，comfortable/large再增量；大量组件使用max与可读下限 |
| 间距 | `--stl-space-*`从4px到40px等；实际工作区也有局部padding/gap，不能声称完全Token化 |
| 布局 | 公开页编辑式标题与正文层次；后台侧栏+稳定工作区，复杂表单双列/窄屏单列、预览和底部操作 |
| 交互 | Dialog、EntityPicker、ActionMenuBehavior、加载动效、焦点/键盘处理；欢迎演示独立并尊重减少动态效果 |

## 页面模式

公开导航与编辑工作导航分开；目录/筛选页使用列表、卡片和局部筛选；详情页有清楚的来源/版本/关系区域；表单页使用显式字段与状态；发布审核显示版本差异和范围；异步处理页显示真实进度与失败。README截图保持实际黑金、纸白视觉，不另增加文档主题框架。

管理端重复的布局需求主要是：列表+编辑器、编辑器+预览、队列+详情、原文+证据、任务+日志摘要。优先抽出稳定的页面容器、操作条和结果状态，再保留领域字段；不把每个字段都包成通用配置系统。

## 已观察的窄屏问题

390px下，手工编目材料类型仍使用四等分网格和nowrap，责任者行使用窄select与多列布局，实际出现标题挤压和“作者”换行。相应CSS位于 [manual-catalog.module.css](../../web/components/admin/workflow/manual-catalog.module.css)，源码还有多段同选择器覆盖。见 [VN-A01](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md#vn-a01)；本轮记录问题，不改生产视觉。

![390px手工编目表单局部，未输入数据](images/admin-cataloging-mobile.jpg)

截图裁掉账户工具栏，只展示未保存的空白表单。建议材料类型改为能完整显示文字的两列或可访问选择控件，姓名与角色在窄屏分行并设稳定宽度。验收需覆盖320/390/768/1440、舒适/大字、键盘焦点与底部操作可见性；不能仅用没有整页横向滚动来判定合格。

## 长期维护

新增样式先确认实际import链、选择器作用域和最终计算值；避免在全局末尾继续叠加同名覆盖。品牌、正文、管理控件与PDF文本层各有职责，不应为了统一字号破坏原文定位。页面验收应记录URL、状态、视口、身份和截图，而不是只记录组件已存在。
