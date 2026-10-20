import { expect, test, type Page } from "@playwright/test";

// Synthetic browser contracts for later unified acceptance. Not production data.
const ids = Array.from({ length: 8 }, (_, index) => `10000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`);
const passage = (id: string, title: string, page: number) => ({ id, excerpt: `合成原文 ${page}，仅用于回归。`, work: { id: ids[6], title, slug: "synthetic-evidence" }, authors: ["合成作者"],
  asset_id: ids[4], edition_id: ids[5], document_revision_id: ids[7], pdf_page: page, printed_page: String(page + 10), source_kind: "native", locator_precision: "page", match_basis: ["原文命中"],
  reader_url: `/reader/${ids[4]}?page=${page}`, section_title: "合成章节", bibliography: { cover_url: "", original_title: "Synthetic title", publisher: "合成出版社", publication_year: 2024, language: "zh-CN", page_count: 20, version_label: "合成版本", document_type: "book" }, attribution: { status: "unknown", label: "待人工核对", notice: "合成归属说明" } });
const rows = [passage(ids[0], "合成第一条证据", 1), passage(ids[1], "合成第二条证据", 2)];
const payload = { id: ids[2], query: "合成问题", access_token: "synthetic-token", status: "completed", generation: 3, expansion_count: 0, mode: "standard", count: 2,
  passages: rows, entities: [], curation: [], warnings: [], coverage_summary: {}, completed_channels: [], channels: {}, next_cursor: null, can_expand: true, can_retry: false, source_changed: false };

async function setup(page: Page, result = payload) {
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: { detail: "Synthetic guest" } }));
  await page.route("**/api/catalog/search/**", route => route.fulfill({ json: { facets: { document_types: [{ value: "book", label: "图书", count: 2 }], theories: [], languages: [], authors: [], topics: [], concepts: [] } } }));
  await page.route("**/api/catalog/discovery-search/**", route => route.fulfill({ json: result }));
}

test("document states distinguish missing returned material and inaccessible text on mobile", async ({ page }) => {
  const document = { edition_id: ids[5], work_id: ids[6], title: "合成文献状态", authors: ["合成作者"], url: "/works/synthetic-evidence",
    bibliography: rows[0].bibliography, material_count: 0, available_versions: [{ id: ids[5], label: "合成公开版本", url: "/works/synthetic-evidence" }] };
  await setup(page);
  await page.route("**/api/catalog/discovery-search/**", route => route.fulfill({ json: { ...payload, documents: { items: [
    { ...document, status: "no_returned" }, { ...document, edition_id: ids[4], status: "unreadable", title: "合成不可读文献" }], tracked: 2, counts: {}, excluded_count: 0, truncated: false, notice: "合成状态说明" } } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore/evidence?q=合成文献状态");
  const panel = page.getByRole("region", { name: "本次文献处理状态" });
  await expect(panel.getByText("本轮未返回直接材料", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: /暂不可读/ }).click();
  await expect(panel.getByRole("heading", { name: "合成文献状态", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("heading", { name: "合成不可读文献" })).toBeVisible();
  await panel.getByRole("button", { name: "查看公开版本" }).click();
  await expect(page.getByRole("dialog", { name: "已公开的出版版本" }).getByRole("link", { name: "合成公开版本" })).toHaveAttribute("href", "/works/synthetic-evidence");
});

test("document removal carries the observed generation and clears only the removed evidence", async ({ page }) => {
  await setup(page);
  let removed = false;
  const document = { edition_id: ids[5], work_id: ids[6], title: "合成待移除文献", authors: [], url: "", status: "completed", bibliography: null, material_count: 2, available_versions: [] };
  await page.route("**/api/catalog/discovery-search/**", route => {
    if (route.request().url().includes("remove-document")) {
      expect(route.request().postDataJSON()).toEqual({ edition_id: ids[5], expected_generation: 3 });
      expect(route.request().headers()["x-discovery-token"]).toBe("synthetic-token");
      removed = true;
    }
    return route.fulfill({ json: { ...payload, passages: removed ? [] : rows, count: removed ? 0 : 2, source_changed: removed,
      documents: { items: removed ? [] : [document], counts: {}, tracked: removed ? 0 : 1, truncated: false, excluded_count: removed ? 1 : 0, notice: "合成移除说明" } } });
  });
  await page.goto("/explore/evidence?q=合成移除文献");
  await page.getByRole("button", { name: "从本次检索移除" }).click();
  await expect(page.locator(`#material-${ids[0]}`)).toHaveCount(0);
  await expect(page.getByText("已移除 1 个版本", { exact: true })).toBeVisible();
});

test("selecting a candidate updates the source inspector and preserves the return location", async ({ page }) => {
  await setup(page);
  await page.goto("/explore/evidence?q=合成问题&topic=synthetic-topic");
  await page.getByRole("button", { name: "查看证据摘要：合成第二条证据", exact: true }).click();
  const summary = page.getByRole("complementary", { name: "证据摘要" });
  await expect(summary.getByRole("heading", { name: "合成第二条证据" })).toBeVisible();
  const reader = summary.getByRole("link", { name: "阅读原文" });
  const url = new URL((await reader.getAttribute("href"))!, "https://synthetic.invalid");
  expect(url.searchParams.get("page")).toBe("2");
  expect(url.searchParams.get("return_to")).toContain("topic=synthetic-topic");
  expect(url.searchParams.get("return_to")).toContain(`#material-${ids[1]}`);
  await expect(summary.getByText("待人工核对", { exact: true })).toBeVisible();
});

test("context is read from the server and exposes only that session's same-book candidates", async ({ page }) => {
  await setup(page);
  await page.route("**/api/catalog/discovery-search/*/context/**", route => route.fulfill({ json: { result_id: ids[0], source: rows[0], excerpt: rows[0].excerpt, before: "", after: "", reader_url: rows[0].reader_url, locator_precision: "page", blocks: [{ role: "hit", text: "合成上下文原文", pdf_page: 1 }], same_work_count: 2, same_work_results: rows } }));
  await page.goto("/explore/evidence?q=合成问题");
  await page.locator(`#material-${ids[0]}`).getByRole("button", { name: "查看上下文" }).click();
  const context = page.getByRole("dialog", { name: "原文上下文" });
  await expect(context.getByText("合成上下文原文", { exact: true })).toBeVisible();
  await context.getByRole("button", { name: "查看同书更多段落（2）" }).click();
  await expect(context.getByRole("button", { name: /PDF 第 2 页/ })).toBeEnabled();
  await context.getByRole("button", { name: "关闭上下文" }).click();
  await expect(page.locator(`#material-${ids[0]}`)).toBeVisible();
});

test("failed expansion retains previously resolved evidence", async ({ page }) => {
  await setup(page);
  await page.route("**/api/catalog/discovery-search/*/expand/", route => route.fulfill({ status: 503, json: { detail: "合成追加失败" } }));
  await page.goto("/explore/evidence?q=合成问题");
  await page.getByRole("button", { name: "扩大研究范围", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("合成追加失败");
  await expect(page.locator(`#material-${ids[0]}`)).toBeVisible();
  await expect(page.locator(`#material-${ids[1]}`)).toBeVisible();
});

test("mobile source details and filter controls use separate closable dialogs", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore/evidence?q=合成问题");
  await page.getByRole("button", { name: "查看证据摘要：合成第一条证据" }).click();
  await expect(page.getByRole("dialog", { name: "证据摘要" })).toBeVisible();
  await page.getByRole("dialog", { name: "证据摘要" }).getByRole("button", { name: "关闭证据摘要" }).click();
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  const filters = page.getByRole("dialog", { name: "筛选原文材料" });
  await expect(filters.getByRole("checkbox", { name: /图书/ })).toBeVisible();
  await filters.getByRole("button", { name: "关闭筛选" }).click();
  await expect(filters).not.toBeVisible();
});

test("source withdrawal refresh removes both the result and stale source summary", async ({ page }) => {
  await setup(page);
  await page.goto("/explore/evidence?q=合成问题");
  await expect(page.locator(`#material-${ids[0]}`)).toBeVisible();
  await page.route("**/api/catalog/discovery-search/*/?**", route => route.fulfill({ json: { ...payload, passages: [], count: 0, source_changed: true, can_expand: false } }));
  await page.getByRole("button", { name: "刷新本次结果" }).click();
  await expect(page.locator(`#material-${ids[0]}`)).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "证据摘要" }).getByText("合成第一条证据")).toHaveCount(0);
});

test("year sorting uses the existing session and server ordering", async ({ page }) => {
  await setup(page);
  let readSort = "";
  let created = 0;
  await page.route("**/api/catalog/discovery-search/**", route => {
    if (route.request().method() === "POST") created += 1;
    readSort = new URL(route.request().url()).searchParams.get("sort") || "relevance";
    return route.fulfill({ json: { ...payload, sort: readSort, passages: readSort === "year_asc" ? [...rows].reverse() : rows } });
  });
  await page.goto("/explore/evidence?q=合成问题");
  await page.getByRole("combobox", { name: "结果排序" }).selectOption("year_asc");
  await expect(page.locator("article[id^='material-']").first()).toHaveAttribute("id", `material-${ids[1]}`);
  expect(readSort).toBe("year_asc");
  expect(created).toBe(1);
});

test("canceled search resumes with its generation and marks only server-declared additions", async ({ page }) => {
  await setup(page);
  let resumed = false;
  await page.route("**/api/catalog/discovery-search/**", async route => {
    if (route.request().url().endsWith("/retry/")) {
      expect(route.request().postDataJSON().expected_generation).toBe(3);
      resumed = true;
    }
    return route.fulfill({ json: { ...payload, status: resumed ? "completed" : "canceled", can_retry: !resumed,
      added_count: resumed ? 1 : 0, passages: rows.map((row, index) => ({ ...row, is_new: resumed && index === 1 })) } });
  });
  await page.goto("/explore/evidence?q=合成问题");
  await page.getByRole("button", { name: "基于保留材料继续检索" }).click();
  await expect(page.locator(`#material-${ids[1]}`).getByText("本轮新增", { exact: true })).toBeVisible();
  await expect(page.locator(`#material-${ids[0]}`).getByText("本轮新增", { exact: true })).toHaveCount(0);
});

test("restarting creates a new session only after the explicit action", async ({ page }) => {
  await setup(page);
  let created = 0;
  await page.route("**/api/catalog/discovery-search/**", route => {
    if (route.request().method() === "POST") created += 1;
    return route.fulfill({ json: { ...payload, id: created > 1 ? ids[3] : ids[2] } });
  });
  await page.goto("/explore/evidence?q=合成问题");
  await expect(page.locator(`#material-${ids[0]}`)).toBeVisible();
  expect(created).toBe(1);
  await page.getByRole("button", { name: "重新开始检索", exact: true }).click();
  await expect.poll(() => created).toBe(2);
});
