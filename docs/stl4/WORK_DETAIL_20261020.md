# PDF33–35 作品与期刊论文详情

## 后续修订：2026-10-20 Reader单元

下文是42f068a时的历史实现。READER_20261020进一步修复：明确选择的公开次版本详情、带edition_id的图片与原文定位不再要求主版本同时公开，而按目标自身发布/文件权限独立判断。馆藏集合及无明确版本的旧图片入口保持原公开主版本规则。对应旧“保留公开主版本资格”表述仅代表当时实现，当前以源码和本修订为准。

日期：2026-10-20。前置检查点 d3acba8（PDF32），当前单元为源码接入，待全站统一验收。

## 依据与产品行为

实际读取唯一 final-r2 PDF 的第33、34、35页及其嵌入原图。对应R10-main、R10-sub01、R10-states；参考图的示例书目、引文和封面未成为生产数据。按总纲纸白、暖灰、炭黑及砂金实现，未沿用图内旧蓝。

同一个 WorkDetailView 继续服务公开页、已保存草稿预览和编目实时预览。加入书封/无封面、题名/副题/原题、原作及当前版本元数据、真实学者、简介展开、版本表、目录、相关著作/概念/专题/路径和研究资料。期刊论文展示刊名/卷期/页码/DOI与有明确关联的整期目录。手机书籍使用折叠区，论文保留横向标签和纵向版本卡。版本标识点击进入对应详情，在线阅读和下载指向该版实际文件，更多操作复用共享引用，收藏/书单复用本人账户边界。分享只复制公开版本链接；草稿预览不执行公共写入或文件动作。

来源元数据缺失显示待补；仅书目保留收藏、书单和引用。可读性取服务返回文件，不以页数判断。access_state根据当前发布文件显示readable、metadata、unavailable、registered、restricted，后两种只作权限状态说明，不伪造馆内借阅或额外获取渠道，不暴露受限文件ID。只有真实公开文件返回Reader/下载入口。原文摘录仅来自当前版本已发布且仍可用的人工策划证据，不套用图中引文。

## 接口与权限

原 GET /api/catalog/works/{slug}/ 现返回 PublicWorkDetail。入口匹配激活快照中的版本slug或Edition UUID；草稿slug、撤回版本、未激活修订不进入。保留既有Work公开主版本资格。所选Edition绑定顶层元数据、edition、outline、cover、recommendation_image；公开详情即使由管理员读取，也不升级文件权限。历史快照缺字段保留空值，不从未发布Work草稿回填。

editions复用CatalogEdition，新增access_state，availability仍保持readable/metadata，兼容馆藏筛选。关联字段relations包含scholars、concepts、topics、reading_paths、curations、works、journal_issues，每类预览最多6条，不是完整数量。相关作品由当前发布快照的同作者/概念/主题等明确关系在SQL筛选后取前6条；不再筛选loadWorks第一页。整期目录由已发布目录里的article_work_id反查，不按刊名猜关系。学者、主题和概念再核验当前公开状态；贡献者名字保留书目快照，撤回的学者链接/头像/简介不回显。

封面和推荐图沿原公开端点增加edition_id参数，核对同Work/当前激活版本，带参数响应no-store。共享journal_issues.public_journal_contents修复所有目录消费者的草稿slug问题，保留已出版目录文字但只给当前公开文章生成链接。PublicWorkDetail也no-store；loadWork使用React请求内cache去重metadata/page读取，不跨请求缓存。

无新模型、迁移、检索算法、索引或任务。来源原件、账户和私人资料不变。已存在的发布账本、ReadingPath与知识对象继续复用。专题反向关联尚无索引，流式查看发布快照头部，只有候选命中才调用原issue_payload；真实规模耗时留待验收。

## 文件

- 后端：public_work_detail.py、services/work_detail_relations.py、services/journal_issues.py、catalog_search_serializers.py、views.py。
- 前端：work-detail-view.tsx及module.css；原人工策划/理论证据内容抽至work-detail-evidence.tsx；Work展示模型、纯adapter、catalog.server、公开路由和两种管理预览同步。
- 契约：api/openapi/schema.json与web/lib/api/generated/schema.ts。原151路径保持不变，现有详情及CatalogEdition响应扩展。
- 用例：test_public_work_detail_20261020.py 7函数/14参数案例；test_work_detail_relations_20261020.py 7函数；work-detail-adapter.test.mjs 3案例。均只编写未运行。

## 静态记录

- Python ast.parse上述5个后端文件及2个测试，共7文件退出0。
- Django在DATABASE_URL=sqlite:///:memory:、PUBLIC_DEPLOYMENT_MODE=false、DJANGO_DEBUG=true下初始化，5条关系SQL仅编译，未执行数据库查询，退出0。
- spectacular --urlconf config.schema_urls --format openapi-json --file tmp/stl4-work-detail-schema-20261020.json --validate，0错误/10条既有Home/Scholar/Topic提示；openapi-typescript同步。
- web下node node_modules/typescript/bin/tsc --noEmit --incremental false：首轮40209因两个语言字段可空退出1；修正后59028与最终45429退出0。
- web下node node_modules/eslint/bin/eslint.js检查10目标文件，退出0、3个img提示；PostCSS parse module.css146顶层节点，退出0。最后版本标识链接与缺失文献类型回退调整后，目标ESLint与全量TS（45429）再次退出0。
- 没有正式测试、浏览器、构建、逐图验收、迁移、模型/OCR/NAS、检索质量评测或生产操作。

## 统一验收范围

两版分别检查题名、版本、目录、封面、原文、下载和引用一致；metadata-only不借主版文件；草稿改slug/撤回/历史字段缺失/失效文件/已登录管理者均保持公开边界。检查目录文章撤回、专题定时发布、学者撤回、无任何关联的空态。桌面与390px手机检查长题名、版本表、更多菜单、标签键盘、折叠、分享手动复制、封面弹层、焦点返回和#citation锚点。两种管理预览不得变成公共写入口。真实NAS/文件分发/全部样式与PDF像素差异尚未验收，不能据静态结果声称完全一致。

下一单元继续唯一PDF36–40 Reader的当前源码回溯与接入，不重复已经实施的目录/页码/笔记服务。其余历史未提交修改保留，209视图/B01–B06未完成。
