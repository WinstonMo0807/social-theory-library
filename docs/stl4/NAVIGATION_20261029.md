# 全站主导航修正

2026-10-29 17:45，NAV-01 开发关闭 D，内网 Web96。

## 需求与证据

用户要求首页的主导航在所有相关页面随时显示，改善字体和间距，适当缩小搜索、夜间模式、菜单三个图形。最新要求解除此前对导航的冻结，Logo、品牌资源及 A 版主体排版继续保留。

原 `web/styles/layout/site-header.css` 的 1120px 断点隐藏 `.desktop-nav`，`brand-identity.css` 只有首页例外。理论流派、学者、主题等页面因此只剩 Logo 和三个图标。实际 1066px 理论页读回 `display:none`，不是导航接口缺失。多个读者页还有独立的隐藏规则；手机阅读器另将整个页头隐藏。

## 最小实施范围

- `web/components/site-header.tsx` 统一标记共用 masthead；所有使用此组件的页面保留首页、探索、理论流派、学者、主题、特别策划六个入口。读者中心原六个私人功能入口移到附加导航，原返回、账户菜单、馆藏搜索及语言功能保留。原文候选页沿用原来的“理论”短标签，支持页保留“关于”入口。
- `web/styles/layout/site-masthead.css` 是共用页头的新统一布局入口，优先于旧页面特例：宽屏横排；1200px 以下导航独立成行；700px 以下六栏目分两行。使用既有本地 Noto Sans 分片，15px/500，手机14px；不增加字体资源。普通页面顶部 sticky；阅读器页头保留在其固定网格行，正文在内部滚动。
- 搜索与月亮图形18px，菜单21px。桌面按钮40px，手机36px；沿用现有悬浮、焦点、菜单、主题行为。
- `web/app/layout.tsx` 引入统一样式。Logo 源码、资源、品牌 CSS 未改。后台保留已有的管理导航；后台内容预览中的公共页头同样使用新布局，没有把公共导航强塞进后台工作区。

## 实际验证及边界

类型检查 `tsc --noEmit`、`vinext build`、镜像构建与内网部署均退出0。没有运行测试套件、业务表单测试、OCR或检索评测。

- 原1066px理论页：六链接可见、字体实际加载、无横向滚动；滚动135.2px后页头 top=0。点击学者后对应导航 `aria-current=page` 正确；菜单实际打开、Escape关闭。
- 现有 `/admin/visual-review` 的1440/768/390/320px iframe实际渲染：理论页无横向滚动，1440页头82px高，768页头118.8px高，390/320页头约135/134px高；六链接均有实际非零尺寸，手机分两行。iframe滚动条占用约15px，所以读取的内容宽度为1425/753/375/305。
- 320px iframe另外读取首页、学者、主题、馆藏检索、原文候选、读者中心、笔记、关于页面，主导航均可见且页面横向溢出为0。关于有第七链接，附加功能所在页头相应增高。
- 390px真实阅读器读取当前校准PDF：页头六链接显示，阅读器844px高、正文区域529.5px高，无横向溢出。没有编辑书签、笔记或业务表单。
- 实际窗口和390px页头截图已保存。1440/768验证来自iframe的浏览器几何读回，外层窗口不能同时完整展示整个宽iframe，不能称完整视图像素验收。没有遍历所有对象详情、私有状态、200%缩放及其他浏览器；原206视图 B 清单保持。
- 浏览器 viewport 控制未实际改变窗口宽度，本轮随后重置并改用上述实际iframe，不把无效的控制调用记为响应式通过。

证据在忽略目录 `output/visual-review-20261029-navigation/`，包括 `theories-desktop.jpg`、`theories-390.jpg`、`scholars-desktop.jpg`、`route-checks-320.json`、`wide-checks.json`。320记录按首页、学者、主题、馆藏、原文候选、读者中心、笔记、关于的顺序保存。构建部署日志在 `tmp/stl4-navigation-20261029/`。

## 发布和恢复

仅内网预览更新到 `social-theory-library-web:stl4-preview-20261029-r96`，SHA `ae523e63825525f5aa00ceead4cb07d0ad2a9d6d78a924053c1f445b49ef83c3`，HTTP200。API、四worker、Postgres、RapidOCR、inference的容器ID保持不变；生产未改。

NAS `/volume2/library/stl-previews/20261026-r1/navigation-r96-recovery` 保存前Web95受限环境和镜像记录。回退只采用保存的 `LIBRARY_WEB_IMAGE` 更新预览Web/edge，不覆盖其他环境、不重启后端。所有原未提交修改和旧运行记录保留，不重建自动任务。
