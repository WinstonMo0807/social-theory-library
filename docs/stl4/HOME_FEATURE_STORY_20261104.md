# 欢迎页滚动功能介绍

## 2026-11-05 Elicit 同画面演示与整页介绍

用户指出五张卡片不是所指的动效，并明确要求仿照 https://elicit.com/ 当前首页、将配色品牌及内容换成书库。新选择覆盖下方五卡片方案，仍只修改 `/welcome`，首页 `/` 和全站公共导航/Logo保持。

实际浏览参考页所得：首屏居中标题/CTA，下方圆角宽幅画面是时长41.884秒、静音自动循环的video；scrollY保持0时currentTime继续变化，用户截图里的处理状态属于视频内一幕。其下是普通长页的理念横幅、交错图文功能区、分组介绍与FAQ/尾部入口。没有把这段自动视频误记为滚动驱动或五屏吸附。本站按此构图和动效方式重新实现，不下载参考站视频或品牌资产。

本站首屏复用原HomeFeatureStory入口和公开书目响应，用同一画布中的CSS时间线演示提问、检索状态、文献、原文、笔记五阶段。40秒循环，保持中心位置，背景形状缩放与内容淡入/位移接续，文字逐步显示；没有轮播页码、滚动锁或劫持。提供暂停/重播，离开视区/标签隐藏时暂停，减少动态效果偏好显示静态文献画面。书名与封面来自真实公开接口，原文采用排版示意线，不编造引文或运行检索任务。保留功能演示标记。没有新增依赖。

下方采用暖纸/炭黑/砂金、居中首屏、深色理念横幅、四个交错功能行、两张发现入口、四项阅读原则、阅读配图、原生details问答与尾部进入书库。沿用已授权生成配图、已有品牌与页脚；机构背书/商业指标位置换成书库栏目和实际功能内容。页面标题及末段图片仍复用已有配置，未改后台或接口。

- r113实看发现savedPanel高378.6px，而该阶段背景为329px；仅去掉重复的第二组笔记示意线，r114为324.6px，完整容纳。320宽时修正后255.1px，背景263.2px。
- r114实际操作暂停/重播并改变视口后，figure.scrollTop达到38.4px，绝对子内容整体上移；原因是overflow:hidden配合超出画布的装饰SVG仍生成内部可滚动区域。r115仅将demo的overflow改为clip，不改变页面正常滚动。相同播放控件与视口操作后，390/320宽scrollTop均0；390宽figureTop与timelineTop同为469.525px，位置已一致。
- 类型检查r113退出0；Vinext构建r113/r114/r115均退出0；三次镜像及NAS更新退出0。当前Web115镜像social-theory-library-web:stl4-preview-20261105-r115，完整ID为880c3ec8906ec0dde16ab35ad5cecb4e459cd1cd3877c1725eda0fb208634c85。
- 1440宽看到首屏处理、文献、原文及保存阶段和交错功能/尾部；暂停后结果画面持续保持。768/390/320宽未观察横向溢出；320宽FAQ实际展开成功。控制台DOM工具不支持getAnimations、按button角色定位原生summary无匹配是探针问题，已改用计算样式和可见文字核对，不列产品故障。
- r115在主动播放后滚动至页尾，data-playing读回false、控制按钮仍为暂停演示，证实离屏暂停。页尾进入书库按钮实际打开/，待页面加载后读回原h1和4个首页栏目，welcome-title为0。390/320内部画布偏移已复核；768和1440排版沿用r114证据，只有clip变更，不重复测试同一布局。系统减少动态效果与实体手机触摸尚未实测。
- 全页截图并撤销工具临时视区后曾读到演示暂停；随后真实滚动至页尾再返回首屏，data-playing由false恢复true。本轮未能确认该现象是否发生于普通设备切换，缺少非工具操作的复现证据，列待核实而非新开发阻塞。交付标签最终位于/welcome首屏且自动播放true，临时视区覆盖已撤销。
- 最新截图为film-hero-r115.png、film-page-r115.png、film-mobile-r115.png；r114的film-saved-r114.png、film-tablet-r114.png保留阶段证据。全页图只用于查看整体版面，动效以真实/welcome交互为准。
- NAS恢复点welcome-film-r113-recovery保存本批前Web112，r114点保存Web113，r115点保存Web114。只重建预览Web和重启edge，其他容器/挂载/启动时间、API/生产/模型及原异步停止状态保持。日志tmp/stl4-copy-20261104/*r113*至*r115*；本批图片output/welcome-20261105/film-*。源码基于185c4e7工作区，继承修改保留，未运行正式全站/E2E或真实检索/OCR。WELCOME-FILM-01及两个已证实排版缺陷开发D，原全站B保持。

以下为历史方案，五张卡片不再是当前欢迎页目标。

## 2026-11-05 最新交付：五张整屏大卡片

WELCOME-CARDS-01开发D。用户要求同一页面内上下滑动切换大卡片，最后第五张进入首页。`HomeFeatureStory`只在/welcome使用，本次直接重组原组件，没有并行实现：前四张沿用真实功能入口和原示意图，第五张使用已有首页配图/欢迎语及进入书库链接。移除欢迎页旧首屏和独立CSS，保留全局Logo/导航，首页源码无变化。无新增依赖、接口、数据库或任务。

采用CSS原生scroll-snap与overflow滚动；五个圆点和上下按钮能直接定位，当前页由真实滚动位置计算。按键触发控件使用即时定位，减少动态效果分支取消平滑与吸附。卡片min-height允许长内容自然延长，不用隐藏正文保持固定尺寸。功能示意字样继续区分演示与真实业务结果。

- Web111观察到`web/app/editorial-v2.css`的路由min-height优先级覆盖局部容器，body比屏幕高22px（1280×720）及75px（390×844）。`home-feature-story.module.css`只针对直接包含欢迎卡片的路由容器增加#main-content限定，清除继承最小高度。Web112读取body高720/844/640，和对应屏幕一致，底部控件不再被裁切。
- Web112桌面1280×720查看第1、2、3、5张，鼠标滚动从第1张吸附到第2张（scrollTop560.8），键盘Enter操作圆点切到第3张；390×844查看第4张，320×640查看第2和第5张，宽度无横向溢出。第五张按钮实际打开/，body恢复block、overflow visible、文档高2063px，原首页恢复正常滚动。没有触发检索或提交资料。
- 类型检查`node node_modules/typescript/bin/tsc --noEmit`退出0；Web111与Web112的`node node_modules/vinext/dist/cli.js build`均完成，镜像打包及NAS发布退出0。日志`tmp/stl4-copy-20261104/type-r111.log`、`build-r111.log`、`build-r112.log`、`image-r11*.log`、`deploy-r11*.log`。
- 当前Web112：`social-theory-library-web:stl4-preview-20261105-r112`，`sha256:d389d1bcaca349118ba56ac320ef4e097fb1169a6c739aefdddbe9aa4a6e0202`。NAS恢复点`welcome-cards-r112-recovery`保存前Web111，`welcome-cards-r111-recovery`保存本批前Web110。仅预览Web重建/edge重启，其他容器ID/挂载、除edge外启动时间保持；生产、API、模型及既有停止服务均未改。
- 截图`output/welcome-20261105/cards-desktop-r112.png`、`cards-citation-r112.png`、`cards-mobile-research-r112.png`、`cards-320-original-r112.png`、`cards-320-enter-r112.png`、`cards-enter-r112.png`；`cards-desktop-r111.png`保留初版问题证据。浏览器视口已恢复，欢迎页保留为可交互交付。
- 实体手机触摸和系统减少动态效果未实测；不称全站或全部设备通过。来源为2f2bd42f工作区加本批四个源码文件，继承脏文件完整保留，非干净提交构建。

以下Web110及以前是历史记录，最新欢迎页不再采用独立首屏加长段落布局。

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
