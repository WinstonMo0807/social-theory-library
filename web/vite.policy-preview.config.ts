import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL(".", import.meta.url));
export default defineConfig({
  root: fileURLToPath(new URL("./policy-preview", import.meta.url)),
  publicDir: fileURLToPath(new URL("./public", import.meta.url)),
  resolve: { alias: { "@": webRoot } },
  plugins: [react(), {
    name: "policy-preview-query",
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        if (request.url !== "/policy/query") return next();
        response.setHeader("content-type", "application/json; charset=utf-8");
        response.setHeader("cache-control", "no-store");
        if (request.method !== "POST") { response.statusCode = 405; response.end(JSON.stringify({ detail: "只接受 POST 请求。" })); return; }
        const origin = request.headers.origin;
        if (origin && origin !== `http://${request.headers.host}`) { response.statusCode = 403; response.end(JSON.stringify({ detail: "仅接受同源请求。" })); return; }
        try {
          let body = "";
          for await (const chunk of request) { body += chunk; if (Buffer.byteLength(body, "utf8") > 8000) throw new Error("请求过长。"); }
          const { searchPolicies } = await server.ssrLoadModule(`${webRoot.replace(/\\/g, "/")}lib/policy-demo/search.server.ts`);
          response.end(JSON.stringify(await searchPolicies(JSON.parse(body))));
        } catch (error) { response.statusCode = 400; response.end(JSON.stringify({ detail: error instanceof Error ? error.message : "检索未完成。" })); }
      });
    },
  }],
  server: { host: "127.0.0.1", port: 5178, strictPort: true, fs: { allow: [webRoot] } },
  build: { outDir: "../dist/policy-preview", emptyOutDir: true, copyPublicDir: false },
});
