# 主导航与检索入口修正 · 2026-11-15

用户要求固定顺序：首页—书库检索—理论流派—学者—主题—特别策划—读者中心；默认书库检索回到包含观点检索、原文检索、向书库提问的总入口。

原因定位到web/components/site-header.tsx中导航第二项被改为/library。实际/explore/page.tsx在无查询参数时仍返回ExploreLanding，三种入口均保留；无需重建页面或改动API。

本次仅改SiteHeader：第二项改回/explore并明确使用书库检索文案，避免旧后台配置探索覆盖用户决定；读者中心放入第七项；桌面与抽屉共用同一数组；去除工具区重复读者中心入口，账户进入仍调用enterAccount保存原页面；关于/帮助页的主导航保持相同顺序。独立/library及首页最近入库查看全部入口继续保留。

首次发布已修正链接，但公网核验发现旧后台navigation.explore值为探索；补发r2将显示名固定为书库检索，再进行完整的本轮导航核验。r1源码/镜像及回执留在tmp/navigation-search-20261115/initial-*，最终以本记录r2为准。

验证：资产准备、类型检查、Vinext生产构建、压缩与性能预算退出码均0。现有Playwright通过本机Edge在公网1280px及390px核对主导航与抽屉7项文字/地址/顺序，检索点击后匿名会话转登录且next=/explore，主导航链接均在视口内、页头scrollWidth未超clientWidth。已复核原/explore无参数分支及三个入口，不进行真实检索或模型任务，也未使用读者会话。现有J/K资源与新site-header资源公网200、SHA与本机构建一致。

工具边界：本地后台预览进程启动被自动审批拦截，未启动该进程；采用构建检查后进行真实公网浏览器只读核验。默认Playwright捆绑Chromium未安装，使用本机现有Edge，无浏览器安装或用户配置修改。

发布时间2026-11-15T13:38:54+08:00，Web sha256:8b89e98a2cfe0bd87a21fdef95cda9623fbeaa372e56296968843a92b372130d，源码6a2facae84780b8b47ed9bdcebae0aa062b8f1e3。生产3210文件哈希匹配，107非Web容器身份/镜像/配置/启动时间不变。备份文件字节数、SHA与原完整归档读取证明复核，活动Compose仅web.image变化；回退路径/volume2/library/stl-releases/20261115-navigation-search-r2/recovery/rollback.py。J/K、E/C/B页面与香港回源保留，无数据库、权限、schema或后台任务变更。

截图位于output/playwright/navigation-search-20261115，浏览器数据、部署与Git回执位于output/navigation-search-20261115；只提交源码与文档，不提交运行产物。共享HEAD及原暂存索引保留。
