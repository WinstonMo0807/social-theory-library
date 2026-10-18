# 验收记录

当前阶段：功能开发。全站正式功能、视觉、权限、迁移、性能验收全部待核实；未部署。

## 2026-10-18 公共导航静态收口

- `node node_modules/eslint/bin/eslint.js components/site-header.tsx components/ui/dialog.tsx components/reader-center.tsx components/public/site-footer-view.tsx lib/public-navigation-return.ts tests/public-navigation.spec.ts`（web）：退出0，6文件，0警告。
- PostCSS解析styles/layout/site-menu.css与public-responsive.css：退出0，32/5节点，仅语法。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：退出0。上一在途检查被会话中断后进程不可读取，没有把它当作通过；本次重新取得明确退出0。较早检索新文件曾报4条可空类型错误，修正后本次通过。
- 5个导航合成用例仅编写，未运行。最终PDF18已实际读取，不曾浏览器截图或正式视觉比对。检查点只纳导航白名单与ReaderCenter的section段，不含正在开发的检索/来源/反馈；所有生产操作未执行。

## 2026-10-18 文件、OCR与DOCX静态收口

- 唯一终稿PDF95–98、109–111及209实际读图。没有浏览器/实施页截图/正式逐图回归。本单元为源码接入，实际服务及全站验收尚未执行。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：生成契约后的最终检查退出0。此前并行修改阶段，先因版权说明types未同步、后因OCR/文件fixture新增字段缺失退出1，均补齐后重新检查通过；没有忽略错误。
- `node node_modules/eslint/bin/eslint.js components/admin/library/work-files-workspace.tsx components/admin/library/work-file-actions.tsx components/admin/library/work-file-preview.tsx components/admin/library/work-file-rights.tsx components/admin/library/work-file-public-preparation.tsx components/admin/library/work-library.tsx components/admin/workflow/workflow-editor.tsx components/pdf-canvas.tsx components/research/citation-docx-preview.tsx components/research/citation-manuscript-preview.tsx components/research/citation-audit-parse.tsx components/admin/library/ocr-workspace.tsx lib/api/work-files.client.ts lib/api/work-files.types.ts lib/api/citation-preview.client.ts lib/api/ocr-workspace.client.ts lib/api.ts tests/work-files.spec.ts tests/citation-docx-preview.spec.ts tests/ocr-workspace.spec.ts app/admin/library/works/[workId]/files/page.tsx app/admin/library/assets/[assetId]/ocr/page.tsx`（web）：22路径退出0，0错误/4警告（OCR真实封面/缩略图2条no-img，旧WorkflowEditor2条导航规则提示）。
- `.venv/Scripts/python.exe tmp/checkpoint-files-ocr-docx.py --stage`：68条已复核源码/契约/单元记录精确暂存，补10条全局记录后78路径提交为e310536，63整文件+5按hunk。脚本对暂存Python逐项`ast.parse(git show :path)`及cached whitespace检查退出0。另标准库AST汇总37个暂存Python文件、PyYAML对可选compose overlay仅语法解析退出0；不导入应用或访问数据库。脚本禁止在已有暂存或HEAD变化时重跑，不能作为下一轮通用git add脚本。
- PostCSS解析work-files.module.css和ocr-workspace.module.css退出0，顶层节点164/79。所有语法结果不证明实际布局。
- 仅本进程环境`DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false`、`DJANGO_DEBUG=true`，执行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/files-ocr-docx-openapi.json --validate`最终退出0，0errors/10条原Home/Scholar/Topic类型提示。首次因文件采用动态get_permissions读取schema缺失kwargs失败，增加swagger_fake_view静态路径修复，真实权限未放宽。新增mode枚举碰撞通过共用DocumentRevisionApplyModeEnum命名消除。
- openapi-typescript的openapiTS/astToString同步schema.json与前端生成类型，退出0。结构化对比原126 paths全部保留、内容未变，新增15 paths至141；原MappingPreviewModeEnum改为页码/人工文字共用枚举，没有删减业务契约。
- DOCX交叉审查修复过期请求仍运行/晚到回写、解密前后未重验稿件/预览身份两项问题；12函数/22案例。文件34函数/37案例、OCR18函数/23案例；后端合计64函数/82案例，前端22场景仅编写，未运行。迁移0069/0012仅编写，未应用。
- ATLAS_INDEX更新95–98、109–111和209共8行，仍209行×22列，page/id/image_path/image_sha256逐项不变。全部为源码接入和正式验收待核实。
- 检查点保留必要OCR来源/取消/几何继承实现，排除旧备份、处理中心筛选/仪表盘、旧主流程OCR统计及下一单元帮助/导航/反馈/来源关注。未运行正式测试、浏览器、构建、真实OCR/转换器/模型/NAS、检索质量评测、迁移、生产清理或部署。

## 2026-10-18 反证、隐私和页码映射静态收口

- 最终PDF198–200、223–225、116–118均已实际渲染读取；没有实施页截图或浏览器操作。
- `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（web）：最终退出0。先前一次退出1仅为并行DOCX新文件缺PdfCanvas回调，补实际页数回调后本次重跑退出0；DOCX新单元尚未纳本检查点。
- `node node_modules/eslint/bin/eslint.js components/research/counter-evidence-workspace.tsx components/research/counter-evidence-editor.tsx components/research/counter-evidence-actions.tsx lib/api/counter-evidence.client.ts app/account/research/[id]/counter-evidence/page.tsx tests/counter-evidence.spec.ts components/research/research-session-detail.tsx lib/api/research.client.ts components/admin/library/page-mapping-workspace.tsx components/admin/library/page-mapping-thumbnails.ts components/admin/library/outline-pdf-preview.tsx components/admin/library/work-library.tsx lib/api/page-mapping.client.ts app/admin/library/assets/[assetId]/page-mapping/page.tsx components/reader-center.tsx components/research/privacy-workspace.tsx lib/api/privacy.client.ts tests/privacy-workspace.spec.ts app/account/settings/privacy/page.tsx app/account/settings/privacy/export/page.tsx playwright.auth.config.ts tests/page-mapping-workspace.spec.ts`（web）：退出0，22文件、0 errors/1条隐私封面no-img-element提示。
- `.venv/Scripts/python.exe -m compileall -q api/catalog/models.py api/catalog/migrations/0068_page_mapping_revision.py api/catalog/page_mapping_views.py api/catalog/services/page_mapping.py api/catalog/services/page_label_metadata.py api/catalog/services/knowledge_publication.py api/catalog/urls.py api/catalog/views.py api/catalog/public_response_serializers.py api/catalog/serializers.py api/catalog/services/search_geometry.py api/catalog/services/evidence_envelope.py api/catalog/services/document_intelligence.py api/distribution/serializers.py api/distribution/services.py api/ingestion/tasks.py api/reading/research.py api/reading/research_serializers.py api/reading/research_views.py api/reading/tasks.py api/reading/citation_audit.py api/tests/test_counter_evidence_atlas_20261018.py api/tests/test_page_mapping_20261018.py api/tests/test_resilient_publication_v260.py api/config/settings.py api/config/schema_urls.py api/reading/privacy.py api/reading/privacy_views.py api/reading/privacy_serializers.py api/reading/research_models.py api/reading/models.py api/reading/urls.py api/reading/views.py api/reading/serializers.py api/reading/migrations/0011_reader_privacy_operations.py api/catalog/services/discovery_sessions.py api/tests/test_privacy_atlas_20261018.py`：退出0，37文件；另单独编译api/distribution/views.py退出0，总38文件仅语法。
- PostCSS对counter-evidence.css、privacy.module.css、page-mapping.module.css执行parse：退出0，顶层节点分别122/141/96。
- 使用仅本进程的DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true执行`.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/counter-privacy-pages-20261018.openapi.json --validate`：最终退出0、10条既有serializer类型提示、0 errors；初次多1条export/erase枚举碰撞，命名ReaderPrivacyOperationKindEnum后消除。更新双页历史来源和可空条件后重新生成，结果相同。
- 用openapi-typescript的openapiTS/astToString同步api/openapi/schema.json及web/lib/api/generated/schema.ts，退出0。全量TypeScript最终检查在此生成之后。
- ATLAS_INDEX记录9个视图，仍为209行×22列，逐项核对page/id/image_path/image_sha256未变。索引只记录源码接入，视觉正式验收仍待核实。
- 新增后端43函数/46参数案例与前端24合成场景仅编写；旧页码73案例保持并适配新流程。没有运行pytest/Playwright/构建/正式E2E/视觉回归、数据库迁移、真实OCR/模型/NAS、检索质量测评或生产动作。静态结果不证明运行行为。
- 提交前核对79个明确路径（78整文件、distribution/views仅Reader相关hunk）；限定git diff --check退出0，来源身份与209×22结构不变，选定私钥/GitHub Token/OpenAI Key模式未命中。继承备份dispatch修改留在工作区，不纳入本单元；该有限模式扫描不等于全仓安全审计。暂存后再次核对79路径、整文件内容及cached diff --check退出0；检查点9a7c68c成功，备份hunk仍保留未暂存。


## 开发期检查

只记录实际完成的命令、退出码和范围。静态成功不能证明服务、数据库、NAS、Provider或公网可用。历史测试报告不覆盖本轮修改。

### 2026-10-16 视觉驱动检索接入静态检查

| 命令 | 结果 | 范围与限制 |
|---|---|---|
| `python -m compileall -q api/catalog/services/retrieval/deep_pipeline.py api/catalog/services/discovery_sessions.py api/catalog/discovery_tasks.py api/catalog/tasks.py api/catalog/discovery_views.py api/catalog/services/discovery_inference.py api/config/settings.py` | 退出0 | 仅语法编译；未启动 Django、Celery、Meilisearch 或推理服务 |
| `git diff --check` | 退出0 | 当前工作区差异；不代表业务行为通过 |
| `node node_modules/eslint/bin/eslint.js components/discovery-search-workspace.tsx lib/api/discovery.types.ts` | 退出0，1条既有警告 | 目标前端文件；`no-img-element` 警告未扩大为错误 |
| `.venv/Scripts/python.exe api/manage.py spectacular ... --validate` | 0 schema errors，10条既有 serializer 类型提示 | 生成并更新 OpenAPI；`--fail-on-warn` 仍会因既有警告退出失败 |
| `node node_modules/typescript/bin/tsc --noEmit --pretty false` | 退出1 | 仅报告三个既有 live 测试 TS7022；未定位到本轮深度检索文件 |

第三步检索质量评测按用户要求未运行；正式 E2E、全量功能、浏览器逐图回归、生产迁移和部署仍为待核实。

## 最终验收矩阵

| 门槛 | 核验内容 | 状态 |
|---|---|---|
| B01 | 计划规则/解释、时间估计、完成项和手动调整 | 待核实 |
| B02 | 授权笔记集合持久化、研究/计划隔离、撤销删除失效 | 待核实 |
| B03 | 体检/OCR容量、并发、NAS CPU/内存、取消/部分报告 | 待核实 |
| B04 | 所有者隔离与匿名公开搜索/阅读/下载/复制/引用 | 待核实 |
| B05 | 真实空库、错误/部分结果，无示例学术数据 | 待核实 |
| B06 | 209视图路由/API/移动/桌面/无障碍/性能逐图检查 | 待核实 |
| 接口 | OpenAPI/前端类型/错误/分页/筛选一致性 | 待核实 |
| 数据 | 迁移、保账号清理预演/恢复/真实登录 | 待核实 |
| 发布 | 上传→去重→编目→OCR→预览→发布→撤回→恢复 | 待核实 |
| 检索 | QueryLexicon、活动索引、真实多来源原文、页码 | 待核实 |
| Reader | 连续滚动、目录、书内搜索、选中、批注、引用 | 待核实 |
| 任务 | 持久状态、幂等、迟到结果、重试、取消、部分成功 | 待核实 |
| 运维 | 备份隔离恢复、NAS资源与生产切换/回退 | 待核实 |

最终视觉记录应逐行对应ATLAS_INDEX中的PDF页码、route和state，保存参考区域与实现截图位置、差异及复测结果，不以页面可打开算通过。

### 2026-10-18 阅读计划开发期静态记录

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`：退出0。
- 目标 ESLint（reading-plan-detail/form/plans、reader-collection-list、research-session-list、use-persistent-workspace、private-owner、research.client、reading-plan-workspace.spec）：退出0，1条no-img-element警告。
- `.venv/Scripts/python.exe -m compileall -q api/reading/research.py api/reading/plan_rules.py api/reading/research_serializers.py api/reading/tasks.py api/reading/local_analysis.py api/tests/test_reading_plan_atlas_20261018.py`：退出0。
- 以进程环境 `DATABASE_URL=sqlite:///:memory:`、`PUBLIC_DEPLOYMENT_MODE=false` 运行 `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-plan-schema-20261018.json --validate`：退出0，0 schema errors、10条既有类型提示。随后openapi-typescript生成成功。未连接生产库。
- Git依赖静态导入清单与45文件恢复检查点见CHECKPOINT_DEPENDENCIES；`git diff --check`与该批`--cached --check`退出0。
- 后端 `test_reading_plan_atlas_20261018.py`、前端 `reading-plan-workspace.spec.ts` 与auth-bootstrap新增用例均只编写，未执行。B01/B02/B04新增行为与B06逐图对照仍待正式验收。

### 2026-10-18 引文体检开发期静态记录

实际参考：仅由最终PDF渲染并读取第208–215页。实现页未打开浏览器、未截图、未与PDF做正式视觉回归。

| 命令/操作 | 结果 | 范围与限制 |
|---|---|---|
| `node node_modules/typescript/bin/tsc --noEmit --pretty false`（web目录） | 退出0 | 全量类型静态检查；最终含打印与上传源码 |
| `node node_modules/eslint/bin/eslint.js 'components/research/citation-*.tsx' components/research/reader-collection-list.tsx lib/api/research.client.ts 'app/account/citation-audits/**/page.tsx' 'tests/citation-audit-*.spec.ts' playwright.auth.config.ts`（web目录） | 退出0，0警告 | 新页面/组件/API/回归用例与配置，只做静态检查 |
| `.venv/Scripts/python.exe -m compileall -q api/reading/citation_audit.py api/reading/research.py api/reading/research_serializers.py api/reading/research_views.py api/reading/tasks.py api/tests/test_citation_atlas_20261018.py api/tests/test_private_research.py` | 退出0 | 不执行数据库、任务、OCR或模型 |
| Node/PostCSS `parse` 读取citation-audit.css、citation-audit-upload.css、citation-source-preview.css | 退出0，123/84/40个顶层节点 | 语法可解析，不代表排版或打印效果通过 |
| `.venv/Scripts/python.exe api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-citation-schema-20261018.json --validate` | 退出0；0 errors，10条既有serializer类型提示 | 进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true；未连接生产库。openapi-typescript随后同步成功 |
| `git diff --check -- <本单元明确文件清单>` | 退出0 | 仅换行提示，没有空白错误；检查点不包含其他继承改动 |
| 限定检查点文件的private-key/provider-token/credential-url模式扫描 | 无命中 | 有限模式静态检查，不能代表所有秘密类型都已证明不存在 |

新增后端test_citation_atlas_20261018.py共11项，前端citation-audit-workspace.spec.ts共6项、citation-audit-upload.spec.ts共3项；旧扫描用例按显式scan_ocr/旧记录兼容更新。均仅编写，未执行。重点覆盖批量原子性/owner、检查项、同请求指纹、失败恢复容量、人工历史、撤回来源、409输入保留和打印快照清理。真实锁并发、NAS负载、OCR/Provider、打印、路由与209视图仍待统一验收。第三步检索质量评测、迁移、部署和清理未运行。

本单元37文件提交前的 `git diff --cached --check` 退出0；ATLAS_INDEX静态比对确认仅208–215八行语义变更、仍为209行22列，来源身份及其他行保留。源码检查点50cf8ed；后续仅补记提交号。

### 2026-10-18 稿件版本与目录校准静态记录

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`，web目录：最终退出0。
- `node node_modules/eslint/bin/eslint.js components/admin/library/document-outline-workspace.tsx components/admin/library/outline-edit-state.ts components/admin/library/outline-pdf-preview.tsx components/admin/library/work-library.tsx components/pdf-canvas.tsx lib/api/document-outline.ts lib/api/curation-workspace.client.ts components/research/citation-audit-versions.tsx components/research/citation-audit-report.tsx components/research/citation-audit-issue.tsx lib/api/research.client.ts tests/citation-audit-versions.spec.ts tests/document-outline-workspace.spec.ts playwright.auth.config.ts 'app/admin/library/assets/[assetId]/outline/page.tsx'`：发现并修正函数名被识别为hook、props重新赋值和memo依赖规则后，目标文件检查最终0错误/0警告，退出0。
- `.venv/Scripts/python.exe -m compileall -q api/reading/citation_audit.py api/reading/research.py api/reading/research_views.py api/reading/research_serializers.py api/catalog/outline_views.py api/catalog/services/document_outline.py api/tests/test_citation_versions_20261018.py api/tests/test_outline_atlas_20261018.py api/tests/test_document_outline_20261013.py`：退出0；仅语法编译。
- `api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-versions-outline-schema.json --validate`：使用.venv Python及进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true；退出0，0 errors/10条既有类型提示。随后openapi-typescript/astToString同步api/openapi/schema.json和web/lib/api/generated/schema.ts，退出0。
- PostCSS解析document-outline.module.css与citation-audit.css：退出0。限定本轮文件`git diff --check`退出0，仅已有换行提示。
- ATLAS_INDEX静态比较：209行/22列、UTF8 BOM保留，仅112–115/211/212/215七行语义改变，图片身份/哈希/来源页及其他行均保留。211打印缺口按已存在的实际实现修正，不表示打印运行通过。

新增citation版本13个测试函数/14参数案例、outline12个单例及3个clear_position参数案例，共29个后端场景；前端版本3项、目录6项，共9项。仅编写，未执行。沿用并保留旧目录测试，原明确采用输入补充confirmed。新spec已加入playwright.auth.config.ts。不存在本轮正式测试通过、浏览器通过、真实OCR/Provider/NAS可用或像素一致的结论。未运行迁移、部署、数据清理和检索质量评测。

稿件版本12文件检查点45c669a、目录校准18文件检查点0fe3a8e分别保存。两批提交前的`git diff --cached --check`均退出0；明确文件清单之外的历史未提交成果保留，未做reset/clean。

### 2026-10-18 笔记授权、私人来源与解析工作台静态记录

仅实际读取final-r2的205–210页及此前已读取的211–215页。没有打开实现浏览器或进行正式逐图对比。

- `node node_modules/typescript/bin/tsc --noEmit --pretty false`（web）：退出0，含新页面、客户端和全部新增回归源码；生成契约同步后再次检查退出0。
- 目标ESLint覆盖confirmed-notes-workspace、research-memory-reminders、research-session-detail、memory.client、research.client、confirmed-notes路由、citation组件/路由、两项新spec/旧upload spec及playwright.auth.config：退出0，1条真实封面no-img-element警告。
- `.venv/Scripts/python.exe -m compileall -q`覆盖config/settings、reading的citation_audit/citation_sources/research/research_models/research_serializers/research_views/urls/tasks、0010，以及test_citation_private_sources_20261018/test_citation_atlas_20261018/test_citation_versions_20261018/test_confirmed_memory_atlas_20261018/test_private_research/test_private_research_completion_20261014，16文件退出0。
- Node/PostCSS parse：confirmed-notes.module.css 103个顶层节点、research.css 230、citation-audit.css 245，全部退出0。仅语法证据。
- 进程环境DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true、PYTHONIOENCODING=utf-8，执行`api/manage.py spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-memory-private-schema-20261018.json --validate`，最终退出0、10条既有serializer提示/0 errors。新增kind/action枚举歧义用明确Enum名称修正，openapi-typescript同步成功。
- 新后端笔记14函数/17参数案例、私人来源13函数/18参数案例；新前端笔记6场景、解析/来源11场景，仅编写。旧private_research/citation/version/upload用例保留并适配明确授权、purpose与实际依据契约。

未执行正式测试、浏览器、构建、视觉回归、OCR/模型/NAS、检索质量评测、迁移、部署或清理。静态检查和检查点不等于B01–B06或209视图验收通过。

本单元51文件准确白名单核验及`git diff --cached --check`退出0；限定private-key/provider-token/credential-url模式扫描无命中。ATLAS_INDEX保持209行22字段，仅205–215记录更新，图像来源身份字段与其他行不变。检查点1d19dd5。
