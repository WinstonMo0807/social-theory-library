# 欢迎页滚动功能介绍

## 2026-11-05 最新决定与交付：欢迎页独立

用户明确“分开吧，欢迎页是这个elicit的，首页维持原来的”。WELCOME-SPLIT-01开发D：`web/app/welcome/page.tsx`及局部样式承载简短欢迎语和既有四段介绍。`HomePublicView`只移除介绍接点，文件与`701ac8e2^`完全一致；原首页搜索、继续阅读与栏目、此前确认的全站界面修改保持。介绍组件的“浏览馆藏”由不存在于欢迎页的`#home-recent`改为`/`。不新增自动跳转或业务依赖。

实际入口：[欢迎页](http://192.168.5.6:18084/welcome)、[首页](http://192.168.5.6:18084/)。Web110镜像`social-theory-library-web:stl4-preview-20261105-r110`，完整ID`sha256:95da9a1f47d85bbccd7a66fe6146242654d676db5ca9e01f19a2994db6f4b772`。

- `node node_modules/typescript/bin/tsc --noEmit`、`node node_modules/vinext/dist/cli.js build`、本机`build_r110.py`、`nas_run.py deploy_r110.py`均退出0。构建与发布日志在`tmp/stl4-copy-20261104/*r110*`。
- 真实NAS浏览器1280宽欢迎页、了解书库锚点及首个图示、进入书库返回首页已查看；首页显示真实继续阅读和原栏目，`#library-features`数量为0。390宽欢迎页标题、按钮、展开导航与首段已实看，scrollWidth375/innerWidth390，无横向溢出。图示内部沿用Web109，不重跑四个业务入口。
- 截图`output/welcome-20261105/welcome-desktop-r110.png`、`welcome-story-r110.png`、`welcome-mobile-r110.png`、`home-restored-r110.png`；两个真实入口保留为交付标签，临时视口已重置。未提交业务表单或创建私人数据。
- 仅预览Web重建、edge重启，其余受核对容器ID和挂载保持，除edge外启动时间未变。恢复点NAS`/volume2/library/stl-previews/20261026-r1/welcome-r110-recovery`保留前Web109配置/状态；回退仅`LIBRARY_WEB_IMAGE`，勿整份覆盖.env。API/数据/生产/模型未改，四worker/beat/RapidOCR/docx原停止状态保持。
- 源为701ac8e2工作区加本批文件，继承的前端未提交改动保留并包含在构建中，不称干净提交构建。仅本次拆分定向验证，全站视觉/业务验收仍B。

以下记录为拆分前实现与验证历史；其中“加入首页”现已被上述用户决定替代，原四段组件和验证证据继续复用。

用户要求参考 Elicit 首页的滚动功能演示，结合书库功能实施；同期确认精简辅助文案、双栏菜单、展开外观设置、Logo 同行导航均应出现在真实内网预览。本项不使用独立空数据夹具。

## 设计与范围

- 参考 https://elicit.com/ 实际首屏和功能介绍的阅读节奏。采用书库原有纸白、黑金、宋体标题与功能字体，不使用 Elicit 品牌或素材。
- 首页保留搜索、继续阅读、策划和馆藏内容，加入提出问题、阅读原文、核对引文、整理研究四段介绍。各段仅一个标题、一句说明与真实功能入口；可从介绍标题直接跳到最近入库。
- 桌面正常滚动，右侧图示停驻并随章节淡入换页，无自动播放和滚动劫持。平板、手机及较矮窗口改为图文顺序排布。键盘进入章节链接时同步图示；减少动态效果偏好关闭过渡。
- 使用已有首页公开作品的书名、作者、封面，无新增 API。其他纸页、引文和笔记仅为明确标记的功能图示，无虚构引文、页码、核验结果、私人内容或检索质量承诺。
- 仅新建组件与局部样式并接入首页；不改 Logo、业务、接口、权限、数据库、检索、OCR 或已有编排数据。

## 状态与实际读回（2026-11-05收尾）

HOME-STORY-01开发D。最终内网Web109：`social-theory-library-web:stl4-preview-20261104-r109`，镜像`sha256:ca5c9241698a31af5ff5be3b5b39679bdda9740e1bf68305b71b95a3787c0281`。入口http://192.168.5.6:18084/，首页搜索下方的“让阅读成为研究”。这是当前实际候选前端。

- Web108观察桌面1440/1280四幅图示和滚动换页、768平板双栏、390/320手机顺序布局。实际发现手机原文图示底部重复说明被裁切，Web109删除此说明及重复进度短线、压缩示意行距，并把章节触发带收紧至视口中线。
- Web109实看1440/1280桌面、390/320手机原文场景完整，无所看页面横向滚动；手机夜间图示已看后恢复白昼，原舒适字号/无衬线设置保留。Tab从检索观点进入查找原文时图示active=1，链接焦点轮廓可见。
- 四个CTA实际打开`/explore/opinions`、`/explore/original`、`/account/citation-audits`、`/account`。原文目录本轮仅核对打开，未追加检索；引文可用检查项及本人3条阅读历史加载完成。未提交稿件、检索或私人内容；扫描识别/深入分析实际显示暂未开放。
- 已登录公共菜单实际为双栏，外观/字号/字体直接展开，公共Logo与导航同行；窄屏导航分行可见。管理端沿用自身工作导航，Web107真实/admin读回9项工作，未重跑历史失败。
- 减少动态效果分支仅代码确认，本轮未切换操作系统该偏好；不称该模式已运行验收。768最终版未重复截图，保留Web108记录；不把定向检查扩称全站/每项业务/精确字体或长期稳定验收。

## 执行与证据

- `web: node node_modules/typescript/bin/tsc --noEmit`，两次（最终改动后含一次）退出0。
- `web: node node_modules/vinext/dist/cli.js build`，Web108及最终Web109退出0；日志`tmp/stl4-copy-20261104/build-r108.log`、`build-r109.log`。
- 本机`build_r108.py/build_r109.py`仅将构建及已有字体/编辑配图打包到受限候选目录，NAS构建退出0；不提交dist或归档。最终归档71,459,959字节，SHA256`fceb372e5355be94c73e344d2c3cd1e2e5079c8574a434e1c0e738a4f72c8a33`。
- `nas_run.py deploy_r109.py`退出0，HTTP200，仅预览Web重建并重启edge。非Web容器ID与挂载不变；除edge外其他容器StartedAt不变，生产/政策/API/数据/模型未改。
- 截图`output/home-story-20261104/desktop-original-r109-final.png`、`desktop-question-r109.png`、`mobile-original-r109.png`、`mobile-320-r109.png`、`dark-320-r109.png`。`menu-live-r108.png`及其余r108图为此前观察，勿冒称最终图。浏览器尺寸覆盖已恢复。
- 源码基于425aef2d工作区，加本批组件和记录，构建同时包含原先保留的前端未提交修改；没有覆盖这些修改，不声称镜像仅来自干净提交。

## 恢复与未验收范围

前置Web107已把既有全站118处精简文案和菜单/导航选择同步NAS。NAS`/volume2/library/stl-previews/20261026-r1/home-story-r109-recovery`保留前Web108，`home-story-r108-recovery`保留前Web107，`reader-admin-r107-recovery`保留本批前Web106。目录0700，配置及容器原始状态0600；回退只恢复对应`LIBRARY_WEB_IMAGE`并沿原Compose更新web/edge，不整份覆盖.env或清理卷。

当前API仍r54，四worker、beat、RapidOCR、docx-preview仍停止。本批恢复范围为网页/登录/已存资料访问，不表示所有异步业务已恢复。全站正式视觉及业务验收、公网配置缺项与最终批准继续按原B清单处理；不重开已关闭开发项、不改模型、不部署生产、不重建自动安排。
