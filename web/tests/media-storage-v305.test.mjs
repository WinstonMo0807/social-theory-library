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
