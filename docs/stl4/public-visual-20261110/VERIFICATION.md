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

构建、定向功能、不同角色真实写入、响应式和图片对照尚未运行。独立预览尚未启动。后续先完成业务清单与设计覆盖，再实施和隔离验证。
