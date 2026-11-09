# 架构索引的生成与解释

[架构目录](../README.md) · [页面清单](../ADMIN_PAGE_INVENTORY.md) · [模块业务契约](../ADMIN_MODULE_CONTRACTS.md)

这些清单帮助定位源码，不自动推断产品语义、运行分支、权限正确性或生产数据库内容。当前基线见[审计版本](../AUDIT_BASELINE.md)。

## 文件与字段

| 文件 | 内容与限制 |
| --- | --- |
| [admin-pages.csv](admin-pages.csv) | 管理端URL、page/handler源文件、直接组件/参数/跳转；77个page与2个handler |
| [component-imports.csv](component-imports.csv) | 解析到本仓库模块的import/re-export边、符号、源行与typeOnly标记；导入不等于执行 |
| [component-renders.csv](component-renders.csv) | JSX内实际出现的组件名与源行；条件分支仍需人工检查 |
| [frontend-api-expressions.csv](frontend-api-expressions.csv) | API调用表达式；模板变量和封装路径不强行展开成静态URL |
| [api-views-services.csv](api-views-services.csv) | Django path声明、View位置、方法、直接Service/Model引用；不自动展开全部继承/动态派发 |
| [model-fields.csv](model-fields.csv) | 205个Model类声明中的自有字段、类型、推定表名；抽象类表名为空，不等于205张实体表；不展开父类字段 |
| [model-consumers.csv](model-consumers.csv) | 模型被函数/类直接引用的源位置；包含写入和读取，业务消费者由人工文档解释 |
| [browser-observations.json](browser-observations.json) | 本轮只读浏览的标题、访问边界与入口，不含业务表单内容、私人数据或登录凭据 |

本轮扫描772个前端模块、632个后端模块，提取517处path声明，其中516处定位到View定义。唯一未定位项为配置根入口的Django admin动态站点对象。声明数包含health/schema等基础入口，不是517项独立业务功能。

## 重新生成

根目录执行，使用项目已安装的TypeScript parser及Python标准库，不启动Django、不访问数据库、不发送网络请求。

```powershell
node scripts/architecture-inventory.mjs
python scripts/architecture_inventory.py
python scripts/architecture_page_map.py
python scripts/check_architecture_docs.py
```

前两步把完整AST中间结果保存在忽略目录 `tmp/architecture-inventory/`，把便于审阅的CSV写在本目录；第三步生成完整页面和组件Markdown表。浏览器观察不是生成脚本的产物，只能按实际新观察更新。

路由到M00–M20业务组是人工维护规则，修改路由后检查脚本`flow()`与[模块契约](../ADMIN_MODULE_CONTRACTS.md)一起变化。多export模块的所有JSX不能一概归到每个入口；精确关系需从入口调用的export继续追踪。

源码行号仅对生成时的树有效。提交前运行生成器并查看diff；出现新API/模型时同步正文、ERD、生命周期和权限解释。机器清单不能代替这些人工判断。

## 截图与图表维护

截图存于相邻`images/`目录，只使用公开资料或空白/合成表单。更换截图应记录页面、日期、视口、角色与检查范围，并实际查看图片确认没有账号、通知、凭据或私人内容。

Mermaid保持在Markdown中作为可编辑源。可在忽略目录安装验证器：`npm install --prefix tmp/mermaid-validation mermaid@11.17.2 --ignore-scripts --no-audit --no-fund`，再运行`node scripts/check-architecture-mermaid.mjs --channel msedge`；不为应用增加文档框架或运行依赖。文档检查脚本校验本地文件、标题锚点、源码行号与必需图类；Mermaid语法和SVG布局需另外用渲染器验证。当前验证环境和结果见[VALIDATION.md](../VALIDATION.md)。
