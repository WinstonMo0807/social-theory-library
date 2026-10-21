import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { PathFollowResponse, PublicReadingPath } from "../lib/api/reading-paths.types";

// Uses the disposable runner's actual synthetic PDF, published versions and
// accounts. Only failed/delayed HTTP delivery is injected, never business data.
const api = "http://127.0.0.1:8105/api", slug = "e2e-reading-path";
const route = `/theories/reading-paths/${slug}`, endpoint = `${api}/catalog/theory-system/reading-paths/${slug}/`;
const follows = `${api}/reading/path-follows/`, pathId = "58000000-0000-4000-8000-000000000001";
async function published(page: Page) {
  const response = await page.request.get(endpoint);
  expect(response.status(), `seed_reading_paths(actor) must run in the disposable runner: ${await response.text()}`).toBe(200);
  return await response.json() as PublicReadingPath;
}
async function ownerHeaders(page: Page) {
  const response = await page.request.get(`${api}/auth/me/`); expect(response.status()).toBe(200);
  const owner = String((await response.json()).id), cookie = (await page.context().cookies(api)).find(row => row.name === "csrftoken");
  expect(cookie).toBeTruthy(); return { "X-Reader-Owner": owner, "X-CSRFToken": cookie!.value };
}
async function login(page: Page) {
  await page.goto("/login"); await page.getByLabel("邮箱", { exact: true }).fill("reader-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click(); await expect(page).toHaveURL(/\/account$/);
  const headers = await ownerHeaders(page), existing = await page.request.get(`${follows}by-path/?path_id=${pathId}`, { headers });
  if (existing.status() === 200) {
    const record = ((await existing.json()) as PathFollowResponse).record;
    if (record) { const removed = await page.request.delete(`${follows}${record.id}/?${new URLSearchParams({ request_id: randomUUID(), expected_revision: String(record.revision) })}`, { headers }); expect(removed.status()).toBe(200); }
  } else expect(existing.status()).toBe(404);
}

async function loginEditor(page: Page) {
  await page.goto("/login"); await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click(); await expect(page).toHaveURL(/\/admin$/);
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Run only against the disposable cataloging environment.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", handler => handler.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
});

test("public list searches actual published paths and topic choices without private or draft material", async ({ page }) => {
  const data = await published(page); expect(data.counts).toMatchObject({ stages: 2, items: 5 });
  expect(JSON.stringify(data)).not.toContain("私人编辑备注不得公开"); expect(JSON.stringify(data)).not.toContain("尚未发布的策划说明不得公开");
  await page.goto("/theories/reading-paths?q=PATH58");
  await expect(page.getByRole("heading", { name: "选择一条阅读路径", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PATH58 从材料进入理论", exact: true })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("隐藏路径不得公开");
  await page.getByRole("form", { name: "筛选阅读路径", exact: true }).getByLabel("搜索阅读路径", { exact: true }).fill("不存在的合成路径");
  await page.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page.getByRole("heading", { name: "没有符合条件的公开阅读路径", exact: true })).toBeVisible();
  await page.goto("/theories/reading-paths?topic=e2e-path-topic&difficulty=beginner");
  await expect(page.getByRole("heading", { name: "PATH58 从材料进入理论", exact: true })).toBeVisible();
});

test("two chapters remain distinct in one stage and unavailable materials retain their actual positions", async ({ page }) => {
  const data = await published(page); expect(data.stages[0].items).toHaveLength(2); expect(data.stages[0].items[0].work_id).toBe(data.stages[0].items[1].work_id);
  expect(data.stages[0].items[0].id).not.toBe(data.stages[0].items[1].id);
  await page.goto(route);
  await expect(page.getByRole("table", { name: "阶段阅读材料", exact: true }).getByRole("row")).toHaveCount(3);
  await expect(page.getByText("PATH58 同页合成选段1", { exact: true })).toBeVisible();
  await expect(page.getByText("PATH58 同页合成选段2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /下一阶段：第二阶段/ }).click();
  await expect(page.getByRole("table", { name: "阶段阅读材料", exact: true }).getByRole("row")).toHaveCount(4);
  await expect(page.getByRole("link", { name: "查看知识条目", exact: true })).toHaveAttribute("href", "/theories/nodes/e2e-path-node");
  await expect(page.getByText("暂无全文", { exact: true })).toBeVisible();
  await expect(page.getByText("材料已撤回", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "暂不可读", exact: true })).toHaveCount(2);
});

test("material links retain the exact edition, original page and current document revision", async ({ page }) => {
  const data = await published(page), item = data.stages[0].items[0];
  expect(item.asset_id).toBe("41300000-0000-4000-8000-000000000103"); expect(item.document_revision_id).toBeTruthy();
  const url = new URL(item.reader_url!, "http://127.0.0.1:3105"); expect(url.searchParams.get("page")).toBe("1"); expect(url.searchParams.get("revision")).toBe(item.document_revision_id);
  await page.goto(route);
  const row = page.getByRole("row").filter({ hasText: "PATH58 同页合成选段1" });
  await expect(row.getByRole("link", { name: "开始阅读", exact: true })).toHaveAttribute("href", item.reader_url!);
  await row.getByRole("button", { name: /的来源与版本$/ }).click();
  const dialog = page.getByRole("dialog"); await expect(dialog).toContainText("原文可读");
  await dialog.getByRole("button", { name: "关闭材料来源", exact: true }).click();
});

test("mobile route tabs support Home, End and wraparound while stage content stays within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto(route);
  const first = page.getByRole("tab", { name: "路线", exact: true }); await first.focus(); await first.press("ArrowLeft");
  const last = page.getByRole("tab", { name: "策划说明", exact: true }); await expect(last).toBeFocused(); await expect(last).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toContainText("隔离验收编辑"); await last.press("Home"); await expect(first).toBeFocused();
  await first.press("End"); await last.press("ArrowRight"); await expect(first).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.getByRole("button", { name: /下一阶段：第二阶段/ }).click();
  await expect(page.getByRole("link", { name: "查看知识条目", exact: true })).toBeVisible();
});

test("a failed history request retains the selected version and the real API can be retried", async ({ page }) => {
  const data = await published(page), old = data.versions.find(row => row.token !== data.revision.token)!; expect(old).toBeTruthy();
  await page.goto(route); await page.getByRole("tab", { name: "策划说明", exact: true }).click();
  const pattern = "**/api/catalog/theory-system/reading-paths/e2e-reading-path/**";
  await page.route(pattern, request => request.abort("failed"));
  await page.getByLabel("查看公开历史版本", { exact: true }).selectOption(old.token);
  await expect(page.getByRole("alert")).toContainText("当前路径和本人记录仍保留");
  await expect(page.getByLabel("查看公开历史版本", { exact: true })).toHaveValue(data.revision.token);
  await page.unroute(pattern); await page.getByLabel("查看公开历史版本", { exact: true }).selectOption(old.token);
  await expect(page.getByLabel("查看公开历史版本", { exact: true })).toHaveValue(old.token);
  await page.getByRole("button", { name: "比较与当前公开版的变化", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "公开版本变化", exact: true }); await expect(dialog).toBeVisible(); await expect(dialog).toContainText("材料调整");
});

test("explicit progress and notes survive a separate private copy and completed progress cannot be reset", async ({ page }) => {
  await login(page); await page.goto(route); await page.getByRole("button", { name: "收藏路径", exact: true }).click();
  await expect(page.getByRole("button", { name: "已收藏路径", exact: true })).toBeEnabled();
  const row = page.getByRole("row").filter({ hasText: "PATH58 同页合成选段1" });
  await row.getByRole("combobox").selectOption("reading"); await expect(row.getByRole("combobox")).toHaveValue("reading");
  await row.getByRole("button", { name: "记录本人笔记", exact: true }).click();
  const note = `PATH58 private ${randomUUID()}`, noteDialog = page.getByRole("dialog", { name: "本人阅读笔记", exact: true });
  await noteDialog.getByLabel("笔记内容", { exact: true }).fill(note); await noteDialog.getByRole("button", { name: "保存本人笔记", exact: true }).click(); await expect(noteDialog).not.toBeVisible();
  await row.getByRole("combobox").selectOption("completed"); await expect(row.getByRole("combobox")).toBeDisabled();
  await page.getByRole("button", { name: "另存为私人计划", exact: true }).click();
  const copy = page.getByRole("dialog", { name: "另存为私人阅读计划", exact: true }); await copy.getByRole("button", { name: "确认另存为私人计划", exact: true }).click();
  const href = await copy.getByRole("link", { name: "打开私人计划", exact: true }).getAttribute("href"); expect(href).toMatch(/^\/account\/plans\//);
  await copy.getByRole("button", { name: "关闭另存计划", exact: true }).click();
  await page.goto(`${route}?copy=${href!.split("/").at(-1)}`);
  await expect(page.getByText("当前私人计划副本", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "已收藏路径", exact: true })).toHaveCount(0);
  await row.getByRole("button", { name: "查看本人笔记", exact: true }).click(); await expect(page.getByLabel("笔记内容", { exact: true })).toHaveValue(note);
});

test("a lost committed follow request retains its nonce through same-owner verification", async ({ page }) => {
  await login(page); await page.goto(route); let writes = 0, nonce = "";
  await page.route(follows, async request => {
    if (request.request().method() !== "POST") return request.continue();
    writes++; nonce = request.request().postDataJSON().request_id; const response = await request.fetch(); expect(response.status()).toBe(201); await request.abort("failed");
  });
  await page.getByRole("button", { name: "收藏路径", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("原操作结果尚未确认");
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  const receipt = page.waitForResponse(response => response.url().includes(`by-request/?request_id=${nonce}`));
  await page.getByRole("button", { name: "核对原操作", exact: true }).click(); expect((await (await receipt).json()).receipt.request_id).toBe(nonce);
  await expect(page.getByRole("button", { name: "已收藏路径", exact: true })).toBeEnabled(); expect(writes).toBe(1);
});

test("an unavailable private copy never falls back to another follow record", async ({ page }) => {
  await login(page); await page.goto(route); await page.getByRole("button", { name: "收藏路径", exact: true }).click();
  await expect(page.getByRole("button", { name: "已收藏路径", exact: true })).toBeEnabled();
  let byPath = 0; page.on("request", request => { if (request.url().includes("/path-follows/by-path/")) byPath++; });
  await page.goto(`${route}?copy=${randomUUID()}`); await expect(page.getByRole("alert")).toBeVisible();
  expect(byPath).toBe(0); await expect(page.getByRole("button", { name: "已收藏路径", exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: /的阅读状态$/ })).toHaveCount(0);
});

test("editorial learning and curation previews use unsaved input without reading or writing a private follow", async ({ page }) => {
  await loginEditor(page);
  const privateRequests: string[] = [];
  page.on("request", request => { if (request.url().includes("/reading/path-follows/")) privateRequests.push(request.url()); });
  await page.goto(`/admin/theories/reading-paths?path=${pathId}&section=learning`);
  const fields = page.locator(".fixed-editor-fields"), preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]');
  const question = `PATH58 本地学习问题 ${randomUUID()}`;
  await fields.locator('[data-field-section="learning"]').getByLabel("问题 1", { exact: true }).fill(question);
  await expect(preview.getByRole("tab", { name: "学习问题", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(preview.locator('[data-module-id="reading-path-questions"]')).toContainText(question);
  await page.getByRole("navigation", { name: "编辑区域", exact: true }).getByRole("button", { name: "策划说明与署名", exact: true }).click();
  const note = `PATH58 本地策划说明 ${randomUUID()}`;
  await fields.getByLabel("公开策划说明", { exact: true }).fill(note);
  await expect(preview.getByRole("tab", { name: "策划说明", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(preview.locator('[data-module-id="reading-path-curation"]')).toContainText(note);
  await expect(preview.locator('[data-module-id="reading-path-versions"]')).toBeVisible();
  expect(privateRequests).toEqual([]);
});

test("editor and preview select the same stages and materials by stable identity in both directions", async ({ page }) => {
  await loginEditor(page); const data = await published(page);
  await page.goto(`/admin/theories/reading-paths?path=${pathId}&section=paths`);
  const fields = page.locator(".fixed-editor-fields"), preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]');
  await fields.getByRole("navigation", { name: "阅读阶段", exact: true }).getByRole("button", { name: /第二阶段 · 概念与补充/ }).click();
  await expect(preview.getByRole("heading", { name: "第二阶段 · 概念与补充", exact: true })).toBeVisible();
  const description = `PATH58 第二阶段未保存说明 ${randomUUID()}`;
  await fields.getByLabel("第二阶段 · 概念与补充阶段说明", { exact: true }).fill(description);
  await expect(preview.locator('[data-module-id="reading-path-stages"]')).toContainText(description);
  await expect(preview.getByRole("link", { name: "查看知识条目", exact: true })).toHaveAttribute("href", "/theories/nodes/e2e-path-node");
  const bibliography = data.stages[1].items.find(item => item.source_status === "no_fulltext")!;
  await preview.locator(`[data-preview-item-id="${bibliography.id}"]`).click();
  const bibliographyFields = fields.locator(`[data-editor-item-id="${bibliography.id}"]`);
  await expect(bibliographyFields).toBeVisible();
  await expect(bibliographyFields.getByLabel("公开推荐理由", { exact: true })).toHaveValue(bibliography.reason);
  await expect(bibliographyFields.locator(":focus")).toHaveCount(1);
  await preview.getByRole("navigation", { name: "阅读阶段", exact: true }).getByRole("button", { name: /第一阶段 · 阅读材料/ }).press("Enter");
  await expect(fields.getByRole("navigation", { name: "阅读阶段", exact: true }).getByRole("button", { name: /第一阶段 · 阅读材料/ })).toHaveAttribute("aria-current", "true");
  await expect(preview.getByRole("heading", { name: "第一阶段 · 阅读材料", exact: true })).toBeVisible();
  await expect(preview.getByText("PATH58 同页合成选段1", { exact: true })).toBeVisible();
  const secondChapter = data.stages[0].items[1];
  await preview.locator(`[data-preview-item-id="${secondChapter.id}"]`).click();
  const secondChapterFields = fields.locator(`[data-editor-item-id="${secondChapter.id}"]`);
  await expect(secondChapterFields).toBeVisible();
  await expect(secondChapterFields.getByLabel("章节或选段标题", { exact: true })).toHaveValue("PATH58 同页合成选段2");
  await expect(fields.locator(`[data-editor-item-id="${data.stages[0].items[0].id}"]`)).toBeHidden();
  await preview.getByRole("button", { name: /下一阶段：第二阶段/ }).click();
  await expect(fields.getByRole("navigation", { name: "阅读阶段", exact: true }).getByRole("button", { name: /第二阶段 · 概念与补充/ })).toHaveAttribute("aria-current", "true");
});
