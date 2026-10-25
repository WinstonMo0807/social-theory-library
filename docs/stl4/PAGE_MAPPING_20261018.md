# 页码映射与校准 · 2026-10-18

## 2026-10-26 M11/M12分段双页标签与诊断定位

outline-v6接入当前分段/双页标签，保留重复观察，已知缺页或范围端点不明不猜落点。候选诊断增加分批显示、节点定位及实际原稿页入口，保留原确认/采用。60ea78五AST/CSS/diff0；04b699→7b5843两目标ESLint/TS0。仅静态检查，验收定义未运行。见OUTLINE_CALIBRATION_20261018.md。


状态：源码已接入，统一验收待核实。唯一视觉来源为 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第 116–118 页。已实际查看该 PDF 渲染的三页及 116/117/118 局部图；没有读取其他设计 PDF。渲染图位于忽略的 `tmp/pdfs/stl4-page-labels-20261018/`，不提交。

## 可恢复入口

- 页面：`/admin/library/assets/[assetId]/page-mapping`，馆藏目录当前阅读文件旁提供入口。
- 接口：`/api/catalog/admin/assets/{asset_id}/page-mapping/`，旧 URL 由新的专用 view 接管；原 `catalog/views.py` 页码类保留为历史实现，不再承接这个路由。
- 数据：`PageMappingRevision` 和 `catalog/0068_page_mapping_revision.py`。迁移仅编写，未执行。旧 Page/Asset/PageLabelSegment 无破坏性回填或清理。

## 已接入契约

GET 返回真实 asset、当前已采用页表 `current`、最新候选 `latest`、20 条分页历史、`expected_revision`、`source_fingerprint`。`?revision_id=` 返回只读完整候选；`?history_page=` 翻历史。发布产生新解释资产后，`preceding_revision` 明确指回此前资产和校准记录。

POST 支持以下操作：

| action | 输入 | 结果 |
|---|---|---|
| save | 完整 `data.pages/segments/missing` | 新候选，不改公开 Page |
| analyze | 当前候选基准 | 从已有页眉页脚文字生成未确认建议，保留人工确认 |
| segment | id/name/start/end/start_label/style | 在真实显式范围内生成连续编号候选，已确认页保持原值 |
| restore | revision_id | 同一有效来源的历史内容另存为新候选 |
| prepare | revision_id | 真实页标签/类型/确认/备注、分段、缺页前后差异和阻止原因 |
| publish | revision_id/prepared_fingerprint | 已上架文件进入原发布链；未上架文件只采用当前稿件映射 |

所有操作要求 `expected_revision` 与 `source_fingerprint`，除只读 prepare 外要求 UUID `request_id`。幂等检查先于来源/CAS 检查，响应丢失可按原 nonce 重试；同一 nonce 换内容或换操作者拒绝。保存权限为 `EDIT_METADATA`，采用/发布为 `PUBLISH_WORK`；普通读者不能读取后台页表。

`pages` 是已有物理页全集，最多 20000 项。每页 labels 为 0、1 或 2 项，合并标签不超过 Page.printed_label 的 40 字限制；不猜测任意范围字符串的左右页。page_type 支持 front/body/appendix/other/blank。无印刷页码同样需要人工确认。改变原人工锁定标签必须同时提供 override_manual、confirmed 和 note。

分段最多 500 项，起止必须在实际页内，不允许重叠。历史 custom 分段可原样保留，自动连续生成需明确阿拉伯/罗马/无标签格式。缺印刷页最多 1000 项，仅包含实际相邻页和说明，不新增虚假的 Page。重复标签必须逐页确认并说明保留原因；缺页标签不能同时存在于实际页表中。

## 发布和引用边界

锁序为 Edition → Asset → MappingRevision。保存候选不修改当前资产。采用已公开文件时复用 `stage_document_asset` 复制正文解释，PDF 字节仍指向原不可变文件；再复用 `synchronize_document_revision` 创建证据修订，最后调用 `create_catalog_publication_event(content_asset_id=...)`。

既有发布服务增加 `source=page_mapping` 的内容更新来源，仅替换文档部分，不夹带未发布的书目或人物草稿。公开指针和当前资产仍由现有投影完成/激活链切换。页码 READY 仅在确切修订激活时更新。已有有效人工目录保留标题、层级、物理位置和确认，随新文档更新印刷页标签；旧目录和旧页表继续保留。正在处理/失败待恢复的较新发布先由原发布记录恢复。

双页保存为同一个 Page 的结构化 labels，显示标签如 `16–17`。`structured_page_labels` 仅在已存结构化值与真实 Page.printed_label 一致时返回 spread。Reader 与证据接口由根代理接通字段。引用体检找到同一双页扫描中的文字时仍为 needs_review，明确尚不能判断左右印刷页，绝不制造半页 bbox 或精确印刷页结论。

## 前端行为

按最终图接入作品信息、分段栏、实际页表与缩略图、原稿预览、页标签/双页/类型/原因/人工确认、检查列表、缺页弹窗、批量确认、修订历史及采用影响预览。原稿沿用 OutlinePdfPreview/PdfCanvas；八个可见缩略图共享受本人会话保护的 blob，使用现有 pdfjs 依赖生成。没有样例封面、虚构页图或假状态。

未保存的页表和弹窗输入有退出保护；409 保留输入，须显式采用新基准；来源变更后的重新保存会清除旧确认。后台请求沿用 usePersistentWorkspace 的 owner 复核、nonce、身份切换清理和有限任务轮询。移动端按分段、页表、原稿与编辑顺序排列；真实屏幕/浏览器及最终逐图对照尚未运行。

## 验证记录

- 12 个目标 Python 文件 `python -m compileall -q` 退出 0。
- 页码 7 个前端文件目标 ESLint 最终退出 0，0 warnings。
- `page-mapping.module.css` 由 PostCSS parse，退出 0。
- 目标 tracked `git diff --check` 退出 0，仅继承 CRLF 提示。
- 全量 `node node_modules/typescript/bin/tsc --noEmit` 最终退出 0。中间曾发现本单元缩略图空 Record 类型以及并行反证/DOCX 工作台的参数类型问题，分别由文件负责人修复后重新检查。
- 新 `api/tests/test_page_mapping_20261018.py` 10 个后端回归函数；旧 PDF73→印刷页50 综合用例已改接候选/预览/采用；新 `web/tests/page-mapping-workspace.spec.ts` 5 个合成界面场景。全部只编写，未运行。

未运行功能测试、浏览器、构建、正式 E2E、视觉回归、真实 OCR/模型/索引、迁移、部署或生产清理。静态检查不证明全链运行或最终视觉一致。

## 本单元文件归属

新增：`api/catalog/page_mapping_views.py`、`api/catalog/services/page_mapping.py`、`api/catalog/services/page_label_metadata.py`、`api/catalog/migrations/0068_page_mapping_revision.py`、`api/tests/test_page_mapping_20261018.py`；`web/lib/api/page-mapping.client.ts`、`web/components/admin/library/page-mapping-workspace.tsx`、`page-mapping-thumbnails.ts`、`page-mapping.module.css`、路由 `web/app/admin/library/assets/[assetId]/page-mapping/page.tsx`、`web/tests/page-mapping-workspace.spec.ts`、本文。

精确修改：catalog models/urls、knowledge_publication 两处（source 集合及激活 READY）、public_response_serializers 的双页字段、citation_audit.check_occurrence、research 的体检 finding 页码重验、旧 test_resilient_publication_v260 对应用例、outline-pdf-preview 的可选 blob 回调、work-library 的新入口。research/public view/Reader 双页展示由根代理协同接入。

public_response_serializers、旧综合测试、research 等包含继承或并行改动。根代理另行核对并保存必要 document_intelligence/ingestion outline task/distribution/目录依赖；不得因本单元提交覆盖或删除其他工作区成果。本子任务不执行 Git add/commit。
