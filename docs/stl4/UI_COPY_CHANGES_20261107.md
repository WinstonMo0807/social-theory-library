# STL 管理台、读者中心及相关公开页面文案对照

2026-11-07。本轮按 STC for-web-dev 整理 203 项界面文字，保留业务条件、来源范围、权限和恢复语义。以下是依次实施的改动，个别同一文件的相邻提示在第二轮继续精简；未改真实馆藏、策展正文或用户笔记。

STC 对最终文字清单的机械检查为 0 错误、0 警告；这不等于全站文案或动态错误状态均已人工验收。内网候选已包含，公网外观发布另行确定。

| 编号 | 文件及原位置 | 改前 | 改后 | 原因 |
|---|---|---|---|---|
| COPY-01 | web/components/admin/preview/knowledge-page-preview.tsx:262 | 该模块在当前草稿中没有可渲染内容。页面契约仍保留编辑入口，发布前不会伪造占位数据。 | 此栏目尚无内容。请返回编辑页补充。 | 预览定位找不到模块时，解释契约与占位策略不能帮助编辑。改为缺失对象和操作。 |
| COPY-02 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:396 | 后端没有为此候选提供安全操作入口。 | 这条建议暂时无法处理，请刷新后重试。 | 无法处理建议时，后端实现不应作为报错正文。 |
| COPY-03 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:401 | 本页还有未保存的填写。请先保存，再单独处理此建议；不会自动替你保存整页。 | 请先保存本页修改，再处理这条建议。 | 前置条件已完整表达，尾句重复。 |
| COPY-04 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:514 | 新资料和研究建议经过整理后显示在这里，不会自动修改正式知识。 | 建议不会自动修改已发布内容。 | 保留候选与正式内容边界，删除空泛过程。 |
| COPY-05 | web/components/admin/knowledge/knowledge-impact-summary.tsx:21 | 已存关联与影响核对 | 使用位置 | 标题改为管理员能直接理解的对象。 |
| COPY-06 | web/components/admin/knowledge/knowledge-impact-summary.tsx:28 | 这里不统计读者私人记录，也不会自动改绑其他页面的原文或执行数据迁移。 | 不含读者私人资料。 | 此组件只读取依赖计数，不存在自动迁移动作；保留私人范围。 |
| COPY-07 | web/components/admin/knowledge/knowledge-impact-summary.tsx:26 | 主体已有未发布草稿；修改不会在确认前替换公开内容。 | 有未发布的修改。发布后，读者才能看到。 | 避免主体、确认等模糊对象，明确发布行为。 |
| COPY-08 | web/components/admin/knowledge/knowledge-impact-summary.tsx:27 | 查看主体历史与依赖 → | 查看发布记录 → | 链接进入原发布记录页，不新增入口。 |
| COPY-09 | web/components/admin/knowledge/topic-fields.tsx:67 | 问题与争论关联规范条目；导读中的文字问题不会自动创建条目或生成讨论数量。 | 请选择已有的问题和争论。导读文字不会新增条目。 | 保留关联方式，删除内部计数说明。 |
| COPY-10 | web/components/admin/knowledge/topic-fields.tsx:69 | 复用已有阅读路径及其真实阶段、材料和来源。草稿或撤下的路径不会公开显示。 | 只有已发布的阅读路径会向读者展示。 | 选择器本身已表达选择已有路径，保留公开条件。 |
| COPY-11 | web/components/admin/knowledge/topic-fields.tsx:70 | 只显示已发布的策划文章及其明确编排的计划材料；不会把私人研究内容公开。 | 只展示已发布的策划文章和计划材料，不含私人研究。 | 保留公开及隐私限制。 |
| COPY-12 | web/components/admin/knowledge/topic-fields.tsx:82 | 引语只取自本主题正式发布且仍可阅读的准确原文。保存选择不等于发布。 | 可选引语来自本主题已发布、仍可阅读的原文。保存后仍需发布。 | 保留来源资格和保存/发布区别，删自证词。 |
| COPY-13 | web/components/admin/knowledge/scholar-work-editor.tsx:30 | 先保存学者草稿，再从真实馆藏选入作品。 | 先保存学者草稿，再选择作品。 | 真实为无效修饰，选择器已是馆藏。 |
| COPY-14 | web/components/admin/knowledge/existing-scholar-start.tsx:32 | 使用已核对的人物身份建立一份公开页草稿。 | 为已核对的人物新建学者页面草稿。 | 说明对象与结果，保留草稿状态。 |
| COPY-15 | web/components/admin/curation/curation-discovery-preview.tsx:18 | 填写公开推荐理由后，这里会按当前文字预览。空白不会自动生成替代文案。 | 填写推荐理由后即可预览。 | 空态重复强调不会编写文案。 |
| COPY-16 | web/components/admin/curation/placement-workspace.tsx:82 | 尚未选择内容。加入真实馆藏后，可调整顺序和本页推荐理由。 | 先添加内容，再调整顺序和推荐理由。 | 保留操作顺序，删自证词。 |
| COPY-17 | web/components/admin/curation/issue-discovery-materials.tsx:64 | 当前候选尚无可稳定引用的原文身份，可先查看阅读位置。 | 这条材料暂不能引用，可以先打开原页阅读。 | 身份为内部数据概念，改为读者可用动作。 |
| COPY-18 | web/components/admin/curation/issue-publication-review.tsx:72 | 正在确认当前保存版本的真实页面预览… | 正在加载已保存稿件的预览… | 等待文案只说实际等待对象。 |
| COPY-19 | web/components/admin/curation/article-body-fields.tsx:52 | 真实出处 | 出处 | 正常表单不需用真实自证。 |
| COPY-20 | web/components/admin/curation-project-workspace.tsx:221 | 项目介绍与问题仅用于内部策划。下面按项目顺序查看各篇文章；公开版本由各文章的明确发布决定。 | 项目介绍和问题仅供内部使用。文章需分别发布。 | 列表顺序由布局表达，保留公开范围。 |
| COPY-21 | web/components/admin/curation-project-workspace.tsx:190 | 项目尚未保存附录材料。请进入文章加入真实来源。 | 暂无附录材料。请在文章中添加来源。 | 明确空态和下一步。 |
| COPY-22 | web/components/admin/curation/curation-field-assistant.tsx:262 | 查询原决定 | 查看处理结果 | 操作是查询原请求回执，决定不是可理解按钮。 |
| COPY-23 | web/components/admin/curation/curation-field-assistant.tsx:262 | 重试原决定 | 重试该操作 | 保持原请求重试语义，不变调用。 |
| COPY-24 | web/components/admin/curation/curation-field-assistant.tsx:258 | 尚未执行的原决定已停止。已保存内容保持不变。 | 已取消尚未执行的操作。已保存内容保留。 | 动作和结果直说。 |
| COPY-26 | web/components/admin/workflow/manual-metadata-prefill.tsx:37 | 点击后仅查询已允许的免费书目来源。不会上传文件，也不会自动新建人物；无结果时可继续手动填写。 | 查询已启用的免费书目来源，不上传文件。采用后仍需核对作者和译者。 | 保留外发边界；控制说明与查找按钮分开。 |
| COPY-27 | web/components/admin/workflow/manual-metadata-prefill.tsx:37 | 查找元数据候选 | 查找书目信息 | 管理员用语直接描述对象。 |
| COPY-28 | web/components/admin/workflow/field-assistant-control.tsx:335 | 新建只保存最小身份草稿；当前书目的关联仍需点击页面保存，完整资料可稍后补充。 | 新建人物后，保存书目修改才能完成关联。人物资料可稍后补充。 | 保留两次保存的必要区别，删除最小身份术语。 |
| COPY-29 | web/components/admin/workflow/field-assistant-control.tsx:338 | 填入后可以继续修改，点击页面顶部“保存书目修改”才会保存。不会自动发布。 | 填入后可继续编辑。保存书目修改后生效，仍需另行发布。 | 保留保存与发布区别。 |
| COPY-30 | web/components/functional-health-panel.tsx:574 | 保留故障发生次数、可能原因和受影响功能。恢复动作来自后端允许清单。 | 删除重复说明 | 待处理事件列表已经展示计数、原因与恢复按钮；整句是实现说明。 |
| COPY-31 | web/components/admin/local-services.tsx:139 | 按权限检查全部服务 | 检查全部服务 | 按钮禁用与权限处理已经存在，不需把授权计算写进按钮。 |
| COPY-32 | web/components/admin/local-services.tsx:140 | 服务身份（本地/自建） | 服务 | 表格列对象清晰，技术部署范围在具体服务详情保留。 |
| COPY-33 | web/components/admin/local-services.tsx:125 | 刷新已有记录 | 刷新记录 | 保留读取与真实检查的区别。 |
| COPY-34 | web/components/admin/local-services.tsx:130 | 刷新后不会自动继续检查。查询只读取原结果；未查到仍可能在途，取消只阻止尚未执行的原请求。 | 上次检查可能仍在运行。请先查看结果，或取消尚未开始的检查。 | 保留不确定性、取消范围，删除在途/原请求行话。 |
| COPY-35 | web/components/admin/ai-runtime-editor.tsx:100 | 启用（保存不会自动发起分析） | 启用此配置 | 操作是启用配置，另处状态与检查按钮已表达保存不是调用。 |
| COPY-36 | web/components/admin/ai-runtime-editor.tsx:74 | 模型配置与本次凭据操作已保存，后续任务读取新配置；已在途任务不由此中断。保存未执行模型调用。 | 配置已保存，下次任务生效。正在运行的任务不受影响。 | 保留生效时间和现有任务影响。 |
| COPY-37 | web/components/admin/ai-runtime-editor.tsx:111 | 保留当前已保存的馆藏检索方案。此处修改模型配置不切换检索路线，也不发起质量评测。 | 删除重复说明 | 当前配置表单不提供检索算法或测评操作，是开发范围声明。 |
| COPY-38 | web/components/research-source-registry.tsx:104 | 与来源绑定在同一事务保存；提交后清除输入，不回显原值，不保存到浏览器恢复记录。 | 密钥加密保存在服务器，不在浏览器中保留。 | 保留凭据存储边界，事务术语无关日常使用。 |
| COPY-39 | web/components/reader-center.tsx:488 | 保留会话并重试 | 重试登录状态 | 按钮应描述用户操作，不需解释会话保护。 |
| COPY-40 | web/components/reader-center.tsx:516 | 有一项主题收藏操作尚待核对，原请求与期望版本仍保留。 | 上次收藏尚未确认，请查看处理结果。 | 原请求/期望版本为实现术语。 |
| COPY-41 | web/components/reader-center.tsx:506 | 创建计划 | 新建计划 | 统一同一动作，其他模块使用新建。 |
| COPY-42 | web/components/research/research-project-notes.tsx:60 | 这份笔记与证据比较共用，仅本人可见。原文依据仍保留各自的引用身份。 | 笔记与比较页同步，仅本人可见。 | 保留同步/隐私，删除引用身份实现说明。 |
| COPY-43 | web/components/research/research-project-notes.tsx:36 | 备注原来源身份未能核对，文字仍保留。 | 暂时无法核对备注的原文来源。备注文字仍保留。 | 指明失败对象和数据保留。 |
| COPY-44 | web/components/research/research-comparison-search.tsx:49 | 扩展寻找新证据 | 补充检索 | 标题直接表达动作。 |
| COPY-45 | web/components/research/research-comparison-search.tsx:59 | 开始寻找 | 开始检索 | 同一功能名称统一。 |
| COPY-46 | web/components/research/research-comparison-search.tsx:57 | 检索会新增研究轮次，保留旧结果。选定作品范围包含其可访问版本，结果不会自动填入比较格，也不会改写你的判断。 | 结果保存为新的研究轮次，旧结果保留。选中原文后，可加入比较。 | 检索范围控件已说明版本；保留新轮次及人工选材。 |
| COPY-47 | web/components/research/research-session-detail.tsx:184 | 已加入选材，来源身份和版本已重新核对。 | 已加入选材。 | 成功状态不复述服务内部检查。 |
| COPY-48 | web/components/research/research-session-compare.tsx:105 | 已导出当前已保存的研究、证据身份与比较记录。 | 已导出研究、来源信息和比较记录。 | 身份换为明确输出内容，不改变导出。 |
| COPY-49 | web/components/research/research-replay.tsx:70 | 查看明确关联的阅读记录 → | 查看阅读记录 → | 关联筛选由链接决定，不需在按钮解释。 |
| LIVE-49 | web/components/research/reader-overview.tsx | <h2>待继续任务</h2><p>按阅读计划的最近更新时间排列。</p> | <h2>继续计划</h2> | 公网页面重复说明；账号页不再提示登录 |
| LIVE-50 | web/components/research/reader-overview.tsx | <h2>我的资料</h2><p>仅显示你创建或保存的资料。</p> | <h2>我的资料</h2> | 公网页面重复说明；账号页不再提示登录 |
| LIVE-51 | web/components/public/site-footer-view.tsx | <small>登录后阅读、下载和使用探索功能。</small> | <Link href="/help/account">账户帮助</Link> | 公网页面重复说明；账号页不再提示登录 |
| LIVE-52 | web/components/theory/theory-overview.tsx | 暂无关联公开馆藏的理论流派。已审核条目与馆藏建立公开关联后，会显示在这里。 | 还没有与馆藏关联的理论流派。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-53 | web/components/theory/theory-overview.tsx | 馆藏理论暂时无法读取。请稍后重试，当前状态不能判断馆藏是否为空。 | 暂时无法读取理论流派，请重试。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-54 | web/components/theory/theory-overview.tsx | {description ? <span>{description}</span> : <span className={styles.missingSummary}>简介尚未发布</span>} | {description ? <span>{description}</span> : null} | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-55 | web/components/theory/theory-directory.tsx | <p className={styles.summary}>{entry.summary \|\| "这项条目的简介尚未发布，可继续查看已公开的关联资料。"}</p> | {entry.summary ? <p className={styles.summary}>{entry.summary}</p> : null} | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-56 | web/components/auth-return-card.tsx | 保留原页面与定位，权限由当前账户重新核对。 | 登录后返回刚才的页面。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-57 | web/components/auth-guest-records.tsx | 本设备暂无待转存的访客浏览记录。 | 本机没有待保存的浏览记录。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-58 | web/components/auth-page-frame.tsx | 登录后可继续您上次的研究与阅读，保存书签、笔记与个人资料。 | 登录后继续阅读，保存书签、笔记与研究。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-59 | web/components/auth-page-frame.tsx | 进入私人保存能力，并返回原先的研究或阅读任务。 | 管理账户，继续阅读与研究。 | 公开页面实际检查与相邻状态；删除内部术语及空简介提示 |
| LIVE-60 | web/components/admin-dashboard.tsx | 今日工作 / 今日工作与继续处理 / 从待办事项继续出发，完成编目、整理与发布。 | 今日工作 | 同一页的栏目、标题和说明重复表达相同动作 |
| LIVE-61 | web/lib/version.ts | STL 4.0 内网审阅版 | STL 4.0 | 公网站点共用组件不应被称为内网审阅版 |
| COPY2-010 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:541 | 本页还有未保存的填写，不会出现在此处预览中。请先保存，再预览或发布。 | 请先保存本页修改，再预览或发布。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-001 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:499 | API 尚未返回基于公开 serializer 的完整度。 | 暂未取得内容完整度。请刷新后重试。 | 无完整度结果时泄漏 API / serializer；附近已有刷新按钮。 |
| COPY2-003 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:509 | 当前没有需要人工处理的高价值候选。 | 暂无待处理建议。 | 空态不需要评价候选价值。 |
| COPY2-009 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:540 | 部分特殊关系暂时只能预览主要内容。 | 预览尚未包含全部关系。请在关系编辑页核对。 | 保留预览缺项，不做已完整的承诺。 |
| COPY2-004 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:519 | 当前没有需要主动呈现的知识更新。 | 暂无关联建议。 | 所属栏目为关联建议，统一名称。 |
| COPY2-008 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:539 | 完整版本历史、撤回与恢复 | 查看版本记录 | 按钮进入已有发布历史，保留撤回与恢复功能在目标页。 |
| COPY2-005 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:206 | 结构化建议 | 建议详情 | displayValue 的复杂对象回退标题，避免把对象编码方式当内容。 |
| COPY2-006 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:251 | 身份标识 | 外部编号 | 对应 external_identifier 字段。人物身份证明与外部数据库编号不同。 |
| COPY2-007 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:282 | 权威资料 | 参考资料 | sourceCategory 实际按 authority/library/registry 来源归类，来源类别不保证事实权威，不推断具体来源机构。 |
| COPY2-002 | web/components/admin/knowledge/knowledge-object-context-panel.tsx:498 | 未接通 | 暂无数据 | 此分支仅表示完整度结果为空，不能据此宣称接口未接通。 |
| COPY2-013 | web/components/admin/knowledge/knowledge-publication-review.tsx:93 | 比较范围为公开页面返回的内容；来源或关系的独立变更需在原记录中核对。 | 这里只比较页面内容。来源和关系的变更请到各自编辑页核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-011 | web/components/admin/knowledge/knowledge-publication-review.tsx:65 | 保存版本或对象身份不完整，请返回编辑页。 | 保存记录不完整，请返回编辑页核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-012 | web/components/admin/knowledge/knowledge-publication-review.tsx:43 | 知识对象已保存版本的真实页面预览 | 已保存内容的页面预览 | iframe 标题无需自证真实。 |
| COPY2-016 | web/components/admin/knowledge/knowledge-publish-control.tsx:130 | 下方摘要取自公开页面的数据，只列主要文本与条目变化。未列出的结构化内容请在完整预览中核对。 | 下方列出主要文字和条目变化。其他内容请在完整预览中核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-017 | web/components/admin/knowledge/knowledge-publish-control.tsx:115 | 发布操作已确认。公开内容与后续检索处理请在原记录中继续核对。 | 发布操作已确认。页面和检索更新进度可在发布记录中查看。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-015 | web/components/admin/knowledge/knowledge-publish-control.tsx:71 | 对象身份不一致，请返回列表重新打开。 | 记录与当前页面不一致，请返回列表重新打开。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-014 | web/components/admin/knowledge/knowledge-publish-control.tsx:24 | 结构化内容，请核对完整预览 | 请在完整预览中核对详情 | 复杂字段 display 回退，管理员不需要知道编码结构。 |
| COPY2-018 | web/components/admin/knowledge/knowledge-aliases-dialog.tsx:65 | 尚无别名或译名。请根据真实来源添加。 | 暂无别名或译名。请按出处填写。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-019 | web/components/admin/knowledge/concept-placement-editor.tsx:73 | 从真实馆藏中选择材料；未核实的作者归属不会自动确认。 | 从馆藏选择材料。作者归属仍需核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-020 | web/components/admin/knowledge/scholar-canonical-sections.tsx:22 | 保存学者草稿并核对原操作后，可打开统一关系工作区。 | 保存学者草稿并核对处理结果后，可编辑学者关系。 | 保留保存与核对原操作处理结果两个前置条件，不改外层 pending/blocked 条件与恢复控件。 |
| COPY2-022 | web/components/admin/knowledge/scholar-work-editor.tsx:38 | 推荐阅读注明本页编者的选择，不改变作者或贡献身份。 | 推荐阅读代表本页编者的选择，不改变作者和译者等署名。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-021 | web/components/admin/knowledge/scholar-work-editor.tsx:42 | 没有符合条件的真实馆藏。 | 没有符合条件的馆藏。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-023 | web/components/admin/knowledge/scholar-editor-frame.tsx:50 | 当前资料用于编辑，完成来源与身份核对后可发布。 | 核对人物信息和出处后，可发布学者页面。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-024 | web/components/admin/knowledge/placement-source-picker.tsx:19 | 正在读取真实材料… | 正在读取材料… | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-025 | web/components/admin/knowledge/placement-uses.tsx:21 | 这里按准确对象身份列出文章正文、分析引用与人物比较中的结构化引用，包含最新已保存、登记公开和排期修订。同一篇文章可以有多份记录；不扫描自由文字，也不自动替换原文。 | 列出文章正文、分析和人物比较中添加的引用，包括最新草稿、发布及排期版本。同一文章可有多版记录，未关联条目的文字引用不计入。 | 保留统计范围与多版本；本组件只读，不需说明不会自动替换原文。 |
| COPY2-026 | web/components/admin/knowledge/placement-uses.tsx:27 | 修订登记不代表当前对外可见，请在文章中核对实际发布与项目状态。 | 此版本不一定正在公开，请到文章页查看发布状态。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-027 | web/components/admin/knowledge/scholar-concept-usages.tsx:29 | 原材料当前不可用，引用身份仍保留。 | 原材料暂不可用，引用记录仍保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-028 | web/components/admin/knowledge/timeline-participants.tsx:23 | 版本身份不一致，请重新选择。 | 所选版本与当前记录不一致，请重新选择。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-029 | web/components/admin/knowledge/person-authority-workspace.tsx:215 | 编辑原人物的异名与核验依据。查询词由已保存的权威来源同步，标准名称和人物身份沿原记录保留。 | 编辑人物别名和核对依据。检索词按已保存的核验和公开状态同步，原人物记录保留。 | 明确保留公开与核验条件，不能暗示未公开名称均会进入公开检索。 |
| COPY2-030 | web/components/admin/knowledge/person-resolution-workspace.tsx:152 | 下方为双方现有引用。学者档案的下游引用保持原编号，只随同一份档案保留。 | 下方列出两个人物的引用。已有学者页面及其引用记录保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-031 | web/components/admin/knowledge/knowledge-visual-editor.tsx:173 | 两端学者共用同一关系、方向、说明和来源。下方历史关联阅读保持原记录。 | 修改关系会同步到两位学者的页面。原有阅读关联保留。 | 保留跨页面同步影响，不把模型关系结构当解释。 |
| COPY2-032 | web/components/admin/accounts/account-workspace.tsx:119 | 权限由服务器按当前账户核对。馆长来自既有身份配置，不能通过分配普通角色取得。旧审核角色沿现有兼容规则显示为内容编辑。 | 馆长权限由服务器配置，此处不能授予馆长权限。 | 角色迁移及服务器授权实现不属普通角色表格说明。 |
| COPY2-033 | web/components/admin/curation/article-metadata-fields.tsx:21 | 公开策划者身份 | 策划者署名 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-034 | web/components/admin/curation/article-body-fields.tsx:66 | 作者身份待核对 | 作者信息待核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-035 | web/components/admin/curation/issue-publication-review.tsx:46 | 已保存稿的真实页面预览 | 已保存稿件预览 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-036 | web/components/admin/curation/reading-path-dependencies.tsx:36 | 保存前可核对材料身份、先修循环和阅读顺序。 | 保存前检查材料是否可用、先后顺序是否冲突。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-037 | web/components/admin/curation/reading-path-workbench.tsx:541 | 新增争论名称在保存草稿后从真实关联核对。 | 保存草稿后，可查看关联的争论。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-039 | web/components/admin/curation-project-workspace.tsx:171 | 选择自己创建、尚未归组的文章。加入后保留原身份、版本与公开状态。 | 选择自己创建、尚未加入项目的文章。文章版本和发布状态保持不变。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-038 | web/components/admin/curation-project-workspace.tsx:122 | 恢复项目编辑，文章身份和版本保留，不自动发布或重启处理。 | 恢复后可继续编辑。文章版本保留，不会自动发布或重启任务。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-044 | web/components/admin/library/work-files-workspace.tsx:111 | 替换生成新的文件身份，旧文件及其锚点仍会保留。已有页面引用继续指向原文件，需在发布设置中确认是否切换。 | 替换后，旧文件和阅读定位保留。已有引用仍指向旧文件，切换时需在发布设置中确认。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-042 | web/components/admin/library/work-files-workspace.tsx:97 | 管理同一作品的版本及每次上传的文件历史。新文件生成新身份，原件和旧记录保留。 | 管理作品的出版版本和上传记录。新文件单独保存，原件和历史记录保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-043 | web/components/admin/library/work-files-workspace.tsx:107 | 发布快照包含书目与文件。切换阅读文件请使用文件列表中的采用操作。 | 发布版本包含书目和文件。更换阅读文件时，请在文件列表中选择“采用”。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-040 | web/components/admin/library/work-files-workspace.tsx:106 | 文件身份 | 文件编号 | 文件列表此列实际显示 file.id，不是人物身份。 |
| COPY2-139 | web/components/admin/processing-workspace.tsx:111 | 项任务。提交时重新核对当前账户、任务状态与执行轮次；状态已变化时保留原记录并提示重新读取。 | 项任务。提交时会核对操作权限和任务状态。状态变化时，请刷新后重试。 | 批量操作确认段：保留权限及状态变化，不展示执行轮次。 |
| COPY2-041 | web/components/admin/processing-workspace.tsx:124 | 文件身份 | 文件编号 | 任务详情显示 asset ID。 |
| COPY2-045 | web/components/admin/library/work-file-actions.tsx:158 | 原件保存为新的文件身份，旧原件和历史引用继续保留。 | 新上传的原件单独保存。旧原件和历史引用保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-046 | web/components/admin/library/work-file-preview.tsx:44 | 文件身份与当前记录不一致，请刷新文件列表后再预览。 | 文件与当前记录不一致，请刷新文件列表后再预览。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-047 | web/components/admin/library/work-library.tsx:67 | 非主版本 · 保留版本身份 | 其他出版版本 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-050 | web/components/admin/library/ocr-workspace.tsx:136 | 保存候选仅保留修订记录。采用会生成正文解释与证据修订，已公开内容经原发布队列更新；旧文件、旧引用和原件继续保留。 | 保存后仍需采用修订。采用后生成新的文字修订，已公开内容经发布流程更新。原件、旧文件和旧引用保留。 | 保留保存/采用/发布流程差异，不能暗示采用会覆盖已有引用或立即公开。 |
| COPY2-052 | web/components/admin/library/ocr-workspace.tsx:125 | 历史文件预览从文件管理读取，此处不借用另一份文件。 | 请在文件管理中预览历史文件。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-051 | web/components/admin/library/ocr-workspace.tsx:92 | 已保存识别任务，请以下方真实任务状态为准。 | 识别任务已提交，可在下方查看进度。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-049 | web/components/admin/library/ocr-workspace.tsx:136 | 文字修订的下游影响 | 文字修改的影响 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-053 | web/components/admin/library/ocr-workspace.tsx:128 | 已绑定真实文档修订 | 已关联文档版本 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-048 | web/components/admin/library/ocr-workspace.tsx:119 | 下游影响 | 修改影响 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-056 | web/components/admin/preview/knowledge-page-preview.tsx:167 | 这里只显示已经审核并关联到该理论的真实时间轴事件。 | 显示已审核并关联到本理论的事件。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-055 | web/components/admin/preview/knowledge-page-preview.tsx:164 | 使用当前草稿身份和已经发布的条目关系生成。 | 预览使用当前草稿和已发布的关系。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-054 | web/components/admin/preview/knowledge-page-preview.tsx:106 | 学者预览缺少身份，已保留草稿。 | 未取得学者记录，草稿已保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-058 | web/components/admin/processing-task-recovery.tsx:38 | 仍符合恢复条件时，将从已保存的检查点重新派发；原执行轮次不能再提交结果。 | 如果仍可恢复，将从已保存的进度继续。旧任务结果不会覆盖恢复后的结果。 | 保留恢复条件和旧执行隔离，但不使用派发/轮次术语。 |
| COPY2-057 | web/components/admin/processing-task-recovery.tsx:38 | 排队任务将沿原执行编号重新通知处理队列。 | 重新提交原排队任务。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-059 | web/components/admin/processing-task-composer.tsx:45 | 原待定请求已停止，已经创建的任务仍按真实操作结果处理。 | 尚未执行的请求已取消。已经创建的任务保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-062 | web/components/admin/recommendation-issue-editor.tsx:56 | 这条计划已建立独立书目。后续关联已有馆藏时保留计划身份和原推介文字。 | 这条计划已有书目。关联馆藏后，原计划和推荐文字保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-061 | web/components/admin/recommendation-issue-editor.tsx:129 | 稳定地址名称（创建后保留） | 固定链接名称（创建后保留） | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-060 | web/components/admin/recommendation-issue-editor.tsx:118 | 专题编辑器与结构化内容 | 文章编辑 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-063 | web/components/admin/research/research-entity-picker.tsx:600 | 维护模式可以关联馆内实体并核对外部候选。需要 UploadItem 的创建、保留和拒绝决定在这里不可记录。 | 这里可选择馆内条目并核对外部建议。收件的处理决定请在收件与编目中完成。 | UploadItem 是明确内部类名，正常编辑人不应看到。 |
| COPY2-126 | web/components/admin/research/research-entity-picker.tsx:535 | 搜索馆内实体、权威来源和外部线索 | 搜索馆内条目和外部资料 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-125 | web/components/admin/research/research-entity-picker.tsx:61 | 权威来源候选 | 资料来源建议 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-064 | web/components/admin/research/research-suggestion-panel.tsx:250 | 研究仍在后台队列或 Worker 中。已停止自动轮询，请稍后使用刷新状态，不要重复创建任务。 | 研究仍在处理中，页面已停止自动刷新。请稍后刷新状态，不要重复新建任务。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-066 | web/components/admin/research/research-suggestion-panel.tsx:492 | 仍在研究队列中等待，页面会继续读取结果。 | 研究仍在排队，页面会自动更新进度。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-121 | web/components/admin/research/research-suggestion-panel.tsx:58 | QueryLexicon 匹配 | 检索词匹配 | 来源分层名称直接暴露内部检索词典类名。 |
| COPY2-065 | web/components/admin/research/research-suggestion-panel.tsx:403 | 候选已采用并记录审计。 | 建议已采用。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-123 | web/components/admin/research/research-suggestion-panel.tsx:60 | 权威与结构化来源 | 书目与资料来源 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-124 | web/components/admin/research/research-suggestion-panel.tsx:124 | 结构化来源 | 书目与资料来源 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-122 | web/components/admin/research/research-suggestion-panel.tsx:57 | 本馆实体 | 馆内条目 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-067 | web/components/admin/recovery-workspace.tsx:156 | 查询只读取已登记结果，不再次提交恢复。查不到时，请求仍可能在途；可以取消尚未执行的原请求。 | 先查看恢复结果，未找到时仍可能正在处理。也可取消尚未开始的恢复。 | 保留不确定性和取消范围。 |
| COPY2-142 | web/components/admin/recovery-workspace.tsx:159 | 同名可能是不同版本或身份。请先比较，恢复时保留各自内容与原身份。 | 同名记录可能属于不同版本或人物。请先比较，恢复后各自内容仍保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-068 | web/components/admin/recovery-batch.tsx:51 | 预览身份与所选对象不一致。 | 预览记录与所选内容不一致，请重新读取。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-070 | web/components/admin/media/media-library-catalog.tsx:124 | 图片来源资料已保存。已选用图片的裁切、出处快照和公开页面保持原修订；请到具体使用对象核对后更新。 | 图片出处已保存。已使用的图片仍保留原裁切和出处，请到使用页面核对并更新。 | 保留图库与已发布使用副本的区别。 |
| COPY2-069 | web/components/admin/media/media-library-catalog.tsx:81 | 查看原图、来源资料及真实使用位置。 | 查看原图、出处和使用位置。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-071 | web/components/admin/site-workspace.tsx:103 | 尚未添加内容。发布空栏目后，首页显示真实空态。 | 尚未添加内容。发布后，此栏目将显示为空。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-077 | web/components/admin/workflow/assistant-commands.tsx:29 | 已查询原决定，原操作没有重复执行。请重新读取建议核对当前状态。 | 已取得处理结果。请刷新建议，核对当前状态。 | Result 仅 applied/cancelled；此分支在非 cancelled 且有返回结果时执行。 |
| COPY2-078 | web/components/admin/workflow/assistant-commands.tsx:42 | 核对并停止材料助手的原决定？ | 取消尚未执行的操作？ | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-076 | web/components/admin/workflow/assistant-commands.tsx:29 | 尚未执行的原决定已停止。 | 尚未执行的操作已取消。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-072 | web/components/admin/workflow/assistant-commands.tsx:32 | 查询原决定 | 查看处理结果 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-073 | web/components/admin/workflow/assistant-commands.tsx:32 | 重试原决定 | 重试该操作 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-079 | web/components/admin/workflow/catalog-field-locks.tsx:66 | 尚未执行的原决定已停止，已完成操作不会撤销。 | 尚未执行的操作已取消，已完成操作保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-080 | web/components/admin/workflow/catalog-field-locks.tsx:85 | 核对并停止原决定？ | 取消尚未执行的操作？ | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-074 | web/components/admin/workflow/catalog-field-locks.tsx:71 | 查询原决定 | 查看处理结果 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-075 | web/components/admin/workflow/catalog-field-locks.tsx:71 | 重试原决定 | 重试该操作 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-081 | web/components/admin/curation/curation-field-assistant.tsx:236 | 尚未执行的原决定已停止，请重新读取候选。 | 尚未执行的操作已取消，请刷新建议。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-082 | web/components/admin/curation/curation-field-assistant.tsx:322 | 核对并停止这项原决定？ | 取消尚未执行的操作？ | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-083 | web/components/admin/workflow/contributor-input.tsx:61 | 尚未确认成功，请查询材料助手的原决定。 | 保存结果尚未确认，请查看材料助手的处理结果。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-087 | web/components/admin/workflow/workflow-editor.tsx:1040 | 当前作品还没有可用预览地址。先保存书目和作品身份后再试。 | 当前作品尚无预览。请先保存作品和书目信息。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-084 | web/components/admin/workflow/workflow-editor.tsx:665 | 请先查询或停止材料助手的原决定。 | 请先查看材料助手的处理结果，或取消尚未执行的操作。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-088 | web/components/admin/workflow/workflow-editor.tsx:1322 | 候选决定已写入审计记录。 | 处理结果已保存。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-085 | web/components/admin/workflow/workflow-editor.tsx:398 | 作品身份与版本判断 | 作品与出版版本 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-086 | web/components/admin/workflow/workflow-editor.tsx:1430 | 作品身份 | 作品信息 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-089 | web/components/admin/workflow/intake-confirmation.tsx:50 | 身份决定已保存，后续处理沿原队列继续。 | 作品与版本选择已保存，后续处理将继续。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-091 | web/components/admin/workflow/intake-confirmation.tsx:63 | 4. 身份差异与来源说明 | 4. 书目信息差异与来源 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-090 | web/components/admin/workflow/intake-confirmation.tsx:58 | 收件身份已经确认。 | 作品与出版版本已确认。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-092 | web/components/admin/workflow/intake-confirmation.tsx:65 | 确认收件身份 | 确认作品与版本 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-093 | web/components/admin/workflow/manual-catalog.tsx:42 | 保存时新建人物草稿，身份仍待核对 | 保存时新建人物草稿，人物信息仍待核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-094 | web/components/admin/workflow/manual-metadata-prefill.tsx:41 | 以下来源将在保存时登记。作者和译者仍需逐人选择馆内身份或明确新建。 | 保存时记录以下出处。作者和译者仍需选择已有馆内人物，或新建人物。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-095 | web/components/admin/workflow/contribution-scope-editor.tsx:24 | 从本版真实目录选择该人承担的章节，并核对结束页；同一人可选择多个章节。更换原文后须重新确认。 | 从本版目录选择该人物参与的章节，并核对结束页。可选择多章，更换原文后须重新确认。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-096 | web/components/admin-upload.tsx:725 | 服务器允许的上传分段小于当前恢复记录，请保留页面并联系管理员升级 API。 | 当前上传记录与服务器限制不兼容。请保留页面并联系管理员。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-099 | web/components/admin-sections.tsx:1872 | 当前运行代码只接入这一方式。外部模型重排需要先定义和验证服务协议，不能只保存一个模型名称。 | 目前只支持所列重排方式。外部重排服务暂不可用。 | 保留功能限制，删开发实施步骤。 |
| COPY2-097 | web/components/admin-sections.tsx:1507 | 本月用量快照已记录，并已经检查预算告警阈值。 | 本月用量已记录，预算提醒已检查。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-098 | web/components/admin-sections.tsx:1857 | 模型 revision | 模型版本 | 仍保留模型真实revision值，不改配置键。 |
| COPY2-100 | web/components/research/citation-audit-shared.tsx:12 | 书目身份 | 书目核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-101 | web/components/research/citation-audit-upload.tsx:23 | 书目身份 | 书目核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-105 | web/components/research/citation-audit-issue.tsx:108 | 身份待核对 | 书目信息待核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-102 | web/components/research/citation-audit-issue.tsx:110 | 书目身份 | 书目核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-103 | web/components/research/citation-audit-parse.tsx:16 | 书目身份匹配 | 书目匹配 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-136 | web/components/research/citation-audit-print.tsx:76 | · 本快照包含全部 | · 本报告包含全部 | 实际为引文体检打印报告，保留动态数量。 |
| COPY2-106 | web/components/research/citation-audit-print.tsx:46 | 版本身份待核对 | 出版版本待核对 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-104 | web/components/research/citation-audit-print.tsx:8 | 书目身份匹配 | 书目匹配 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-107 | web/components/research/citation-source-preview.tsx:58 | 原文身份核对失败，请重试。 | 原文记录核对失败，请重试。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-108 | web/components/research/confirmed-notes-workspace.tsx:215 | 原来的来源身份仍保留在历史中。请先查看当前原文，再明确更新关联。 | 原来源保留在历史记录中。请先查看当前原文，再更新关联。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-109 | web/components/research/counter-evidence-workspace.tsx:150 | 原文已变化、撤回或不可访问。旧片段不再显示，材料身份和前次人工判断保留。 | 原文已变化、撤回或不可访问。旧片段不再显示，来源记录和上次人工判断保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-110 | web/components/research/privacy-workspace.tsx:130 | 下载时重新核对来源资格；失效来源保留身份信息，不提供旧原文。 | 下载时核对来源权限。失效来源只保留出处，不提供旧原文。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-111 | web/components/research/reader-notebook.tsx:290 | 原请求身份无法读取，请到我的研究核对。 | 暂时无法读取处理记录，请到我的研究核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-112 | web/components/research/research-replay.tsx:115 | 原请求身份无法读取，请先在我的研究核对。 | 暂时无法读取处理记录，请到我的研究核对。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-113 | web/components/research/research-comparison-search.tsx:92 | 来源暂不可用，保留原引用身份。 | 来源暂不可用，原引用记录保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-114 | web/components/research/research-evidence-card.tsx:30 | 旧引用身份保留 | 原引用记录保留 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-116 | web/components/research/research-session-compare.tsx:157 | 来源暂不可用，原引用身份仍保留。 | 来源暂不可用，原引用记录保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-115 | web/components/research/research-session-compare.tsx:150 | 来源暂不可用，保留原有引用身份 | 来源暂不可用，原引用记录保留 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-118 | web/components/research/research-session-detail.tsx:211 | 旧引用身份和已保存笔记仍保留，不会自动换成另一版本。请在选材中核对，重新选取的材料会作为新引用保存。 | 原引用和笔记保留，不会自动更换版本。请核对选材；重新选择的材料会另存为新引用。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-117 | web/components/research/research-session-detail.tsx:174 | 导出研究的身份无法核对，请重新读取。 | 暂时无法核对研究记录，请刷新后再导出。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-120 | web/components/theory-system-admin.tsx:1079 | 删除这条错误候选？已生成的条目和关系保留，本次删除会留下审计与请求结果。 | 删除这条错误建议？已生成的条目、关系和操作记录保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-119 | web/components/theory-system-admin.tsx:495 | 已通过旧版映射打开理论或概念资料。后续只需在本页维护。 | 已打开对应的理论或概念，可在本页继续编辑。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-127 | web/components/admin/local-services.tsx:175 | 模型身份、设备与加载记录 | 模型版本、设备与加载记录 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-128 | web/components/admin/local-services.tsx:175 | 模型文件身份 | 模型文件编号 | 这里对应 artifact_id，值保持不变。 |
| COPY2-131 | web/components/admin/restore-history.tsx:27 | 此窗口未找到与当前归档身份匹配的有效报告。 | 本页未找到与当前归档校验值匹配的有效报告。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-129 | web/components/admin/restore-history.tsx:27 | 归档身份 | 归档校验值 | 表格实际展示 archive_sha256，不是备份编号。 |
| COPY2-134 | web/components/admin/storage-workspace.tsx:222 | 此旧记录尚未登记共享快照证据，须在隔离恢复时核对。 | 这份旧备份未记录数据库与文件清单的一致性，需在隔离恢复时核对。 | 保留真正恢复限制，不换成全部安全保证。 |
| COPY2-133 | web/components/admin/storage-workspace.tsx:227 | 原件副本按现有校验身份核对；归档会增大。 | 原件副本会校验后加入备份，归档文件会增大。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-132 | web/components/admin/storage-workspace.tsx:222 | 归档身份生成后可查看相应的恢复记录。 | 归档校验值生成后，可查看对应的恢复记录。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-130 | web/components/admin/storage-workspace.tsx:222 | 归档身份 | 归档校验值 | 实际展示 checksum，保留校验含义。 |
| COPY2-135 | web/components/admin/knowledge/timeline-editor-details.tsx:44 | 页。文件身份随记录保存。 | 页。 | 此前已显示已关联原文文件，无需再叙述保存ID。 |
| COPY2-137 | web/components/admin/knowledge/topic-hierarchy.tsx:65 | 个已公开。原主题身份和材料关联保留。 | 个已公开。原主题和关联材料保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-138 | web/components/admin/knowledge/topic-organization.tsx:59 | 个已公开；原身份和关联材料保留。 | 个已公开；原主题和关联材料保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-140 | web/components/admin/recovery-restore-dialog.tsx:47 | 个管理对象使用。请确认处理方式；各对象的内容、原身份和关联都会保留。 | 个条目使用。请确认处理方式，已有内容和关联将保留。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
| COPY2-141 | web/components/admin/recovery-restore-dialog.tsx:55 | 适用于不同作品、版本或身份确实同名的情况。两个对象保持独立。 | 适用于作品、版本或人物同名的情况。两条记录保持独立。 | 将内部实现术语改为当前用户可理解的对象或结果；保持原条件、调用与权限。 |
