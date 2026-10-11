import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("recycle previews can be framed only by the same site through both gateways", async () => {
  const [nginx, caddy] = await Promise.all([
    readFile(new URL("../../deploy/nginx/default.conf.template", import.meta.url), "utf8"),
    readFile(new URL("../../deploy/caddy/Caddyfile", import.meta.url), "utf8"),
  ]);
  const nginxRules = [...nginx.matchAll(/^\s+~(\S+) 1;$/gm)].map(match => match[1]);
  const caddyRules = [...caddy.matchAll(/^\s+~(\S+) SAMEORIGIN "'self'"$/gm)].map(match => match[1]);
  assert.deepEqual(caddyRules, nginxRules);
  const accepts = value => nginxRules.some(rule => new RegExp(rule).test(new URL(value, "https://library.test").pathname));
  for (const suffix of ["", "?embed=1", "/?embed=1"]) assert.equal(accepts("/admin/preview/recycle/b94fea3d-83fd-4ac1-b3fd-2ad2d75ddf7a"+suffix), true);
  for (const path of ["/admin/preview/recycle", "/admin/preview/recycle/not-an-entry", "/admin/preview/recycle/id/edit", "/admin/recycle?embed=1", "/api/catalog/admin/recycle/b94fea3d-83fd-4ac1-b3fd-2ad2d75ddf7a/preview/", "/login?next=/admin/preview/recycle/b94fea3d-83fd-4ac1-b3fd-2ad2d75ddf7a", "/admin/preview/recycle/../../users"]) assert.equal(accepts(path), false, path);
  assert.match(nginx, /map \$library_preview_frame \$library_frame_options\s*\{\s*default DENY;\s*1 SAMEORIGIN;/);
  assert.match(nginx, /map \$library_preview_frame \$library_frame_ancestors\s*\{\s*default "'none'";\s*1 "'self'";/);
  assert.match(caddy, /default DENY "'none'"/);
});
