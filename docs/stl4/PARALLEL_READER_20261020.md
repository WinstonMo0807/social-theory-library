# PDF41–43 并读与私人对齐实施记录

日期2026-10-20。前置Reader检查点a5898aa。本单元为源码实施与静态检查，正式功能、运行、逐图和性能验收尚未执行。唯一视觉来源为final-r2 PDF物理41、42、43，均已实际查看原图。

## 页面与真实功能

`/reader/[assetId]?mode=parallel` 接入原Reader路由，`alignment`可恢复本人任务。桌面两栏版本选择、交换、独立翻页/段落定位、字号、书内搜索、两侧正文和底部私人对齐/术语表均使用真实来源；手机使用版本选择、阅读方式、对齐与笔记分区，手动对齐另有对照/候选/笔记切换。共用SiteHeader、原生Dialog、Reader书内搜索和既有身份/原文协议。纸白、灰、炭黑、砂金沿MASTER_SPEC，不沿用图中旧蓝操作色。

版本来自同一Work和已激活发布快照中的translation_of关系，最多60版本。关系遍历最多8层/64作品/每步256行；达到限制明确标示，不凭标题猜译本、不采用未发布关系。扫描本/仅书目版本诚实显示无正文，可打开获授权的原PDF或反馈版本建议。

正文每次最多20段，严格绑定Asset、DocumentRevision、页和内容hash。优先真实EvidenceSpan，次为有效Passage偏移，无结构页才显示明确文字分片。每段最多12000字符，截断明确提示。focus支持真实span及页内片段，跨分页查回所在窗口，段间空隙404、来源变化409。候选内部选区恢复保留完整范围，不误改为整段或窗口第一段。

候选调用既有Discovery首推检索链，限定目标Asset并读回重验，最多6项，仅为待确认候选。不建新检索架构，不开展检索质量评测。无命中/部分/不可用不等于不存在对应段，读者可明确记录无对应段或增补。同步滚动仅跟随本人已确认关系，不假定同页或同段号。两侧页码及定位独立保存。

## 私人与公共边界

新增加密ParallelReadingTask、最小ParallelReadingReceipt、独立ParallelCalibration，迁移0015仅编写未应用。私人Task使用已有PrivateResearchRecord加密、账户锁、修订CAS与固定请求UUID；所有私有读写要求X-Reader-Owner，响应no-store，客户端不重放401。新建和修改遵守personal_notes保留偏好，读回/重试/删除保持原权限。

任务的四个来源身份字段不可原地更换。切换或交换版本另建任务，旧任务保留；初次恢复单独锁定，防止迟到恢复覆盖主动选择，恢复后切换不会永久锁住。保存请求体不可变；结果未知先by-request查回，仅404重发原请求。已保存但随后修订变化时保留草稿和已创建任务ID，读取最新前阻止重复新建。离开、退出及关闭编辑保护未保存输入。

来源撤回、换文件或换修订后保留既有私人文字，可编辑术语或对齐笔记；来源身份/位置保持原值，不从当前版本拼接旧修订。新关系必须重新选当前版本。读取隐私导出重验原文权限，不把旧引用公开展示。删除私人任务保留无内容回执墓碑，迟到旧请求不得复活内容。用户删除账户时相应记录级联处理。

私人对齐归notes导出和personal_notes删除，新增parallel_alignments叶节点，不增设另一保留开关。公共校准由本人显式选择书目级或所选段落级并填写依据，单独生成记录；不带私人note、terms、positions。公共来源始终按匿名权限重验。私人任务删除不撤回已独立投稿，页面/隐私说明明确告知。

管理入口`/admin/support/parallel-calibrations`复用后台壳与权限。审核/退回需can_review_candidate，发布另需can_publish_authority且必须已审核；固定命令UUID和修订防重复/迟到覆盖。段落投稿提供精确原文核对，书目投稿不伪装有段落。公开列表必须指定left_asset，单页最多重验20条，撤回来源不展示，count为null并允许继续翻页，避免无界解密扫描及虚报可用总数。

## 接口与恢复范围

新增16路径：catalog/parallel下versions、segments、candidates；reading/parallel-tasks列表/详情/by-request；parallel-calibrations本人列表/详情/by-request、public列表/详情、admin列表/详情及review/publish/reject。总契约174路径，原158全部保留。schema_urls为静态契约表面，不另建运行接口。

需共同恢复catalog parallel服务/serializer/view/urls、reading parallel模型/迁移/服务/serializer/views/urls、privacy、原文cover的edition_id补充、Reader并读组件/hooks/client/路由、后台管理与入口、OpenAPI/生成TS、隔离夹具/配置和本记录。不包含继承脏OCR/后台/检索实验/数据文件。原框架、数据库、索引、OCR和队列保持同一系统。

## 静态与验收准备

22个Python路径ast.parse退出0，不执行代码。并读CSS120节点、管理CSS18节点PostCSS解析退出0。17目标ESLint退出0，3条真实img提示；最后并读六路径复查退出0、1条img提示。TypeScript首次四个空值诊断已修复，最终全量结果登记VALIDATION。

spectacular在本进程SQLite内存配置生成tmp/stl4-parallel-schema-20261020.json，退出0、0错误/10条原有Home/Scholar/Topic提示；openapi-typescript同步174路径。首轮新增enum/public schema提示修正后重生成，没有将其忽略。

后端用例源接口10函数、私人任务15函数、隐私6函数。前端8个真实API并读场景、9个管理契约场景均只编写未运行。真实API场景覆盖独立页/不同段号、超过20段、片段恢复、跨账户、写入后丢响应、迟到修订、换版锁、手机、公共/私人隔离。业务响应不模拟；候选服务不可用可以如实报告，不能据此判定质量通过。

`parallel_reader_e2e_fixtures.py`仅接受现有隔离SQLite与同目录media，生成真实合成原文、译本和纯图扫描PDF，经过提取、段落持久化、修订与发布；断言25/27实际段落及位置/hash，拒绝覆盖既有ID。已接入原隔离启动器，playwright.v306收录两新spec。夹具与启动器均未执行，耗时/实际服务成功待核实。

正式统一验收仍需真实权限/并发/保留/删除、迁移、候选服务、PostgreSQL、手机布局与全部三图对照。没有运行测试、浏览器、构建、迁移、OCR/模型/NAS、生产清理或部署。PDF40细分OCR进度/暂停仍在下一单元补齐；全站209视图/B01–B06尚未完成。
