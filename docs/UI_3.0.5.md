# 3.0.5界面与样式收敛

当前保留黑、白、暖灰的编辑型界面、公开导航和Reader。没有引入另一套组件框架，也没有用静态资料代替失败的API。

## 设计基础与CSS

`web/styles/tokens/design.css`统一typography、spacing、container、surface、ink、border、accent、radius、shadow、motion、z-index十一类设计值。原短名称和页面自己的主题作用域保留，新值使用stl前缀，避免意外改变原fallback颜色。

globals.css从16921行变为明确的有序导入，原规则按连续职责分到67个文件，目录包括tokens、base、layout、components和features。不是把整份文件换名为legacy.css。既有基础规则有189处等值token替换。展开导入并还原token后，3413条规则、10728项声明及其顺序的AST摘要与d51928d基线一致。新增overlay样式独立验收，不混入等价声明。

## 共享组件清单

| 要求 | 实际共享组件和位置 | 使用位置 |
| --- | --- | --- |
| Button、IconButton | ui/controls.tsx | ActionButton、确认框、公开菜单、检查器 |
| Input、Textarea、Select | ui/controls.tsx | CanonicalField、实体查询、确认说明 |
| SearchInput | ui/controls.tsx | 公开SearchField |
| EntityPicker | admin/research/research-entity-picker.tsx及workflow-fields.tsx | 编目和知识编辑，候选/字段状态仍由原业务服务负责 |
| Tabs | ui/tabs.tsx | Work引用格式，方向键和Home/End支持 |
| Badge、StatusChip | ui/controls.tsx及admin-ui.tsx的StatusBadge | 原后台状态组件共用Badge，不重复状态事实 |
| BookCover | ui.tsx | 馆藏、详情、Reader和预览 |
| PersonAvatar | ui.tsx的ScholarPortrait | 学者卡片和页面，复用响应式肖像 |
| KnowledgeCard | theory-system-ui.tsx的KnowledgeNodeCard | 知识目录和关联列表 |
| Dialog、Drawer | ui/dialog.tsx | ConfirmDialog和公开导航菜单 |
| Inspector | ui/inspector.tsx | WorkflowInspector |
| Tooltip | ui/tooltip.tsx | 结构化引用导出说明 |
| EmptyState | admin-ui.tsx | 已有后台空态 |
| ErrorState、Skeleton | ui/feedback.tsx | 检查器文件错误和真实加载状态 |
| Pagination | ui/pagination.tsx | ScopedSearchPagination，保留context、过滤和页码 |

既有BookCover、ScholarPortrait、KnowledgeNodeCard、EmptyState等继续复用，不为名称整齐复制实现。组件按文件直接导入，没有新增庞大的聚合出口。普通控件保留原生属性、表单行为、ref和页面class。

原确认框和导航菜单共用原生modal dialog，保留关闭条件、初始焦点、焦点归还和背景不可交互。Inspector为非模态侧栏，不锁焦点。Tooltip补充文字不包含可交互控件，支持Escape关闭。Tabs为一个键盘tab入口，不增加额外业务状态。

## 验证范围

CSS结构/语义摘要、直接API领域边界及原反馈检查共16项通过。最终统一构建和212项前端检查通过，退出0，35.791秒。真实公网Reader已渲染并检查PDF画布；最终菜单、引用键盘行为与响应式复核在新镜像切换后记录。没有将未登录的后台写入测试写成通过。
