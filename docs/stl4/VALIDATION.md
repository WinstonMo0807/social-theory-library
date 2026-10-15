# 验收记录

当前阶段：功能开发。全站正式功能、视觉、权限、迁移、性能验收全部待核实；未部署。

## 开发期检查

只记录实际完成的命令、退出码和范围。静态成功不能证明服务、数据库、NAS、Provider或公网可用。历史测试报告不覆盖本轮修改。

### 2026-10-16 视觉驱动检索接入静态检查

| 命令 | 结果 | 范围与限制 |
|---|---|---|
| `python -m compileall -q api/catalog/services/retrieval/deep_pipeline.py api/catalog/services/discovery_sessions.py api/catalog/discovery_tasks.py api/catalog/tasks.py api/catalog/discovery_views.py api/catalog/services/discovery_inference.py api/config/settings.py` | 退出0 | 仅语法编译；未启动 Django、Celery、Meilisearch 或推理服务 |
| `git diff --check` | 退出0 | 当前工作区差异；不代表业务行为通过 |
| `node node_modules/eslint/bin/eslint.js components/discovery-search-workspace.tsx lib/api/discovery.types.ts` | 退出0，1条既有警告 | 目标前端文件；`no-img-element` 警告未扩大为错误 |
| `.venv/Scripts/python.exe api/manage.py spectacular ... --validate` | 0 schema errors，10条既有 serializer 类型提示 | 生成并更新 OpenAPI；`--fail-on-warn` 仍会因既有警告退出失败 |
| `node node_modules/typescript/bin/tsc --noEmit --pretty false` | 退出1 | 仅报告三个既有 live 测试 TS7022；未定位到本轮深度检索文件 |

第三步检索质量评测按用户要求未运行；正式 E2E、全量功能、浏览器逐图回归、生产迁移和部署仍为待核实。

## 最终验收矩阵

| 门槛 | 核验内容 | 状态 |
|---|---|---|
| B01 | 计划规则/解释、时间估计、完成项和手动调整 | 待核实 |
| B02 | 授权笔记集合持久化、研究/计划隔离、撤销删除失效 | 待核实 |
| B03 | 体检/OCR容量、并发、NAS CPU/内存、取消/部分报告 | 待核实 |
| B04 | 所有者隔离与匿名公开搜索/阅读/下载/复制/引用 | 待核实 |
| B05 | 真实空库、错误/部分结果，无示例学术数据 | 待核实 |
| B06 | 209视图路由/API/移动/桌面/无障碍/性能逐图检查 | 待核实 |
| 接口 | OpenAPI/前端类型/错误/分页/筛选一致性 | 待核实 |
| 数据 | 迁移、保账号清理预演/恢复/真实登录 | 待核实 |
| 发布 | 上传→去重→编目→OCR→预览→发布→撤回→恢复 | 待核实 |
| 检索 | QueryLexicon、活动索引、真实多来源原文、页码 | 待核实 |
| Reader | 连续滚动、目录、书内搜索、选中、批注、引用 | 待核实 |
| 任务 | 持久状态、幂等、迟到结果、重试、取消、部分成功 | 待核实 |
| 运维 | 备份隔离恢复、NAS资源与生产切换/回退 | 待核实 |

最终视觉记录应逐行对应ATLAS_INDEX中的PDF页码、route和state，保存参考区域与实现截图位置、差异及复测结果，不以页面可打开算通过。
