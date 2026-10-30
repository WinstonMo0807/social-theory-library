# 2026-10-30 导航参考、反馈选页与原文优先

本轮只处理用户连续三条批注，沿用 A 排版、现有 Logo、字体与业务接口。最终 PDF 第 10 页原图已实际读取，用于核对首页的主推策划与三张次级卡片。导航新方案只放在参考页，未改实际首页默认布局。

## 本轮范围与证据

| 编号 | 具体证据与操作 | 最小实施范围 | 当前状态 |
| --- | --- | --- | --- |
| HOME-LAYOUT-02 | 用户要求把导航放到顶端，并查看有图片及第 2—4 期策划的首页状态 | `/layout-preview` 复用 `HomePublicView`，仅该路由可切换当前布局、导航顶行、Logo 同行；策划样例明确标注，不写数据库 | D 已实现，定向读回完成 |
| FEEDBACK-PICKER-01 | `public/feedback-form.tsx` 的关联窗口只有地址输入，正常读者必须寻找网址才能选择具体页面 | 常用页面选择、现有公开目录按名称查找、书籍阅读页和 PDF 页码、保留手动网址；提交仍用原 path 字段和两端安全过滤 | D 已实现，定向读回完成 |
| EVIDENCE-ORDER-01 | 用户截图与 `discovery-search-workspace.tsx` 中 `DiscoveryDocumentProgress` 位于结果卡片之前一致，三本书的状态占据节选前的阅读空间 | 将文献状态块移至原文卡片和查看更多操作之后；接口、任务、排序、筛选、摘要、移除与定位回调不变 | D 已实现，定向读回完成 |

首页真实接口已只读确认：1 期公开策划，`home_layout.featured=null`。默认网格宽屏最多四期，701—1150px 隐藏第四张，700px 及以下仅保留主推一期和继续浏览入口。人工编排组件另有手机横滑规则；此次参考默认首页，不声称修改该规则。

示例标题和四期编号仅供版面比较。图片复用已有 `/editorial/library-architecture-hero.webp` 与 `/visual/stl4/subdisciplines/` 的 shelves、branches、street 素材，不增加发布内容或替换实际策划封面。点样例卡片只说明其为排版示例；真实公开策划目录仍可进入。

页面选择器读取现有 `/catalog/search/` 的公开 envelope，以及 `/catalog/recommendation-issues/?view=directory`。阅读页取现有 `/reading/source-status/` 公开解析结果，不拼造文件 ID。选择和更换只影响未提交的反馈草稿；此次不代读者提交反馈。未改数据库、权限、业务 API 或检索模型。

## 构建与恢复记录

- TypeScript 与 Vinext 构建退出 0，日志 `tmp/stl4-layout-20261030/typecheck.log`、`build-final.log`。
- 初次从 Web101 增量构建 Web102 在 COPY 阶段报 `max depth exceeded`。只读核对 Web101 有 124 个文件层，当前活动网站未变化。失败日志 `image-r102.log` 保留。
- 已从 Web101 文件系统创建独立底包 `stl4-preview-20261030-r101-flat`，镜像 `82ccabfc320a`、1 个文件层。Env、User、WorkingDir、Entrypoint、Cmd、ExposedPorts 与 StopSignal 逐项相同。未导出活动容器的运行环境、私有数据或挂载目录。原镜像保留。构建过程见 `flatten-r101.log`。
- 最终 Web102 `5437b99c8f561fc5f6847c12d80f8f9fd68ec4aa8ee95c117be95979438517a7` 已在 12:12 更新内网，首页 HTTP 200。日志 `image-r102-final.log`、`deploy-r102.log`；NAS `layout-r102-recovery` 保留前 Web101 环境与镜像记录，回退仅取 `LIBRARY_WEB_IMAGE` 单项，不能整份覆盖环境。API r54、四 worker r53、数据库、OCR 与模型容器 ID 均保持；生产、隧道、DNS 和已删除自动安排不变。

## 验收边界

- 参考页实际查看 1440、1066、768、390、320px；所检查页面均无横向溢出。1440px 的 1/2/3/4 期卡宽分别约 1353；890/445；658/329/329；571/243/243/243px。1066px 同行导航高度 42px、完整页头 82px；768px 显示三期，390/320px 显示一期，六个导航仍可见。320px 顶行方案的导航 y=0、品牌 y=92.25，无图单期正常。已恢复常规视口。
- 原生 details 鼠标的工具模拟点击未切换，改用实际键盘 Enter 已展开/收起；不据工具差异认定产品缺陷。
- 反馈实际完成点选首页、书名搜索 Enter、选择《国家的视角》真实阅读文件并填 PDF88，关联卡读回准确标题/版本/页码与 `/reader/326f7b3f-2a17-4878-afbf-22546a9dd5aa?page=88`。实际选择现有策划正常。390px 选择弹窗居中、宽336.2px、无横向溢出；手动 `/account/notes` 被原校验拒绝。未填反馈正文/邮箱/同意条款，未提交反馈，临时所选路径已清除并关闭工作标签。
- 用户原检索会话在恢复读取时显示不存在或过期；只刷新同一个问题一次以读取新版布局，没有批量查询或模型评测。真实读回 3/181 段时，首段 blockquote y=742.42，“本次文献” y=3269.95；DOM 顺序为进度、原文列表、更多操作、文献状态，且无横向溢出。后台深度整理当时仍在继续，不能记为该轮全部检索完成或模型质量通过。
- 截图目录 `output/visual-review-20261030-layout/`：nav-top-1440、nav-inline-1440、layout-768/390/320、feedback-picker-desktop/390、feedback-reader-page、evidence-first-desktop。初次手机截屏发生尺寸切换过渡，随后已重新读取并覆盖保存稳定画面。
- 更新既有 `support-feedback.spec.ts` 中选页和手填路径的定位步骤，补留常用页面选择断言；未运行正式 E2E/全量测试。超时、分页等其他动态状态与全部类型逐项选择仍 B，不能由类型/构建或这些截图代替全站验收。

此轮不重复 OCR、索引补写或全站 206 视图验收。原公网前环境、邮件凭据、最终批准与 B 类未验收范围保持。
