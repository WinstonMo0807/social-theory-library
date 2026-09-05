import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public work and authenticated preview reuse one presentational component", async () => {
  const [publicPage, previewRoute, previewPage, view] = await Promise.all([
    readFile(new URL("../app/works/[slug]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/preview/works/[editionId]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/preview/work-page-preview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/work-detail-view.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(publicPage, /<WorkDetailView work=\{work\} relatedWorks=\{relatedWorks\} footer=\{<SiteFooter \/>\}/);
  assert.match(previewRoute, /<AdminWorkPagePreview editionId=\{editionId\} footer=\{<SiteFooter \/>\}/);
  assert.match(previewPage, /<WorkDetailView[\s\S]*preview=\{\{/);
  assert.match(previewPage, /\/catalog\/admin\/page-preview\/editions\/\$\{editionId\}\//);
  assert.match(view, /草稿预览/);
  assert.match(view, /返回编辑/);
  assert.match(previewPage, /returnHref: payload\.return_url/);
});

test("full draft preview removes the normal admin navigation shell", async () => {
  const shell = await readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8");
  assert.match(shell, /preview\\\/works\\\/\[\^\/\]\+/);
  assert.match(shell, /\{!focusMode \? <aside/);
  assert.match(shell, /\{!focusMode \? <header/);
});

test("workbench opens a compact preview in the existing inspector", async () => {
  const [editor, inspector] = await Promise.all([
    readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/inspector/workflow-inspector.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(editor, /kind: "page_preview"/);
  assert.doesNotMatch(editor, /window\.open\(previewUrl/);
  assert.match(inspector, /打开完整前台预览/);
  assert.doesNotMatch(inspector, /Math\.round\(candidate\.confidence/);
  assert.doesNotMatch(inspector, /词典影响/);
});

test("admin preview keeps async server components outside the client module graph", async () => {
  const [previewPage, view] = await Promise.all([
    readFile(new URL("../components/admin/preview/work-page-preview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/work-detail-view.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(previewPage, /@\/components\/site-footer/);
  assert.doesNotMatch(view, /@\/components\/site-footer/);
  assert.match(previewPage, /footer: ReactNode/);
  assert.match(view, /footer: ReactNode/);
  assert.match(view, /\{footer\}/);
});

test("admin preview keeps reader, download, save and public links inactive", async () => {
  const view = await readFile(new URL("../components/work-detail-view.tsx", import.meta.url), "utf8");

  assert.match(view, /preview \? \(/);
  assert.match(view, /引用、保存、下载和公共 Reader 动作在管理员页面预览中不执行/);
  assert.match(view, /preview \? association\.node\.name/);
  assert.match(view, /!preview \? \(/);
  assert.match(view, /<AssetDownloadButton assetId=\{work\.id\}/);
  assert.match(view, /<SaveWorkButton workId=\{work\.workId\}/);
});

test("public work routes preserve API 404 semantics without masking service failures", async () => {
  const [publicPage, serverApi] = await Promise.all([
    readFile(new URL("../app/works/[slug]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/server-api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(serverApi, /export class ServerApiError extends Error/);
  assert.match(serverApi, /throw new ServerApiError\(response\.status, path\)/);
  assert.match(serverApi, /error instanceof ServerApiError && error\.status === 404/);
  assert.match(publicPage, /if \(!work\) notFound\(\)/);
  assert.match(serverApi, /if \(!allowDemoFallback\) throw error/);
});
