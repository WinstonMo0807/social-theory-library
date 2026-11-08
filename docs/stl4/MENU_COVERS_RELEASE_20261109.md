# 2026-11-09 菜单、帮助页与六组默认封面合并发布

## 范围与授权

用户明确要求全站同类问题排查，并将下拉裁切、三角折叠、账户导航、帮助页图文与此前阅读器/引文/品牌弹窗合并推送公网。六组图形封面起初只供选择，随后明确同意未选定封面的书和期刊自动随机使用并一并发布。该最新授权覆盖预览限制，不再重复确认。

## 实现

- 全量源码清点344处details和296处select，共640处。逐项登记MENU_CONTROL_COVERAGE_20261109.csv。181处普通内容直接显示，1处书目简介直接作为正文，1处账户导航直接分组，1处帮助栏目改为直接链接，1处只重复同一摘要的上下文控件移除；122处长历史/比较/按需选择器保留统一展开与收起，37处操作菜单保留点击行为。
- select的高度和内边距随文字缩放；单选按内容适配，窄屏账户筛选逐行显示。账户阅读资料与设置入口展开，研究导航搜索框独立成行，修复隐私标记继承标题字号。
- 帮助页三张指南卡按内容自然排高，替换会盖住文字的固定截图；阅读步骤可点击，引用格式示例保留可复制/导出行为并明确示例属性。文案改为“书库收录什么”“原文、版本与页码”等读者用语。
- 共享DefaultCover提供六组纸白/炭黑/暖灰几何图形：偏心圆弧、错位色面、书页折面、疏密线纹、留白窗口、交叠轮廓。真实封面优先；题名经稳定分配保证同书跨页一致。适配书、整期期刊及相关书目引用，封面文字按容器宽度缩放并限行，90px以下不显示次要作者/期号，完整标题仍可由页面正文和无障碍名称读取。未将生成样图当作真实封面写入数据库。
- 合并289285f3的阅读器紧凑页头/全屏、引文装饰重叠和151处原生浏览器弹窗迁移。beforeunload由浏览器控制的离开提醒保留，应用内确认/通知/理由弹窗共用现有黑金品牌。

## 验证与边界

- `node --import tsx --test tests/default-cover-20261109.test.mjs tests/content-controls-20261109.test.mjs tests/ui-dialog-20261109.test.mjs tests/reader-fullscreen-20261109.test.mjs tests/reader-modules-v305.test.mjs`：14项通过，0失败。包含全树控件分类、无遗留alert/confirm/prompt、确认取消与重复点击、阅读器全屏失败回退、页码边界、六组分配稳定性。
- 隔离TypeScript `--noEmit --incremental false -p tsconfig.task-check.json`退出0。本地Vinext正式构建退出0；保留构建器对动态路由无法静态分类的既有提示。
- r1实际核对1440桌面帮助页、390手机/大字号最长角色和状态、账户静态导航、收纳Enter展开与收起。帮助三卡文字与交互示例有正常间隔，无覆盖；移动端页面宽度与滚动宽度一致。核对记录和截图位于tmp/stl4-menu-layout-20261109。
- r2实看默认封面尺寸/文字正常；发现详情简介重复开关及旧蓝色后备值，r3已将列表与详情简介直接显示，并补齐全站旧组件共用的品牌颜色别名。最终公网发布结果在下节追加。本轮是源码全量检查与代表状态实际验证，不称所有路由所有业务状态均完成视觉验收；未提交修改用户资料的测试表单。

## 发布来源与恢复边界

候选继承已上线responsive-r4的隔离发布快照，再叠加289285f3和本轮明确文件差异。独立Git暂存只包含本轮变化，原CURRENT_PROGRESS.md和WORKSPACE_TYPE_REVIEW暂存保持。三处发布快照中既有差异（inline-media-picker超时、workflow-fields的pickerRef、workspace-v307处理状态样式）已核对在responsive-r4源快照中，原样继承，不把其他工作区脏改动混入。

本机打包、NAS仅load；仅更新Web镜像，保留API、数据库、队列、OCR与按需服务配置、原件/账号/私人资料。生产恢复保留准确旧Compose/环境/镜像与edge配置，只回退Web，不以旧数据库覆盖新资料。恢复脚本只准备不实际回退。

## 最终结果

- 2026-11-09 02:02:36+0800正式上线。公网与LAN共用Web `social-theory-library-web:4.0.0-20261109-menu-cover-r3`，容器`b6990f93ee58`，镜像`a0570b700e3e`。合并源码289285f3、5c26b68e、e2f5e001。r1/r2/r3候选均已停止，最终候选未OOM。
- 1,847个运行文件全部SHA256一致，包括runtime-config；API就绪200。两Host的/home、/admin、/theories均200，其他16个Compose服务ID及启动时间保持。
- 公网HTTPS实际打开《规训与惩罚》详情：220px默认封面、中文题名、暖灰几何图形，标题颜色rgb(27,27,24)，简介内无折叠控件。手机65px列表与95px详情同一图形；320px视口实际内容宽305/滚动宽305，无横向溢出。
- 公网帮助页三卡自然排版，实际点击“核对页码”和Chicago后示例内容更新；手机390px阅读/引用示例不重叠。账户隐私标记恢复小字号、阅读资料导航直接显示。
- 公网383页真实PDF加载成功；点击全屏后h1隐藏、工具栏top=0，PDF占满剩余高度。该浏览器使用应用全屏回退（document.fullscreenElement为空），退出后紧凑书目标题恢复。截图public-reader-fullscreen-final.png；之前原生失败回退自动测试也通过。
- 最终恢复目录 `/volume2/library/stl-releases/20261109-menu-cover-r3/web-recovery`，已保存带版本守卫的rollback-web-only.py，未执行回退。准确活动Compose入口仍为20261107-r1/public/compose-command.json，最后追加20261109-menu-cover-r3/web-menu-cover.compose.json。
- 首次传包/tmp空间不足，755,142,656字节本次不完整文件被准确删除；随后将包写到volume2独立预览发布目录并核验哈希。未清理馆藏、备份、历史发布或其他运行数据。
- 浏览器验证的临时视口已恢复，验证标签已关闭。14项定向检查、最终构建及隔离类型检查均退出0；没有把源码全量统计当作每个业务状态的实测验收。

截图与执行日志：`tmp/stl4-menu-layout-20261109/`，包括public-cover-final.png、public-help-final.png、public-reader-fullscreen-final.png、cover-mobile-r2.png、help-mobile-r2.png、selects-mobile-r1.png，以及promote-r3.log和verify-runtime-r3.log。
