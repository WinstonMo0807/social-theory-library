# PDF209 私人 DOCX 分页预览

日期：2026-10-18。状态：源码接入，迁移和运行验收待统一阶段。

视觉依据只使用 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第209页；实际查看了对应渲染图，并回看213–215的稿件定位要求。209的 DOCX 纸页预览与真实段落定位分别实现，不能把段落组号当 Word 页码。

## 实际链路

- 解析工作台默认显示分页预览；明确点击某一引文/书目位置后显示真实解析文字。引用位置仍是原稿 XML 部件、段落、脚注与字符范围，没有从派生 PDF 猜测高亮或页映射。
- `CitationDocxPreview` 读取本人预览状态并按需请求生成，复用 `usePersistentWorkspace`、`withPrivateOwner`、受控 Blob URL 与原有 `PdfCanvas`。生成排队、处理中、失败或未启用时继续显示实际解析文字；原稿 PDF 保持直接预览。
- 预览写命令禁用401后的自动刷新重发，会话变更中止等待；保留原请求编号供明确重试，避免在新会话下自动提交。
- `reading.document_preview` 单独登记 Celery 任务。状态绑定原件 SHA256、稿件版本、原件处理 generation、预览 generation/task_id。派生 PDF 和状态使用 CitationAudit 的两个独立字段，更新不重写报告、人工判断或原始 DOCX，也不增加报告 revision。
- 服务返回真实转换器版本、实际字体文件清单摘要和输出哈希；API校验输入/输出哈希、协议、PDF类型、密码、页数与页面尺寸，再加密保存。来源处理版本变化、取消或删除后的迟到结果不能回写。
- 任务按请求时间执行十分钟绝对截止，转换前和保存前都核对确切 generation；过期队列恢复不会再启动转换，合法的75秒转换仍受同一截止限制。文件读取在解密前后重新查询本人记录，复核原稿身份、预览代次、状态与密文摘要；换代、删除或所有权变化时不返回旧字节。

## 接口

两类本人对象共用同一契约，路由前缀分别是 `/reading/citation-audits/{id}` 与 `/reading/citation-sources/{id}`。

| 方法与后缀 | 行为 |
| --- | --- |
| `GET /preview/` | 返回稿件身份、预览修订/代次、真实状态、可选页数、转换器/字体身份和提示；`enabled` 仅表示配置启用，不代表服务运行验证。 |
| `POST /preview/` | `{action: generate/cancel, request_id, expected_preview_revision, source_generation}`；202返回状态，同请求回放先于过期修订检查。409须读回后再次明确操作。 |
| `GET /preview/file/?generation=N` | 仅当前本人和当前有效代次读取派生 PDF；`private,no-store`、nosniff、sandbox。 |

所有接口按实际 owner 查询，管理员身份不扩大私人访问。独立隐私导出保留原稿与报告，派生二进制不塞入 JSON；删除 CitationAudit 同时删除其派生字段。列表/隐私查询 defer 两种二进制字段。

## 隔离与实际限制

- 新增可选 `compose.docx-preview.yaml`。转换容器 `network_mode:none`，不带数据库、NAS、账号凭据、馆藏挂载或主机端口；现有 Celery worker 只通过专用 socket volume 调用，worker侧挂载只读。
- 输入12 MiB，解包64 MiB/3000 ZIP条目，输出32 MiB/1000页。转换进程75秒截止，终止完整进程组。Celery软/硬限制110/120秒，工作进程请求80–100秒且检查总耗时，浏览器Blob读取60秒截止。本人至多两项近期活动预览。
- 容器非root、只读根、cap_drop ALL、no-new-privileges、384 MiB tmpfs、768 MiB内存、单CPU、64进程。每次唯一临时目录，正常结束清理；启动清理上次异常退出的受控临时目录。不记录原文、文件名或转换器标准输出。
- 拒绝宏、OLE、ActiveX、DDE/外部字段、外部关联内容、路径穿越及DTD。普通超链接不主动访问。不能安全转换的文件回退解析文字/原稿下载。
- 字体和分页可能不同于用户本机 Word；派生预览不能宣称像素一致。公式、复杂表格、批注/修订及字体替换须用合法合成样本在统一验收中核对；不修改或覆盖原稿。

## 配置与恢复

- `DOCX_PREVIEW_ENABLED` 默认false；固定socket为 `/run/docx-preview/preview.sock`，不接受网络URL或任意路径。可选overlay显式设为true。服务需显式启用 `docx-preview` profile；本轮没有运行配置或启动服务。
- 迁移 `0012_citation_document_preview` 依赖 `0011_reader_privacy_operations`，只新增以空值为默认值的派生字段，未执行。部署前先按统一迁移安排完成schema，再启用这段API代码/配置；不能把仅源码接线当成服务已运行。
- 关闭配置保留原件和解析能力；已存在且身份仍有效的派生PDF仍可由本人查看。失败可重试，取消仅终止/丢弃预览结果，不取消引文检查。旧任务或服务中断后不会重建已删除对象。
- 原稿不得换成派生PDF；派生字段可重新生成，其生产清理仍遵循当前数据保护/确认流程。

## 验证记录

- 已执行：在 `web` 目录运行 `node node_modules/eslint/bin/eslint.js components/research/citation-docx-preview.tsx components/research/citation-manuscript-preview.tsx components/research/citation-audit-parse.tsx lib/api/citation-preview.client.ts tests/citation-docx-preview.spec.ts`，退出0，无警告。
- 已执行：通过 `.venv/Scripts/python.exe -` 使用标准库 `ast.parse(Path(name).read_text(encoding='utf-8-sig'), filename=name)` 解析本单元11个Python文件，退出0。范围为转换服务、预览业务/视图、0012迁移、回归用例及6个共享接线文件；不导入应用，不调用数据库或转换器。
- 已执行：使用现有PyYAML对 `compose.docx-preview.yaml` 执行 `yaml.safe_load` 语法解析，退出0。没有运行Docker Compose或容器。
- 新写后端12个测试函数、22个参数场景；前端4个合成场景，仅编写。覆盖owner/管理员边界、原件与报告不变、加密派生、请求重放、取消/换代/删除后的迟到结果、失败回退、固定socket以及活性内容拒绝、前端冲突与会话切换。交叉审查新增过期队列、转换跨越绝对截止、解密期间原稿/预览/密文/所有权/删除变化，以及读取前视图快照过期的回归断言。
- 交叉修复后使用标准库 `ast.parse` 再解析 `document_preview.py`、`document_preview_views.py` 与 `test_document_preview_20261018.py`，退出0；没有导入Django、运行测试或转换。
- 未运行：测试、浏览器、构建、转换器、容器、迁移、真实DOCX/字体样本、生产部署。全站正式验收继续待核实。

## 依赖核对

使用Debian官方LibreOffice Writer软件包及Noto CJK/Liberation字体，不在Django或浏览器内装Office引擎。保留软件包自带许可证文件；版本以镜像构建时实际读取结果记录。

- [LibreOffice 官方命令行参数](https://help.libreoffice.org/latest/en-GB/text/shared/guide/start_parameters.html?DbPAR=BASIC&System=WIN)
- [LibreOffice 官方许可说明](https://www.libreoffice.org/licenses/)
- [Debian bookworm LibreOffice Writer软件包](https://packages.debian.org/bookworm/libreoffice-writer)
- [Debian bookworm Noto CJK软件包](https://packages.debian.org/bookworm/fonts-noto-cjk)

这些依赖资料仅用于核验技术接口/许可；不是产品视觉参考。
