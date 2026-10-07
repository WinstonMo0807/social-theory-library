import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("only the edition cover endpoint admits 12 MiB images plus multipart overhead", async () => {
  const source = await readFile(new URL("../../deploy/nginx/default.conf.template", import.meta.url), "utf8");
  assert.match(source, /client_max_body_size 2m;/);
  const cover = source.split("location ~ ^/api/catalog/admin/editions/[0-9a-fA-F-]+/cover/$ {")[1]?.split("location ^~ /api/distribution/assets/")[0];
  assert.ok(cover);
  assert.match(cover, /client_max_body_size 13m;/);
  assert.match(cover, /proxy_pass http:\/\/api:8000;/);
  assert.match(cover, /proxy_set_header Host \$host;/);
  assert.match(cover, /proxy_set_header X-Forwarded-Proto \$library_forwarded_proto;/);
  assert.match(cover, /limit_conn per_ip 8;/);
});

test("every API storage mount persists private media beside public files", async () => {
  for (const name of ["compose.public.yaml", "compose.yaml", "compose.nas.yaml"]) {
    const source=await readFile(new URL(`../../${name}`,import.meta.url),"utf8");
    const publicMounts=source.split(/\r?\n/).filter(line=>line.trim().endsWith("/public:/data/public"));
    const privateMounts=source.split(/\r?\n/).filter(line=>line.trim().endsWith("/private:/data/private"));
    assert.ok(publicMounts.length>0);
    assert.equal(privateMounts.length,publicMounts.length,name);
  }
});

test("gateways admit the actual same-origin previews without framing login, API or admin editors", async () => {
  const nginx = await readFile(new URL("../../deploy/nginx/default.conf.template", import.meta.url), "utf8");
  const caddy = await readFile(new URL("../../deploy/caddy/Caddyfile", import.meta.url), "utf8");
  const nginxRules = [...nginx.matchAll(/^\s+~(\S+) 1;$/gm)].map(match => match[1]);
  const caddyRules = [...caddy.matchAll(/^\s+~(\S+) SAMEORIGIN "'self'"$/gm)].map(match => match[1]);
  assert.ok(nginxRules.length > 0);
  assert.deepEqual(caddyRules, nginxRules, "direct gateway must not add a second framing denial");
  const accepts = value => nginxRules.some(rule => new RegExp(rule).test(new URL(value, "https://library.test").pathname));
  // These are the iframe targets of AdminPublicPreviewFrame, FixedPageEditor,
  // SelectedWorkPreview, curation queues and WorkflowInspector.
  const previews = [
    "/", "/about", "/explore?q=韦伯", "/recommendations", "/recommendations/daily-reading",
    "/works/book-slug", "/reader/asset-id", "/scholars/weber", "/scholars/weber/network",
    "/scholars/weber/evidence", "/topics/modernity", "/topics/modernity/passages",
    "/theory-schools/critical-theory", "/theory-schools/critical-theory/evidence",
    "/theories/nodes/critical-theory", "/theories/nodes/critical-theory/evidence",
    "/theories/disciplines/sociology", "/subdisciplines/social-theory",
    "/theories/reading-paths/intro", "/admin/preview/works/edition-id?embed=1",
    "/admin/preview/knowledge/scholar/profile-id?embed=1&page=network",
    "/admin/preview/evidence/topic/topic-id", "/admin/about/preview?embed=1",
    "/admin/recommendations/issues/issue-id/preview?embed=1",
  ];
  for (const path of previews) {
    assert.equal(accepts(path), true, path);
    const url = new URL(path, "https://library.test");
    if (url.pathname !== "/") url.pathname += "/";
    assert.equal(accepts(url.href), true, `${path} trailing slash`);
  }
  for (const path of [
    "/login", "/login?embed=1", "/account", "/admin", "/admin/library/works/id",
    "/admin/users", "/admin/preview", "/admin/preview/not-a-page/id",
    "/admin/about", "/admin/recommendations/issues/id", "/api/auth/login/",
    "/api/catalog/admin/page-preview/editions/id/", "/media/private/file",
    "/works/id/extra", "/admin/preview/works/id/edit", "/login?next=/admin/preview/works/id",
    "/admin/preview/works/../../users", "/recommendations/id/../../login",
  ]) assert.equal(accepts(path), false, path);
  assert.match(nginx, /map \$uri \$library_preview_frame/);
  assert.match(nginx, /map \$library_preview_frame \$library_frame_options\s*\{\s*default DENY;\s*1 SAMEORIGIN;/);
  assert.match(nginx, /map \$library_preview_frame \$library_frame_ancestors\s*\{\s*default "'none'";\s*1 "'self'";/);
  assert.match(nginx, /add_header X-Frame-Options \$library_frame_options always;/);
  assert.match(nginx, /add_header Content-Security-Policy "frame-ancestors \$library_frame_ancestors" always;/);
  assert.match(caddy, /default DENY "'none'"/);
  assert.match(caddy, /X-Frame-Options "\{library_frame_options\}"/);
  assert.match(caddy, /frame-ancestors \{library_frame_ancestors\}; frame-src 'self' blob:/);
});
