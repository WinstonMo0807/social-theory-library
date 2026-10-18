# 私人来源与稿件解析工作台

状态：源码已接入，统一功能/视觉验收待核实。唯一依据是final-r2最终PDF第208–210页及此前已读取的211–215页。解析页遵循209页左侧文件/设置、中间原稿、右侧实际进度与识别结果的结构；移动端切换对应区域。数据不取自图集示例。

## 实际接入

- 上传后进入`/account/citation-audits/[id]/parse`，支持真实阶段、引文/书目定位、取消/重试、独立人工校正、来源确认和报告跳转。PDF复用PdfCanvas；DOCX仅展示实际解析段落/脚注/尾注与字符位置，尚未实现精确Word排版。
- 私人来源使用已有CitationAudit加密存储和Celery/OCR链。`purpose=manuscript|private_source`和`file_size_bytes`由0010迁移添加，迁移只编写，未执行。普通稿件列表与账户audits计数只含manuscript；本人数据导出将citation_sources单列。
- `private_materials`含公开馆藏和本人明确选择的私人文件。新上传不自动选入；每次最多4个来源，书目对应关系必须由本人确认。私人引用不会伪造公开Reader身份，不流入公开馆藏、索引或研究公共证据。
- 每个文件最多12MiB，个人最多24个来源、原件合计128MiB，PDF最多1000页，解析最多100万字符，保留最多10000个文字单元；每人稿件/来源共用2个活动任务容量。界面能力只说明配置资格，不证明NAS和OCR服务已运行。
- 匹配只报告规范化文字的精确相同，最多5个连续可匹配单元/10个命中；未OCR扫描页或DOCX嵌图形成覆盖断点。没有据相邻可读页跨过缺失页推断连续原文，也未把文字相同当作学术支持或印刷页码核实。

## 接口与身份

- `GET/POST /reading/citation-sources/`：本人列表或multipart文件、request_id、title、citation、显式scan_ocr。
- `/reading/citation-sources/{id}/`：本人详情及带expected_revision删除；`original/`、`segments/`、`ocr/`和`command/`复用现有权限、任务和错误边界。
- `GET /reading/citation-audits/{id}/manuscript/`：真实分页文字，可按occurrence_id/entry_id/unit_id定位。Unicode非BMP字符与4000字符分块位置按原解析偏移换算。
- 稿件创建接受private_source_ids；`sources`命令替换明确名单，清空回到公开范围；`match_private`明确书目来源。sources/private_references与公开EvidenceReference分别表达。
- 每个私人引用核对owner、选中范围、source generation/hash、单元ID/连续性/offset/content hash。重解析/删除/重试使旧引用失效；读取不显示旧批次片段。
- 更换public/private匹配或链接的实际依据时归档旧人工决定并清空当前决定，同身份重选不误清。失效依据的报告分类先标待核对，再保留本人历史决定和校正文案。
- 409保留输入、文件或所选来源，只有明确选择最新基准后才重提。删除冲突关闭旧确认，不自动用新修订删除。账户/会话变化丢弃临时内容、下载和迟到响应。

## 验证和剩余边界

前后端类型及OpenAPI已同步。目标ESLint、全量TypeScript、Python compileall及CSS解析退出0。详情见VALIDATION.md。新增后端13函数/18参数案例、前端11合成场景仅编写；旧上传与版本fixture同步真实契约，未删原场景。

未运行测试、浏览器、视觉回归、OCR/模型/NAS、迁移、部署、清理或检索质量评测。DOCX精确排版仍是实施缺口；设备负载、真实锁/配额/取消、打印和209视图/B01–B06需统一验收。源文件及运行图像保持在忽略目录，不进入Git。
