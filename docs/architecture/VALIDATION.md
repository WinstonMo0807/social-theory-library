# 本轮验证记录

[架构目录](README.md) · [质量与测试边界](14_TESTING_AND_QUALITY.md) · [问题依据](15_KNOWN_ISSUES_AND_OPEN_QUESTIONS.md)

日期：2026-11-09。运行基准为`curation-publish-r1`，源码整合检查点`f5406339`；随后变化是文档、维护索引和派生API schema。生产只读，后端测试使用内存SQLite、locmem和memory broker。

## 实际结果

| 检查 | 执行与结果 | 限制 |
| --- | --- | --- |
| 初始/最终Git核对 | 分支、HEAD、status、remote、远端main分别核对 | 原工作区没有reset、切换或覆盖；在隔离分支整合 |
| 生产源码 | API791份、OCR5份规范化摘要一致；Web1847项与既有发布清单一致，环境注入项单列 | 没有从新commit重新构建；不倒推原生产构建SHA |
| 最后镜像核对 | 15:06（Asia/Shanghai）API/Web/OCR digest与初始证据相同 | OCR仍exited，未启动任务 |
| 静态索引 | TS/Python AST重新生成：772/632模块；155全站入口、79管理入口；517path/516可定位View；205模型声明 | 包含抽象模型与兼容入口；不等于实际执行覆盖或生产表数 |
| Python语法 | 整合的变更Python源文件AST解析、索引脚本实际执行成功 | 无应用启动/生产数据库访问 |
| TypeScript | `tsc --noEmit --incremental false`，退出0 | Node24.22.1，使用现有已安装依赖；未fresh install |
| Web定向测试 | `node --experimental-strip-types --test --test-force-exit tests/runtime-api.test.mjs`，7/7，退出0 | 同源URL、兼容跳转与会话header |
| API定向测试 | 下列4份文件，41例中39通过、2失败，退出1 | 本地Python3.14.6，不是生产Python3.12容器；SQLite不证明PostgreSQL锁 |
| 失败定位 | 单独重跑知识发布owner用例，仍400，退出1；响应说明缺少可公开关联内容 | 诊断记录不改变失败总数，不把重复运行算新通过 |
| API契约 | 初次`generate-api-contracts.mjs --check`退出1；生成schema后复查退出0 | 仅两处Unicode slug pattern更新，TypeScript类型无差异 |
| 文档链接 | `python scripts/check_architecture_docs.py`退出0，覆盖31份维护Markdown、本地链接/标题/源码行号、入口数量 | 不检查全部历史文档或外部网站持续可达性 |
| Mermaid | Mermaid11.17.2 + 新建headless Edge会话，22/22成功生成SVG；退出0 | 本地渲染，不宣称GitHub服务端使用完全相同版本；C4使用flowchart表达 |
| 图表版面 | 实际查看C4、运行、管理组件、ERD、发布时序等代表图，拆分过宽关系图 | 完整细节由CSV和模块契约补足，不把所有对象挤入一图 |
| README视觉 | 本地Markdown渲染1300px/390px检查，图片无断链、文档无横向溢出 | GitHub风格近似渲染，不冒称GitHub实际服务端截图 |
| 公网页面 | 真实授权/匿名浏览器只读核对；6张代表截图 | 页面范围见公网报告；未提交业务表单 |
| Git内容检查 | 新历史10591个blob作大小和高置信凭据模式扫描；最大约8.1MB，无超过50MB项；受保护数据/运行目录与新文件检查未发现应排除内容 | 模式扫描并非形式化秘密检测；CSS/task类名误匹配已按边界修正排除 |
| GitHub推送 | `7cadf014..33643ed6 HEAD -> main`成功；原main为新提交祖先，合并树与已验证文档提交一致 | 普通push，无force；本轮不触发生产部署 |
| diff whitespace | `git diff --check`退出0；暂存后复核 | 不以此替代业务验收 |

## 后端定向测试命令

在`api`目录，对本地测试进程设置以下环境后执行；不使用生产配置。

```powershell
$env:DATABASE_URL='sqlite:///:memory:'
$env:DJANGO_DEBUG='true'
$env:PUBLIC_DEPLOYMENT_MODE='false'
$env:CACHE_URL='locmem://'
$env:CELERY_BROKER_URL='memory://'
python -m pytest tests/test_curation_publication_intent_20261109.py tests/test_contribution_scope_20261021.py tests/test_knowledge_publish_owner_20261023.py tests/test_stl4_media_library_workspace_20261024.py -q
```

失败分别是章节责任者用例创建空document_type的Work，以及主题owner重放用例缺少当前要求的公开关联。它们没有到达原定目标断言，保留为测试契约待修项；没有改业务来迎合旧夹具，也没有将其解释为已复现生产权限缺陷。

## 可维护的检查入口

`architecture-inventory.mjs`、`architecture_inventory.py`、`architecture_page_map.py`重新生成清单；`check_architecture_docs.py`检查文档和入口覆盖；`check-architecture-mermaid.mjs`在临时安装Mermaid后逐图解析、生成SVG和截图。中间产物、渲染图片与原始运行回执留在忽略的tmp目录，正式页面截图位于`images/`。

没有执行新的生产部署、数据库迁移、全站写入E2E、全量视觉回归、真实OCR/Provider基准或邮件测试。也没有读取和并入首期PDF项目正在进行的知识策展内容。
