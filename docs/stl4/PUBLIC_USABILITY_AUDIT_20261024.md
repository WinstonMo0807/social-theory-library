# 首页与探索的无引导使用核验

2026-10-24。用户要求按8个一级分类使用grill-me自行追问，本子任务负责ATLAS_INDEX中“首页”9图和“探索”24图。先以普通访客/读者的实际目标追问，再查图、源码和接口；只提出服从终稿的小细节修正。本次仅新增本文件，没有改业务源码、提交、测试、浏览器操作、构建、业务请求或部署。

实际查看的是唯一终稿PDF提取原图 `tmp/pdfs/stl4-full-review-20261024/view-NNN.*`：首页10–18页，探索20–43页，共33张。没有使用CSV image_path里的旧图作为视觉依据。这里的“已读图/已定位源码”不等于实际页面几何、交互、权限或服务验收通过。

方法依据为[作者官方grilling规则](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md)，尤其环境事实由代理查明。用户本轮明确要求自行提问，因此将问题与源码答案一起记录；没有用技能的普通访谈流程要求用户再回答已能查明的事实。本任务不创建更多代理。

## 1. 本轮追问与结论

### 首页一轮

1. 第一次进站，不知道“原文/观点/提问”的差异，能否从搜索直接进入可用结果？已有 `HomeSearch → /explore?context=global&q=...`，全局结果另可转馆藏/观点入口；空馆藏及分区不可用有真实状态，不能拿终稿示例书籍填库。
2. 不登录能否了解使用方法、查看来源、提交问题？帮助/FAQ/来源说明均有真实入口；`PublicFeedbackView`是AllowAny，邮箱可选、显式同意、成功回执与未知结果重试均存在。无需把访问帮助变成注册前置。
3. 首页继续阅读会不会暴露上一个账号的资料？组件按owner展示并在会话变化时中止/清除；尚未实测多账号并发与退出。
4. 手机菜单打开后能否知道当前位置，并回到先前页面？SiteHeader/Drawer/返回位置服务已有入口和焦点/滚动恢复代码；实际触屏、键盘和滚动锁仍需统一运行核对。
5. 普通人从浏览器地址栏复制相关页面来纠错，是否必须会编辑路径？当前只接受相对路径，有轻微可用性摩擦，见U04；不影响不关联页面也可提交反馈。

### 探索一轮

1. 搜索后能否缩小范围、清除条件、切换版本并读到真实原页？馆藏工作台有URL保存筛选、分页、版本展开与真实阅读/下载入口；错误时保留关键词与条件。已定位相关API和正式发布资格过滤，未实际请求。
2. 只读书目与有公开文件，界面是否分清？CatalogResultCard/WorkDetailView从readable_asset决定阅读/下载；无文件有“仅书目/暂不可用”等说明，未见以登录代替不存在的全文。
3. 问题检索的范围能否由普通人选择？OpinionSearchEntry提供全部/主题/学者/文献及公开选项，未选有效范围不能提交；访客可检索，私人记录保存另按本人偏好。
4. 看更多结果、核对上下文、打开PDF，再回来，是否回到同一候选？同标签下有内存会话与片段锚点恢复；桌面强制新标签与此机制不一致，见U02。
5. 复制与引用无需登录，等待失败是否可恢复？匿名引用/清理接口开放；翻页引用按版本+页请求键失效旧响应，公共选材浮层重新核验来源。Reader两处调用缺少独立deadline，半开请求的恢复不足，见U03。
6. 第一次保存笔记/书签需要新账号时，注册后还能回到原页吗？登录链接带完整原页，注册链接漏传，见U01。
7. 并读是否把自动对应当成已校准？页面区分候选、无对应、增补与人工决定；保存默认私人，公共校准须另选范围和提交审核。真实加载、保存/恢复与手机状态尚未运行验证。

## 2. 优先修正的具体问题

### U01 / P1 注册入口丢失阅读位置

- 依据图：36、39–40，私人保存须登录，返回阅读位置应连续；18展示账户往返。
- 源码：`web/components/reader-shell.tsx:458`的gate中，“登录”使用完整 `readerReturnPath(...)`，而“注册读者”为裸 `/register`。`web/lib/auth-navigation.ts:safeAuthDestination`缺少next时回退 `/account`；`web/components/auth-form.tsx:14,47–50`注册后带该默认destination进入登录，最终返回账户。
- 普通用户路径：访客在某PDF具体页点击保存笔记/书签 → 选择注册读者 → 注册并登录 → 回到账户，原文页和来源返回路径没有传过去。已有用户走“登录”不受此缺口影响。
- 最小建议：gate内先生成一份当前 `readerReturnPath`，登录和注册共同使用；注册复用现有 `authPageHref('register', next)`。保留原安全白名单、物理页、准确来源参数和允许的return_to，不把选文/私人草稿放进URL。
- 验收待办：从PDF不同页、搜索命中、研究来源分别触发注册，核对登录后回同一Asset/页/来源返回入口。未执行。

### U02 / P1 桌面“返回候选位置”可能重新创建另一场检索

- 依据图：31的“打开阅读器：定位并可返回”，32要求保留已经取得的材料。
- 源码：`web/components/discovery-evidence-detail.tsx:76,103`通过 `CollectionLink`打开Reader；`web/components/collection-link.tsx:16–18`在桌面fine pointer强制target=_blank。`web/components/discovery-search-workspace.tsx:26,77,103`仅以模块内存Map保留会话id/token/已显示数量/排序，`returnTo:303`URL仅有原查询/范围和material锚点。新标签没有原Map，重新进入时调用 `createDiscoverySearch`，默认只显示3段。
- 普通用户路径：原结果查看更多或扩大范围 → 从较后面的候选打开PDF新标签 → 点击Reader“返回候选位置”。这条返回在新标签中可能重新查询，目标候选不在新结果首3条或结果身份已变化，无法恢复原位置。原结果标签仍保留，不能据此声称新标签返回已恢复原会话。
- 最小建议：需要return_to的证据阅读链接使用同标签导航，保留已有内存Map与锚点恢复；不要全局改变所有CollectionLink。若必须保留新标签，应提供明确返回原结果标签的机制，或设计服务端可授权的会话恢复。不能把匿名X-Discovery-Token写进URL，不能以重跑同查询冒充恢复。
- 验收待办：桌面/手机均在查看更多、扩大、排序后选择非首3条，打开阅读并返回；核对会话身份、候选、已显示范围、位置与登录变化后的权限复核。未执行。

### U03 / P1 Reader引用与清理请求缺deadline，网络半开时缺少恢复

- 依据图：22引用生成中、38复制加载中，40失败可重试；用户需要知道等待何时转入可行动状态。
- 源码：`web/components/reader/use-reader-citation.ts`读取 `/catalog/editions/{id}/citations/?pdf_page=...`只传组件AbortController；`web/components/reader/use-reader-selection.ts:cleanCopy`先等 `/catalog/clean-copy/`，没有超时，再进入已有本地清理/剪贴板兜底。`web/lib/api.ts:215`的apiRequest直接fetch，不提供默认deadline。引用的错误/重试入口依赖请求最终reject；cleanCopy本地兜底同样须等该请求结束。
- 普通用户影响：在半开连接下可能长期显示“正在读取本页引用”或复制无结果；重试入口不会按可控时间出现。直接系统复制有本地清理路径，不应写成所有复制都不可用。这与主线已修“HTTP环境缺Clipboard API”是两种问题。
- 最小建议：仅在这两个读取/清理调用合并现有30秒 `AbortSignal.timeout`，引用超时走现有错误+重试，清理超时走现有本地兜底。组件卸载、换页和账号变化的取消继续保留。不要全局改apiRequest、上传或长任务时限。
- 验收待办：引用/清理悬挂、超时后重试、等待时翻页、失败时原选文与当前引用身份。未执行。

### U04 / P2 纠错关联页面只能填内部路径

- 依据图：16关联相关页面，17来源暂不可用时提交纠错。
- 源码：`web/components/public/feedback-form.tsx:savePath`将输入直接交 `safeFeedbackPath`；`web/lib/api/feedback.client.ts:8`必须以单个 `/`开头；`SupportSourceStatus`也直接要求内部路径。读者从地址栏复制的完整同站https/http地址会被拒绝，界面要用户自己去掉域名。
- 最小建议：在客户端输入边界识别同window.location.origin的完整URL，取pathname+search再交现有safeFeedbackPath；依旧只提交清洗后的公开路径和Reader物理页，不改变服务端白名单，不接受外站、凭据、私人路径或令牌。可保留相对路径输入与现有提示。
- 这是小摩擦，不应因此阻断匿名反馈，也不需要新增页面选择数据库。实际普通用户操作未验证。

### U05 / P2 阅读失败页的“返回馆藏检索”实际到探索总入口

- 依据图：40来源失效/失败的下一步要明确。
- 源码：`web/components/reader/reader-route-failure.tsx:21`文案“返回馆藏检索”指向 `/explore`；无参数的ExplorePage返回三入口landing，不是 `/explore/original`馆藏检索。
- 最小建议：改指向 `/explore/original`；或者保留目标将文案改为“返回探索”。不在文件404时猜测原作品或暴露受限元数据。错误状态仍保留重试与本人笔记入口。

## 3. 每张实际阅读记录

下表每行均已打开对应 `view-NNN`终稿原图。记录的是图示行为和本轮查到的实现位置；“待运行”包括真实数据、移动触控、焦点、错误恢复与几何对照，不能解读为通过。

| PDF页 / ID | 本轮从图中追问的行为 | 对应源码或核验重点 |
|---|---|---|
| 10 R01-main | 不登录能从首屏搜索与内容卡开始吗 | HomeSearch/HomePublicView；公开查询与实际卡片链接，待运行 |
| 11 R01-sub01 | 学者/主题卡及“查看全部”去哪里 | HomeDiscoveryCards/HomeCuratedSection；实际slug，不以图例实体填库 |
| 12 R01-states | 空内容、缺封面、继续阅读和加载反馈可区分吗 | EmptyDiscovery/HomeContinueReading；owner、公开空态与分区不可用，待运行 |
| 13 R33-main | 搜索/阅读/引用三指南能进入实际帮助吗 | SupportHub/SupportGuides；帮助内搜索action、指南路由，待运行 |
| 14 R33-sub01 | 能理解访客与私人资料边界并继续了解吗 | about页面/帮助和隐私说明；未把访客阅读变成登录前置 |
| 15 R33-sub02 | 文章目录、复制示例与页码纠错能找到吗 | HelpArticlePage/SupportCitationExample；示意内容明确，反馈入口存在 |
| 16 R33-sub03 | 匿名反馈、可选邮箱、关联页面和回执是否真实 | FeedbackForm/PublicFeedbackView/submit；U04，同请求重试与输入保留 |
| 17 R33-states | FAQ无结果、来源不可用、提交成功有下一步吗 | SupportFaq/SupportSourceStatus；真实来源状态与可选反馈，U04 |
| 18 R34-sub04 | 手机菜单能关闭、找到当前栏目并回到来源位置吗 | SiteHeader/Drawer/usePublicNavigationReturn；焦点/滚动待运行 |
| 20 R34-main | 引用、研究/书单保存、导出是否各有身份与边界 | SharedCitationOverlay；匿名复制/导出、本机保存和本人目标区分 |
| 21 R34-sub01 | 成功与撤销是否基于真实保存结果 | overlay的run/fresh/原请求与书单回执；实际保存/撤销待运行 |
| 22 R34-states | 生成等待、失效、匿名本机、重复、部分导出可恢复吗 | overlay来源复核/manualCopy/localRows/exportRows与Reader调用，U03 |
| 23 MISSING-01 | 原文/观点/提问三入口能自行选吗 | ExploreLanding；三张卡实际route，首页查询进入全局结果 |
| 24 R02-main | 馆藏结果能直接阅读、下载、收藏吗 | CatalogSearchWorkspace/CatalogResultCard/SaveWorkButton；正式可读文件决定入口 |
| 25 R02-sub01 | 手机筛选可取消、应用、恢复当前条件吗 | CatalogFilterFields/mobile Dialog；URL条件、年份校验、公开facets，待运行 |
| 26 R02-sub02 | 一部作品多版本不会混淆正文吗 | CatalogResultCard版本表；各version对应asset/slug，待真实多版本样本 |
| 27 R02-states | 无结果/失败/仅书目仍能继续吗 | catalog空态/错误/重试与版本可用性；保留关键词/筛选，待运行 |
| 28 R03-main | 自然语言问题与范围选择无需口头指导吗 | OpinionSearchEntry/ScopePicker；示例只填问题，明确提交才进入结果 |
| 29 R03-states | 范围无效、访客、服务错误会不会清掉问题 | ready/范围Dialog/访客提示；后续检索错误仍原URL，待运行 |
| 30 R04-main | 原文摘要能看来源、读原文、复制和收藏吗 | EvidenceSummary/EvidenceQuote；当前引用服务核对来源，U02 |
| 31 R04-sub01 | 上下文、同书更多与Reader返回是否连续 | EvidenceContextBody/returnSessions/return_to，U02 |
| 32 R04-states | 部分结果、取消、失败、追加保留旧材料吗 | DiscoverySearchWorkspace/sessionAction/DocumentProgress；真实结果及任务状态，待运行 |
| 33 R10-main | 版本、收藏、书单、引用、分享入口可辨吗 | WorkDetailView/VersionTable/SharedCitationButton；具体版本独立链接 |
| 34 R10-sub01 | 文章题名/刊名/卷期/页码及本期目录是否分清 | WorkDetailView article分支/JournalIssues；真实公开关联，待材料核对 |
| 35 R10-states | 元数据缺失、无文件与可读版本是否清楚 | missing/sourceNotice/accessLabel/WorkContents；无文件不画可用下载 |
| 36 R08-main | 目录、物理页、选文、引用和个人记录能找到吗 | ReaderShell各面板与登录门槛，U01/U03；终稿布局待运行对照 |
| 37 R08-sub01 | 多级目录搜索/展开后能跳目标页吗 | prepareOutline/filterOutline/ReaderShell；主线正在修needs_review/几何，不重复记未修 |
| 38 R08-sub02 | 书内搜索、命中页、引用等待与复制能恢复吗 | useReaderSearch/validateReaderSearch/useReaderCitation，U03 |
| 39 R08-sub03 | 保存私人笔记与引用的位置会不会混淆 | useReaderRecords/当前选文citationPage/未知保存回执，U01 |
| 40 R08-states | 扫描/OCR/无目录/失败/撤下是否提供明确下一步 | ReaderRouteFailure、ReaderOcrStatus及页错误，U03/U05；权限不因提示放宽 |
| 41 R09-main | 两版本、独立页与同步是否指向确认对应关系 | ParallelReader/ParallelColumn；同步跟随人工对应，待真实版本 |
| 42 R09-sub01 | 手动候选/无对应/增补与私人保存可区分吗 | findCandidates/addAlignment/useParallelSave；原版本与source reference，待运行 |
| 43 R09-states | 版本缺失、私人笔记与公共投稿边界清楚吗 | savedSourceUnavailable/public calibration/明确scope与依据，待运行 |

## 4. 接口与权限的本轮事实

- `GET /catalog/search/`由现有公开检索服务和CatalogSearchWorkspace调用；目录结果以作品整合版本，结果/筛选在URL中保留。未请求服务，不报告召回质量或计数正确率。
- `/catalog/discovery-search/`、详情、扩展、取消、重试和上下文沿 `DiscoveryView.permission_classes=[AllowAny]`，匿名会话令牌通过X-Discovery-Token传递，不能放URL。重新读取还复核当前公开来源，前端会话变化清除原结果与上下文。
- Reader manifest/page/search/focus继续使用原正式来源身份；useReaderSearch验证asset/document_revision，未知几何不伪造精确定位。目录待复核统计和旋转几何由主线实施中，本报告不将其重复列为待修发现。
- `CitationView`和`CleanCopyView`为AllowAny。前者从当前公开出版版本及对应物理页生成引用；共享选材预览另走来源重新核验。能调用不等于引用内容或纸本页码已人工核对。
- 收藏/书单/笔记/对齐保存使用本人会话和owner边界，匿名时提供登录或明确本机保存。SaveWorkButton的重试先读取当前值；共享浮层的来源核验、原请求和未知结果恢复已存在，尚未真实并发运行。
- `POST /catalog/feedback/`为AllowAny，显式用途同意、可选邮箱、request_id幂等和真实回执。后台反馈处理限管理员。公开来源状态走 `/reading/source-status/`匿名解析，不转送私人上下文。

主线已完成的HTTP安全请求编号与Clipboard缺失时手动复制，在本轮源码已见复用，不列作新问题。首页策划人头像/署名、目录校准的正在实施改动同理。本次没有发现需要改权限、换技术栈或增加解析模型才能解决的前台阻断。

本轮建议优先按U01–U03做小范围修复；U04–U05为可顺手处理的输入/文案目标细节。最终仍需用户允许的统一验收覆盖匿名和登录、首次注册、手机、键盘、无内容、服务失败、来源变化及新标签往返；33张实际读图记录不代表33张实施页面已验收。
