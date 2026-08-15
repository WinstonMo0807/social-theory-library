# Social Theory Library Web

本目录是 Social Theory Library 的公开站、Explore、PDF Reader、账户中心和管理后台前端。

## 运行环境

- Node.js 22.13 或更高版本
- React 19
- Next.js 16
- Vinext 与 Vite
- Django API

主数据库是 Django 使用的 PostgreSQL。`db`、`drizzle`、`examples/d1` 和 `.openai/hosting.json` 来自前端基础模板，不是馆藏主数据库，也不得建立一份需要与 PostgreSQL 同步的书库数据。

## API

浏览器默认通过同源 `/api` 访问 Django。服务端渲染使用 `INTERNAL_API_URL`。生产环境必须保持 `ALLOW_DEMO_FALLBACK=false`，API 故障应明确显示，不能以静态示例替代真实馆藏。

认证使用 Django 的 HttpOnly JWT Cookie 与版本化 token。不得把生产 token 写入浏览器源码、测试或 Git。

## 本地开发

```powershell
npm.cmd ci
npm.cmd run dev
```

常用验证：

```powershell
npm.cmd run lint
npm.cmd run build
npm.cmd test
```

`postinstall`、`prebuild` 和 `prestart` 会从 `pdfjs-dist` 生成 `public/pdfjs` 中的 worker、CMap、标准字体和 WASM。该目录属于可重建产物，不进入 Git。

## 目录

- `app` 保存页面、布局和样式。
- `components` 保存 Reader、上传、复核、检索和管理组件。
- `lib` 保存服务端与浏览器 API、认证和数据类型。
- `public/editorial` 与 `public/explore` 保存正式前端素材。
- `tests` 保存 Node 回归，`playwright.public.config.ts` 用于浏览器验收。

完整项目规则见根目录 `AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/PROGRESS.md` 和 `docs/ISSUES.md`。
