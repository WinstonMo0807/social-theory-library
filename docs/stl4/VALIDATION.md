# 验收记录

当前阶段：功能开发。全站正式功能、视觉、权限、迁移、性能验收全部待核实；未部署。

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
