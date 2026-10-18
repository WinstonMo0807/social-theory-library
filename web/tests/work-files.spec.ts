import { expect, test, type Page } from "@playwright/test";
import type { WorkFile, WorkFilesState, WorkFileUploadResult } from "../lib/api/work-files.types";

// Synthetic contracts only. Authenticated storage/Range and conversion await final acceptance.
const id = (n: number) => `81000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const workId = id(1), editionId = id(2), stamp = "2026-10-18T00:00:00Z";
const contentPath = (n: number) => `/catalog/admin/editions/${editionId}/files/${id(100 + n)}/content/`;
function pdfBytes() {
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Contents 4 0 R >>", "<< /Length 0 >>\nstream\nendstream",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Contents 6 0 R >>", "<< /Length 0 >>\nstream\nendstream"];
  let text = "%PDF-1.4\n"; const offsets = [0];
  for (const [index, object] of objects.entries()) { offsets.push(Buffer.byteLength(text)); text += `${index + 1} 0 obj\n${object}\nendobj\n`; }
  const xref = Buffer.byteLength(text);
  text += `xref\n0 7\n0000000000 65535 f \n${offsets.slice(1).map(value => `${String(value).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(text);
}
const pdf = pdfBytes();
const file = (n: number): WorkFile => ({ id: id(100 + n), kind: "normalized", filename: `合成文件${n}.pdf`, mime_type: "application/pdf",
  byte_size: pdf.length, page_count: 2, sha256: "a".repeat(64), version: n, source_asset_id: id(200 + n), created_at: stamp, updated_at: stamp,
  created_by: "Synthetic", status: "ready", validation_status: "valid", is_current: n === 1, is_public_reader: n === 1,
  preview_url: contentPath(n), download_url: `${contentPath(n)}?download=1`, can_adopt: n !== 1, generate_reader_url: "", rights_note: "合成授权", access_status: "public",
  public_preparation: { required: false, status: "not_required", can_prepare: false, prepare_url: "", detail: "合成环境无需云端分发准备" } });

async function setup(page: Page) {
  const fixture = {
    owner: 1, denied: false, fileError: 0, csvError: false, uploadError: 0, newEditionError: 0, rightsConflict: false, refreshes: 0,
    receipt: null as WorkFileUploadResult | null, holdUpload: null as Promise<void> | null,
    uploads: [] as { requestKey: string; action: string; reader: string; expected: string }[],
    editions: [] as Record<string, unknown>[], rights: [] as Record<string, unknown>[], heads: [] as string[], contentGets: [] as string[], pages: [] as number[],
    state: {
      work: { id: workId, title: "合成版本工作台", updated_at: stamp, cover_url: "", authors: [], document_type: "book", original_publication_year: null },
      editions: [{ id: editionId, label: "合成出版版本", version_label: "合成出版版本", publication_year: 2024, publisher: "合成机构", language: "zh",
        is_primary: true, state: "published", original_count: 21, reader_count: 21, current_reader_asset_id: file(1).id }],
      selected_edition_id: editionId,
      edition: { id: editionId, updated_at: stamp, active_revision_id: id(3), current_reader_asset_id: file(1).id, public_reader_asset_id: file(1).id,
        rights: { note: "合成授权", access_status: "public", source_asset_id: file(1).id, updated_at: stamp, can_edit: true }, workbench_url: `/admin/library/works/${workId}?edition=${editionId}` },
      files: { count: 21, page: 1, page_size: 20, results: Array.from({ length: 20 }, (_, index) => file(index + 1)) }, current_reader_file: file(1), public_reader_file: file(1),
      tasks: [], task_count: 0,
      capabilities: { can_edit: true, can_publish: true, max_active_tasks_per_edition: 1, formats: [
        { extension: "pdf", max_bytes: 500 * 1024 * 1024, max_derived_bytes: null, available: true, can_generate_reader: true, service_verified: false, reason: "" },
        { extension: "docx", max_bytes: 12 * 1024 * 1024, max_derived_bytes: 32 * 1024 * 1024, available: true, can_generate_reader: false, service_verified: false, reason: "合成转换器未配置" },
      ] },
      history: { count: 0, page: 1, page_size: 20, results: [] },
      impact: { count: 21, page: 1, page_size: 20, results: [{ id: id(501), kind: "catalog_evidence", title: "合成馆藏来源1", asset_id: file(1).id, file_page_index: 1, printed_page_label: "", status: "confirmed", href: "" }],
        summary: { catalog_evidence: 21, reader_annotations: 0, reader_bookmarks: 0, reader_progress: 0 }, notice: "不读取私人正文", export_url: `/catalog/admin/editions/${editionId}/files/impact.csv` },
    } as WorkFilesState,
  };
  const field = (body: string, name: string) => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]+)`).exec(body)?.[1] || "";
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const response = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return response({ id: fixture.owner, role: "admin", display_name: "Synthetic", capabilities: ["access_back_office", "can_edit_metadata", "can_publish_work", "can_view_evidence"], reading_preferences: {} });
    if (path === "/api/auth/token/refresh/") { fixture.refreshes += 1; return response({}, 401); }
    if (fixture.denied && path.includes("/catalog/admin/")) return response({ detail: "当前管理权限不可读取此文件" }, 403);
    if (path === `/api/catalog/admin/works/${workId}/files/`) {
      const currentPage = Number(url.searchParams.get("page") || 1), impactPage = Number(url.searchParams.get("impact_page") || 1);
      fixture.pages.push(currentPage);
      return response({ ...fixture.state, files: { ...fixture.state.files, page: currentPage, results: currentPage === 2 ? [file(21)] : fixture.state.files.results },
        impact: { ...fixture.state.impact, page: impactPage, results: [{ ...fixture.state.impact.results[0], title: `合成馆藏来源${impactPage}`, file_page_index: impactPage }] } });
    }
    if (path === `/api/catalog/admin/works/${workId}/editions/`) {
      const body = request.postDataJSON(); fixture.editions.push(body);
      if (fixture.newEditionError) return response({ detail: "合成新增版本失败" }, fixture.newEditionError);
      return response({ created: true, work_id: workId, edition_id: id(4), request_key: body.request_key, workbench_url: "" }, 201);
    }
    if (path.endsWith("/rights/") && request.method() === "PATCH") {
      const body = request.postDataJSON(); fixture.rights.push(body);
      if (fixture.rightsConflict) {
        fixture.state.edition!.rights = { ...fixture.state.edition!.rights, note: "另一管理员保留的合成说明", updated_at: "2026-10-18T00:01:00Z" };
        return response({ detail: "合成版权说明并发冲突" }, 409);
      }
      return response({ request_key: body.request_key, asset_id: file(1).id, rights_note: body.rights_note, updated_at: "2026-10-18T00:02:00Z" });
    }
    if (path.includes("/files/requests/")) return fixture.receipt ? response(fixture.receipt) : response({ detail: "尚无本次请求" }, 404);
    if (path === `/api/catalog/admin/editions/${editionId}/files/` && request.method() === "POST") {
      const body = request.postDataBuffer()?.toString("utf8") || "", requestKey = field(body, "request_key");
      fixture.uploads.push({ requestKey, action: field(body, "action"), reader: field(body, "generate_reader"), expected: field(body, "expected_updated_at") });
      if (fixture.uploadError) return response({ detail: "合成文件响应未确认" }, fixture.uploadError);
      fixture.receipt = { accepted: true, created: true, request_key: requestKey, item_id: requestKey, work_id: workId, edition_id: editionId,
        status: "received", dispatch_status: "queued", workbench_url: "", detail: "原件请求已保存，尚未采用" };
      if (fixture.holdUpload) await fixture.holdUpload;
      return response(fixture.receipt, 202).catch(() => {}); // User may have canceled this transport after server acceptance.
    }
    if (path.endsWith("/files/impact.csv")) return fixture.csvError ? response({ detail: "合成导出暂不可读取" }, 503) : route.fulfill({ status: 200, contentType: "text/csv", body: "synthetic\n" });
    if (path.endsWith("/content/")) {
      if (request.method() === "HEAD") fixture.heads.push(path); else fixture.contentGets.push(path);
      if (fixture.fileError) return response({ detail: "合成文件读取错误" }, fixture.fileError);
      return route.fulfill({ status: 200, headers: { "Content-Type": "application/pdf", "Content-Length": String(pdf.length), "Accept-Ranges": "bytes", ETag: `"${"a".repeat(64)}"` }, body: request.method() === "HEAD" ? "" : pdf });
    }
    return response({ count: 0, results: [] });
  });
  await page.goto(`/admin/library/works/${workId}/files?tab=files`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "版本与文件管理", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "文件与历史", exact: true })).toContainText("合成文件1.pdf");
  return fixture;
}

async function selectUpload(page: Page, replace = false, name = "synthetic.pdf") {
  await page.getByRole("button", { name: replace ? "替换文件" : "补充文件", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: replace ? "替换文件与预览" : "补充文件与预览", exact: true });
  await dialog.getByLabel("选择当前版本的新文件").setInputFiles({ name, mimeType: "application/pdf", buffer: pdf });
  return dialog;
}
async function confirmUpload(page: Page) {
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "下一步：确认影响" }).click();
  await dialog.getByRole("checkbox", { name: "已核对出版版本、所选文件与历史保留说明。" }).check();
  await dialog.getByRole("button", { name: "保存原件并开始处理", exact: true }).click();
}

test("file pagination preserves the independently returned current reader and physical page numbering", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("navigation", { name: "文件历史分页" }).getByRole("button", { name: "下一页" }).click();
  await expect(page.getByRole("region", { name: "文件与历史", exact: true })).toContainText("合成文件21.pdf");
  await expect(page.getByRole("complementary", { name: "所选版本的文件与影响" })).toContainText("合成文件1.pdf");
  expect(fixture.pages).toContain(2);
  await expect(page.getByText(/^PDF 页 1 ·/)).toBeVisible();
  await page.getByRole("navigation", { name: "馆藏影响分页" }).getByRole("button", { name: "下一页" }).click();
  await expect(page.getByText("合成馆藏来源2", { exact: true })).toBeVisible();
  await expect(page.getByText(/^PDF 页 2 ·/)).toBeVisible();
});

test("server errors never download JSON as an original or CSV", async ({ page }) => {
  const fixture = await setup(page), downloads: string[] = [];
  page.on("download", download => downloads.push(download.suggestedFilename()));
  fixture.fileError = 503;
  await page.getByRole("region", { name: "文件与历史", exact: true }).getByRole("button", { name: "下载", exact: true }).first().click();
  await expect(page.getByText("文件暂不可读取（503），请重新核对权限或文件状态。", { exact: true })).toBeVisible();
  expect(fixture.heads).toHaveLength(1); expect(fixture.contentGets).toHaveLength(0); expect(downloads).toHaveLength(0);
  fixture.csvError = true;
  await page.getByRole("button", { name: "导出可见引用影响", exact: true }).click();
  await expect(page.getByText("合成导出暂不可读取", { exact: true })).toBeVisible();
  expect(downloads).toHaveLength(0);
});

test("PDF preview verifies HEAD and renders the existing two-page canvas at actual 100 percent", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("region", { name: "文件与历史", exact: true }).getByRole("button", { name: "预览", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "合成文件1.pdf", exact: true });
  await expect(dialog.getByLabel("PDF 页码")).toHaveAttribute("max", "2");
  await expect(dialog.getByText("100%", { exact: true })).toBeVisible();
  await expect.poll(() => dialog.locator("canvas").evaluate(canvas => canvas.getBoundingClientRect().width)).toBeGreaterThan(100);
  expect(fixture.heads).toHaveLength(1); expect(fixture.contentGets.length).toBeGreaterThan(0);
  await dialog.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(dialog.getByLabel("PDF 页码")).toHaveValue("2");
});

test("unknown upload result must be looked up and retries use the original request id", async ({ page }) => {
  const fixture = await setup(page); fixture.uploadError = 503;
  await selectUpload(page); await confirmUpload(page);
  await expect(page.getByRole("button", { name: "查回本次请求", exact: true })).toBeVisible();
  const originalKey = fixture.uploads[0].requestKey; expect(originalKey).toBeTruthy();
  await page.getByRole("button", { name: "查回本次请求", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("当前尚未查到本次请求");
  fixture.uploadError = 0;
  await page.getByRole("button", { name: "重试同一文件请求", exact: true }).click();
  await expect(page.getByRole("heading", { name: "文件请求已保存", exact: true })).toBeVisible();
  expect(fixture.uploads).toHaveLength(2); expect(fixture.uploads[1].requestKey).toBe(originalKey);
});

test("canceling transport retains the server-accepted request and reads it back without another upload", async ({ page }) => {
  const fixture = await setup(page); let release!: () => void;
  fixture.holdUpload = new Promise<void>(resolve => { release = resolve; });
  await selectUpload(page); await confirmUpload(page);
  await expect.poll(() => fixture.uploads.length).toBe(1);
  await page.getByRole("button", { name: "取消传输并保留请求", exact: true }).click();
  await expect(page.getByRole("button", { name: "查回本次请求", exact: true })).toBeVisible();
  release();
  await page.getByRole("button", { name: "查回本次请求", exact: true }).click();
  await expect(page.getByRole("heading", { name: "文件请求已保存", exact: true })).toBeVisible();
  expect(fixture.uploads).toHaveLength(1);
});

test("replacement requires a reader copy and unsupported conversion returns to the supplement entry", async ({ page }) => {
  const fixture = await setup(page);
  const dialog = await selectUpload(page, true);
  const reader = dialog.getByRole("checkbox", { name: "生成可阅读的 PDF 副本（替换文件必须生成）", exact: true });
  await expect(reader).toBeChecked(); await expect(reader).toBeDisabled();
  await dialog.getByLabel("选择当前版本的新文件").setInputFiles({ name: "synthetic.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("synthetic") });
  await expect(dialog.getByRole("button", { name: "下一步：确认影响" })).toBeDisabled();
  await expect(dialog.getByRole("alert")).toContainText("不能替换阅读文件");
  page.once("dialog", prompt => prompt.accept());
  await dialog.getByRole("button", { name: "返回上级，改用补充文件" }).click();
  await expect(dialog).toHaveCount(0); expect(fixture.uploads).toHaveLength(0);
});

test("session invalidation clears local file preview and prevents stale owner submissions", async ({ page }) => {
  const fixture = await setup(page);
  await selectUpload(page, false, "previous-owner.pdf");
  await expect(page.getByRole("dialog")).toContainText("previous-owner.pdf");
  fixture.owner = 2; fixture.denied = true;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("previous-owner.pdf", { exact: true })).toHaveCount(0);
  expect(fixture.uploads).toHaveLength(0);
});

test("edition write uses exact input limits and never refreshes a 401 into another mutation", async ({ page }) => {
  const fixture = await setup(page); fixture.newEditionError = 401;
  await page.getByRole("button", { name: "新增出版版本", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增出版版本", exact: true });
  await expect(dialog.getByLabel("版本名称")).toHaveAttribute("maxlength", "120");
  await expect(dialog.getByLabel("出版机构")).toHaveAttribute("maxlength", "300");
  await dialog.getByLabel("版本名称").fill("保留的合成新版本");
  await dialog.getByRole("button", { name: "建立版本草稿", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("合成新增版本失败");
  await expect(dialog.getByLabel("版本名称")).toHaveValue("保留的合成新版本");
  expect(fixture.editions).toHaveLength(1); expect(fixture.refreshes).toBe(0);
});

test("changing a selected PDF revokes its object URL and removes the old preview", async ({ page }) => {
  await page.addInitScript(() => {
    const state = { created: [] as string[], revoked: [] as string[] };
    Object.defineProperty(window, "__stlFileUrls", { value: state });
    const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = value => { const url = create(value); if (value instanceof File) state.created.push(url); return url; };
    URL.revokeObjectURL = url => { state.revoked.push(url); revoke(url); };
  });
  await setup(page);
  const dialog = await selectUpload(page);
  await expect(dialog.getByLabel("PDF 页码")).toHaveAttribute("max", "2");
  await dialog.getByLabel("选择当前版本的新文件").setInputFiles({ name: "changed.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("synthetic") });
  await expect(dialog.getByLabel("PDF 页码")).toHaveCount(0);
  const urls = await page.evaluate(() => (window as unknown as { __stlFileUrls: { created: string[]; revoked: string[] } }).__stlFileUrls);
  expect(urls.created).toHaveLength(1); expect(urls.revoked).toContain(urls.created[0]);
});

test("copyright conflict preserves the draft and only patches the note after a fresh explicit base", async ({ page }) => {
  const fixture = await setup(page); fixture.rightsConflict = true;
  await page.getByRole("button", { name: "版权与授权", exact: true }).click();
  await page.getByRole("button", { name: "编辑版权与授权说明", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "编辑版权与授权说明", exact: true });
  await dialog.getByLabel("文件来源与授权依据").fill("当前编辑者保留的合成说明");
  await dialog.getByRole("button", { name: "保存版权说明", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("合成版权说明并发冲突");
  await expect(dialog.getByLabel("文件来源与授权依据")).toHaveValue("当前编辑者保留的合成说明");
  await expect(dialog.getByRole("button", { name: "保存版权说明", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "已核对，保留输入并采用最新文件基准", exact: true }).click();
  fixture.rightsConflict = false;
  await dialog.getByRole("button", { name: "保存版权说明", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(fixture.rights).toHaveLength(2);
  expect(fixture.rights[1]).toMatchObject({ expected_asset_updated_at: "2026-10-18T00:01:00Z", rights_note: "当前编辑者保留的合成说明" });
  expect(fixture.rights[1]).not.toHaveProperty("access_status");
  expect(fixture.rights[1].request_key).not.toBe(fixture.rights[0].request_key);
});
