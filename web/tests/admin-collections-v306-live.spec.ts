import { expect, test, type Page } from "@playwright/test";

const localApi = "http://127.0.0.1:8105";

test.beforeEach(async ({ page, baseURL }) => {
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  // Select loopback transport only; every business response is the real
  // application API over the disposable seeded SQLite database.
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${localApi}/api'});` }));
});

async function login(page: Page, role: "curator" | "reader" | "administrator" = "curator") {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
}

async function allApiRows(page: Page, path: string) {
  const rows: Array<Record<string, unknown>> = [];
  let next: string | null = path;
  for (let count = 0; next && count < 10; count += 1) {
    const response = await page.request.get(new URL(next, localApi).href);
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    rows.push(...body.results);
    next = body.next;
  }
  expect(next).toBeNull();
  return rows;
}

test("A11 live API 45 manual works match browser pages and restore exact filter after editing", async ({ page }, testInfo) => {
  await login(page);
  const apiRows = await allApiRows(page, "/api/catalog/admin/library/works/?q=V306-PAGE&ordering=title");
  expect(apiRows).toHaveLength(45);
  await page.goto("/admin/library?q=V306-PAGE&ordering=title");
  const list = page.getByRole("region", { name: "馆藏作品列表" });
  await expect(list.locator("article[data-record-id]")).toHaveCount(40);
  const ids = await list.locator("article[data-record-id]").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-record-id")));
  await page.getByRole("navigation", { name: "馆藏分页" }).getByRole("link", { name: "下一页" }).click();
  await expect(list.locator("article[data-record-id]")).toHaveCount(5);
  ids.push(...await list.locator("article[data-record-id]").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-record-id"))));
  expect(new Set(ids).size).toBe(45);
  expect([...ids].sort()).toEqual(apiRows.map((row) => String(row.id)).sort());
  const returnUrl = new URL(page.url());
  const row = list.locator("article[data-record-id]").last();
  const title = await row.locator("strong").first().textContent();
  const href = new URL((await row.getByRole("link", { name: "编辑当前版本", exact: true }).getAttribute("href"))!, page.url());
  const rowId = await row.getAttribute("data-record-id");
  const expected = apiRows.find((value) => value.id === rowId);
  expect(href.searchParams.get("edition")).toBe((expected?.primary_edition as { id: string }).id);
  await row.getByRole("link", { name: "编辑当前版本", exact: true }).click();
  await expect(page.getByRole("heading", { name: title!, exact: true, level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "返回列表", exact: true }).click();
  await expect(page).toHaveURL(returnUrl.href);
  await expect(page.getByRole("region", { name: "馆藏作品列表" }).locator("article[data-record-id]")).toHaveCount(5);
  await page.screenshot({ path: testInfo.outputPath("live-library-page2-return.png"), fullPage: true });
});

test("A10/A12 live unified queue pages contain all 45 manual records and their real sessions", async ({ page }, testInfo) => {
  await login(page);
  const apiRows = await allApiRows(page, "/api/catalog/admin/workflows/queue/?scope=publication&category=all&source=manual&q=V306-PAGE");
  expect(apiRows).toHaveLength(45);
  expect(apiRows.every((row) => row.item_id === null && row.edition_id && row.session_id)).toBeTruthy();
  await page.goto("/admin/publication?source=manual&q=V306-PAGE");
  const list = page.getByRole("region", { name: "馆藏发布列表" });
  await expect(list.locator("article[data-record-id]")).toHaveCount(30);
  const ids = await list.locator("article[data-record-id]").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-record-id")));
  await page.getByRole("navigation", { name: "发布列表分页" }).getByRole("link", { name: "下一页" }).click();
  await expect(list.locator("article[data-record-id]")).toHaveCount(15);
  ids.push(...await list.locator("article[data-record-id]").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-record-id"))));
  expect([...ids].sort()).toEqual(apiRows.map((row) => String(row.id)).sort());
  await list.getByRole("link", { name: "预览与影响", exact: true }).last().click();
  await expect(page.getByRole("region", { name: "当前版本公开预览" })).toBeVisible();
  await expect(page.getByRole("region", { name: "发布内容差异" })).toBeVisible();
  await expect(page.getByText("当前没有PDF预览。", { exact: false })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("live-manual-publication-preview.png"), fullPage: true });
});

test("A10 live older unbound upload opens its original source and preserves identity on retry", async ({ page }, testInfo) => {
  await login(page);
  await page.goto("/admin/review?source=upload&category=exception&q=V306-OLD-ERROR");
  const list = page.getByRole("region", { name: "待办记录" });
  await expect(list.locator("article[data-record-id]")).toHaveCount(1);
  await expect(list.getByText("V306-OLD-ERROR.pdf", { exact: true })).toBeVisible();
  const stableId = (await list.locator("article").getAttribute("data-record-id"))!;
  const itemId = stableId.replace(/^upload:/, "");
  const beforeResponse = await page.request.get(`${localApi}/api/ingestion/items/${itemId}/`);
  expect(beforeResponse.ok()).toBeTruthy();
  expect((await beforeResponse.json()).edition).toBeNull();
  await list.getByRole("link", { name: "继续处理", exact: true }).click();
  const source = page.getByRole("region", { name: "选定上传来源" });
  await expect(source.getByRole("heading", { name: "V306-OLD-ERROR.pdf", exact: true })).toBeVisible();
  await expect(source.getByText("这个文件还没有生成书目", { exact: false })).toBeVisible();
  await expect(source.getByRole("alert")).toContainText("原来源待重新提交");
  const retryResponse = page.waitForResponse((response) => response.url().endsWith(`/items/${itemId}/retry/`) && response.request().method() === "POST");
  await source.getByRole("button", { name: "重试原来源任务", exact: true }).click();
  expect((await retryResponse).status()).toBe(202);
  await expect(source.getByRole("status").filter({ hasText: "重试请求已接受" })).toBeVisible();
  const afterResponse = await page.request.get(`${localApi}/api/ingestion/items/${itemId}/`);
  const after = await afterResponse.json();
  expect(afterResponse.ok()).toBeTruthy();
  expect(after.id).toBe(itemId);
  expect(after.edition).toBeNull();
  expect(after.status).not.toBe("published");
  await page.screenshot({ path: testInfo.outputPath("live-unbound-source-retry-receipt.png"), fullPage: true });
});

test("A26 live ordinary Admin settings do not read Owner backup or Prompt registries", async ({ page }) => {
  await login(page, "administrator");
  const restrictedRequests: string[] = [];
  page.on("request", (request) => { if (/\/distribution\/backups\/|\/admin\/prompt-registry\//.test(request.url())) restrictedRequests.push(request.url()); });
  await page.goto("/admin/settings#backups");
  await expect(page.getByText("仅System Owner可读取正式备份和创建归档。", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "AI 提示词", exact: true }).click();
  await expect(page.getByRole("tabpanel").getByText("只有书库所有者可以查看和修改。", { exact: true })).toBeVisible();
  expect(restrictedRequests).toEqual([]);
  const denied = await page.request.get(`${localApi}/api/distribution/backups/`);
  expect(denied.status()).toBe(403);
});

test("A26/A32 live reader cannot use collection or source admin APIs", async ({ page }) => {
  await login(page, "reader");
  for (const path of ["/api/catalog/admin/library/works/?q=V306-PAGE", "/api/catalog/admin/workflows/queue/?category=all"]) {
    const response = await page.request.get(`${localApi}${path}`);
    expect(response.status()).toBe(403);
    expect(await response.text()).not.toContain("V306-PAGE-00");
  }
});

test("A31 manual creation and preview preserve exact editor and nested list return", async ({ page }) => {
  await login(page);
  const list = "/admin/library?q=V306-PAGE&ordering=title&page=2";
  await page.goto(`/admin/cataloging/new?return_to=${encodeURIComponent(list)}`);
  await page.getByRole("textbox", { name: "作品题名", exact: true }).fill("V306-RETURN 手工会话返回验收");
  await page.getByRole("button", { name: "创建草稿并开始编目", exact: true }).click();
  await expect(page.getByRole("heading", { name: "V306-RETURN 手工会话返回验收", level: 1, exact: true })).toBeVisible();
  const editor = new URL(page.url());
  expect(editor.searchParams.get("return_to")).toBe(list);
  const preview = new URL((await page.getByRole("link", { name: "打开完整前台预览", exact: true }).getAttribute("href"))!, page.url());
  const editorReturn = new URL(preview.searchParams.get("return_to")!, page.url());
  expect(editorReturn.pathname).toBe(editor.pathname);
  expect(editorReturn.searchParams.get("return_to")).toBe(list);
  await page.goto(preview.href);
  const back = page.locator(`a[href="${editorReturn.pathname}${editorReturn.search}${editorReturn.hash}"]`).first();
  await expect(back).toBeVisible();
  await back.click();
  await expect(page.getByRole("heading", { name: "V306-RETURN 手工会话返回验收", level: 1, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回列表", exact: true }).click();
  await expect(page).toHaveURL(new URL(list, page.url()).href);
});

test("A03 live unready Edition explains primary blockers without making a write", async ({ page }) => {
  await login(page);
  const response = await page.request.get(`${localApi}/api/catalog/admin/workflows/queue/?q=V306-PAGE&source=manual`);
  const row = (await response.json()).results[0];
  const writes: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/primary/")) writes.push(request.url()); });
  await page.goto(`/admin/library/works/${row.work_id}?edition=${row.edition_id}`);
  const preview = page.waitForResponse((result) => result.request().method() === "GET" && result.url().endsWith(`/editions/${row.edition_id}/primary/`));
  await page.getByRole("button", { name: "主版本设置", exact: true }).click();
  const body = await (await preview).json();
  expect(body.can_select).toBe(false);
  await expect(page.getByRole("alert").filter({ hasText: "当前不能更改主版本" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "确认更改作品主版本", exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("A03/A13 live primary selection survives lost response without duplicate audit or snapshot rewrite", async ({ page }, testInfo) => {
  await login(page);
  const workResponse = await page.request.get(`${localApi}/api/catalog/admin/library/works/?q=${encodeURIComponent("作品规范记录")}`);
  const work = (await workResponse.json()).results[0];
  expect(work).toBeTruthy();
  const editionsUrl = `${localApi}/api/catalog/admin/library/works/?view=editions&work_id=${work.id}`;
  const before = await (await page.request.get(editionsUrl)).json();
  expect(before.results).toHaveLength(2);
  const target = before.results.find((row: { is_primary: boolean }) => !row.is_primary);
  const snapshots = before.results.map((row: { id: string; publication: { active_revision_id: string } }) => [row.id, row.publication.active_revision_id]);
  const writes: unknown[] = [];
  let savedAudit = "";
  await page.route(`**/api/catalog/admin/editions/${target.id}/primary/`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    writes.push(route.request().postDataJSON());
    if (writes.length === 1) {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      savedAudit = (await response.json()).audit_id;
      return route.abort("failed");
    }
    return route.continue();
  });
  await page.goto(`/admin/library/works/${work.id}?edition=${target.id}`);
  await page.getByRole("button", { name: "主版本设置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "确认更改作品主版本", exact: true });
  await expect(dialog).toContainText("第2版");
  await expect(dialog).toContainText("Page ID和私人阅读记录保留");
  await dialog.getByRole("button", { name: "确认更改主版本", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "重试同一切换请求", exact: true })).toBeVisible();
  const retried = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/editions/${target.id}/primary/`) && response.status() === 200);
  await dialog.getByRole("button", { name: "重试同一切换请求", exact: true }).click();
  const receipt = await (await retried).json();
  expect(writes).toHaveLength(2);
  expect(writes[0]).toEqual(writes[1]);
  expect(receipt.audit_id).toBe(savedAudit);
  expect(receipt.listing_effective).toBe(true);
  expect(typeof receipt.projections_complete).toBe("boolean");
  await expect(page.getByText("作品列表：所选版本已生效", { exact: false })).toBeVisible();
  const after = await (await page.request.get(editionsUrl)).json();
  expect(after.results.filter((row: { is_primary: boolean }) => row.is_primary).map((row: { id: string }) => row.id)).toEqual([target.id]);
  expect(after.results.map((row: { id: string; publication: { active_revision_id: string } }) => [row.id, row.publication.active_revision_id]).sort()).toEqual(snapshots.sort());
  const publicResponse = await page.request.get(`${localApi}/api/catalog${receipt.public_url}/`);
  expect(publicResponse.status()).toBe(200);
  expect((await publicResponse.json()).title).toBe("第2版已经公开的题名");
  await page.screenshot({ path: testInfo.outputPath("live-primary-selection-accepted-effective.png"), fullPage: true });
});
