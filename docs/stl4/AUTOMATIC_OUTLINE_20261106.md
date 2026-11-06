# 自动目录与带书签下载副本

2026-11-06。用户最新选择替代“编辑—确认—采用—导出”的常规流程。原文件、人工校准、旧修订及失败记录保留。自动化开发 D；更多书种的识别质量 B，不承诺每书无误。

## 实际工作方式

1. 文件解析或 OCR 保存正文修订后，沿 `document_intelligence` 原调用排入 `outline_rebuild`，同文件、同正文修订、同解析器只排一次。
2. `outline-v9-docling-geometry` 读取已有原生书签、印刷目录、正文标题、OCR 框和页码观察。合并同一标题的断行，按目录缩进与字形高度分级，匹配实际正文落点，排除重复页眉。不调用第二个 OCR 或生成式模型。
3. 可定位节点自动成为读者目录，并自动排入现有 `outline_export` 任务。`reviewed=false` 如实表示没有人工验收。没有可靠落点的条目留在后台识别记录，其余目录正常生效。
4. 在独立 PDF 写入书签，回读检查标题、层级、页数和页内位置；下载入口优先返回这份当前副本。已有合格 OCR PDF 时复用其文字层，保留原件下载。原文件和读者笔记的锚点不变。
5. 管理端修改后点“保存修正”，目录立即生效并自动更新下载副本。无需逐项确认、再采用、再导出。修正目录优先于以后自动重建；历史可恢复，旧副本保留。
6. 已有云端分发时，复用原件已经配置的存储目的地同步副本，不选择新服务商；原件先上云或目录先完成这两种先后顺序均有接续。预算或队列失败留下可重试记录。当前内网无云端存储配置，本轮未上传任何文件。

数字签名文件继续提供原件；不生成使其签名失效的副本。来源撤回、替换、权限和当前正文身份检查沿原服务。旧的编辑/采用接口为历史兼容保留，不再是日常必经步骤。

## 复用来源

| 项目 | 固定版本、许可 | 本次使用 |
|---|---|---|
| [Docling](https://github.com/docling-project/docling/blob/c715294cd774ef0a59dd8e5c8a63ae3432cd611e/docling/models/stages/heading_hierarchy/heading_hierarchy_model.py) | c715294cd774ef0a59dd8e5c8a63ae3432cd611e，MIT | `_cluster_sizes`、标题归一化、编号去除、`_match_score`。只复用纯算法，未安装其完整模型流水线。相似度是启发式分数，不是正确概率 |
| [pdf-toc-ocr](https://github.com/ennheng/pdf-toc-ocr/blob/577c36d248556d69f17ee2dd07ba5a24463a9889/app/core.py) | 577c36d248556d69f17ee2dd07ba5a24463a9889，MIT | OCR 框按行合并及分栏。项目维护历史较短，未称其整套系统成熟，仅使用已读过的轻量函数 |

适配代码在 `api/catalog/services/outline_upstream.py`，完整许可证在 `api/third_party/`。没有复制许可不合适的 autoContents，也未引入第二套 PaddleOCR/GROBID 服务或新模型下载。原 RapidOCR＋ONNX＋PP-OCRv6 tiny 继续使用。

## 两份公开扫描文献的实际结果

两份来源均没有原生 PDF 书签。虽然原件含旧隐藏文字层，本轮确实将扫描页用本机 RapidOCR 重新识别，共116页，再将结果经过当前 `extract_ocr_pages` / `persist_pages` / 目录任务 / 书签任务 / 下载选择代码。隔离 SQLite 与媒体目录，不混入正式馆藏，没有外部推理调用。

| 文献 | 扫描页 | 全自动结果 | 对照结果 |
|---|---:|---:|---|
| Boas，The limitations of the comparative method of anthropology（1896） | 8 | 1 项完整文章标题 | 标题跨两行、双栏 OCR 交错已合并，未把 SCIENCE 刊头和编委表作为章节 |
| Mooney，The Siouan tribes of the East（1894） | 108 | 38 项章节书签 | 38 项目标物理页与层级均与前一轮逐页人工核对一致；1 条地图条目没有可靠落点，保留提示 |

来源：[Boas 馆藏页](https://commons.wikimedia.org/wiki/File:The_limitations_of_the_comparative_method_of_anthropology_(IA_101484863.nlm.nih.gov).pdf)、[Mooney 馆藏元数据](https://archive.org/metadata/b30477578)。原件 SHA256 分别为 `23eab6c2596c6278e9303e29e8fa22515e17d27183a71230736a5072ce686e14`、`be4749f28fc5fe51736e708d9f70334844016cc9f332aa48c05992ebbaecd89a`。

自动副本：

- `output/outline-validation-20261106/boas1896-automatic-bookmarks.pdf`，SHA256 `e63a14f5f02175fefea1bae21e4124d8100b9c1d654fe07d88678956c02ba211`。
- `output/outline-validation-20261106/mooney1894-automatic-bookmarks.pdf`，SHA256 `886c67057afd9d0f46451664c7c32cb3edec01bdb64f7eb8f6bc90dd1621889d`。

以上是无人工输入的新一轮结果。旧 `with-reviewed-bookmarks.pdf` 是此前人工校准产物，二者没有混称。自动副本页数、页面内容流、页面矩形、旋转和原件 hash 均保持，书签回读一致，默认下载解析指向新副本。目录与导出用时0.70秒/10.98秒包含本机已有 OCR 结果入库，**不包括 OCR 时间，不代表 NAS 性能**。

部分英语标题仍含 OCR 拼写错误；本轮验证的是自动目录与下载流程及这两份材料的落点。中文古籍、竖排、复杂合订期刊、更多旋转/双页实书没有因此验收。不存在“保证每书完全正确”的结论。

## 检查、运行与恢复

- `api/tests/test_automatic_outline_20261106.py` 与 `test_stl4_outline_exports_20261024.py` 首轮合计11项通过。追加“无节点不提示已生成”后，4项自动目录用例再次通过，两轮涵盖12个不同用例；覆盖自动生效、原件不变、管理员一步纠错、未编辑节点不伪装人工确认、人工修订优先、重复请求、旧来源失效、读者越权拒绝、云目的地继承，以及0/90/180/270度书签落点回读。
- Web类型、OpenAPI契约生成及构建退出0。不是全站视觉/E2E验收。
- 定向命令在`api`目录、`DATABASE_URL=sqlite:///:memory:`及`PYTHONIOENCODING=utf-8`环境执行：`../.venv/Scripts/python.exe -m pytest tests/test_automatic_outline_20261106.py tests/test_stl4_outline_exports_20261024.py -q`；追加用例后执行`../.venv/Scripts/python.exe -m pytest tests/test_automatic_outline_20261106.py -q`，均退出0。pypinyin弃用和既有pytest缓存目录警告保留，未删除缓存或掩盖失败。
- 实际样本证据 `tmp/stl4-local-ocr-20261106/*-automatic-workflow.json`、`automatic-workflow.log`、`automatic-tests.log`。第一次控制台使用GBK打印英文 ñ 失败，JSON已经写入；是输出编码问题，已用UTF-8完成整轮流水线，原失败日志保留。
- 最终已部署API62 `bb5fd9d5fd264987ce67218461ae7ccbf75ac45d32c523b5d776db052bdaf92c` 与Web126 `8fd5bc0468b48583c17cb8eb606d809b91f88ba0a7114be2d16e61c146cc36f3`。API、四worker及beat同版，HTTP200；原生产、政策和其他容器身份/挂载/启动时间保持。原API60、API61镜像保留恢复。
- 最终轻量读回API/四worker/RapidOCR/DOCX健康，Web及beat运行，无OOM/重启。`runtime-r62.log`为队列空、在途0，`health-r62.log`记录最终容器状态；不是长期稳定性结论。
- 真实后台只读查看原170页样书，10项人工目录、PDF预览和“保存修正”正常显示。发现封面旧直链破图后仅改outline_state封面字段，API61修复已包含API62；实际截图`output/outline-validation-20261106/admin-outline-final.png`。没有在该书保存编辑或重跑OCR/目录，没有把旧人工目录说成新算法运行结果。
- 首次API更新检测到在途定时健康探针而中止，未重启容器；第二次暂停beat新增调度，等待原探针和队列自然结束后更新API及四worker/beat。原失败/OOM/重试历史未清除。
- NAS `automatic-outline-api-r60-recovery-2` 保留前API59配置、镜像、日志与数据库包；`automatic-outline-api-r61-recovery`保存API60，`automatic-outline-api-r62-recovery`保存API61；`automatic-outline-web-r126-recovery`保存Web125。首次未更新的恢复目录也保留。DB包未独立恢复。仅内网候选，生产与公网入口未动。

## 接口与调用位置

`POST /catalog/admin/assets/{asset_id}/outline/` 新增 `action=correct`，需要编辑元数据权限、当前修订号和请求标识。原读取、任务状态、重试、冲突保护与PDF预览继续复用。后台 `/admin/library/assets/{asset_id}/outline` 以“保存修正”为主操作；识别记录中可查看未定位条目。`distribution` 仍在有阅读权限的原文件锚点下解析下载，派生 Asset 本身不获得公开入口。
