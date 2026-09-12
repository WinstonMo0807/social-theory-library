import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("every API storage mount persists private media beside public files", async () => {
  for (const name of ["compose.public.yaml", "compose.yaml", "compose.nas.yaml"]) {
    const source=await readFile(new URL(`../../${name}`,import.meta.url),"utf8");
    const publicMounts=source.split(/\r?\n/).filter(line=>line.trim().endsWith("/public:/data/public"));
    const privateMounts=source.split(/\r?\n/).filter(line=>line.trim().endsWith("/private:/data/private"));
    assert.ok(publicMounts.length>0);
    assert.equal(privateMounts.length,publicMounts.length,name);
  }
});
