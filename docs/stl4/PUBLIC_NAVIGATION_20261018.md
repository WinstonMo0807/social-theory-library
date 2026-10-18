# 公共与账户手机导航

2026-10-18。唯一视觉依据为终稿 `social-theory-library-visual-atlas-20261015-final-r2.pdf` 第18页，主代理实际查看了该页六个交互状态。源码已补齐；未运行浏览器或正式逐图验收。

- 继续复用原 SiteHeader、Wordmark、原生 Dialog/Drawer、公开会话和账户路由。窄屏右侧面板保留原页及遮罩，面板独立滚动，背景锁滚。目录取消旧编号表样式，当前公共栏目与账户栏目按实际URL高亮。配色使用当前最高纸白/炭黑/暖灰/砂金约定。
- 菜单内搜索以实际 `/explore?q=` GET进入原统一搜索。公共入口仍为首页、探索、理论流派、学者、主题和特别策划；增加我的资料、账户设置、帮助与支持、关于。管理入口只对实际包含 `access_back_office` 能力的会话显示，后端权限保持不变。页脚增加帮助与反馈链接。
- 点击我的资料或账户设置时，仅在当前标签页保存允许的公共来源路径、检索筛选、滚动位置和时间。不保存账户、后台、认证路由、未知查询参数或私人正文。30分钟后过期；浏览器禁用sessionStorage时保留当前标签页内存回退。
- 账户页显示返回原页面入口，返回后等待内容高度恢复滚动并把焦点放回菜单按钮。用户主动滚动/触摸/键盘输入会停止迟到恢复；恢复完成清理记录。正常关闭菜单仍保留当前页位置。Dialog焦点恢复使用preventScroll，避免焦点把页面带回顶部。
- 修复ReaderCenter只在首次挂载读取section的问题。当前页面从菜单进入账户设置时，实际切换相应现有内容；切换未改变任何账户数据或权限。

## 验证与范围

- 6个目标TS/TSX文件ESLint退出0，无警告。新增导航5个合成浏览器场景仅编写，未执行。
- PostCSS解析site-menu.css与public-responsive.css退出0，分别32和5个顶层节点。该结果仅为CSS语法，不证明实际布局。
- 全量TypeScript在本单元和当前文件/OCR源码合并时退出0；最终帮助/反馈接入完成后仍需同步类型与相应静态记录。
- 背景保留、长内容面板滚动、Escape/焦点、浏览器回退、账户登录后返回及手机实际尺寸仍须统一运行验收。没有正式测试、浏览器截图、构建、生产操作或检索质量评测。
- 对应源码：`web/components/site-header.tsx`、`web/lib/public-navigation-return.ts`、`web/styles/layout/site-menu.css`、`web/styles/layout/public-responsive.css`、`web/components/ui/dialog.tsx`、`web/components/reader-center.tsx`、`web/components/public/site-footer-view.tsx`、`web/tests/public-navigation.spec.ts`。与当前95–98/109–111文件单元分开保存，不混算170–172检索评审页面。
