# 开源组件采用说明

本项目不自行重写成熟的 PDF 渲染、OCR、学术元数据解析和搜索引擎。业务代码负责把这些组件的输出统一为作品、版本、文件、页面和关系数据。

| 能力 | 组件 | 在本项目中的职责 |
| --- | --- | --- |
| PDF 在线渲染 | [PDF.js](https://mozilla.github.io/pdf.js/) | 浏览器渲染、缩放、翻页和 Range 读取 |
| PDF 结构与原生文本 | [PyMuPDF](https://pymupdf.readthedocs.io/) | 校验、逐页文本、文字块、坐标、目录和页数 |
| OCR 与版面 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 简体、繁体、英文文字识别与 PP-StructureV3 阅读顺序 |
| 期刊论文元数据 | [GROBID](https://grobid.readthedocs.io/) | 解析题名、作者、摘要、期刊、卷期页和 DOI 候选 |
| DOI 元数据 | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI 对应的书目候选 |
| ISBN 元数据 | [Open Library APIs](https://openlibrary.org/developers/api) | ISBN、题名、作者、出版年和出版者候选 |
| 全文索引 | [Meilisearch](https://www.meilisearch.com/docs/) | 页内段落、题名、作者、公开状态和文件过滤 |
| 任务队列 | [Celery](https://docs.celeryq.dev/) | 逐文件处理、重试、云同步和备份任务 |
| 复制清理 | [ftfy](https://ftfy.readthedocs.io/) | 常见 Unicode 编码损坏修复 |
| 拼音检索 | [pypinyin](https://github.com/mozillazg/python-pinyin) | 中文题名、姓名、主题和流派的拼音别名 |
| 引用数据 | [CSL](https://citationstyles.org/) | CSL JSON 交换结构和多格式扩展位置 |
| 2025 引用样式参考 | [GB/T 7714—2025 numeric CSL](https://www.zotero.org/styles/china-national-standard-gb-t-7714-2025-numeric) | 核对责任者、文献类型、卷期、页码、DOI 和标点规则 |

## 集成边界

- 原始 PDF 始终不可变。OCR 和文本解析只生成派生数据与规范阅读副本。
- 外部书目只产生候选，不能在无证据时直接覆盖人工锁定字段。
- 搜索索引不是公开状态来源。API 返回结果前仍检查数据库中的发布状态和当前文件。
- PaddleOCR、GROBID、Crossref 和 Open Library 失败时保留日志。系统不会把服务不可用记录为识别成功。
- GB/T 7714—2025 的 CSL 样式采用 CC BY-SA 3.0。若以后把完整样式文件打包进发布物，需要保留其作者和许可证信息。
