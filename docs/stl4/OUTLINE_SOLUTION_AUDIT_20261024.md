# 书籍目录、PDF 书签与期刊题名方案核验

2026-10-24。范围为当前工作区的只读源码追踪与成熟项目官方资料核验。本报告只新增本文件，没有修改业务源码、提交、测试、浏览器操作、构建、业务请求、模型运行、检索质量基准或部署。结论是源码事实及据此提出的方案，不是实际材料识别效果或运行验收。主代理同时开发，行号按本次读取时的文件定位，后续以函数名为准。

最小可行路线是继续增强现有 `DocumentOutlineRevision → ProcessingJob → 目录校准 → 明确采用 → Reader`，复用已安装的 PyMuPDF、RapidFuzz 和现有 PP-StructureV3 接口。优先修复待复核漏选、几何转换和期刊候选到原编目草稿的连接，再增强版式、标题匹配及分段页码。无须先安装一整套新解析框架。

## 1. 已有需求与阅读范围

已有需求并非本次新增推断。`docs/NEXT_DEVELOPMENT_MANUAL.md` F05/F06（约139–158行）明确要求原生书签、印刷目录、正文标题融合，保留层级/同页节点，分段页码，不覆盖人工校准，旧馆藏批量修复，Reader 同源，允许人工修正。该文档同时明确不承诺任意 PDF 零错误还原。`docs/stl4/OUTLINE_CALIBRATION_20261018.md` 已记载目录三栏、候选/修订/采用/恢复及权限边界，状态为源码接入、统一验收待核实。

已完整读取 Ponytail full、开发专项规则及根 `AGENTS.md`，核对当前 Git 分支 `codex/stl4-unified` 和继承未提交改动。已读 `CURRENT_PROGRESS.md`、`docs/stl4/PROGRESS.md`、`RECOVERY.md` 顶部，`MASTER_SPEC.md`、上述 F05/F06 与目录校准文档，以及 `ARCHITECTURE.md`、`PROGRESS.md`、`ISSUES.md` 的目录相关记录。没有加载研究/学术写作模式，没有采用其他图片作为视觉依据。本次没有评定终稿112–115页的视觉实现质量。

主要已读源码如下。

| 文件 | 已读关键函数/内容 |
|---|---|
| `api/catalog/services/document_outline.py`（完整） | `extract_outline`、`validate_nodes`、`edit_outline`、`adopt_outline`、`public_outline`、`queue_outline_rebuild`、`run_outline_job`、取消/重试与派发 |
| `api/catalog/outline_views.py`（完整） | 管理/公开读取与命令、批量 inventory/重建、原任务动作 |
| `api/catalog/models.py`（相关类） | `Page`、`DocumentOutlineRevision`、`JournalIssueArticle`、`Edition` 期刊字段 |
| `api/ingestion/services/extract.py`（相关函数） | `_native_pages`、OCR结果转换、`persist_pages`、人工文字/页码保护 |
| `api/catalog/services/document_intelligence.py`（相关函数） | `synchronize_document_revision`、native/OCR后续调度与文档来源绑定 |
| `api/catalog/services/page_labels.py`（识别部分） | 页边号码、罗马数字、邻页连续证据、段应用 |
| `api/catalog/services/page_mapping.py`（相关函数） | `current_data`、`validate_data`、`diagnostics`、`save_mapping`、`prepare_mapping`、`apply_mapping` |
| `api/catalog/services/page_geometry.py`（完整） | `native_geometry`、`validated_geometry`、`normalized_bbox`、`locator_geometry` |
| `api/ingestion/services/metadata.py`（相关函数） | `detect_document_type`、`extract_text_candidates`、`resolve_grobid`、`enrich_candidates`、`select_best` |
| `api/ingestion/services/metadata_scoring.py`（完整） | 来源权重、字段冲突、相似候选归一化；这些分数不是实证校准的正确概率 |
| `api/ingestion/services/candidate_store.py`、`candidate_decisions.py`、`candidate_context.py`（相关部分） | 候选上下文、来源证据、人工决定/锁保护与采用路径 |
| `api/catalog/services/journal_issues.py`（完整） | 整期目录校验、同步、快照与公开链接过滤 |
| `api/catalog/services/work_editor.py`、`editorial_revision.py`、`workflow_serializers.py`（相关部分） | 原书目草稿、`journal_contents` 校验/保存、确认字段锁 |
| `api/ingestion/tasks.py`、`processing.py`、`processing_recovery.py`（相关部分） | 目录原队列、任务 claim/恢复、执行编号与来源复核 |
| `ocr_service/app.py`（相关部分） | `structure_engine`、`extract_structure_blocks`、`recognize`、进程/模型负载边界 |
| `web/components/admin/library/document-outline-workspace.tsx`（完整）、`outline-edit-state.ts`（完整）、`outline-pdf-preview.tsx`（完整） | 节点/子树、来源候选、人工确认、保存/采用/恢复、真实PDF预览与owner清理 |
| `web/lib/api/document-outline.ts`（完整）、`curation-workspace.client.ts`（目录部分） | Reader树筛选、`outlinePosition`、目录契约与命令 |
| `web/components/admin/workflow/workflow-editor.tsx`（期刊部分） | `JournalContentsField`、已有论文关联与书目草稿 |

另以 `rg` 追踪所有目录服务调用点，定位 `catalog/views.py` manifest、`serializers.py`、`public_work_detail.py` 和任务中心，不将只搜索到的文件写成完整审阅。已有 `test_document_outline_20261013.py`、`test_outline_atlas_20261018.py` 与前端目录场景已定位，仅阅读相关覆盖入口，未执行。

## 2. 已确认的真实链路与可复用保护

1. 原生解析/OCR写入既有 `Page/TextBlock/Passage`。`persist_pages` 保持 `Page` 主键，保护人工文字及人工页码；已发布正文禁止原位改写。`synchronize_document_revision` 保存原文解释版本，并调用 `queue_outline_rebuild(... automatic=True)`。
2. 目录任务仍是 `ProcessingJob.job_type=text_extraction`、`stats.operation=outline_rebuild`，幂等身份绑定 Asset、SHA、DocumentRevision、`PARSER_VERSION`。Celery 的 `process_outline_job` 调 `run_outline_job`，沿原 claim/心跳/恢复机制，没有第二套收件或目录任务库。
3. `extract_outline` 用 `get_toc(simple=False)` 取完整书签层级/同页条目/落点；逐页文字和块提供印刷目录与正文标题观察；按每个实际标签查物理页，没有猜全书统一偏移。自动结果新增不可变修订，当前人工已采用目录不会被重建替换。
4. 管理 `GET /catalog/admin/assets/{asset}/outline/` 返回 active/latest/history/jobs。保存 `edit` 只新增候选；`adopt/restore` 要求有效落点及所有节点 `confirmed/native`，并新增修订。`expected_revision` 防并发覆盖，`base_revision_id` 分清编辑基准；固定 `request_id` 回放原回执。旧 PDF 与旧修订保留。
5. 后台读取需 `CanAccessBackOffice`，写目录需 `EDIT_METADATA`，重建/任务动作需 `RETRY_JOBS`。公开服务检查当前正式文件/访问状态/准确原文解释，剥离未采用候选来源。Reader/manifest/详情共同调用 `public_outline`。这套资格与身份链必须继续复用。
6. 页码校准已经有 `PageMappingRevision`、阿拉伯/大小写罗马段、缺页、每个物理页最多两个印刷标签。采用走暂存文件和原发布链，复制原目录并更新标签，不覆盖已发布原文。目录提取器目前尚未充分消费这个结构化映射。
7. 单篇论文元数据已有 GROBID 可配置端点。`resolve_grobid` 调 `processHeaderDocument`，提取文章题名、作者、摘要、刊名、卷期、页码、DOI，`consolidateHeader=0`。Crossref/OpenAlex等已有候选来源。它们进入候选/字段决定体系，不能代替 PDF 原文核实。
8. 整期期刊已有 `JournalIssueArticle`，保存题名、作者显示、印刷页码、顺序及可选馆内论文关联。`JournalContentsField → 书目草稿 → normalize_journal_contents/sync_journal_contents → 发布快照 → public_journal_contents` 已存在；公开链接只指向仍正式公开的单篇论文。

“网站目录”和“下载PDF内嵌书签”应分清。当前业务源码没有 `set_toc` 或等价目录写回调用，只有测试生成样本使用它。已采用目录目前是数据库/Reader导航，不能宣称下载文件已补写书签。若需要下载副本内嵌书签，后续应在既有派生阅读/下载副本链中输出新文件，绑定采用修订，保持 ORIGINAL 字节不动。

## 3. 可定位的缺口与最小修正

### P0：待人工复核的目录可能被漏出工作清单

`document_outline.py:223`附近的唯一正文匹配把印刷目录节点标成 `matched`，只有 `needs_review` 分支写 `contents_target_uncertain`。`run_outline_job:668`附近却以 `bool(diagnostics)` 写任务 `needs_review`；`outline_views.py:134`附近批量“needs_review”也仅查未reviewed修订的非空 diagnostics。因此，一个全部匹配到唯一页、没有其他诊断的纯印刷目录，仍需要确认才能采用，却可能不在待复核筛选。前端已经把 `matched` 显示为“待复核”，存在跨层语义差异。此结论来自分支阅读，尚未执行复现。

最小修正是在共享服务从真实节点计算 `unconfirmed_count`、`invalid_target_count`、`needs_review = any(status not in {confirmed,native} or invalid_target)`，用于任务、管理状态和批量清单。不要只修文案，也不要以给全部matched自动confirmed消除问题。可在新修订保存时写一个明确诊断/汇总，同时为历史修订提供准确回退；新增字段放现有JSON/响应即可，不必先加表。`reviewed`表示采用历史，不足以替代逐节点状态。

### P0：目录落点绕过了已有精确几何转换

`document_outline.py:199`附近块查询只读 Page.width/height/text_source，不读 `Page.geometry`。原生解析保存的 width/height 来自已经随旋转变化的 `page.rect`，bbox来自未旋转坐标；`web/lib/api/document-outline.ts:outlinePosition` 先除这些尺寸再按90/270度旋转。非正方旋转页可产生比例偏差。现有共享 `page_geometry.normalized_bbox/locator_geometry` 已验证旋转矩阵、CropBox和OCR渲染矩阵，目录没有复用它。

最小修正为目录块读取真实 `geometry`，后端复用 `normalized_bbox` 生成已验证的 `normalized_position`，保存原bbox及坐标来源；前端优先这一值，未知空间只降到页级。原生书签的 PyMuPDF TOC 坐标与未旋转TextBlock坐标继续区分。不能靠 clamp 把错误坐标压进0–1冒充准确。真实旋转/裁切/不同DPI PDF仍待统一验收。

### P0：整期目录只有人工表单，尚无可复核的自动候选桥梁

`journal_issues.py` 全部函数只校验/同步已提交条目。`workflow-editor.tsx:445`附近 `JournalContentsField` 仅添加、编辑、排序和选馆内论文。`document_outline.extract_outline` 对所有文献跑相同章节规则，没有文章/作者/栏目类型，也不产出整期书目候选。`metadata.detect_document_type:69`只返回书/单篇论文/学位论文/报告，不能产生journal_issue；DOI或摘要+关键词即可返回单篇论文，整期内第一篇的这些线索可能触发错误类型候选。

最小桥梁沿现有目录修订保存文章候选，先提供只读候选列表与“填入本期目录草稿”，再由原工作流保存。每项候选绑定 outline_revision_id、node_id、Asset SHA、DocumentRevision、印刷目录原页、正文题名块、作者相邻块和物理页。正文找不到、题名重复、作者不明、栏目/广告未分清时标待核对。不要自动建立 Work、合并论文、拆PDF、建立人物或直接调用 `sync_journal_contents` 改正式条目。

建议入口仍在原目录API与原 `JournalContentsField`，新增结果只是候选投影。填写时校验当前准确来源、候选身份、书目edit_version和账户能力；把勾选项追加到当前草稿，原行及其ID保留，重复候选说明原因。通过原 `WorkWorkspaceEditsView` / `save_editorial_workflow_section` 保存 bibliography，再走既有发布；显式替换整期目录才允许移除原行。候选来源和采用节点写现有AuditEvent回执。现有row serializer不接收来源字段，不能假定往表单多塞JSON就已持久化来源。

### P1：原生书签“结构有效”还不等于题名/落点正确

`_readable:49`只拒绝空、替换字符和部分控制字符。`extract_outline:147`附近只要标题可读、页/坐标在范围内就标native；`run_outline_job` 可在全native且没有人工active时自动激活。乱码而无U+FFFD、广告/网址、重复无意义题名、错到另一章的有效页，均不被这层检测发现。

保留原生观察及完整树，增加标题对实际落点/邻近正文题名的核对、重复异常和明显无效标题诊断。坏书签不能因为“页数合法”自动获得可信地位；没有正文或OCR时保留“原生来源，内容未核对”，不能虚构验证成功。已有人工目录保持优先。Docling可借鉴匹配与层级信号，但其“匹配不到即丢弃”的策略不直接照搬，本站要保留供人工比较。

### P1：印刷目录与标题识别的主要上限

`CONTENTS/ENTRY/TRAILING_PAGE/HEADING/_level` 与逐行循环有以下确定限制。

| 情形 | 当前源码限制 | 最小增强 |
|---|---|---|
| 多级书籍目录 | 编/部/篇/章多归一级，节归二级；字面缩进、字体和版式未参与层级 | 文献内部综合编号类别、字号/字重、缩进、父章节和原生层级，不写死所有书同一层级表 |
| 繁体、多语种、无编号标题 | CONTENTS只有简体目录与英文；正文HEADING不覆盖无编号Introduction/Preface、单个1标题等 | NFKC匹配键、已观察标题的编号/字体样式候选、繁体标记；保留原文标题，不用翻译生成题名 |
| 多栏/续行目录 | 把整页text逐行串接，pending可能跨列/跨条混合 | 用现有TextBlock bbox/版面读序分列、按页码右侧对齐与缩进组行；记录目录来源bbox |
| OCR差错/换行/断词 | 正文匹配主要为去标点后精确key，正文行与整块分别收集 | 精确优先，再在受页码段/父级/邻近范围限制的候选上用已安装RapidFuzz或stdlib匹配；保留候选差距，不用全书任意相似句直接落点 |
| 重复Introduction/参考文献等 | target受last_page约束；匹配阶段没有真正用父章节范围消歧 | 将父范围、前后已验证锚点、同段页码及实际标题块共同约束；并列候选待复核 |
| 前言罗马页、多段重起 | 仅按整个printed_label字符串查页，未用label_segment和page_mapping的labels列表 | 从现有结构化映射取标签+段身份；重复号码不取首个；分段单调，遇插页/缺页停止推断 |
| A-1、e123、页码范围与合订 | ENTRY标签只支持阿拉伯或罗马数字，双页的“10–11”不能按单标签命中 | 分离原始标签、标签列表及段；合订各部分独立，双页目标绑定区域；缺物理页不能造跳转 |
| 索引、书目表、栏目/广告 | 三条点引线可判目录，任何匹配HEADING的正文行可作标题，未消费block_type过滤 | 目录页形态、标签模式、题名块类型联合判断；索引/参考文献可作为导航节点，不能把每个索引词当章节/论文 |
| 扫描/竖排 | 正文正则不读方向/竖排；普通OCR按y再x排序易串栏 | 复用PP-Structure的标题类型/读序；竖排先依实际语言/方向能力处理，无法证明读序则待校准 |

原生 `_native_pages` 已拿到 spans，却只保存文字和bbox，字号、字体和方向在此丢失。第一步可在目录任务内用现有PyMuPDF按需读取实际候选页的 `dict` spans，不必为了目录立即迁移整张TextBlock表。随后若共享结构确有需要，再明确保存版本化结构字段。

### P1：已有 PP-StructureV3 应接准，再考虑新增解析器

`ocr_service/app.py` 已导入PPStructureV3，`structure_engine`约234行、`extract_structure_blocks`约401行、`recognize`约426行可复用；默认 `OCR_ENABLE_STRUCTURE=false`，不能把代码存在写成服务已启用。官方结果包含block_label/block_bbox/block_order等；当前adapter主要读取旧`index`，没有明确保留新版block_order/block_id，并在默认路径把普通OCR按几何排序。应按实际部署版本规范化字段，保留读序、标题/页眉页脚类型和真实模型版本；缺失时明确回退，不伪造置信度。现有structure的`score`缺失会回退1，这只能是字段缺省，不能宣传为100%识别信心。

### P1/P2：任务与来源修订边界

目录任务目前有阶段进度、心跳和结果修订，但没有持久化逐页目录解析中间产物；恢复会重新提取，不能承诺从某节点继续。几何全页扫描在首个进度回调后较久没有新的回调，全书Page文字和块也在内存聚合。先在每页/分批读取处补心跳、取消检查与边界，目录独立结果失败不影响已经完成的正文。确需耗时增强时，将按页观察缓存放既有任务派生存储，身份包括SHA/原文修订/解析器版本，完成后一次性写目录修订。不要用未完成树替换active。

重试继续核对task_id、源文件、原文解释和人工active。变更算法须提升PARSER_VERSION，避免自动任务被旧幂等结果吞掉。新文本解释不能直接继承旧确认；只有确定没变的原文件/页/题名证据可以提出“保留原人工校准”的候选，仍需明确复核/重定基准。旧人工修订及原失败记录保留。

## 4. 推荐数据契约与实施顺序

尽量扩展原节点JSON/候选响应，已有字段保持含义。

| 层 | 最小新增/明确约定 |
|---|---|
| 来源 | revision继续绑定asset_id、source_checksum、document_revision_id、parser_version；外加结构解析实际engine/model/version，不冒用OCR默认模型 |
| 来源观察 | `candidate_sources`可加source_page、source_bbox/geometry、真实文字/块引用；目录原页和正文目标页分别记录；输出长度设限 |
| 精确定位 | 验证后的normalized_position优先，unknown降页级；原始坐标留档，不能把OCR pixels冒充PDF points |
| 页码 | printed_label继续作显示，另用既有page_mapping取labels/segment；多对一和重复标签不自动唯一化 |
| 质量 | match_signals（题名相似、标签相符、父范围、读序、候选差距）和diagnostics；这是规则支持程度，未经校准不可命名为正确概率 |
| 人工决定 | calibration_status与机器支持程度独立；confirmed必须由明确操作产生。变更标题/父级/页/位置撤回确认；保存不等于采用 |
| 整期候选 | 类型article/section/unknown及题名、author_display、原始页码、可核对正文范围；馆内论文ID只人工选；机器不认定作品/人物相同 |
| 汇总 | unconfirmed_count、invalid_target_count、needs_review、diagnostic_counts来自同一共享函数，贯穿任务/批量/工作台 |
| 采用 | 使用原expected_revision/base_revision_id/request_id；整期草稿另核书目edit_version和来源版本，回执可查，冲突保留输入 |

建议按三个最小单元实施，每个单元沿项目约定保存契约、进度和Git检查点，最终统一验收。

1. 修复待复核统计与旋转/裁切定位。涉及 `document_outline.py`、`outline_views.py`、`document-outline.ts` 和契约。补漏选与真实旋转样本用例，仅编写到当前禁止测试阶段结束。
2. 在原目录候选服务增加期刊内容候选投影，原 `JournalContentsField` 显示来源、预览、明确选择和追加到当前草稿。复用原工作流保存/锁/发布，禁止自动新建论文和覆盖原行。为整期类型保留人工选择，不以一个DOI把整期当单篇。
3. 增强目录分栏/续行、受约束模糊匹配和字号编号层级；接入已存在PP-Structure的实际结构输出。以失败原因决定是否对少量页面启用增强，不把每一本整书都送新模型。需要下载内嵌书签时另接派生副本。

## 5. 成熟方案官方资料、许可与取舍

以下于2026-10-24查阅，均为项目官方文档、作者仓库或原始论文，不引用第三方排名或重做检索质量基准。链接为移动分支/最新文档时只证明所阅版本；实施前固定真实版本/提交。项目声明的API PyMuPDF为1.26范围，不能直接假定latest文档新增的2.0能力已在本地。

| 项目 | 可复用能力及本项目用法 | 许可/新增依赖 |
|---|---|---|
| PyMuPDF | 官方 `get_toc(simple=False)`完整目的地、PageLabels可重复；`get_text('dict')`有span字体/字号/flags及bbox。继续用已安装能力完成候选页样式与原始书签读写。 | AGPL/商业双许可。现有依赖，不新增；不能因其已安装就省略发布包现有许可核对。[Document API](https://pymupdf.readthedocs.io/en/latest/document.html)、[文字结构](https://pymupdf.readthedocs.io/en/latest/app1.html)、[官方许可](https://pymupdf.readthedocs.io/en/latest/about.html) |
| Docling | 官方heading hierarchy逐标题结合书签、编号、字体样式；书签按题名+页匹配；规则本身无需额外模型。参照其方法局部改现有服务，保留本站人工与疑点观察。不要直接依赖整套Docling的对象树。 | 代码MIT。复制实质代码需保留版权/许可；整体安装会增加其转换依赖，模型另核权重许可，本轮无必要。[层级文档](https://github.com/docling-project/docling/blob/main/docs/usage/heading_levels.md)、[源实现](https://github.com/docling-project/docling/blob/main/docling/models/stages/heading_hierarchy/heading_hierarchy_model.py)、[LICENSE](https://github.com/docling-project/docling/blob/main/LICENSE) |
| PaddleOCR / PP-StructureV3 | 官方版式类型、多栏读序和bbox适合扫描目录/期刊；当前OCR服务已有接入点，优先规范其输出，按需处理候选页。不能由文档能力推出本机服务已启用/已正确识别。 | 代码Apache-2.0，新增模型文件与各自声明/资源预算仍需核对；无需第二套OCR主库。[官方管线与输出](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md)、[LICENSE](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE)、[作者技术报告](https://arxiv.org/abs/2507.05595) |
| GROBID | 当前已接header服务，可辅助单篇文章题名/作者/刊名。全文服务可返回所选结构坐标，需与PDF实际尺寸/CropBox对齐。官方明确主要针对学术文章、长书与非主要训练语言质量不确定，不作为整期期刊拆篇器。 | 主项目Apache-2.0，分发包中pdfalto等独立许可另核；服务端能力已配置才使用，不新增强制Java服务。[REST API](https://grobid.readthedocs.io/en/latest/Grobid-service/)、[坐标](https://github.com/grobidOrg/grobid/blob/master/doc/Coordinates-in-PDF.md)、[适用边界](https://grobid.readthedocs.io/en/latest/Frequently-asked-questions/)、[LICENSE](https://github.com/grobidOrg/grobid/blob/master/LICENSE) |
| RapidFuzz | 受父范围/页码段限制后比较OCR题名候选；相似度只排序，不证明同书/同篇/同一作者。短候选也可用stdlib difflib，按现有代码风格选择。 | MIT，已列API requirements，无新增依赖。[官方项目](https://github.com/rapidfuzz/RapidFuzz)、[LICENSE](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE) |
| pdf.tocgen | 成熟的字体/位置配方与精确纵向书签写回范例，适合软件生成PDF；官方不期待其处理扫描件。仅作算法/操作参考，现有PyMuPDF已能覆盖所需读写。 | 程序GPLv3；recipes单独CC BY-NC-SA 4.0，不能当成同一种自由代码许可直接搬入产品。无需新增此依赖。[作者仓库与许可](https://github.com/Krasjet/pdf.tocgen) |

## 6. 人工高精度复核与统一验收样本

自动处理可以把证据齐全、易确认的候选提前呈现，不能保证每本书、每种扫描和每一期刊100%正确。原生书签也可能错。人工复核应逐项查看真实目录原页与正文目标，核对题名全文、父级、顺序、物理页、印刷标签及页内位置；期刊另核作者、栏目/文章身份、起止范围和刊名/卷期。无正式印刷目录时明确标“生成导航”。缺页、文字破损或来源不明保留未解决，不能把批量确认当作已经读过原文。

以下是待统一验收的代表性样本设计，不是已经取得材料或已运行结果。优先用用户合法本地材料及可公开获取原文，功能边界可用合成PDF，真实质量必须由人工核实的真实PDF补齐。每份保留源SHA、版本、人工期望节点/页/区域、解析版本及差异，不编造书名、页码或准确率。

| 样本 | 必核结果 |
|---|---|
| 有效三级原生书签、父子同页 | 全层级和顺序保留，节点各自跳转，不压成Page.chapter_title |
| 原生书签有乱码/网址/重复名/合法页但错章 | 原观察保留，疑点入待复核，不自动认定正确 |
| 无书签但完整中文/英文/繁体目录 | 目录原页、续行题名、子层级和正文落点可核对 |
| 字号标题、无编号前言/导言/后记 | 候选来自原文，未虚构章节，人工可调 |
| 单栏、双栏、跨页目录及同页多章 | 不跨列拼题，不漏后续目录，保留独立节点 |
| 罗马前言→阿拉伯正文→附录A-1 | 各段独立，标签与物理页分列，不套全书偏移 |
| 重复页号、合订多卷、译本导言/附录 | 段/父章节消歧，不能借另一个版本页码或首个同名标题 |
| 缺页、插页、折页、双页扫描 | 不造物理页；双页标签与区域区分，无法确认时保持待校准 |
| 90/180/270度与非零CropBox、不同OCR DPI | 用真实几何矩阵定位，未知空间降级，逐项查看落点 |
| 纯扫描、混合文字、缺ToUnicode、竖排 | 显示真实OCR来源与读序限制，不用乱码正文强行匹配 |
| 单篇中文/英文期刊论文 | 文章题名/作者/刊名分清，摘要/关键词/页眉不误作题名 |
| 整期含封面、栏目、文章、书评、广告 | 生成候选与栏目类型，排除/待核对明确，人工选入原期刊草稿 |
| 整期含双语题名/多作者/连续或重起页码 | 同篇双语候选不自动拆成两篇；作者、页码范围据原文核对 |
| 无题名页/仅摘页/没有真实目录 | 返回不足和人工入口，不从外部匹配捏造原文结构 |
| 已采用人工目录后重建、并发编辑/采用 | 人工active与历史不覆盖；冲突保留输入，回执重放无重复写 |
| OCR后原文修订变化、换PDF、迟到任务 | 旧候选拒绝采用，原件/人工历史/私人书签身份保留 |
| 取消、队列失败、恢复、限内存长PDF | 状态真实，来源/执行令牌复核，结果不会半树激活；重新提取与断点恢复文案准确 |
| 匿名/读者/编目员/重试能力分离、撤销权限 | 未采用来源只后台可见，所有写入口遵守原能力与当前账户边界 |

现有用例已涉及同页层级、分段标签、人工保护、修订冲突、取消、来源更换、候选私密和OCR坐标。它们不能替代上表真实复杂材料的逐项人工核对。本次全部保持未运行，下一步由主线先实施上述最小缺口，再按用户允许的统一验收阶段记录实际结果。
