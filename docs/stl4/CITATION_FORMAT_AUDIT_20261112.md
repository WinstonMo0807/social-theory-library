# 五种引文格式核对与阅读器引用修正

日期：2026-11-12。范围为用户截图中的馆藏图书引文及阅读器选段流程。仅本地修改，没有推送、公网发布、数据库迁移或生产数据写入。

## 核对结论

原实现不能判为五种格式均正确。它们主要是简单字符串模板，Harvard 直接调用 APA；没有独立处理责任方式、有效版次和图书引文页码的不同位置。本轮已修正有直接证据的图书模板问题，并用各样式的发布者示例对照。通过的范围是下述图书示例、字段规则和权限流程，不是对全部馆藏、全部文献类型或完整标准的认证。

| 样式 | 对照依据 | 原实现问题 | 本地修正与已比对范围 |
| --- | --- | --- | --- |
| GB/T 7714—2025 | 第7.1、7.4、8.2及附录B.1 | `version_label` 整段直拼，含首版日期和印刷次数；遗漏已确认整版译者；无作者时写入推定的佚名 | 引文专用版次清理，首版省略，保留其他版次/修订版；译者放在题名后、版本前；引文页码跟出版年。附录B.1《经济数学与金融数学》译著示例比对通过。 |
| APA 7 | APA官方 Book/Ebook References | 无有效版次、译者及编者责任标识；超过3人就使用“等”；在图书参考文献末尾直接加引用页码；未带已知DOI | 版次/译者放题名后括号，编者加Ed./Eds.；作者列表按20人规则；已知DOI保留；图书条目和文内引文分开。Jackson著作及Kesharwani编著示例比对通过。 |
| MLA 9 | MLA Style Center Books | 漏版次/译者/编者；多人沿用“等”；把所引书页拼到图书条目末尾 | 独立的责任者、译者、版次和出版项顺序；3人及以上使用首人加et al.；文内引文单列页码。Mantel著作及Sánchez Prado编著示例比对通过。 |
| Chicago 18（书目与注释） | Chicago官方Notes and Bibliography | 没有区分书目条目和脚注，所引页码直接附在书目后；漏译者/版次 | 书目条目不附单次引文页码；选页时另列脚注；加入译者和有效版次。Liu Xinwu译著的书目与脚注位置比对通过。 |
| Harvard（Leeds） | University of Leeds官方规则 | 直接复用APA，因而年份括号、出版地和字段顺序不能代表Leeds Harvard | 明确命名Leeds变体，独立模板；年份不加APA式括号，包含出版地；引文页码单列。Adams著作示例比对通过。 |

书名在引用浮层的APA、MLA、Chicago、Harvard图书输出中以斜体呈现，可由读者选择复制到富文本编辑器；纯文本目标本身不保留斜体。引文显示通过React文本节点渲染，不把题名当HTML执行。

## 外文作者与当前适用边界

- GB/T 7714—2025第7.1.1的示例将原题含“（瑞士）”的姓名著录为“乔纳斯”。国别前缀不是此处缺失的必备项目，不能为补国籍而猜测或强行写入。
- 当前人物数据主要提供 `preferred_name`、`sort_name`、`original_name`、`country_region`，没有专门确认的引文姓／名结构。本轮不按中点、国籍或空格猜测姓氏，也不将中文译名擅自转换为英文。因此截图中的完整显示名仍保留，**尚不能保证所有真实外文作者都满足各格式的姓氏著录、排序和缩写规则**。测试采用已经明确著录形式的姓名，只证明模板，不能替代姓名规范数据核对。
- APA再版译著涉及原作出版年；当前快照不足以普遍确定该年，不能从译本年份推算。本轮未虚构原作年份。
- 本轮图书模板包含常见作者、译者、编者及版次场景；有作者又有多种编校责任、匿名古籍、复杂多卷本等未做完整样例验收。
- **非图书类型不能算核对通过**。现有APA/MLA/Chicago/Harvard没有完整的期刊、章节、学位论文、报告专用分支，不能用本轮图书结果证明这些类型正确。这是源码可确认的适用限制，后续需按真实文献类型补齐，不能将标签存在当作标准支持。
- 缺出版社、年份、译者等真实书目数据时，格式模板不能补造事实。本次没有批量改写馆藏元数据。

## 实际调用链与错误修正

1. `api/catalog/services/citations.py` 是阅读器和引用浮层共用格式器。版次仅在生成引文时清理，原始编目字段不变。保留模型端CSL中已有其他字段；公开快照不读取未公开编辑内容。
2. `shared_citation_views.py` 原来在两次原文核验都强制使用 `AnonymousUser()`，已登录读者引用registered来源也被拒绝。改为保留登录身份、但不授予后台私有来源权限的读者访问范围。
3. `citation_booklists.py` 保存前和事务末尾同样强制匿名，现与预览使用相同读者范围。保存回执、账户归属、隐私保留偏好、幂等及撤销不变。
4. `research.resolve_reference` 原来把原文是否可引用依赖在异步全文索引是否完成。现在准确引用可不依赖检索投影完成，但仍校验已生效书目、规范文件、文档修订、文件校验和、访问范围、文字哈希、选文范围；默认检索查询仍要求索引就绪。
5. 阅读器右侧 `CitationView` 原来在未知印刷书页时把PDF序号作为书页写进引文。现在不填造书页，只在末尾注明“PDF 第 N 页”。已知书页（包括罗马页码）照实使用。
6. `reader-shell.tsx` 右侧默认GB/T 7714—2025，页码随选段或当前页；其他格式进入完整浮层。
7. `shared-citation-overlay.tsx` 直接显示引用格式和可选择的正文；移除导出按钮、下载、进度、格式任务及强制保存后复制。研究和私人书单保存仍独立可用。来源失败时不再误显示“当前为书目引用”。

## 实际检查

- 20项图书格式与版次检查通过，覆盖五种样式发布者示例、两种编著、截图问题、未知姓名不猜国籍、整版/章节译者边界及原始字段不变。
- 30项引用访问与既有选文检查通过，覆盖registered登录读者、匿名/私有拒绝、后台身份不越权、索引未就绪、错误修订/哈希/校验和/撤回、书页/PDF序号、保存后重试不重复。
- 首轮48项使用项目迁移在隔离内存SQLite执行，退出0；后续加入保存和编著用例后，50项使用`--nomigrations`在隔离内存SQLite执行，退出0。无生产数据库连接。
- 最终命令：`$env:DATABASE_URL='sqlite:///:memory:'; ../.venv/Scripts/python -m pytest tests/test_citation_format_audit_20261112.py tests/test_citation_reader_access_20261112.py tests/test_shared_citation_20261019.py --nomigrations -q -p no:cacheprovider`，工作目录`api`。
- 前端限定入口类型检查 `node web/node_modules/typescript/bin/tsc -p tmp/citation-20261112.tsconfig.json --pretty false` 退出0。临时配置只包括阅读器、引用浮层及其依赖，没有更改项目总配置。
- `node --import tsx --test tests/citation-text-20261112.test.mjs design-previews/search-directions-20261111/search-model.test.mjs` 2项通过，验证安全的可复制斜体文字以及多选筛选/计数规则。
- 本轮浏览器连接重复超时，不能将旧截图当作新版视觉验收；未完成真实PDF选段到浮层的浏览器复核，也未在公网验证。接口用例和类型检查不等于实际页面验收。

## 对照来源

- [国家标准公开系统：GB/T 7714—2025现行状态及实施日期](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=C6CE52E55AC09B9C79A20AEA77CEDD14)
- [学报编辑部提供的GB/T 7714—2025标准文本](https://www2.abc.edu.cn/xbbjb/upload/2026-01/26012010262341.pdf)：搜索服务可读取第7.1、7.4、8.2和附录B.1，整份PDF直接打开超时；本轮不声称逐页通读。
- [APA官方图书参考文献](https://apastyle.apa.org/style-grammar-guidelines/references/examples/book-references)
- [MLA官方图书示例](https://style.mla.org/works-cited/citations-by-format/books/)
- [Chicago官方注释与书目示例](https://www.chicagomanualofstyle.org/tools_citationguide/citation-guide-1.html)：搜索索引可读译著及书目/脚注示例，直接打开重定向到登录页；没有绕过访问限制。
- [Leeds Harvard官方图书规则](https://library.leeds.ac.uk/referencing-examples/9/leeds-harvard/73/book)

状态：B 图书模板和引用流程已实现、定向检查通过，待实际页面验收；A/C边界为上述姓名数据与未覆盖文献类型，不称全格式认证；未发布。
