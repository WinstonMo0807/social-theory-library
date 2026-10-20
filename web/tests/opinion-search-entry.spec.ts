import { expect, test, type Page } from "@playwright/test";

// Synthetic contracts, authored for unified acceptance; no actual search services or accounts.
const work = "10000000-0000-4000-8000-000000000001";
const author = "10000000-0000-4000-8000-000000000002";
const topic = "10000000-0000-4000-8000-000000000003";
const person = "10000000-0000-4000-8000-000000000004";
const identity = { id: 77, email: "synthetic@example.invalid", display_name: "合成账户", role: "reader" };

async function setup(page: Page, authenticated = false) {
  await page.route("**/api/auth/me/", route => route.fulfill(authenticated ? { json: identity } : { status: 401, json: { detail: "Synthetic guest" } }));
  await page.route("**/api/auth/refresh/", route => route.fulfill({ status: 401, json: { detail: "Synthetic guest" } }));
  await page.route("**/api/catalog/discovery-search/**", route => route.fulfill({ status: 503, json: { detail: "Synthetic search not running" } }));
  await page.route("**/api/catalog/search/**", route => {
    const context = new URL(route.request().url()).searchParams.get("context");
    return route.fulfill({ json: { visibility: "public", context, pagination: { page: 1, total_pages: 1, total: 1 },
      groups: [{ results: [{ id: context === "scholars" ? person : topic, title: context === "scholars" ? "合成学者" : "合成主题", subtitle: "仅用于回归", context, entity_type: context === "scholars" ? "person" : "topic" }] }] } });
  });
}

test("entry preserves canonical scope and additional filters when submitting", async ({ page }) => {
  await setup(page);
  await page.goto(`/explore/opinions?work_ids=${work}&authors=${author}&topic_ids=${topic}&year_min=2000&languages=zh`);
  await expect(page.getByRole("button", { name: "检索原文", exact: true })).toBeDisabled();
  await page.getByRole("textbox", { name: "你的研究问题" }).fill("合成研究问题");
  await page.getByRole("button", { name: "检索原文", exact: true }).click();
  await expect(page).toHaveURL(/\/explore\/evidence\?/);
  const params = new URL(page.url()).searchParams;
  expect(params.get("work_ids")).toBe(work);
  expect(params.get("authors")).toBe(author);
  expect(params.get("topic_ids")).toBe(topic);
  expect(params.get("year_min")).toBe("2000");
  expect(params.get("languages")).toBe("zh");
});

test("replacing one scope keeps earlier selections from the other scope", async ({ page }) => {
  await setup(page);
  await page.goto(`/explore/opinions?work_ids=${work}`);
  await page.getByRole("radio", { name: /特定主题/ }).click();
  const dialog = page.getByRole("dialog", { name: "选择检索范围", exact: true });
  await dialog.getByRole("checkbox", { name: /合成主题/ }).check();
  await dialog.getByRole("button", { name: /确认范围/ }).click();
  await page.getByRole("radio", { name: /特定学者/ }).click();
  await dialog.getByRole("checkbox", { name: /合成学者/ }).check();
  await dialog.getByRole("button", { name: /确认范围/ }).click();
  await page.getByRole("textbox", { name: "你的研究问题" }).fill("合成复合范围问题");
  await page.getByRole("button", { name: "检索原文", exact: true }).click();
  await expect(page).toHaveURL(/\/explore\/evidence\?/);
  const params = new URL(page.url()).searchParams;
  expect(params.get("work_ids")).toBe(work);
  expect(params.get("topic")).toBe(topic);
  expect(params.get("scholar")).toBe(person);
});

test("mobile range selection can cancel without changing the inherited scope", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/explore/opinions?authors=${author}`);
  await page.getByRole("button", { name: "特定学者", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择检索范围", exact: true });
  await dialog.getByRole("radio", { name: /全部文献/ }).check();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("textbox", { name: "你的研究问题" }).fill("合成移动问题");
  await page.getByRole("button", { name: "检索原文", exact: true }).click();
  await expect(page).toHaveURL(/\/explore\/evidence\?/);
  expect(new URL(page.url()).searchParams.get("authors")).toBe(author);
});

test("history 401 is shown once without replaying the private read", async ({ page }) => {
  await setup(page, true);
  let historyReads = 0, refreshes = 0;
  await page.route("**/api/auth/refresh/", route => { refreshes += 1; return route.fulfill({ status: 401, json: {} }); });
  await page.route("**/api/reading/search-records/**", route => {
    historyReads += 1;
    expect(route.request().headers()["x-reader-owner"]).toBe("77");
    return route.fulfill({ status: 401, json: { detail: "合成历史登录失效" } });
  });
  await page.goto("/explore/opinions");
  await expect(page.getByRole("alert").filter({ hasText: "合成历史登录失效" })).toBeVisible();
  expect(historyReads).toBe(1);
  expect(refreshes).toBe(0);
});

test("wrong-owner history is discarded instead of being rendered", async ({ page }) => {
  await setup(page, true);
  await page.route("**/api/reading/search-records/**", route => route.fulfill({ json: { owner_id: "88", recording_enabled: false,
    count: 1, page: 1, page_size: 3, results: [{ id: work, query: "不得显示的合成其他账户记录", filters: {}, created_at: "2026-10-19T00:00:00Z" }], notice: "" } }));
  await page.goto("/explore/opinions");
  await expect(page.getByRole("alert").filter({ hasText: "登录账户已变化" })).toBeVisible();
  await expect(page.getByText("不得显示的合成其他账户记录")).toHaveCount(0);
});
