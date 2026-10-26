# STL 4.0 内网候选与公网切换前门槛

## 2026-10-27 03:43 整书OCR完成，目录页定向核对继续

原任务cd28e58a已成功保存170/170页，03:43:24完成；自动目录任务29c23598和页码任务be283768成功，目录修订2e2aef9f为outline-v7自动候选、未采用。新Discovery派生任务d61e9223运行中，不开展检索质量评测。原公开文件仍保留，不能把识别成功当作目录正确或已公开。接下来仅重识别目录物理页7–13，以替换开头沿用旧引擎的目录结果；另两书不OCR。

03:22预览PostgreSQL的256MiB上限确实发生一次OOM，117页已保存。查询EXPLAIN没有JIT证据，未改SQL或禁JIT。仅预览compose及活动容器内存提高512MiB，无重启/表结构变更；旧compose留在guest-records-recovery。确认四worker空闲后用既有recover_stalled_processing_jobs仅恢复原任务，未直接改状态/删锁，随后152→170。03:40 memory.events仍oom=1/oom_kill=1，无新增；真实中断不能写成全程稳定。

实际视觉批注台/admin/visual-review已恢复最终PDF读取：NAS参考副本权限只允许API实际uid100/gid101读取、挂载保持只读。原ACL备份保留；Windows最终PDF不变。画线+文字+视口保存、刷新后打开回读均成功，截图tmp/stl4-rapidocr-20261027/review-saved-r77.png。本条测试批注明确不代表首页视觉验收通过。

视觉收尾VISUAL-74进行中：实际看过唯一PDF10/23/45/62/68/73/80/183与内网对应入口，首页/学者/主题二级标题字重及PDF73策展首页文案、首卡、品牌、手机筛选存在明确差异。理论流派控件及后台关联补原JSON元数据/正式发布投影，不建新表。Web类型及构建退出0；聚焦测试先定位到原序列化模块循环导入，最小移出共用策划者Serializer，旧用例原始对象改走实际公开投影调用后复测中。严格OpenAPI生成退出0。仍未更新内网r45/Web77，不能把本地修改称已上线。


## 2026-10-27 03:14 访客转存已更新内网候选

API及四worker r45（067a879d3d03）、Web r77（8eb97807a375）、RapidOCR r3已运行。reading0028增量迁移完成，4个账号身份/密码哈希/角色摘要与更新前一致。更新8fa9ab→c331a6退出0；首次被正在执行的定时健康检查阻止，随后临时停预览beat、确认四worker空闲后完成，beat已恢复。生产不变。

PDF186访客勾选转存已接真实本机公开阅读/文章/检索记录和本人导入接口，详情GUEST_RECORDS_20261027.md。初轮API9项、追加文章1项、本机存储2项通过；Web类型、构建及严格OpenAPI生成退出0。实际/login已显示真实空态、默认未选且禁用的转存框；没有伪造浏览记录或读取私人资料。实际账号登录转存仍B待验收。

预览数据库备份guest-records-recovery/before-reading-0028.dump已读回归档目录（12,666,535字节），环境及账户摘要另存；尚未恢复演练。OCR原任务在98/170安全暂停后继续，同一任务保留已保存页，完成数继续按管理端实际回读。另两书不OCR。全站精确视觉、整书/目录及公网前运行门槛仍按各自证据记录，不宣称全部验收。


## 2026-10-26 原文证据中英文界面控件已更新内网

前置3e8307f4。依据唯一PDF30–32及原VISUAL-09缺口，页顶按图补中/EN，原品牌、搜索和账号入口保留。界面偏好只存浏览器且只在原文证据路由启用；切换不改URL、查询请求或会话键。结果、筛选、摘要、上下文、文献进度，以及在此页打开的收藏、引用浮层和手机菜单固定文案同步。书目、人物、原文、引句、备注和服务返回的未知自由文本保持来源原样，不调用翻译服务、不改变引用导出内容。该范围不是全站英文版。

类型2edbc4→fa8cb9及最终类型/编译7b6d3e→86cdf0退出0。静态文案核对0eac4f确认所引用的固定字典键无缺项。包2461文件49273497字节SHAfb901f7430e617c950c0d9abb5eb270c88a75ffeb3d207a233c912f7b415fa71。镜像682983→fe30ad退出0；更新f32b0e退出0，Web r72 99f99b683302，API r35 5751eefa1c51/worker r33保持。恢复点.env.before-language-r72（Web71/API35）。未运行测试、提交检索/业务表单、模型评测、迁移或公网切换。

只读查看无q的/explore/evidence；观察中/EN显示和390px布局，最后恢复中文。evidence-r72-zh-desktop.png、evidence-r72-en-desktop.png、evidence-r72-en-mobile.png、evidence-r72-zh-mobile.png保存在原tmp目录。语言切换仅改本机显示；没有创建检索或用示例材料冒充实际结果。

D关闭中/EN固定界面切换的开发缺口。有材料时的完整排版、未知服务通知和所有业务操作B待统一验收；精确字体几何及PDF186访客记录勾选转存原有A继续。

## 2026-10-26 OCR问题文字高亮与完整修订差异已更新内网

前置e1a69318。唯一PDF109–111为依据。OCR正文和原文比较显示实际乱码字符；已有OCR段落低置信度只在原始块文本与当前页逐字一致且有有效评分时标出，不推断字框、不把缺失评分当错误。手工改稿不沿用旧置信度。Unicode码点区间通过原工作区详情返回，前端只渲染文本mark；修订差异保留完整换行及Unicode字符，避免原按行拆合吞掉换行。未修改识别任务或保存发布接口。

Python AST 2d6da7、类型455abf→5c3110及最终类型/编译9327ef→7dff10退出0。包2452文件49232340字节SHA07de6b04cf174560477e0f29377a36a130d961822770e53cbfbc72a19481170b。首次镜像构建触发125层上限，保留原镜像，将API r34整理为单层r34-flat 5abe13aaadd4，逐项核对运行配置一致后重建成功；未清理数据或运行容器。最终镜像只读检查ca35bc确认API r35 5751eefa1c51/Web r71 415c6e2aeba9存在。更新8c171d→67c6df退出0，b295ca确认新Web/API运行、API健康。worker保持r33。恢复点.env.before-ocr-spans-r71（Web70/API34）。未执行测试、真实OCR任务、提交校改、迁移或公网切换。

D关闭109–111实际问题区间显示与差异换行的开发缺口；真实文件高亮、修订保存/发布和有数据视觉B待统一验收。字体及精确几何不以本批构建认定完成。下一项为原VISUAL-09登记的PDF30–32中/EN界面控件，原文/用户内容不得翻译或改写。

## 2026-10-26 人物作品职责页内编辑已更新内网

前置32fd0537。依据唯一PDF138，人物作品列表补真实封面、职责控件和原发布状态。展开职责读取原具体版本工作区，保留全部其他贡献者/顺序/scope，仅修改此人物职责，提交原workspace edits接口，沿edit_version/原权限/事务/请求回执与正式发布流程，不新增保存服务。字段选项与原编目共用。人物规范与作品职责分别保存，编辑职责时暂停其他人物输入与切栏；未确认请求沿原书目恢复入口核对，未调用发布。封面只读使用已有媒体版本/原封面，无示例作品。

类型26d682与e77134退出0，Python AST c791c5完成，编译a3bf74→207fae退出0。包2447文件49221928字节SHAd4bfb50c5f5a420b40a100e5c090bc98c055c874458a4d55d999d7567fe187e5。镜像99e7ab→ccec36、更新f58d44→7b3f5b退出0。Web r70 e7365894a4ae/API r34 0594ebfc37bf；worker保持r33。恢复点.env.before-roles-r70（Web69/API33）。未执行测试、真实职责保存/发布、迁移或公网切换。

D关闭138作品列表职责控件及原保存链开发缺口；真实有作品列表、职责保存、版本冲突恢复与发布B待统一验收。没有虚构人物/作品来制造截图通过。继续109–111已有问题文字高亮与逐图差异，字体和精确几何未以本批编译认定完成。

## 2026-10-26 人物照片与生平资料已接入并更新内网

前置6fb867ce。实际读取唯一PDF138。补右侧人物照片与生平资料区，三图缩略/说明/翻页/移除关联复用原媒体库card版本；原比例、出处与素材原件保留。人物命令的版本/预览hash/确认/审计保持，同一ScholarProfile.curation保存资料，经原编辑草稿与发布流程；已有其他草稿仍要求先处理，不覆盖。媒体清单及EditorialRevisionMedia保护当前/草稿/历史关联，无新增表或迁移。标题说明、基本信息小标题和生卒年同行按原图调整。

五个Python AST ea613d完成，类型dbfb84→d7af2a退出0，最终类型及编译62d075→200c07退出0。包2439文件49209145字节SHA03dbfd04fed7c553d2a9e68825298ecb0bcdd06cee47ebdf3672bd7887771e9f。镜像d69148→b6498f、更新0e9b4f→d17f67退出0；初次active检查发现一项任务而延期，四节点为0后更新。Web r69 a3128249999f/API与worker r33 892dd3d43f3a；恢复点.env.before-materials-r69（Web68/API32，worker31）。未测试、上传图片、提交表单、迁移或公网切换。


只读实际/admin/people?new=1桌面与390px手机，person-r69-desktop.png及person-r69-mobile.png已保存，资料区与生卒年同行可见。未创建人物；有图状态未伪造，仍B。

D关闭138资料区控件与保存链开发单元；真实人物图片、保存/发布与媒体版本恢复B。A同页贡献者职责仍只有原书目跳转，继续接原编目草稿流程。字体/几何与其他已登记图像差异不据本批关闭。

## 2026-10-26 人物研究领域与检索一级栏目已更新内网

前置41ee7af7。唯一PDF138与119为依据。人物基本信息补研究领域标签，读写同一ScholarProfile；无学者档案时经原创建权限/Serializer建立同人物草稿，已发布档案保存为原编辑草稿。版本/预览hash/人工确认/审计沿原人物命令，无迁移。检索维护保留原八个路由标签，按PDF收拢为五个一级栏目；词表与版本工具为下级入口。

Python AST2完成；类型b1189a→333837退出0。build-person-r68.log已显示Build complete，原会话结束后退出码未保留，不补称已取得退出码。包2432文件49174511字节SHA785cddf74a48e7e9180e7b9d4cbf05143d4122f0eebe72480472f00a73cc9234。镜像8b143f→6438a1、更新647845→677687退出0。Web r68 5758fb68d2c4/API r32 c4e719c20251，worker保持r31。恢复点.env.before-person-r68（Web67/API31）。只读index-r68-desktop.png确认五个一级栏目与七项范围可见；更新过程短暂502在容器就绪后已恢复。未运行测试、提交业务表单、迁移或公网切换。

D关闭研究领域字段链与检索一级导航开发单元；真实档案保存/发布和有数据视觉B。A138照片与生平资料区及贡献者页内职责仍待实现，继续按已有具体差异收尾。

## 2026-10-26 七项检索范围已接入并更新内网

前置5eab384f。唯一PDF119再次读取。七项范围按钮接原Discovery请求、本人查询回执与结果恢复。书名/作者限定已有索引字段；正文/注释/主题写入同一分块的独立可检索字段，正文排除已有明确注释/页眉页脚段，注释仅来自解析器已有明确类型及原文精确位置，不猜测注释、不改原文。中英文术语复用原QueryLexicon已确认、可展示、无歧义的中英对译。全部范围保持原稀疏/向量融合、重排及深度方案；指定字段仅在该字段召回，不用跨字段深度结果混入。旧索引字段不足时明确提示更新，未自动重建或运行检索评测。

6个Python AST与类型c98dcd→9be836退出0；编译8191a0→cb7354退出0。包2422文件49168421字节SHA0e0cc1705efd9cf03c2b021c277f9f0759c61309705e6e2a0b84eedd36c7f30d。镜像ce3250→41220b、更新49c039→9bf04e退出0；四节点active为0后Web r67 5f8e22e8ded5/API r31 6a68e20a1010及普通/入库/Discovery查询/索引worker同步。恢复点.env.before-scope-r67（Web66/API30；Discovery此前版本按原容器记录恢复）。只读实际检索维护页截图index-r67-scopes-desktop.png，七项可见。真实公开馆藏0，不填示例，未提交查询/重建索引/业务操作/运行测试/迁移/公网切换。

D关闭七项范围控件与后端请求链的开发单元；真实原文分类覆盖、匹配结果和有数据视觉B。A同页实际八个并列栏目仍与PDF119五个一级栏目不同，应将词规则/中英/异名归入检索词管理、增量/旧版归入索引与任务；仅调整原导航分组，功能与路由保留。人物138与原有其他具体差异继续。

## 2026-10-26 补页结果接入阅读版本与章节定位已更新内网

前置8f28a431。唯一PDF118再次逐图读取。生成副本与采用流程共用确定的页序映射；采用已回读核对的副本时新建阅读资产和页面身份，目录起页、印刷标签与已确认章节责任的发布快照同步映射，原文件/旧正文/原人工责任记录保留。未上架版本采用仍需正式上架；已发布版本沿原发布事件完成后切换。发布预览显示旧→新页序、插入页、最终分段与总页数。仅明确补入且无文本的空白页不计作缺失OCR正文，不生成原文证据。无数据库迁移。

6个Python AST edcdb6退出0；类型4385f1→4b1b6f退出0；编译af9dc4→3c8e09退出0。包2418文件49150537字节SHA49a2aef8e69c0a4533dbbc9d605e56f1aa116496fcd3affc750037275f681a3b。镜像5b2573→e96c58、更新a3cb94→26a69e退出0；四个Celery节点active均0后更新。Web r66 693ece192ccb/API与worker r30 edfa6974ba6c；Discovery worker保持原版本。恢复点.env.before-mapping-r66（Web65/API29；worker此前API28）。未执行测试、真实副本生成、采用发布、迁移或公网切换。

D关闭118补页副本进入阅读版本的开发单元；真实文件、发布恢复、章节定位和有数据视觉仍B。A119–121检索范围控件、138研究领域/资料与贡献者等已登记差异继续，不以本批关闭代替全站验收。

2026-10-26 当前Web r65 2f5177ca57e9/API r29 9c91a6dcd3c9，worker r28；恢复点.env.before-index-r65。仍有视觉A和业务B，尚未公网切换。

2026-10-26 当前Web r64 7fdb24e8601b/API与worker r28 7715bcf53638，恢复点.env.before-mapping-r64。视觉A与业务B仍保留，尚未公网切换。

2026-10-26 当前Web r63 ae6ec6af5eb4/API r27 0fc4693adbb0，worker API24；恢复点.env.before-management-r63。视觉A与业务B仍保留，尚未公网切换。

2026-10-26 当前Web r62 e395bd9ad6bd/API r27 0fc4693adbb0，恢复点.env.before-reader-r62；其余视觉A及业务B仍保留，不可公网切换。

2026-10-26 当前Web r61 a5ecd8c18c3d/API r26 d67210db72a0，恢复点.env.before-private-r61。视觉A与业务B未全关闭，不可公网切换。

2026-10-26 当前Web r60 9982905f64a6/API r26 d67210db72a0，恢复点.env.before-booklists-r60。视觉A和业务B仍有剩余，不可公网切换。

2026-10-26 当前Web r59 e7ac65f951b6/API r25 928fd07a8c5e，恢复点.env.before-notebook-r59。视觉A和业务B仍有剩余，不可公网切换。

2026-10-26 当前Web r58 3687cd1b98a4/API r24 22b9d3045bfb，恢复点.env.before-citation-r58。视觉A和业务B仍有剩余，不可公网切换。

2026-10-26 当前Web r57 f84e25e507ca/API r24 22b9d3045bfb，恢复点.env.before-memory-r57。视觉A及业务B仍有剩余，不可公网切换。

2026-10-26 当前Web r56 c3466f464596/API r24 22b9d3045bfb，worker/ingestion-worker/beat同步API24；恢复点.env.before-plans-r56。仍有视觉A及业务B，不可公网切换。

2026-10-26 当前Web r55 e145af50117e/API r23 e1126ae674ea，恢复点.env.before-analysis-r55。仍有视觉A及业务B，不可公网切换。

2026-10-26 当前内网Web r54 a013dfbec7e9/API r23 e1126ae674ea，恢复点.env.before-research-r54。尚未最终视觉与业务验收，不可公网切换。

2026-10-26 当前内网Web r53a f8f600340f69/API r23 e1126ae674ea，恢复点.env.before-auth-r53a / .env.before-auth-r53。尚未最终视觉与业务验收，不可公网切换。

2026-10-26 当前内网Web r52 daac797ae863/API r23 e1126ae674ea，恢复点.env.before-reader-r52。原账户及私人资料服务保留，未公网切换。

当前内网Web r51 2bae11bf0926/API r22 079485e17f55，恢复点.env.before-sharing-r51。引用/分享视觉批次，未业务提交与公网切换。

当前内网Web r50 53c34c7f9567/API r22 079485e17f55，恢复点.env.before-placement-r50。内容编排批次，不表示正式验收/公网就绪，生产未改。

2026-10-26当前：Web r49 25577fe7a641、API r21 bd0fb9058351。恢复点.env.before-home-r49（r48/API20）。未公网切换。

2026-10-26当前：Web r48 8106d7d82983、API r20 ba142dd9633b。恢复点.env.before-recovery-r48（r47/API19）。未公网切换。

2026-10-26当前：Web r47 a6b24d849d49、API r19 b89a5d48247b。恢复点.env.before-storage-r47（r46/API18）。未公网切换。

2026-10-26当前：Web r46 3592f7ba5d3d、API r18 1cfffebce14a。恢复点.env.before-services-r46（r45/API18）。未公网切换。

2026-10-26当前：Web r45 3ad8f787e1fc、API r18 1cfffebce14a。恢复点.env.before-accounts-r45（r44a/API18）。未公网切换。

2026-10-26当前：Web r44a c7557636a481、API r18 1cfffebce14a。恢复点.env.before-path-r44a（r44/API18）及.env.before-path-r44（r43/API18）。未公网切换。

2026-10-26当前：Web r43 1a6073db31ab、API r18 1cfffebce14a。恢复点.env.before-timeline-r43（r42/API17）。未公网切换。

2026-10-26当前：Web r42 cf212589bdae、API r17 f2e053e02288。恢复点.env.before-topic-r42（r41/API16）。未公网切换。

2026-10-26当前：Web r41 528ad31ab305、API r16 f20c1c710e00。恢复点.env.before-concept-r41（r40/API16）。未公网切换。

2026-10-26当前：Web r40 797ef6dcfc4a、API r16 f20c1c710e00。恢复点.env.before-scholar-r40（r39/API16）。未公网切换。

2026-10-26当前：Web r39 1503378cc175、API r16 f20c1c710e00。恢复点.env.before-people-r39（r38/API16）。未公网切换。

2026-10-26当前：Web r38 1f364bf0fafd、API r16 f20c1c710e00。恢复点.env.before-ledger-r38（r37/API16）。未公网切换。

2026-10-26当前：Web r37 b2ed4df43478、API r16 f20c1c710e00。恢复点.env.before-publication-r37（r36/API16）。未公网切换。

2026-10-26当前：Web r36 fa1afb2822cd、API r16 f20c1c710e00。恢复点.env.before-selection-r36（r35/API16）。未公网切换。

2026-10-26当前：Web r35 8a91b6236cd2、API r16 f20c1c710e00。恢复点.env.before-editor-r35（r34/API16）。未公网切换。

2026-10-26当前：Web r34 7bab48258801、API r16 f20c1c710e00。恢复点.env.before-curation-r34（r33/API15）。未公网切换。

2026-10-26当前：Web r33 `30d330e78189`、API r15 `675dde21d90d`。恢复点.env.before-index-r33（Web r32/API14）。未公网切换。

2026-10-26当前：Web r32 `01a8c1f58d18`、API r14 `25d1279a0b31`。恢复点.env.before-mapping-r32（Web r31fix/API13）。未公网切换。

2026-10-26当前：Web r31fix `97d23811e254`、API r13 `cd535d9368d5`。恢复点.env.before-outline-r31（Web r30/API13）。未公网切换。

2026-10-26当前：Web r30 `e4fb18c4b037`、API r13 `cd535d9368d5`。恢复点.env.before-ocr-r30（Web r29fix/API13）。r29初版/r12已知有错，不作恢复目标；未公网切换。

2026-10-26当前：Web r29fix `852fde4ff8ee`、API r13 `cd535d9368d5`。恢复点.env.before-processing-r29fix/.env.before-processing-api-r13。r29初版/r12查询修复均已被后续替代；未公网切换。

2026-10-26当前：Web r28 `32bbd471a3d9`、API r11 `1bee6941612c`。恢复点.env.before-media-r28，未公网切换。

2026-10-26当前：Web r27 `b27fbcc3b578`、API r11 `1bee6941612c`。恢复点.env.before-assistant-r27，未公网切换。

2026-10-26当前：Web r26 `0195de274f06`、API r11 `1bee6941612c`。恢复点.env.before-files-r26，未公网切换。

2026-10-26当前：Web r25 `913af890fb3b`、API r10 `a79b2b97f68d`。恢复点.env.before-editor-r25，未公网切换。

2026-10-26当前：Web r24 `271b389ee5fb`、API r10 `a79b2b97f68d`。恢复点.env.before-manual-r24，未公网切换。

2026-10-26当前：Web r23 `af5bb793ad24`、API r10 `a79b2b97f68d`。恢复点.env.before-intake-r23。无公网切换。

2026-10-26当前：Web r22 `7e986bde778b`、API r10 `a79b2b97f68d`。恢复点.env.before-upload-r22；未公网切换。

2026-10-26当前：Web r21 `d652f13d7815`、API r10 `a79b2b97f68d`。恢复点.env.before-admin-r21，r20保留；无公网切换。

2026-10-26当前：Web r20 `0c4a6c9d20b1`、API r10 `a79b2b97f68d`。恢复点.env.before-editorial-r20，Web r19/API r9保留；仅隔离内网，未公网切换。

2026-10-26当前：Web r19 `06d4ecd85426`、API r9保持。恢复点.env.before-topics-r19，r18保留；隔离内网更新，非整站验收/公网切换。

2026-10-26当前：Web r18 `d46cca8dc3d9`、API r9保持。恢复点.env.before-scholars-r18，r17保留；仅隔离内网预览更新，不是完整验收或公网切换。

2026-10-26当前：Web r17 `03a22da36188`，API r9 `f95578893171`，Discovery r2保持。恢复点.env.before-reading-path-r17；r16保留。仅隔离预览更新，不是完整验收或公网切换。

2026-10-26当前：Web r16 `91783fe867e3`，API r9 `f95578893171`，Discovery r2保持。恢复点.env.before-graph-timeline-r16；r15保留。只是隔离预览视觉更新，不是公网切换或完整验收。

2026-10-26当前：Web r15 `588ed651b3c1`，API r9 `f95578893171`，Discovery r2。概念/流派详情本批视觉已部署；真实有数据详情未验收。恢复点.env.before-theory-detail-r15，前Web r14保留。未测试、业务写入、迁移或公网切换；下文旧版为历史。

2026-10-26当前：Web r14 `8fcaae75e65a`、API r9 `f95578893171`、Discovery r2。PDF41–43并读和45/50/51总览/子学科本批源码修正已部署；真实空库总览桌面与手机已只读查看。最新备份.env.before-theory-r14；上一Web r13 3c1810b6c241保留。未测试、迁移或公网切换；下文旧版本为历史。

2026-10-26当前：Web r12 `c52c2124ad41`、API r9 `f95578893171`、Discovery r2。PDF36–40 Reader本批视觉修正已更新；账号/数据库/批注保留。最新恢复点.env.before-reader-r12，上一Web r11 8bf383419b1e仍保留。仅隔离Web更新与Edge重启；无测试、迁移或公网切换。下文均为历史记录。

2026-10-26最新：API r7 `36667a3509da`、Discovery r2、Web r8。仅探索/馆藏/观点视觉和facets.total投影更新，原账号、批注和数据库保留。恢复点.env.before-web-r6、.env.before-catalog-r7、.env.before-web-r8只留NAS。下文r5等均是历史，不能覆盖当前。公网未切换。

2026-10-26当前：API r6 `57c1db0af199`、Discovery r2、Web r5 `0fdefd11deb0`；R33视觉更新，已有数据/13服务保留。最新操作和恢复见VISUAL_FIDELITY_20261026.md与RECOVERY.md；下文初始候选摘要是历史，不能覆盖当前版本。公网切换仍未执行。

2026-10-26。当前是可交互内网候选，尚不能声明公网切换就绪。不得把 B 待验收改成新的开发欠项，也不得跳过既定验收后直接切换公网。

## 2026-10-26 当前修正候选

用户已实际登录，并明确允许浏览器只读截图对照。当前前端被确认不符合PDF，存在VISUAL-01–04修正项，详见VISUAL_FIDELITY_20261026.md。内网不是仅供参考的静态草图，也不是已经完成的视觉终稿。

隔离项目保留原数据，c4792f更新至API r5（3c9dc1b5ac11fbd4c7527ed2846452c372f8ae6406ee3d3d2403cff81205f265）、Discovery r2（62edb5c0010d4c6956e04d9e1f3010dcda4e2a8ab72148d6f139f609688277bd）、Web r2（170e2f693b8541189fb43c890ff69051a69bc2570872cbfccebbd055bd072d9c）。其余镜像未变。深度bundle只读挂载，查询主开关仍false；未调用模型或运行检索测评。

现在Compose文件顺序在下文四文件之后再加`-f compose.stl4-deep.yaml`。恢复使用当前`.env`；前版保存于`.env.before-deep-r1`，它含凭据不得输出或提交。下一轮仅替换Web，不能重复运行首次深度环境准备脚本或重建数据库。

Web随后由de295f更新为r3（5f6857a52fb7），只替换Web与重启预览Edge；当前恢复以`.env`中r3为准，r2记录为上一视觉候选。

## 可交付入口

- 网站：`http://192.168.5.6:18084/`
- 交互、绘图及批注：`http://192.168.5.6:18084/admin/visual-review`
- 账号：原有4个账号的隔离副本，使用原密码；不创建替代账号或重置密码。原生产账号和库保持。
- 参考：只读挂载用户指定 final-r2 PDF，目录209视图，其中206个B、3个按D010排除。

接口就绪和预览入口已返回200，嵌入头为SAMEORIGIN。没有浏览器检查、实际登录、批注写入或业务测试；页面保存、真实文件转换、OCR、检索和精确视觉仍须验收。

## 当前运行候选

NAS项目 `stl4-preview-20261026-r1`，目录 `/volume2/library/stl-previews/20261026-r1`。13个容器包含API、Web、Edge、PostgreSQL、Redis、Meilisearch、普通/入库/检索查询/索引Worker、OCR、Discovery推理、DOCX转换。Beat和公网网关未启动。

| 镜像 | 当前摘要 |
| --- | --- |
| API `social-theory-library-api:stl4-preview-20261026-r3` | `sha256:44944438072fef9b7fadc47fb6da97a9cb814a52ca6ac93edb43938b4770a14b` |
| Web `social-theory-library-web:stl4-preview-20261026-r1` | `sha256:5e9b78fe92358b2e9504b1e07a77c82ce3f63b9c5768134df5d1be8476fa6c30` |
| OCR `social-theory-library-paddleocr:stl4-preview-20261026-r1` | `sha256:33c318ef3b62a061c0fd16ddd86ade329b25c8801c9263b9302e2f6c93a5ac3b` |
| Discovery `social-theory-library-discovery-inference:stl4-preview-20261026-r1` | `sha256:4f14d26b3d05c6993c5d4f80ecde831756b38c2fc2306f157745e17d2cc75754` |
| DOCX `social-theory-library-docx-preview:stl4-preview-20261026-r1` | `sha256:56d6d5c860641c43cb1b8b991fc409c3d34e11a8dc74317bda881ab2d0693ac7` |

使用已准备的10月24日依赖升级包，Node24.22.1、Nginx1.30.6。API readiness仍显示源码中的旧APP_VERSION=3.0.8.1，识别本次候选应使用上表摘要及源码清单；版本文案在正式发布元数据阶段统一，不据旧文案误判运行了旧源码。

OCR预览构建使用临时派生Dockerfile，仅未执行原构建中的数值自检，以遵守不测试要求。原 `offline/ocr.Dockerfile` 与数值断言完整保留；该预览镜像不能替代正式发布所需的运行验证。没有识别样书、模型基准、第三步质量评测或实际DOCX转换。

Discovery当前启用原首屏E5/mMARCO运行服务；首选方案的EG2/BGE/ConvMemory深度阶段已有源码，实际bundle/generation尚未在本预览启用。不能把首屏服务启动记作深度阶段已经可用，也不重开评测开发。

## 数据、迁移和恢复记录

源库只读快照：`evidence/source-database.dump`，SHA256 `aa610123d030572c22b856944fa4b4c4455110b6734391ecb407116177faa2cd`，保留于上述NAS目录，权限0600。恢复后只对预览副本执行迁移；生产未写入、未重启。4个账号的ID、邮箱、密码哈希、角色、激活/管理标记、token_version合成摘要与源库一致；没有输出账号详情或凭据。

实际源码初始清单为1776文件，包含工作区原未提交实现；补包 `source-delta-r2.json` 登记24个补充/修正输入，包括初次打包漏掉的Nginx模板、三份研究提示词及媒体组件源码。Web dist来自完整本机源码构建。该补包失误属于预览制备过程，未计为原产品缺陷。

`evidence/preview-migrate.log`保留第一次旧迁移分支冲突；`evidence/preview-migrate-r2.log`记录修正后迁移完成至catalog0089、reading0027等当前末端。构建日志分别为api-build-r3.log、web-build.log、ocr-build.log、discovery-build.log、docx-build.log。初次失败镜像与日志保留，不用失败记录冒充成功。

恢复当前预览时使用以下文件顺序和项目，不能改成生产项目名：

```sh
cd /volume2/library/stl-previews/20261026-r1
sudo docker compose --env-file .env -p stl4-preview-20261026-r1 \
  -f compose.yaml -f compose.discovery.yaml -f compose.stl4-preview.yaml -f compose.docx-preview.yaml \
  --profile tasks --profile ocr --profile docx-preview \
  up -d --no-build api worker ingestion-worker web edge paddleocr docx-preview \
  discovery-inference discovery-query-worker discovery-index-worker
```

若仅停止预览，沿同一项目及文件组合执行 `stop`，保留数据库、批注、文件与镜像。禁止删除卷或把预览数据自动同步到生产。

## 公网切换前仍需完成的 B 项

1. 全站按8个一级分类统一验收，覆盖明确PDF布局/交互、B01–B06、公开与私人权限；本轮未运行。
2. 实际登录、批注保存、上传→编目→处理→发布→Reader及私人资料的业务闭环；确认正常空库行为。启动健康不能代替它们。
3. 实际OCR、DOCX分页、所需深度模型制品/独立generation及服务资源条件。使用已确定的检索方案，不增加第三步检索质量评测。
4. 原生产配置的模型/文件/邮件/OAuth/域名与新接口接续，公网和内网管理的预览嵌入策略；缺少实际配置或作用路径证据的项不推定为源码缺陷。
5. 以最终候选准备新鲜生产备份与实际回退证据。此次成功恢复的是预览副本；旧镜像在新schema上写入的兼容性未验收，不能承诺仅切回旧镜像即可完整回退。
6. 形成明确的切换影响和恢复安排后取得最终确认。当前没有执行公网切换或生产不可逆清理，不因有预览URL而视为获得批准。

以上是原有交付责任和验收条件，不是新增功能清单。只有验收或源码证据证明符合A条件时才回到针对性修复。
