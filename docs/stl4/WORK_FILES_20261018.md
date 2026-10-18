# 版本与文件工作台 2026-10-18

本单元依据唯一 `social-theory-library-visual-atlas-20261015-final-r2.pdf` 第 95–98 页实际渲染图实施。此记录描述源码接入，不表示正式视觉、真实服务或生产验收通过。前端与最终静态结果由主代理补录。

## 前端接入

- `/admin/library/works/[workId]/files` 接通作品摘要、真实出版版本表、版本切换、文件历史、当前选择与公开文件侧栏、版权说明、正式发布历史和引用影响。桌面表格/侧栏与窄屏顺序沿95–98图实现，静态源码不表示逐像素通过。
- 新增版本、补充/替换文件、原件后续生成阅读副本、影响预览与明确采用均连接实际接口。文件选择、预览、影响确认与服务器接收分别显示；实际处理失败不显示为完成。
- 大PDF先核对受保护HEAD、MIME与ETag，再用原PdfCanvas按Range读取，修正原先把比例1当百分比1%的缩放错误。下载前核对真实响应，再走浏览器原生附件下载；不会把500MiB原件完整读到JS内存或把错误JSON作为文件下载。
- 原apiUpload增加可选AbortSignal/timeoutMs，旧调用不传选项仍保持timeout=0。新文件上传显式15分钟，可取消当前传输；未知结果沿原UUID查询服务器回执，查不到也只允许同原文件/参数/UUID重试。
- 写入禁用401自动刷新重放，所有私人异步结果绑定当前身份/会话；409保留输入，基于新修订需重新核对。文件、影响与发布历史独立分页；没有封面或数据时显示真实空态。
- 版权说明单独CAS保存，不改访问策略。公开准备单独弹窗说明所选文件将传入公开分发存储，需显式勾选确认；准备回执与实际可采用状态分开呈现。新文件处理不会隐式公开。
- 从原馆藏列表/工作台文件区进入，不新建平行后台；原主版本控件仍处理主版本，选用阅读文件是独立操作。OCR、目录、页码入口链接至原同文件工作台。
- 10个合成前端场景只编写未运行。最终接口生成、语法/类型检查与检查点证据集中记录在VALIDATION.md；实际服务、并发、浏览器下载及全部图像对照保留至统一验收。

## 后端职责与原件保护

- 继续使用 Work、Edition、Asset、CatalogingSession、UploadItem、原处理队列、CatalogPublicationRevision 与发布事件。没有建立第二套馆藏、文件库或任务系统，没有新增表或迁移。
- 一个作品可新增出版版本；新版本不是新的 Work，也不会自动成为主版本。版本标签最多 120 字，出版者最多 300 字。语言来自 Work。新增版本使用作品修订与请求编号，确认的字段进入既有人工决策记录。
- 同一版本可保留多份补充原件，每个原件有独立文件版本及处理记录。原件和请求标识先在数据库预占，再写文件，避免全局重复约束失败后产生未归属原件。存储第二步或后续事务失败时，事务退出后只清理本请求新生成且无 Asset/UploadItem 引用的文件；清理失败显式报错。已有原件不删除。同一原件不会跨出版版本重绑。
- PDF、DOCX、TIFF 支持仅保留原件或生成阅读 PDF。大小上限分别为全局限制与 500 MiB、12 MiB、64 MiB 的较小值。DOCX 转换复用隔离 Unix socket 服务，派生 PDF 上限 32 MiB；TIFF 使用已有 Pillow/PyMuPDF，限 300 帧、单帧 2500 万像素、总计 1.5 亿像素、派生 64 MiB。能力字段只表示本机依赖/配置资格，`service_verified=false`。
- 仅保留原件后可以明确请求生成阅读副本，复用原 UploadItem，不重新上传或新建原件。转换前核对原件哈希和大小，写回时核对任务 token 与原件身份，旧 worker 不能覆盖新一次处理。
- 新文件处理绕过旧自动编目、前置页智能分析、封面、理论关系及自动 OCR/语义/目录任务，只做 PDF 校验、原生文字提取、文档解释与质量记录。不会改同作品字段、人工锁或当前版本的处理状态。晚到重试遇已公开文件，不原位重建页与解释。
- 同版本最多一个活动文件处理任务；重试再次检查其他活动任务。失败和需处理状态保留原件及原因，可恢复原任务。OCR 单元单独明确启动。

## 选择与公开分发

- `current_reader_file` 表示管理工作台当前选择；`public_reader_file` 表示正式活动发布快照的阅读文件。未公开版本采用只更新管理选择，不公开或恢复公开。
- 已公开版本的采用先返回文件、文档及正式修订的指纹与影响说明，确认后创建原发布事件。保持正式书目快照，避免把无关未发布元数据一并公开。处理中仍保留原公开文件；失败不能伪装切换成功。
- 采用新的扫描文件会明确提示正文检索尚未就绪。人工明确 `file_selection` 可以选择该副本；其他自动来源继续遵守原全文质量门槛。
- 补充处理和草稿采用均不上传云存储。部署要求云端副本时，管理员需明确执行“准备公开阅读文件”，告知将传至公开分发存储。此操作复用 CloudObject 持久状态与 `sync_cloud_object` 任务，提交后排队，队列失败写入失败状态，失败或超时可重试。同 nonce 复用原准备记录，不新建对象。
- 公开准备成功后仍须重新预览采用或正式发布。已公开版本采用及原发布预检都要求所需云副本就绪。准备命令本身不修改当前文件、公开快照、索引或访问策略。新准备任务传 `resume_publication=false`，禁止完成回调推进旧替换任务的自动发布；旧调用默认行为保留。
- 原件、旧阅读文件、旧页标识和引用保留，不做自动页码迁移。影响明细当前覆盖 EvidenceSnippet 的实际文件/页定位，页序为 **1-based**；私人 Annotation、Bookmark、ReadingProgress 仅汇总数量，不读取正文、身份或导出旧引文。它不是全站所有引用模型的完整迁移清单。

## 接口

所有接口受后台能力校验，并返回私有 no-store 响应。JSON 使用独立命名 serializer。前端人工类型位于 `web/lib/api/work-files.types.ts`，OpenAPI 由主代理统一同步。

| 方法 | 路径（省略 `/api`） | 契约 |
| --- | --- | --- |
| GET | `/catalog/admin/works/{work_id}/files/` | `edition/asset/page/impact_page/history_page`，分别分页文件、影响及正式历史；返回真实任务和能力 |
| POST | `/catalog/admin/works/{work_id}/editions/` | `request_key/expected_work_updated_at/version_label/publication_year?/publisher?` |
| POST | `/catalog/admin/editions/{edition_id}/files/` | multipart `action/file/request_key/expected_updated_at/expected_reader_asset_id?/confirm/generate_reader` |
| GET | `/catalog/admin/editions/{edition_id}/files/requests/{request_key}/` | 当前提交者与版本绑定的权威查回；未知、跨提交者或跨版本返回 404 |
| POST | `/catalog/admin/editions/{edition_id}/files/{asset_id}/generate-reader/` | `request_key/expected_asset_updated_at`，从已保存原件生成 |
| GET/POST | `/catalog/admin/editions/{edition_id}/files/{asset_id}/adopt/` | 预览指纹与影响；提交 `request_key/fingerprint/confirm:true` |
| POST | `/catalog/admin/editions/{edition_id}/files/{asset_id}/prepare-public/` | 发布能力，`request_key/expected_asset_updated_at/confirm:true`；返回实际公开准备状态 |
| PATCH | `/catalog/admin/editions/{edition_id}/files/{asset_id}/rights/` | `request_key/expected_asset_updated_at/rights_note`，最多 4000 字；其他字段拒绝；保留审计 |
| GET/HEAD | `/catalog/admin/editions/{edition_id}/files/{asset_id}/content/` | 历史文件的受控 Range/HEAD；`download=1` 保留实际 MIME 与文件名，DOCX/TIFF 仅附件下载 |
| GET | `/catalog/admin/editions/{edition_id}/files/impact.csv?asset=` | 真实证据定位 CSV，上限 10000 条，公式单元格转义，不导出正文 |

版权说明仅修改 Asset.rights_note；不修改 access_status。读取返回 rights.source_asset_id/updated_at/can_edit，没有当前阅读文件时可编辑实际保留原件。公开访问策略只读展示。所有写入保留幂等请求与修订冲突，不覆盖并发更新。

## 检查与剩余验收

- 新增 `api/tests/test_work_files_20261018.py` 34 个测试函数、37 个参数案例，覆盖多份原件、nonce、跨版本/提交者、原件/派生分离、转换迟到、TIFF 限额、采用指纹、草稿选择、正文质量提示、历史读取/HEAD、版权 CAS、公开准备与失败、禁止补充时自动元数据/智能/云处理、事务回滚后的限定存储清理、已完成云准备回放与禁止自动发布回调。均仅编写，未运行。
- 旧 `test_edition_files_v306.py` 仅补新 dispatcher 的隔离 mock，原断言保留。
- 后端代理执行 13 个目标 Python 文件 AST 解析，退出 0；限定 tracked diff 空白检查退出 0，只有既有 CRLF 提示。未运行正式测试、浏览器、构建、真实转换/OCR/模型/云服务、迁移或生产操作。
- PostgreSQL 并发锁与重复上传竞态、真实 DOCX 字体/公式/分页还原、TIFF 大样本资源限额、云端鉴权/预算/失败恢复、历史 Range 下载和最终 PDF 95–98 视觉对照均待统一验收。代码和控件存在不计验收完成。
- `document_intelligence.py` 本单元仅增加 `schedule_outline` 默认参数与条件，保持其他调用原行为；同文件其余人工文字保护由 OCR 单元负责。`ingestion/views.py` 本单元只增加 staged 重试并发与旧发布入口守卫；该文件其余改动须按既有依赖单独审查。
- `distribution/tasks.py` 本单元仅增加 `sync_cloud_object` 可选回调开关；该文件其余备份修改属于继承成果。`pipeline.py` 原 `ExtractedPage.ocr_reasons` 与原因统计在 HEAD 已存在，当前旧主流程额外 `ocr_decision` 汇总为继承差异；新 staged 分支复用真实页检测，不重新评测检索。
