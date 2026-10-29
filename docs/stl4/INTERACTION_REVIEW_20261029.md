# 2026-10-29 弹窗、原文排版、悬浮比较及回车检索

## 19:24 用户选定第一套，真实长引文与引用页码修正

本节为最新接续，以下18:45以前的版本和验证范围保留作历史。用户明确采用01书刊细线，并要求注意弹窗排版、检查引文。沿用A主体、已有品牌和导航；重新读取唯一PDF的31、181页原图，保留桌面上下文双栏、引用侧窗和手机底部面板。

| 项目 | 具体证据、触发与影响 | 最小修复及状态 |
|---|---|---|
| HOVER-01 | 用户已选择01；原比较页未将样式应用到业务文字入口 | 共用editorial-links.css覆盖真实栏目/卡片标题、书名和学者链接、管理导航文字及原文操作入口；1px细线/160ms，不把普通正文、整条多操作记录或图标变成链接。D |
| CONTEXT-02 | discovery-evidence-detail.tsx从前段开始呈现；真实PDF19页两段在PDF20命中段前，打开后读者需长距离滚动才能看到刚选原文 | 初次定位命中段，段落导航限定本弹窗范围，工具栏sticky；小屏换行，遮住工具栏上方露出的半行旧正文。D |
| CITATION-LAYOUT-01 | viewpoint-search.module.css的.summaryActions button匹配嵌套引用浮层；1440实际关闭按钮flex为1 1 0%、宽211.2px，其他内部按钮也被摘要样式影响 | 改为直接子层按钮选择器，保留引用浮层自身布局。D |
| CITATION-LAYOUT-02 | 1280已打开的引用浮层切到320后，父evidenceInspector被响应式CSS隐藏，dialog仍open但实际宽高0且不可见；Escape可退出 | shared-citation-overlay.tsx仅将引用Dialog用React portal挂到document.body，保留语言上下文、原生modal焦点/关闭、已选原文与原保存接口。D，最终运行读回见下文 |
| CITATION-PAGE-01 | shared_citation_views.py以printed or str(pdf_page)传入citation_bundle；实际《国家的视角》印刷页码空、PDF20却生成“2019：20.”，误把文件页序当印刷页 | 书目页码仅传printed；无印刷页时五种文字格式另附“（PDF 第 20 页）”，CSL保持无虚构page。D |

真实原文验证使用《国家的视角》极端现代主义检索的五个上下文块（PDF19/19/20/20/21）。通过“原始换行”读取与整理显示对比，五块全部非空白字符完全一致，换行数从19/11/14/15/20变为4/2/2/2/6，保留空行段落。原格式器已实现并有效，本轮没有再次改写算法、原文、PDF、定位偏移或索引，也没有OCR/检索质量评测。该记录不证明任意多栏、诗行、表格或OCR错字均已修正。

实际复制入口读回末尾已从“社会科学文献出版社，2019：20.”改为“社会科学文献出版社，2019.（PDF 第 20 页）”。当前内网HTTP自动Clipboard未成功，页面已提供“手动复制引文”可选文本；没有将自动复制或公网HTTPS行为记为通过。

验证：前端TypeScript退出0；Vinext构建退出0。SQLite定向pytest 4 passed/13 deselected，覆盖有印刷页、只有PDF页序、书目引用和精确原文选择；116.41秒，保留原warning记录，不宣称全量后端测试通过。Web99真实上下文1280/1440双栏、768单栏、390/320手机底部面板均无内部横向超出，关闭与段落按钮可见；首次打开定位PDF20。首页键盘焦点实际在策展卡片标题产生1px细线、offset6.4px；管理页实际加载共用规则，工具的语义点击未产生真实:hover，不能将此冒充鼠标悬浮的截图证明。

内网API r54 ca45017317c52e3abcf4658a7ad7e76989c5b02e82b0c372765091305fed9baa，仅替换共享引用HTTP视图；四worker仍r53（环境的LIBRARY_API_IMAGE已r54，今后重建worker才会跟进），beat、RapidOCR、数据和模型容器未重启。NAS citation-r54-recovery保留原环境/镜像。Web99 cf1a46e1a5e90aca4f09e00de5f8a3b31b4a574f4287a6b4150250a4a8623e7a后以Web100 eea5480f66d48f0b7bae62c4ebbd20a64ed25ea745ea52b069a3a1d787de21bb补齐工具栏遮挡与按钮作用域，HTTP200；interaction-r99-recovery保留前Web98，interaction-r100-recovery保留前Web99。预览Host端口修复保留，生产未改。

日志tmp/stl4-line-20261029、截图output/visual-review-20261029-line均忽略不提交；真实原文比较JSON不入Git。仅提交本轮指定文件，全部继承未提交修改、账号、私人数据、人工修订和历史失败保持。原206视图、其他特殊弹窗和公网前B/批准清单仍有效，不将本轮有限实看扩为全站验收。

最终Web101 e93a89b7372b8893762d0de492bb5b9180441524295545a156006d1c51870dc7已于19:20部署，补齐引用窗口portal；interaction-r101-recovery保留Web100。最终类型/构建退出0，HTTP200，API/worker/数据/模型ID不变。Web101实际已打开的桌面引用窗口切320后parent=BODY、clientWidth/scrollWidth均288、高604，原文与来源加载正常，关闭可用；手机正常从证据摘要再开引用可见两层窗口，Esc实际退至结果且焦点回书名按钮，不将此记录为逐层返回。没有执行加入研究、导出、保存或私人样例创建。

最终上下文1280×720实际clientWidth/scrollWidth均958，命中段顶端205.5px，stl-dialog-enter入场仍在，工具栏上方无旧正文漏出。Web100的320截图clientWidth/scrollWidth均303、24px遮挡层有效；此CSS在Web101未变。恢复默认视口并保留真实引文标签供用户操作。引用侧窗和长文截图分别为citation-320-final.jpg、context-desktop-final.jpg；较早Web99截图不能冒充最终版。

## 授权与最小范围

用户连续要求处理原文上下文弹窗靠左上、开窗生硬、OCR引用硬换行；制作几套按用途区分的悬浮反馈；补充回车检索。继续A主体及既有Logo。只更新内网Web/edge；生产、API/worker、OCR、索引、权限和业务数据保持。删除的自动接续未恢复。

| 项目 | 证据与触发条件 | 最小改动 | 当前状态 |
|---|---|---|---|
| OVERLAY-01 | Tailwind preflight将全部元素margin清零；viewpoint-search.module.css的contextDialog无居中margin，用户长文截图显示窗口靠左上；原弹窗没有animation | overlays.css用零特异性恢复原生dialog的auto margin；220ms透明度/8px入场、160ms遮罩；保留显式侧栏/底部窗口与菜单自身动效 | D 已实现；具体长文原会话运行状态仍B |
| SOURCE-TEXT-01 | discovery-evidence-detail直接输出excerpt/block.text，CSS pre-wrap保留OCR逐行断句；长文滚走后右栏空白 | 纯展示/已核验引用导出使用formatSourceText；上下文可切回原始换行；标题固定、正文独立滚动、桌面出处栏sticky | D 已实现；原截图具体引文的完整动态状态仍B |
| HOVER-PREVIEW-01 | 用户新增三套方案比较需求 | /interaction-preview，局部CSS与本页状态；书刊细线/温和底色/轻盈指向，可固定显示悬浮态，无业务写入 | D 比较页完成；业务页面采用哪套仍待用户选择 |
| SEARCH-ENTER-01 | opinion-search-entry等多行问题框没有键盘提交；默认Enter只插入换行 | 五个提问/检索textarea共用submitSearchOnEnter，调用原form.requestSubmit与原submitter | D 已实现；Web98首页及观点入口实际回车通过，其余私人/研究动态状态B |
| REDIRECT-PORT-01 | opinions带q服务端307丢18084，默认80入口再跳NAS9999登录 | 仅Web反代Host保留$http_host；预览edge热加载 | D 指定路径HTTP和浏览器实际通过，网络边界详NAS_REDIRECT_REVIEW_20261029.md |

## 原文整理边界

- 新增web/lib/source-text.ts及memo化SourceText。连接单行硬换行、整理中文字符间空格；保留空行段落、列表、制表符、脚注编号、普通连字符、标点。英文单词保留分隔，只有软连字符按排版用途移除。
- 覆盖检索卡片、摘要、上下文、同书材料及共享引用浮层。citationText仅在来源重新核验之后整理quote导出，其他书目格式与CSL保持。
- 原API参数selectedText、来源匹配、定位偏移、保存原文、PDF和索引不变。共享引用编辑框仍显示原始文字。没有修改作者撰写的知识介绍或全局编辑器粘贴行为。
- 不推断诗行、正文真实段落、错字或跨栏阅读顺序；保留空行可能仍保留少量OCR段落间断。上下文原始换行开关可核对。
- 本机Node处理自写11440字符样例，预热20次后100次平均0.532062ms。仅本机字符串处理记录，不是NAS或所有设备性能保证；无新依赖、模型/网络调用或索引重写。

## 悬浮方案

| 方案 | 反馈 | 用途 |
|---|---|---|
| 01 书刊细线 | 文字下方1px细线，160ms颜色过渡 | 书名、学者姓名、栏目和正文链接 |
| 02 温和底色 | 浅砂金底色与边框，160–180ms | 管理导航、筛选、单一入口卡片 |
| 03 轻盈指向 | 箭头右移4px/180ms，卡片侧线；文字保留细线 | 策展、继续阅读和重点内容入口 |

不对普通正文或包含多个操作的整行添加点击假象。禁用控件保持不响应；键盘焦点用轮廓；真实hover仅在精细指针支持hover时启用；减少动态效果规则移除位移/过渡。本页“显示悬浮状态”用于比较终态，不是全局开关。不存储用户偏好，不更改现有导航或业务模块。

参考官方资料（2026-10-29读取）：

- [Carbon Link](https://www.carbondesignsystem.com/building-blocks/core/components/link/guidelines)：区分导航链接与执行动作的按钮，文字链接反馈有上下文区别。
- [Adobe Spectrum Motion](https://spectrum.adobe.com/page/motion/)：有目的的动效、重点入口少量箭头位移、支持减少动态效果。
- [Scottish Government Card](https://designsystem.gov.scot/components/card)：单一导航卡片与包含独立操作的内容卡片分开处理。

## 回车检索范围

新增web/lib/search-submit-key.ts，仅用于观点检索、向书库提问、研究继续提问、比较补充检索、命题重新检索的五个问题框。Shift+Enter仍换行；Ctrl/Meta/Alt组合键保持原义；isComposing/keyCode229选词时不提交；repeat长按不重复提交；原提交按钮disabled时不提交。沿用原范围、权限、原生校验与请求防重，不增加检索调用链。

已读首页HomeSearch、探索入口、catalog-search-workspace、discovery-search-workspace、site-header菜单及admin-shell全局检索：已有form/submit。原书内即时查找保持既有行为；文稿、私人笔记和编辑题目等普通textarea未改成回车保存。

## 验证与限制

- Node --experimental-strip-types --test tests/source-text.test.mjs：2项通过，文字/标点不改写、中文和英文断行、列表、段落、软连字符与空输入。
- Node --experimental-strip-types --test tests/search-submit-key.test.mjs：2项通过，正常Enter、disabled、重复键、IME、Shift/Ctrl/Meta/Alt保留。
- TypeScript --noEmit及Vinext构建退出0。无全量测试或检索质量评测。
- Web97实际1280宽比较页：三方案切换和固定悬浮终态截图、Tab焦点可见。示例Dialog x292.4/y138.75/w680/h442.5，margin自动，animation stl-dialog-enter/0.22s；原始换行切换、Esc关闭和焦点返回原按钮通过。
- 真实《国家的视角》书目“更多格式与选材”：显式靠右布局修复前后均x733.6/y105/w480/h591，未被强制居中，新增0.22s入场；只读来源，未加入/导出/保存。
- Web98回车检索后打开真实《国家的视角》PDF第4页上下文：窗口x152.4/y54/w960/h612（1280×720视口，页面含滚动条），animation stl-dialog-enter/0.22s，scrollWidth/clientWidth均958；封面/版本、出处侧栏和原始换行按钮实际显示，截图context-real-after.jpg。此处为文前版权页，不冒充原用户截图长篇中文的完整复核。
- 批注台iframe 1440/768/390/320布局无横向超出（客户区1425/753/375/305，含滚动条差值）；390/320示例弹窗实际宽339.2/268.8，内部scrollWidth等于clientWidth，关闭按钮和文字完整。截图属于本轮示例/指定页面，不代表206视图全部验收。
- 原用户检索页后来已离开；此前返回原查询时页面自动创建了一次检索。没有重新补索引或重复原DEEP-RUN-02。具体原上下文及所有特殊弹窗、真实IME硬件输入、系统减少动态效果切换仍B，不凭CSS静态记录称全部运行验收通过。
- 一次工具body键盘定位失败是自动化动作问题，未作为产品故障；通过明确按钮继续完成检查。

## 发布和恢复

Web97 social-theory-library-web:stl4-preview-20261029-r97，sha256:02e736e4260f2bbcd53adf9dc3cf6f279109d2c8c946a8e4d13b7b393d0eb988。
NAS interaction-r97-recovery保留前Web96受限.env及images.json。类型/构建/镜像/部署记录tmp/stl4-interaction-20261029，截图output/visual-review-20261029-interaction，均忽略不提交。部署验证后端、数据、OCR与模型容器ID不变，HTTP200，生产未改。Compose报告既有旧Paddle孤立容器，未借本轮删除历史环境。

18:26回车增补Web98已发布，SHA 92d4fd4ddf31fc909671bcdfeea45848646aadf1e05768bad4e32dedad3d128c，HTTP200，API/worker/数据/模型容器ID保持。NAS interaction-r98-recovery保留前Web97。真实首页Enter进入馆藏结果（本次52个混合结果/1作品）；观点入口Shift+Enter保留换行，Enter进入原文证据，已显示真实原文卡片。长任务仍按原状态显示，不以此宣称质量或时延通过。

本轮单次观点检索最终页面状态为“检索完成”，三个阶段卡片分别显示已获得1/153/16段原文（各阶段可重合，不求和冒充唯一条数）。已打开一个真实上下文并关闭，未加入研究、修改私人内容或导出。最终截图enter-evidence-after.jpg。

18:38另修复预览Web代理Host丢端口，nginx配置检查及reload退出0，全部活动容器ID与生产模板hash不变。恢复点interaction-redirect-recovery；与Web镜像回退分别处理，详NAS_REDIRECT_REVIEW_20261029.md。

Web回退仅从相应恢复点取LIBRARY_WEB_IMAGE更新预览Web/edge；不整份覆盖环境、不重启后端、不修改生产。全部继承脏文件继续保留。网络外围规则缺少证据，登记B待核实，不扩展为未经授权的网络变更。
