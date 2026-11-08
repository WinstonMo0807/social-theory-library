# 全站页面边界与响应式修正 · 2026-11-09

用户要求修复原文证据页的左右错位，宽屏按可用比例铺开，保留阅读舒适度，并将 r9 及未发布的前端合并后同步公网。本轮已获直接发布授权，不重问。基线为 9653ce72，包含 1b009db9 的统一预览和 da57d170 / 474345af 的字体修正。其他工作区未提交内容保持。

## 有证据的修改

| 项目 | 证据、范围与处理 | 当前分类 |
| --- | --- | --- |
| 检索主体错位 | `viewpoint-search.module.css` 的 `.page` 为1440px最大宽、没有居中；2560px浏览器实际观察到页头x552、主体x0。外框改随视口，页头/页脚/共享公开页面同规则；未改变导航、品牌、查询或权限。 | D，候选实际核对 |
| 宽屏层次 | 筛选栏195–260px、摘要295–400px、间距24–48px随屏幕调整；结果列可伸缩。正文仍限制行宽，理论阅读区居中、保留目录。20份CSS修改，没有新增框架或依赖。 | D，候选实际核对 |
| 手机筛选标签 | 320px真实截图的三个并排按钮把“文献类型”“理论流派”拆行。480px以下改为两列，年份另占一行。 | B，已上线，最终两列截图因Edge断连未读回；原三列及弹窗实看已完成 |
| 原学者肖像挤压 | 旧问题为肖像固定尺寸超过平板列宽，已在readable-r4修复。此次768px实看210px肖像没有超列，320px大号没有横向溢出。 | D，原修复保持并复看 |
| 新宽屏肖像裁切 | r3公网2560px实际显示肖像随24%列宽放大但仍固定285px高。r4仅增加1001px以上列宽上限320px、恢复.94竖幅比例；实看2560为320×340.4px、1440为259.2×275.7px。 | D，92c608cc，已上线并读回 |
| r9导语计数 | 390px大号textarea底部631.1，计数顶部639.1，position=static；320px大号页面305px且无横向溢出。 | D，实际核对 |
| r9笔记弹窗 | 320px大号正文19px；窗口在视口内，内部可滚动；Tab到取消后两按钮完整进入视口，未保存私人资料。 | D，实际核对 |

## 已执行

- 独立Edge窗口，不操作策展窗口。检索2560/1440/768/390/320；文档clientWidth与scrollWidth一致，2560修正后页头和主体均x0、宽2544.8px。手机筛选弹窗及已确认笔记选择实际打开。
- 本机隔离构建r1/r2均成功。初次隔离复制漏了Vite配置依赖，补入原有`.openai/hosting.json`与`build/sites-vite-plugin`后成功，未改变产品逻辑。20文件diff检查退出0。
- 保留之前理论/学科四档宽度、大号及133正常入口样式覆盖证据，不扩大为全部页面逐状态验收。
- 原r9 NAS构建不再使用。本机从未启动、无业务挂载的正式Web基础镜像导出打包，剔除旧dist后放入新1839文件，生成单层Web镜像。NAS仅load。
- r1 LAN候选68851b41c8a1；准备r2时NAS可用内存约1.2GiB，原1.5GiB同时启动门槛阻止创建。先只停止本轮r1并将LAN暂归正式Web；释放后约1.3GiB，再以单一候选方式替换，未退出业务服务。
- 浏览器在复看李怀印页时连续超时，未记为通过。已请求其他策展对话暂让浏览器控制，继续发布准备。
- 用户确认已停止其他浏览器对话并再次明确推送公网。Edge仍超时；使用独立应用内浏览器完成李怀印页平板/手机大号、候选宽屏与公网HTTPS首页/学者详情复看。未操作策展标签或写入业务数据。
- r2镜像候选启动失败：剔除dist时未保留目录权限，node用户无法写runtime-config.js.tmp；未接入任何入口。r3/r4本机打包保留原目录权限后正常启动。失败日志保留，不称产品运行故障。NAS内存门槛阻止的两次候选准备亦保留，未中断业务服务；最终单候选384MiB上限，已停止且OOMKilled=false。
- r4使用`build-r4-final.log`对应的完整构建；此前一次复制命令工作目录错误的产物未发布。1,839文件中1,838静态文件hash全部一致，唯一运行时配置已和候选单独核对一致。API就绪200；未重新运行OCR、深度检索或模型评测。

布局方法参考W3C的[Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)、Carbon的[2x Grid](https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/guidelines)及MDN的[min-width](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/min-width)：区分随视口伸缩的页面外框、可缩小的内容列，以及限制行宽的长文本。没有引入组件库或更换品牌。

## 发布与恢复

2026-11-09 00:45:25+0800最终公网与LAN统一为`social-theory-library-web:4.0.0-20261109-responsive-r4`，容器`9614f8f308c0`，镜像`2fce4be0a7d0c1192c7efd64c20ac6e6650971dc37615c35d5290a9219df140a`。源码`f5db6f14`、`92c608cc`，已包含原r9、1b009db9的全路由/iframe统一及9653ce72的Elicit阅读布局。其他未提交后端/媒体/阅读器工作未混入本次Web构建。

两个Host的/home、/admin、/theories均200，公网HTTPS首页和学者详情真实读回；16个其他服务的容器身份和启动时间不变。活动入口沿用`/volume2/library/stl-releases/20261107-r1/public/compose-command.json`，追加r4 Web覆盖层。部署解析严格比对只有Web image变化，沿用resource-r4等现用后端覆盖层，未按旧Web标签重建旧配置。只执行`up -d --no-deps web`及edge平滑reload，没有数据库、权限、DNS或隧道变更。

NAS恢复点`/volume2/library/stl-releases/20261109-responsive-r4/web-recovery`保存当前准确Compose/env/Web/edge及`rollback-web-only.py`。该脚本仅允许从本次r4回到r3，将LAN归正式Web，不依赖已停止候选；未执行回退演练。此前readable-r4完整恢复仍在`20261109-responsive-r3/web-recovery`，原镜像保留。不得用旧数据库覆盖新策展内容，不运行全量compose up。

本地证据在`tmp/stl4-responsive-20261109/`，最终截图`output/playwright/responsive-20261109/public-scholar-r4-1440-loaded.png`；早期带r2/r3和未加载图的截图仅留过程，不作最终证据。原r1/r2/r3/r4候选均已停止，r4停止后正式Web仍running。应用内浏览器恢复默认视口和舒适字号。Edge断连时该检查窗口仍可能保留临时大号偏好，未声称已恢复。

仍属B的是未逐态访问的权限页面和内容状态；不据此新建开发任务，不宣称全站像素或长期稳定性已验收。
