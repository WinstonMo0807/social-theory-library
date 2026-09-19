// Loopback HTTP transport to the synthetic NAS acceptance API. Business
// responses, cookies, CSRF, streaming and Range headers pass through intact.
// This avoids a cross-site test topology that cannot retain SameSite cookies;
// it never changes the application's cookie or permission policy.
import http from "node:http";

const upstream = { hostname: "192.168.5.6", port: 18106 };
const server = http.createServer((request, response) => {
  if (!request.url?.startsWith("/api/")) {
    response.writeHead(404).end();
    return;
  }
  const forwarded = http.request({ ...upstream, path: request.url, method: request.method, headers: request.headers, timeout: 180_000 }, result => {
    response.writeHead(result.statusCode ?? 502, result.headers);
    result.pipe(response);
  });
  forwarded.on("timeout", () => forwarded.destroy(new Error("Isolated API timed out")));
  forwarded.on("error", () => {
    if (!response.headersSent) response.writeHead(502, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ detail: "隔离测试服务暂时无法连接。" }));
  });
  request.on("aborted", () => forwarded.destroy());
  request.pipe(forwarded);
});
server.listen(8106, "127.0.0.1", () => process.stdout.write("Synthetic service API transport listening on loopback 8106\n"));
