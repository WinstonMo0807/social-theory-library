# 盘点验证记录

环境为独立工作区 `C:/Users/12297/.codex/worktrees/stl-public-visual-20261110/书库开发3`。尚无视觉实现，以下不是全站功能或视觉验收。

| 日期 | 实际动作 | 结果与范围 |
|---|---|---|
| 2026-11-10 | NAS Docker 元数据、路由、Web 发布清单和 API 文件摘要只读核查 | Web1860文件、API788文件一致；基线7b8963fe；未变更服务 |
| 2026-11-10 | Python HTTPS 匿名 GET12个已知业务接口 | 8个公开/健康接口200，身份/检索/管理3个401，以及ready200；逐项见 ANONYMOUS_HTTP.json，不含数据正文 |
| 2026-11-10 | `C:/Python314/python.exe scripts/audit_public_visual_api.py` | 退出0；本地已部署源码 resolver，内存SQLite配置，不访问生产DB；730路由模式、535处理类、1067方法路径。包含格式别名，不等同有效业务数 |
| 2026-11-10 | bundled Node `scripts/audit-public-visual-web.mjs` | 退出0；152个 page 文件，最新714个传输/薄包装调用位置，298个需动态路径/选项继续核对。未运行网站 |
| 2026-11-10 | `C:/Python314/python.exe scripts/link_public_visual_contracts.py` | 退出0；2694条候选路径关联，覆盖131个page入口；未据此宣称全部调用已验证 |
| 2026-11-10 | `git diff --check` | 退出0；仅检查差异空白，不代表类型/构建/功能通过 |
| 2026-11-10 | 独立Edge标签只读观察公开入口与管理导航 | 见 BUSINESS_FINDINGS.md；未提交、未发信、未触发模型/文件任务，未保存私人内容截图 |

运行 Python 时仅复用原工作区 `.venv/Lib/site-packages`；Node 的 TypeScript 库复用已核实发布构建目录依赖。没有复制真实 `.env`。本地 resolver 只解析声明，不运行 queryset/serializer 输出，不创建用户。

一次尝试在 NAS 容器中做完整 inspect 源码定位超过35秒，未获得完整结果；随后改在已核对一致的本地源码运行。不能称“生产运行时完整 API 探测通过”。

完整静态发现中间文件保存在本工作区 `output/public-visual-20261110/audit/`：API_ROUTES、API_METHOD_HINTS、API_SOURCE_HINTS、FIELD_CONTRACTS、WEB_SOURCE_MAP。它们可由脚本重新生成，属于本地盘点产物，不提交Git。正式范围及证据摘要保存于本目录CSV/Markdown。

除 Django API 清单外，前端有两个 GET307兼容入口 `/admin/theory-schools`、`/admin/theory-schools/[entityId]`，已登记PV153/154。`POST /policy/query` 仅为已暂停 policy-demo，接受同源请求、正文上限8000字符；属于排除项，未执行。没有将该Demo加入公网业务改造。

`scripts/audit_public_visual_fields.py` 退出0，1239个serializer类中1237个解析字段成功，2个是无Meta的抽象基类。数据库执行包装器禁止任何查询；记录类型、必填、只读/只写、长度、数值、选择和嵌套字段，不运行对象序列化或访问生产数据。API_CONTRACTS新增可读public_path_template，保留人工审阅列。

独立前端18110已启动用于业务核查；API18111在新临时SQLite中运行既有合成夹具，并用进程内socket连接禁止器阻断出站。未复制数据库、真实环境变量或生产文件。两处旧夹具缺陷（重复sha256/kind、重复活动catalog revision）已定位并修正测试输入/历史状态；业务模型约束保留。首次启动失败不是公网缺陷，重启结果另记。依赖复制只进入隔离worktree/node_modules。

正式构建、全站定向功能、响应式和图片对照尚未运行。后续先完成业务清单与设计覆盖，再实施和隔离验证。

2026-11-10 02:45 隔离环境已运行：Web18110/API18111，API独立临时目录stl-v305-e2e-blmwfzde。GET直接API及前端/api/health和auth/login均200。Edge使用仅此测试库的合成馆长登录，实际观察/admin、/home、/works/parallel-fixture-left及/reader/41300000-0000-4000-8000-000000000103。PDF画布及原生文字层出现；自动progress/history仅写入本测试库。未将这些合成数据截图或计数当成生产事实。

预览兼容修复：Workers拒绝fetch redirect:error导致首页SSR异常；改manual后非2xx仍抛ServerApiError，不跟随跳转、不转发凭据。既有api-domain-boundaries测试加302拒绝与单次请求断言。整文件实际执行3项：2通过1失败（旧纯适配器断言不允许任何运行时导入，而基线已有mediaAllows），退出1；仅相关split catalog requests运行1项通过退出0。失败未删除或改弱。

`node scripts/prepare-pdfjs-assets.mjs`退出0，补本地worker/CMaps/fonts/WASM后PDF实际可读。开发用Vite仅在显式STL_ISOLATED_API_ORIGIN且值为127.0.0.1端口时代理/api；生产edge设置不变。未把本机预览作为生产部署。

追加：`scripts/check_public_visual_fixture_roles.py`退出0。五角色各28个GET入口：访客5成功/23未登录，读者16成功/12无权限，编辑20成功/8无权限，管理员与馆长均28成功。只有合成账户登录POST，业务均GET；结果仅记录响应字段名。首次脚本缺少X-Reader-Owner/X-Editor-Owner产生额外403，按实际客户端补齐后重跑，未修改权限。

`scripts/enrich_public_visual_contracts.py`退出0，1067方法路径中914条解析到相关serializer；补继承权限来源、查询字段、直接请求键、分页参数、两层服务调用与校验来源。来源解析包含同类其他HTTP方法，已明确标注范围，不宣称运行覆盖。字段定义见API_FIELD_CONTRACTS，业务摘要与单独运行证据仍分开。

前端路径发现脚本补源码已核实的researchRecordPath/privateCitationSourcePath/citationPreviewPath/replayPath及人物/账号前缀，750个请求位置，256处动态表达式保留待对应。页面/API候选映射4619条、131页面；不能将候选数量当作完整业务完成率。

Edge追加实际观察/account空资料及继续阅读、/account/citation-audits能力限制、/admin/theories列表与编辑预览。合成理论解释对象未保存改文，在实际公开组件预览读到相同文字；切回保持内容，最后恢复原输入未保存/发布。实际截图见output/public-visual-20261110/screenshots/baseline-theory-draft-preview.jpg。
