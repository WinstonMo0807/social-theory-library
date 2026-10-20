# 馆藏检索与多版本接入（2026-10-19）

对应唯一终稿 `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf` 第 24–27 页，已实际查看这四页图像。实施范围为馆藏筛选、同作品多版本、结果计数与页码、仅书目信息和失效文件状态。此单元不改 Discovery、首推语义检索方案或检索质量评测。

## 接入与数据边界

沿现有 `GET /catalog/search/` 增加 `scope=catalog` 分支，使用原 Django/PostgreSQL 模型与活动发布修订，不建立第二套馆藏或索引。其他 scope 和 context 分支保持原实现。馆藏分支只接受 global context，响应 `private, no-store`。

作品必须有当前公开主版本，与公开作品卡、收藏和书单入口一致。每个候选出版版本都必须通过 `public_editions()` 的 published、活动修订归属、active 与 metadata_ready 守卫。主版本不公开时，不能用另一个版本或 Work 草稿填补作品卡。

题名、摘要、语言、版本、年份、出版者、作者及关系读取正式 snapshot。所有筛选必须同时命中同一 Edition；不能把甲版本的作者/语言与乙版本的年份拼成一个命中。一个 Work 返回一次，并携带其全部当前公开版本和真正命中的 `matched_edition_ids`。历史 snapshot 未保存的字段保持空值，不能回退到当前编辑值。

关键词和关系来自 snapshot 中的 topic/node 数组；查询与 facet 还实时核验关联实体仍为 published。新编辑关系不参与匹配。作者名称/别名使用正式发布时的贡献者快照。

可读性要求正式修订指向同版本 NORMALIZED 文件，文件 ready、validation_status=valid、有文件路径、匿名 public/inherit 权限，并与 snapshot 的 document.asset_id 一致。管理员使用该公开入口也不能获得 registered/private/restricted 文件链接。资格不足的公开版本仍显示真实书目信息，并归入 metadata。

全文匹配仅使用活动修订指定的、仍 active 的 DocumentRevision 下非 stale EvidenceSpan，证据页与文件相同，fulltext_ready 与匿名可读性同时成立。不匹配未激活文件、旧正文或后台 OCR 草稿，也不拼接跨缺页内容。

## 契约

请求 `GET /catalog/search/?context=global&scope=catalog` 支持：

- `q` 最长 500 字，最多 20 个空白分隔词，各词须匹配；同一词在已选范围之间使用或条件。
- 重复 `match=title|author|keyword|abstract|fulltext`，默认前四项，必须至少一项。
- 可重复 `document_type`（book、journal_article/article、journal_issue、thesis、report）、`author`（正式快照 Person ID）、`language`、`theory`、`topic`、`concept`（后四者按当前筛选项值，关系为快照 slug）。同字段多值用或，跨字段用且。
- `year` 兼容 before-1900、1900-1949、1950-1999、2000-2009、2010-2019、2020-now；`year_min/year_max` 为 1–9999，反向区间返回 400。
- `access=readable|metadata` 可重复；两者都选相当于不限可用性。
- `sort=relevance|newest|year`；`page` 从 1 开始，`page_size` 默认 24、最大 50。

响应保留 `SearchPayload` 结构，另明确 `context=global`、`scope=catalog` 和 `query`：

- `works` 是公开 WorkCard，新增 `editions: PublicEdition[]`、`matched_edition_ids: UUID[]`。每个 edition 增加正式快照 `language` 与 `availability=readable|metadata`；`readable_asset=null` 时不能生成阅读/下载动作。
- `counts.works` 与 `pagination.total` 均为筛选后的去重作品数；books/articles/theses/reports 按同一匹配版本集合统计。学者、主题、理论和原文片段不是本分支的结果行，相关 count 为 0、集合为空。
- `facets` 保留原分类，新增 `year_histogram:[{year,count}]`。facet 基于当前关键词和匹配范围、应用其他筛选前的公开候选集合，使筛选项仍可切换；每个选项的 count 是不同 Work 数，不是 Edition 数。版本可能跨年，因此各年份计数之和不必等于作品总数。
- relevance 使用正式题名完全匹配、前缀匹配、其他匹配三档，再用主版本正式题名和 Work ID 稳定排序；year 使用命中版本最新出版年；newest 使用命中版本最晚首次发布时间。所有排序都在 Work 层分页，避免多版本 JOIN 把一部作品变成多行。

`CatalogSearchQuery` 和 `CatalogSearchOutput` 已提供给主线契约生成。原 GlobalSearchView 同时承载 legacy 和其他 context，本单元没有将整个 GET 错标为只返回 catalog。由主线统一处理 schema_urls 与分支文档。

## 实现与检查

筛选、JSON 数组匹配、去重、排序、分页和 facet 聚合均在数据库执行。只有当前结果页的作品与公开版本进入应用内存。固定 JSON 路径和表名来自源码；用户值使用绑定参数并按 LIKE 规则转义。PostgreSQL 使用 JSONB，SQLite 提供同等 JSON 语法适配，均沿 Django QuerySet 编译。

已执行的静态检查：

- 使用 `ast.parse` 读取 4 个本单元 Python 文件，退出 0。
- `git diff --check -- api/catalog/views.py`，退出 0。
- 在进程内把 `DATABASE_URL` 设为 SQLite 内存配置，并把 `BaseDatabaseWrapper.ensure_connection` 替换为立即报错守卫。只编译复杂匹配/筛选、Work 分页和年份聚合三种 QuerySet，分别生成 SQLite 与 PostgreSQL SQL，退出 0。没有打开数据库或执行 SQL。最终长度/参数数依次为 SQLite 14294/135、23229/274、14545/138；PostgreSQL 10774/99、18511/200、10831/100。
- 新增合成回归 11 个测试函数，包含参数化权限/校验条件。用例覆盖草稿值不泄漏、别名、同版本过滤、多版本分页/facet 去重、主版本资格、stale/未激活全文、validation_status、匿名文件权限、关系撤回、查询校验和 LIKE 字符安全。**仅编写，未运行**。

未运行正式测试、接口联调、浏览器、构建、迁移、真实模型/索引或生产部署。SQL 编译不能证明数据库查询、结果正确性或性能已通过；PostgreSQL/SQLite JSON 聚合、并发撤回、真实大馆藏代价及逐图效果须在统一验收执行。

## 文件白名单

1. `api/catalog/catalog_search_serializers.py`（新）
2. `api/catalog/services/catalog_search.py`（新）
3. `api/catalog/views.py`（只在 GlobalSearchView.get 开头加入 scope=catalog 分支）
4. `api/tests/test_catalog_search_20261019.py`（新）
5. 本记录。

以上为后端最初交接范围。主线随后接入下列前端、收藏与书单改造，共同形成检查点；没有部署。

## 前端与共享动作

主线实际读取PDF23–27并接入探索入口及馆藏页。探索装饰素材只从唯一PDF23–24提取，脚本 `web/scripts/extract-stl4-explore-art.py` 生成9个无UI/无示例书目内容的素材，保留原图分辨率；没有把整页图作为网站。

`catalog-search-workspace.tsx` 读取 scope=catalog，匹配范围、年份直方图、责任者/理论/主题/概念/语言/类型/可用性过滤、排序、分页和列表/网格均保留于URL。`catalog-result-card.tsx` 按Work合并并展开真实公开版本，读取和下载指向对应可用文件，引用复用共享弹层。加载、失败重试、无结果和真空馆藏分别显示，错误不回填虚构结果。

收藏批量按最多50个作品ID逐批读取，书单通过本人列表明确选择。写入前后校验账户，不重放401写请求；未知收藏响应先查回再决定动作。后端保存元数据公开但尚无PDF的作品，保留撤回来源的私人收藏记录但遮蔽旧公开信息；同作品重复收藏/加入书单使用原对象和所有者事务锁。本人数据读取加 `X-Reader-Owner` 核对，细节见源码收尾记录。

馆藏前端7个浏览器案例、收藏后端6个函数/9个参数案例仅编写未运行。首轮8目标ESLint、5文件AST与两CSS解析通过；收尾静态结果以 `VALIDATION.md` 最新项为准。作品/版本数量、年份分面、真实空库、并发撤回及本人动作仍须统一验收。
