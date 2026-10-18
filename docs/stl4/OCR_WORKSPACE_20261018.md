# OCR 与页面文字质量工作台

2026-10-18。唯一视觉依据为 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第 109–111 页，已实际读取渲染图及第 111 页细节图。当前为源码接入与静态检查记录，不是运行验收或上线证明。

## 接入与真实行为

- 页面 `/admin/library/assets/[assetId]/ocr`，接口 `/api/ingestion/ocr-workspace/{asset_id}/`，复用 `ProcessingJob`、`catalog_ocr`、原 OCR provider、PDF 画布、文档修订与发布事件。没有第二套 OCR 服务或馆藏。
- 三栏页面列表/原页与当前正文/问题及来源。页数来自真实 Asset 和 Page；没有解析记录的页单独提示，不补造空白页或任务成功率。原稿预览使用受权限保护的既有画布，缩略图来自真实 PDF。
- 状态筛选使用实际正文来源、引擎置信度、失败页记录、人工正文与人工核验记录。替换符提示仅基于实际 U+FFFD；横向页面候选仅基于宽高比大于 1.2，不据此认定合扫、拆页或猜左右字形位置。
- 逐页/已选页/全部未保护页识别传入真实物理页序；暂停、从已有页面继续、取消剩余识别复用原逐页检查点。运行中先安全暂停才能取消。旧任务、已保存正文和错误记录保留。
- 语言（简体中文、繁体中文、英语）与版面开关经 `job.stats.task_options` → worker → extract → provider 的 Form 参数实际传递。质量阈值改变待校对筛选；这些设置和跳过页范围保存在任务中，恢复时保留。服务实际启用的模型决定版面能力，未做健康探测，不显示已连通。

## 人工修订与核验

- `PageTextRevision` 保存不可原位改写的原文、候选正文、说明、人工确认、来源指纹、操作者、请求标识及采用记录。`0069_page_text_revision` 仅编写，未执行。
- `save` 只保存候选；`prepare` 返回实际前后正文、阻止原因和采用影响指纹；`apply` 再次验证全部来源、候选修订和影响指纹。空白正文必须说明依据，未确认候选不能采用。
- 采用后 Page 的显式 `is_text_manual` 与 `manual_text_revision` 保护正文。普通导入、批量重识别、缺页清空和暂存重置均不得覆盖。保护不藏在 geometry 中。人工标记/记录 ID 参与文档校验和，因此原字相同但确认状态改变也生成真实证据修订。
- 曾经公开过的文件先克隆正文解释，再调用原文档修订、证据片段和公开发布链；旧 Page、Passage、引用及文件保留。当前未公开文件采用后显式选择新规范副本；只切换规范文件，不误启用旧 normalized 类型的 source_asset。人工目录按原文档身份复制到新修订，未发布书目由 `ocr_text_correction` 发布来源规则保护。
- 人工正文没有可靠字形位置，Passage 仅保存准确字符偏移，bbox 为空，不编造坐标。原 OCR confidence 保留，质量报告另记人工核验覆盖与权重，不把人工决定变成模型概率。独立正文采用不会声称已重写下载 PDF 的文字层。
- `review` 批量核验最多 200 页、合计一百万字，必须逐页对照明确确认。每页绑定来源指纹，批次绑定全局候选修订；任一页变化则整个批次不写入。核验以 `review_only` 修订和 `Page.reviewed_text_revision` 单独保存，不改正文、文档证据、公开文件或 OCR 任务状态。空白页须附说明。
- 人工核验绑定实际文档修订和准确正文。正文重新写入会清除当前核验指针，文档修订变化时旧记录失效，历史继续保留。识别默认跳过当前有效的人工核验页，可显式关闭该跳过策略；已采用的人工正文始终保护。
- 新结果文件能查看所继承的人工正文原始修订记录；本文件自己的候选历史单独分页，避免伪造新文件的旧修订号。

## 契约与权限

GET 参数：`pdf_page`、`list_page`、`history_page`、`status`、`quality_threshold`、`detect_spreads`、`detect_garbled`。返回文件实际身份/来源资格、当前正文、候选与历史、真实任务、逐页状态、缺失解析页数；返回 `source_version`、全局 `expected_revision` 和每页 `source_fingerprint`。

POST action：`save / prepare / apply / review / start / pause / resume / cancel`。保存和核验需 EDIT_METADATA，采用需 PUBLISH_WORK，OCR 任务命令需 RETRY_JOBS；均需后台读取权限。

- 保存/采用使用 `expected_revision + source_fingerprint`；采用另需 `prepared_fingerprint`。
- 批量核验使用 `pages:[{pdf_page,source_fingerprint}] + expected_revision + confirmed + note`。
- start 使用 `source_version + confirmed + page_indexes? + task_options?`；任务命令使用 `job_id + job_version`。
- 所有写入使用 UUID `request_id`。幂等回执先于来源/CAS检查，响应丢失后可查回原结果；同 nonce 不允许改操作内容。锁顺序为 Edition → Asset/Job → Page；恢复器释放 Job 锁后才修复 Edition 摘要。
- 409 保留正文、说明与选择；重新对照后才能基于新来源再次提交。写接口关闭 401 自动刷新重放。外层工作台按会话 epoch 重新挂载，同一账号的新会话也清除候选输入/历史/预览，旧异步结果不回显。

## 修改归属与检查点白名单

本单元新增的 10 个文件：

1. `api/catalog/migrations/0069_page_text_revision.py`
2. `api/ingestion/services/ocr_workspace.py`
3. `api/ingestion/ocr_workspace_views.py`
4. `api/tests/test_ocr_workspace_20261018.py`
5. `web/lib/api/ocr-workspace.client.ts`
6. `web/components/admin/library/ocr-workspace.tsx`
7. `web/components/admin/library/ocr-workspace.module.css`
8. `web/app/admin/library/assets/[assetId]/ocr/page.tsx`
9. `web/tests/ocr-workspace.spec.ts`
10. 本文档。

本单元改动的既有文件及准确归属：

- `api/catalog/models.py`：Page 三个人工字段及 PageTextRevision 模型；本轮新增。
- `api/catalog/services/document_intelligence.py`：stage 重置保护、人工正文指纹、真实质量权重为本单元；`schedule_outline` 参数为并行文件工作台单元。后者仅控制新文件解析是否自动安排目录，原 OCR 默认不变。
- `api/ingestion/services/extract.py`：本单元增加 Edition→Asset 锁、人工正文保留、核验失效和 task_options。继承的 geometry/provenance 校验及 `_passage_chunks` 准确原文偏移已审阅，人工正文直接复用该 helper，需要一起保存。
- `api/ingestion/services/processing.py`：本单元增加 selected_pages 的范围/剩余页/完成页/发布与派生处理支持、保护页过滤、task_options 透传。继承的 claim token、来源核验、心跳、取消及迟到 worker 检查、逐页恢复、锁后修复 Edition 摘要已审阅，为当前工作台依赖；同文件继承的 EDITORIAL_ASSISTANCE/TEXT_EXTRACTION 调度与恢复为先前策划/目录依赖，不应误称 OCR 新增。
- `api/ingestion/services/catalog_ocr.py`：本单元增加选页、策略、跳过人工核验/正文、nonce 内容约束与任务返回策略；继承的 `OCRSourceChanged`、暂存来源身份/页数/哈希检查和恢复保护已审阅，需要保留。
- `api/ingestion/services/ocr_provider.py`：本单元仅新增策略校验与语言/版面参数透传。
- `api/ingestion/services/ocr_inventory.py`：本单元仅扩展 selected_pages；继承的取消旧任务排除、同一任务文档修订后允许收尾、来源重验和终结阶段恢复已审阅，属于工作台恢复链。
- `api/ingestion/urls.py`：本单元仅 OCRWorkspaceView 导入与路由。
- `api/ingestion/views.py`：本单元仅 ProcessingCenterActionView 的 requested_mode 接受 selected_pages。其余继承或文件代理新增 staged 守卫应由主代理按各自单元审阅，不据本条全文件归为 OCR。

需要随 OCR 保存的已审继承依赖：`api/ingestion/services/ocr_pdf.py` 的 crop/rotation 几何映射、无可靠坐标不写字形、缺定位块报告与无可写块失败说明。该文件本单元没有再修改。

`knowledge_publication.py` 中 `ocr_text_correction` 来源由文件代理与 `file_selection` 一起添加，主代理合并白名单。work-library/WorkflowEditor 的 OCR 入口由主代理负责，未在本代理改动范围。

已读但不是本 OCR 单元新增依赖：`processing_identity.py` 中特别策划标签，`processing_center.py` 中策划查询和作品/版本筛选。后者可能由文件工作台采用，不应无依据全部归到 OCR。OCR 服务 `ocr_service/app.py` 的 languages/layout 表单原已存在，本单元未改服务；其其他继承修改须独立归属。

## 静态检查与待验收

- 目标 Python 13 文件 `python -m compileall -q ...` 退出 0；目标 Git diff whitespace 检查退出 0（CRLF→LF 提示不改变现有文件）。
- OCR 前端组件/client/route/spec 目标 ESLint 退出 0，真实封面和缩略图有 2 条 next/no-img 提示。
- 最近一次全量 TypeScript 仅报并行文件单元 `tests/work-files.spec.ts` 缺 `public_preparation`，已通知主代理；OCR 类型未报错。最终合并检查由主代理记录，不提前宣称全量通过。
- 后端回归覆盖保存/采用/版本/幂等/权限/保护/并发/取消/批量核验/策略/真实候选；前端 8 个合成场景覆盖保存、409、未保存保护、选页、人工页、策略与核验。均仅编写，没有执行。
- 未运行测试、浏览器、构建、正式视觉回归、真实 OCR/模型/NAS、索引或检索评测、迁移、生产操作。硬件服务能力、实际 PDF 字体/裁剪/旋转效果与任务恢复仍须统一验收。未执行 Git 提交。
