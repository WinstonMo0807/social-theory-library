import { expect, test, type Page } from "@playwright/test";

// Synthetic, non-production records. These cases are written for unified acceptance, not run during development.
const workId = "11111111-1111-4111-8111-111111111111";
const editionId = "22222222-2222-4222-8222-222222222222";
const assetId = "33333333-3333-4333-8333-333333333333";
const edition = { id: editionId, public_slug: "synthetic-catalog-work", version_label: "合成测试版本", publication_year: 2024, publisher: "合成测试出版信息", contributors: [{ role: "author", person: { preferred_name: "合成作者" } }], readable_asset: null };
const work = { id: workId, document_type: "book", title: "合成目录测试文献", subtitle: "", abstract: "仅用于界面回归的合成书目。", language: "zh-CN", cover: "", theories: [], topics: [], edition, editions: [edition], matched_edition_ids: [editionId] };
const payload = {
  counts: { works: 1, books: 1, articles: 0, theses: 0, reports: 0, scholars: 0, topics: 0, theories: 0, passages: 0 },
  works: [work], scholars: [], topics: [], theories: [], passages: [],
  facets: { document_types: [{ value: "book", label: "图书", count: 1 }], authors: [], years: [], languages: [{ value: "zh-CN", label: "中文", count: 1 }], access: [{ value: "metadata", label: "仅书目信息", count: 1 }], theories: [], topics: [], concepts: [], year_histogram: [{ year: 2024, count: 1 }] },
  pagination: { page: 1, page_size: 24, total: 1, total_pages: 1 },
};

async function setup(page: Page) {
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: { detail: "Synthetic anonymous session" } }));
  await page.route("**/api/catalog/search/**", route => route.fulfill({ json: payload }));
}

test("catalog entry sends its public catalog scope and shows metadata without invented file controls", async ({ page }) => {
  await setup(page);
  const request = page.waitForRequest(request => request.url().includes("/api/catalog/search/"));
  await page.goto("/explore/original?q=合成");
  const query = new URL((await request).url()).searchParams;
  expect(query.get("scope")).toBe("catalog");
  expect(query.get("context")).toBe("global");
  const card = page.locator(".stl4-catalog-result");
  await expect(card.getByText("仅书目信息")).toBeVisible();
  await expect(card.getByRole("button", { name: "下载 PDF", exact: true })).toHaveCount(0);
  await expect(card.getByRole("link", { name: "在线阅读", exact: true })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "收藏", exact: true })).toBeVisible();
});

test("one work expands its actual editions without inventing a file for a metadata version", async ({ page }) => {
  await setup(page);
  await page.route("**/api/catalog/search/**", route => route.fulfill({ json: { ...payload, works: [{ ...work, editions: [edition, { ...edition, id: "44444444-4444-4444-8444-444444444444", public_slug: "synthetic-second-edition", publication_year: 2025, readable_asset: { id: assetId, page_count: 2 } }] }] } }));
  await page.goto("/explore/original");
  await page.getByText("可查看的版本（2）", { exact: true }).click();
  const table = page.getByRole("table", { name: "合成目录测试文献的出版版本" });
  await expect(table.getByRole("link", { name: "阅读", exact: true })).toHaveAttribute("href", `/reader/${assetId}`);
  await expect(table.getByRole("link", { name: "查看书目", exact: true })).toHaveAttribute("href", "/works/synthetic-catalog-work");
  await expect(page.locator(".stl4-catalog-result")).toHaveCount(1);
});

test("failure retains query and filters, retry reads again without a simulated success", async ({ page }) => {
  await setup(page);
  let attempts = 0;
  await page.route("**/api/catalog/search/**", route => ++attempts === 1 ? route.fulfill({ status: 503, json: { detail: "Synthetic service outage" } }) : route.fulfill({ json: payload }));
  await page.goto("/explore/original?q=合成&language=zh-CN");
  await expect(page.getByRole("heading", { name: "连接服务时遇到问题" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "检索馆藏" })).toHaveValue("合成");
  expect(new URL(page.url()).searchParams.get("language")).toBe("zh-CN");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".stl4-catalog-result")).toHaveCount(1);
  expect(attempts).toBe(2);
});

test("empty result clears filters while preserving the entered query", async ({ page }) => {
  await setup(page);
  await page.route("**/api/catalog/search/**", route => route.fulfill({ json: { ...payload, works: [], pagination: { ...payload.pagination, total: 0 } } }));
  await page.goto("/explore/original?q=合成&language=zh-CN&year_min=2024");
  await expect(page.getByRole("heading", { name: "未找到与“合成”相关的文献" })).toBeVisible();
  await page.getByRole("link", { name: "清除全部筛选", exact: true }).click();
  await expect(page).toHaveURL(/q=/);
  expect(new URL(page.url()).searchParams.get("language")).toBeNull();
  expect(new URL(page.url()).searchParams.get("year_min")).toBeNull();
  expect(new URL(page.url()).searchParams.get("q")).toBe("合成");
});

test("mobile filters are a focus-contained panel, reject reversed years and preserve unapplied query", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore/original?q=合成");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "筛选条件" });
  await dialog.getByRole("spinbutton", { name: "起始年份" }).fill("2025");
  await dialog.getByRole("spinbutton", { name: "截止年份" }).fill("2020");
  await dialog.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("起始年份不能晚于截止年份。");
  await dialog.getByRole("spinbutton", { name: "截止年份" }).fill("2026");
  await dialog.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(new URL(page.url()).searchParams.get("year_min")).toBe("2025");
  expect(new URL(page.url()).searchParams.get("q")).toBe("合成");
});

test("loading retains the filter structure without claiming zero results", async ({ page }) => {
  await setup(page);
  let complete!: () => void;
  const pending = new Promise<void>(resolve => { complete = resolve; });
  await page.route("**/api/catalog/search/**", async route => { await pending; await route.fulfill({ json: payload }); });
  await page.goto("/explore/original?q=合成", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "正在检索文献…" })).toBeVisible();
  await expect(page.locator(".stl4-catalog-toolbar")).not.toContainText("共 0 条");
  complete();
  await expect(page.locator(".stl4-catalog-result")).toHaveCount(1);
});

test("anonymous save keeps the full public search location as the login return", async ({ page }) => {
  await setup(page);
  await page.goto("/explore/original?q=合成&language=zh-CN");
  await page.locator(".stl4-catalog-result").getByRole("button", { name: "收藏", exact: true }).click();
  await expect(page).toHaveURL(/\/login\?next=/);
  expect(new URL(page.url()).searchParams.get("next")).toContain("language=zh-CN");
});
