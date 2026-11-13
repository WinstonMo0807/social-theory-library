# 14 · 测试、证据与维护

[架构目录](README.md) · [问题清单](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md) · [公网观察](PUBLIC_SITE_VERIFICATION.md)

## 本轮验证边界

本轮没有运行正式全站E2E、全量视觉回归、生产业务写入、OCR或Provider基准。运行源码校验、静态扫描、类型/契约检查、有限隔离回归与浏览器只读观察分别记录；旧报告只作为历史记录，不合并计算通过数。

| 检查 | 本轮结果 | 证明范围 |
| --- | --- | --- |
| Git/远端/工作区/镜像身份 | 已核对并记录 | 原workspace保留；按运行文件形成整合提交 |
| API应用源码791份 / OCR5份 | LF规范化摘要一致 | 不证明所有依赖包/环境配置相同 |
| Web清单1847项 | 除环境注入项外与既有发布产物一致 | 没有新建可逐字节复现构建 |
| 前后端AST扫描 | 772前端模块、632后端模块、79管理入口、517path声明 | 声明与静态引用，不等于分支执行 |
| TypeScript | `tsc --noEmit --incremental false`，退出0 | 当前前端类型检查；不证明页面交互 |
| Web runtime-api测试 | 7/7，退出0 | 同源API、URL修复、旧路由、会话header |
| API有限回归 | 41例中39通过、2失败，退出1 | 内存SQLite与locmem，不接生产；失败详见下文 |
| OpenAPI契约 | 初次失败；重生成Unicode slug schema后复查退出0 | TypeScript声明无差异；业务实现未变 |
| Markdown/链接/Mermaid/数据安全 | 见 [VALIDATION.md](VALIDATION.md) | 只按实际完成的检查填记录 |

## 有限回归发现

执行文件为 `test_curation_publication_intent_20261109.py`、`test_contribution_scope_20261021.py`、`test_knowledge_publish_owner_20261023.py`、`test_stl4_media_library_workspace_20261024.py`。

失败1：章节责任者测试复用的`test_reading_paths_20261021.source()`只创建Work(title)，document_type为空，进入`work_editor._refresh_edition_metadata`的材料类型映射产生KeyError。它证明测试输入与当前必要字段不一致；尚不能推断正常表单可以创建该非法状态。

失败2：知识发布owner重放测试预期200，实际发布返回400。具体返回原因和结论见[问题报告](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md)，未把失败改成通过，也没有为了审计改写业务逻辑或测试断言。

这两项属于需修复/校准的测试契约证据。新的发布意图回归通过，不代表所有历史测试保持兼容。

## 维护者可运行的检查

以下命令应在一次性本地测试库与本地缓存环境执行。真实PostgreSQL并发、Redis/Celery外部worker与正式浏览器验收使用仓库各自配置，不能把测试URL指向生产。

```powershell
# 根目录：静态架构索引，无数据库导入
node scripts/architecture-inventory.mjs
python scripts/architecture_inventory.py
python scripts/architecture_page_map.py
python scripts/check_architecture_docs.py

# web目录
npm run api:check
npx tsc --noEmit --incremental false
npm run test:runtime-api

# api目录；先配置隔离数据库/缓存
python -m pytest tests/test_curation_publication_intent_20261109.py -q
python manage.py check
python manage.py makemigrations --check --dry-run
```

`npm run test`会先build再执行单测；Playwright public/auth/workflow/cataloging配置各有目标与会话要求。没有运行的命令不计入本轮通过。pytest存在postgres_integration与celery_redis_integration标记；SQLite不能证明select_for_update竞争行为。

## 文档维护规则

路由/组件变更重跑静态索引并核对人工模块编号；API serializer变更重跑api:generate/api:check；模型/公开规则变更同步ERD、消费者、生命周期和权限；发布变更更新版本基线，不把历史截图当当前证据。Mermaid图保持单一主题、明确箭头与建议标记；CSV提供细节，正文负责解释业务含义。

新截图使用公开页面或空白测试表单，裁去账号/通知/私人内容，不修改图片伪装状态。提交前核对秘密、馆藏、数据库、模型、索引、运行日志与构建产物均未混入Git。
