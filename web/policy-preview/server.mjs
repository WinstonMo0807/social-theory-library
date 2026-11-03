// Isolated preview server: only public sample search and allowlisted static files.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { searchPolicies } from "./server/search.server.js";

const root = resolve(process.env.POLICY_PREVIEW_ROOT || ".");
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
let active = 0;
createServer(async (request, response) => {
  response.setHeader("x-content-type-options", "nosniff");
  response.setHeader("cache-control", "no-store");
  response.setHeader("x-robots-tag", "noindex, nofollow");
  const json = (status, body) => { response.writeHead(status, { "content-type": "application/json; charset=utf-8" }); response.end(JSON.stringify(body)); };
  try {
    const url = new URL(request.url, "http://preview.local");
    if (url.pathname === "/policy/query") {
      if (request.method !== "POST") return json(405, { detail: "只接受 POST 请求。" });
      if (request.headers.origin && request.headers.origin !== `http://${request.headers.host}`) return json(403, { detail: "仅接受同源请求。" });
      if (active >= 1) return json(429, { detail: "检索模型正在处理另一条问题，请稍后重试。" });
      active++;
      try {
        let body = "";
        for await (const chunk of request) { body += chunk; if (Buffer.byteLength(body, "utf8") > 8000) return json(413, { detail: "问题内容过长。" }); }
        return json(200, await searchPolicies(JSON.parse(body)));
      } finally { active--; }
    }
    if (request.method !== "GET" && request.method !== "HEAD") return json(405, { detail: "不支持此操作。" });
    const pathname = decodeURIComponent(url.pathname);
    const page = pathname === "/" || pathname === "/policy" || pathname === "/policy/";
    if (!page && !/^\/(?:assets|brand|fonts)\//.test(pathname)) return json(404, { detail: "预览仅开放政策库页面。" });
    const path = page ? resolve(root, "index.html") : resolve(root, `.${pathname}`);
    if (!path.startsWith(root + sep)) return json(404, { detail: "文件不存在。" });
    const type = types[extname(path)];
    if (!type) return json(404, { detail: "文件不存在。" });
    const content = await readFile(path);
    response.writeHead(200, { "content-type": type, "content-length": content.length });
    response.end(request.method === "HEAD" ? undefined : content);
  } catch (error) {
    json(error?.code === "ENOENT" ? 404 : 400, { detail: error?.code === "ENOENT" ? "文件不存在。" : "请求未完成，请检查问题和筛选条件后重试。" });
  }
}).listen(Number(process.env.PORT || 5178), process.env.HOST || "127.0.0.1", () => console.log("Policy research preview ready"));
