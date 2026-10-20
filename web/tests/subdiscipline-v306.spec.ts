import { expect, test, type Page } from "@playwright/test";
import type { Subdiscipline, SubdisciplineListItem } from "../lib/api/taxonomy.types";

// Final acceptance only. SSR and browser share the real disposable API seeded
// by seed_subdisciplines() after actual parallel PDF extraction/publication.
// No business API payload, source text, quality value or page HTML is mocked.
const api = "http://127.0.0.1:8105/api";
const base = "/subdisciplines";
const main = `${base}/e2e-subdiscipline-01`;
const discipline = "e2e-subdiscipline-discipline";
const featured = (page: Page) => page.getByRole("region", { name: "精选子学科", exact: true });
const all = (page: Page) => page.getByRole("region", { name: "全部子学科", exact: true });
const result = (page: Page) => page.getByRole("region", { name: "子学科搜索结果", exact: true });
const detail = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const cards = (region: ReturnType<typeof all>) => region.locator('a[href^="/subdisciplines/e2e-subdiscipline-"]');

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use only the disposable loopback acceptance configuration.").toBeTruthy();
  expect(new URL(baseURL!).origin).toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
});

async function payload(page: Page, slug = "e2e-subdiscipline-01") {
  const response = await page.request.get(`${api}/catalog/subdisciplines/${slug}/`);
  expect(response.status(), "Run the real isolated subdiscipline seed before acceptance.").toBe(200);
  return await response.json() as Subdiscipline;
}

test("PDF50 desktop uses real curated three-column cards and a six-column public directory", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/subdisciplines/?featured=true&discipline=${discipline}`);
  expect(response.status()).toBe(200);
  const list = await response.json() as { results: SubdisciplineListItem[] };
  expect(list.results).toHaveLength(3);
  for (const row of list.results) {
    expect(row.featured).toBe(true);
    expect(row).not.toHaveProperty("core_works");
    expect(row).not.toHaveProperty("sources");
    expect(row).not.toHaveProperty("works");
    expect(row).not.toHaveProperty("theories");
    expect(row.discipline).not.toHaveProperty("work_count");
  }
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`${base}?discipline=${discipline}`);
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1, name: "子学科", exact: true })).toBeVisible();
  await expect(page.locator('picture img[src="/visual/stl4/subdisciplines/hero.webp"]')).toBeVisible();
  await expect(cards(featured(page))).toHaveCount(3);
  await expect(cards(all(page))).toHaveCount(24);
  const curated = await cards(featured(page)).evaluateAll(links => links.map(link => {
    const { x, y, width } = link.getBoundingClientRect();
    return { x, y, width };
  }));
  expect(Math.max(...curated.map(row => row.y)) - Math.min(...curated.map(row => row.y))).toBeLessThan(2);
  expect(curated[1].x).toBeGreaterThan(curated[0].x + curated[0].width);
  const firstRow = await cards(all(page)).evaluateAll(links => links.slice(0, 7).map(link => link.getBoundingClientRect().y));
  expect(Math.max(...firstRow.slice(0, 6)) - Math.min(...firstRow.slice(0, 6))).toBeLessThan(2);
  expect(firstRow[6]).toBeGreaterThan(firstRow[0]);
  await expect(page.getByText(/E2E子学科未公开条目|理论传统总数|馆藏文献总数/)).toHaveCount(0);
});

test("PDF50 mobile preserves full-width featured cards and compact directory rows", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}?discipline=${discipline}`);
  const selected = cards(featured(page));
  await expect(selected).toHaveCount(3);
  const boxes = await selected.evaluateAll(links => links.map(link => {
    const { x, y, width, height } = link.getBoundingClientRect();
    return { x, y, width, height };
  }));
  expect(boxes[1].y).toBeGreaterThanOrEqual(boxes[0].y + boxes[0].height);
  expect(Math.abs(boxes[1].x - boxes[0].x)).toBeLessThan(1);
  const compact = cards(all(page)).first();
  const row = await compact.boundingBox();
  expect(row).not.toBeNull();
  expect(row!.width / row!.height).toBeGreaterThan(3);
  expect(await page.locator("body").evaluate(element => element.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});

for (const query of ["E2E子学科01", "E2E子学科关联概念", "E2E子学科关联主题"]) {
  test(`directory search resolves actual published associations for ${query}`, async ({ page }) => {
    await page.goto(base);
    await page.getByRole("searchbox", { name: "子学科名称、概念或主题", exact: true }).fill(query);
    await page.getByRole("search", { name: "搜索子学科", exact: true }).getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`q=${encodeURIComponent(query)}`));
    await expect(cards(result(page))).toHaveCount(1);
    await expect(cards(result(page)).first()).toHaveAttribute("href", main);
    await cards(result(page)).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "E2E子学科01", exact: true })).toBeVisible();
  });
}

test("a real non-featured result does not get promoted to a featured card", async ({ page }) => {
  await page.goto(`${base}?q=${encodeURIComponent("E2E子学科04")}`);
  await expect(featured(page)).toContainText("当前筛选下没有已发布的精选子学科");
  await expect(cards(featured(page))).toHaveCount(0);
  await expect(cards(result(page))).toHaveCount(1);
  await expect(cards(result(page)).first()).toHaveAttribute("href", `${base}/e2e-subdiscipline-04`);
});

test("an empty public discipline keeps distinct honest empty states and can clear its filter", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/subdisciplines/?discipline=e2e-subdiscipline-empty-discipline`);
  expect(response.status()).toBe(200);
  expect((await response.json() as { count: number }).count).toBe(0);
  await page.goto(`${base}?discipline=e2e-subdiscipline-empty-discipline`);
  await expect(featured(page)).toContainText("当前筛选下没有已发布的精选子学科");
  await expect(all(page)).toContainText("没有找到符合条件的公开子学科");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("link", { name: "清除筛选", exact: true }).click();
  await expect(page).toHaveURL(/\/subdisciplines$/);
  await expect(cards(featured(page))).toHaveCount(3);
});

test("all-result pagination retains the actual query and independently keeps curated cards", async ({ page }) => {
  await page.goto(`${base}?q=${encodeURIComponent("E2E子学科")}&discipline=${discipline}`);
  const next = result(page).getByRole("link", { name: "下一页", exact: true });
  await expect(next).toHaveAttribute("href", new RegExp(`discipline=${discipline}`));
  await next.click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("searchbox", { name: "子学科名称、概念或主题" })).toHaveValue("E2E子学科");
  await expect(cards(result(page))).toHaveCount(5);
  await expect(cards(featured(page))).toHaveCount(3);
  await expect(result(page).getByRole("link", { name: "上一页", exact: true })).toBeVisible();
});

for (const [parameter, failed, healthy] of [
  ["page", "全部子学科", "精选子学科"],
  ["featured_page", "精选子学科", "全部子学科"],
] as const) {
  test(`a real out-of-range ${parameter} failure is not silently rendered as empty content`, async ({ page }) => {
    await page.goto(`${base}?discipline=${discipline}&${parameter}=999999`);
    const unavailable = detail(page, failed);
    await expect(unavailable.getByRole("alert")).toBeVisible();
    await expect(unavailable.getByRole("link", { name: /重新载入/ })).toBeVisible();
    await expect(cards(detail(page, healthy))).not.toHaveCount(0);
    await expect(unavailable.getByText(/尚无已发布|没有找到符合条件/)).toHaveCount(0);
  });
}

test("PDF51 reads real source identities and keeps book-only works separate from readable editions", async ({ page }) => {
  const item = await payload(page);
  expect(item.core_works).toHaveLength(2);
  expect(item.sources).toHaveLength(2);
  expect(item.works_pagination).toEqual({ count: 2, page: 1, total_pages: 1 });
  await page.goto(main);
  await expect(page.getByRole("main")).toHaveCount(1);
  for (const heading of ["关键问题", "相关理论", "代表性学者", "核心文献", "相关主题", "延伸阅读"]) {
    await expect(page.getByRole("heading", { level: 2, name: heading, exact: true })).toBeVisible();
  }
  const section = detail(page, "核心文献");
  await expect(section).toContainText("共 2 部文献 · 当前第 1—2 部");
  for (const work of item.core_works) {
    const card = section.locator("article").filter({ has: page.getByRole("heading", { name: work.title, exact: true }) });
    await expect(card.getByRole("link", { name: "查看版本", exact: true })).toHaveAttribute("href", work.detail_href!);
    if (work.reader_href) {
      expect(work.edition_id).toBeTruthy();
      expect(work.document_revision_id).toBeTruthy();
      expect(work.reader_href).toContain(`revision=${work.document_revision_id}`);
      await expect(card.getByRole("link", { name: "阅读原文", exact: true })).toHaveAttribute("href", work.reader_href);
    } else {
      await expect(card).toContainText("这一版本暂无可读原文");
      await expect(card.getByRole("link", { name: "阅读原文", exact: true })).toHaveCount(0);
    }
  }
});

test("questions only link to confirmed research problems and section navigation uses real anchors", async ({ page }) => {
  await page.goto(main);
  const questions = detail(page, "关键问题");
  await expect(questions.getByRole("heading", { name: "E2E只有编辑说明的问题", exact: true })).toBeVisible();
  await expect(questions.getByRole("link", { name: /E2E只有编辑说明的问题/ })).toHaveCount(0);
  await expect(questions.getByRole("link", { name: /E2E子学科关联问题/ })).toHaveAttribute("href", "/theories/nodes/e2e-subdiscipline-problem");
  await page.getByRole("navigation", { name: "子学科内容", exact: true }).getByRole("link", { name: "学者", exact: true }).click();
  await expect(page).toHaveURL(/#scholars$/);
  await expect(detail(page, "代表性学者")).toBeInViewport();
});

test("representative people without exact evidence show no false source link or replacement portrait", async ({ page }) => {
  const item = await payload(page);
  expect(item.scholars).toHaveLength(3);
  expect(item.scholars.every(person => person.source_href === null && person.portrait_url === "")).toBeTruthy();
  await page.goto(main);
  const people = detail(page, "代表性学者");
  await expect(people.getByRole("link", { name: "查看来源", exact: true })).toHaveCount(0);
  await expect(people.getByText("原文来源未提供", { exact: true })).toHaveCount(3);
  await expect(people.locator("img")).toHaveCount(0);
  for (const person of item.scholars) {
    await expect(people.getByRole("link", { name: person.name, exact: true })).toHaveAttribute("href", person.href);
  }
  await people.locator("summary").first().focus();
  await page.keyboard.press("Enter");
  await expect(people.getByText(item.scholars[0].source_label, { exact: true }).first()).toBeVisible();
});

test("theories, topics, hierarchy and reading paths keep their actual published destinations", async ({ page }) => {
  const item = await payload(page);
  await page.goto(main);
  for (const theory of item.theories) {
    await expect(detail(page, "相关理论").getByRole("link", { name: theory.name, exact: true })).toHaveAttribute("href", theory.href);
  }
  await expect(detail(page, "相关主题").getByRole("link", { name: "E2E子学科关联主题", exact: true })).toHaveAttribute("href", "/topics/e2e-subdiscipline-topic");
  const paths = detail(page, "延伸阅读");
  await expect(paths.getByRole("link")).toHaveCount(1);
  await expect(paths.getByRole("link")).toHaveAttribute("href", "/theories/reading-paths/e2e-subdiscipline-path");
  await expect(page.getByRole("link", { name: "下级子学科 · E2E子学科已确认下级", exact: true })).toHaveAttribute("href", `${base}/e2e-subdiscipline-30`);
  await expect(page.getByText(/E2E子学科未公开概念|E2E子学科未公开主题|E2E子学科未公开路径/)).toHaveCount(0);
});

test("source disclosure opens by keyboard and keeps its own exact edition, page and revision", async ({ page }) => {
  const item = await payload(page);
  await page.goto(main);
  const sources = page.locator("details#sources");
  await sources.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(sources).toHaveAttribute("open", "");
  for (const source of item.sources) {
    expect(source.reader_href).toBe(`/reader/${source.asset_id}?page=${source.pdf_page}&revision=${source.document_revision_id}`);
    expect(source.quote).toContain("PARALLEL");
    const excerpt = sources.locator("blockquote").filter({ hasText: source.quote });
    await expect(excerpt.getByRole("link", { name: "核对原文", exact: true })).toHaveAttribute("href", source.reader_href);
    await expect(excerpt).toContainText(source.edition_label);
    const response = await page.request.get(`${api}/catalog/assets/${source.asset_id}/manifest/`);
    expect(response.status(), "The real current public source must remain anonymously readable.").toBe(200);
    expect((await response.json() as { document_revision_id: string }).document_revision_id).toBe(source.document_revision_id);
  }
});

test("hidden parent and discipline stay null without breaking the published child page", async ({ page }) => {
  const item = await payload(page, "e2e-subdiscipline-28");
  expect(item.discipline).toBeNull();
  expect(item.parent).toBeNull();
  await page.goto(`${base}/e2e-subdiscipline-28`);
  await expect(page.getByRole("heading", { level: 1, name: item.name, exact: true })).toBeVisible();
  await expect(page.getByText(/E2E子学科未公开条目|E2E子学科未公开学科/)).toHaveCount(0);
  await expect(page.getByRole("main")).toHaveCount(1);
});

test("an empty published detail has honest per-section states and never borrows atlas scholars or books", async ({ page }) => {
  await page.goto(`${base}/e2e-subdiscipline-29`);
  for (const [section, text] of [
    ["关键问题", "尚无已确认并公开的关键问题"], ["相关理论", "尚无已确认并公开的相关理论"],
    ["代表性学者", "尚无已确认并公开的代表性学者"], ["核心文献", "尚无与本子学科建立公开关联的核心文献"],
    ["相关主题", "尚无已确认并公开的相关主题"], ["延伸阅读", "尚无包含本子学科已确认条目的公开阅读路径"],
  ]) await expect(detail(page, section)).toContainText(text);
  await expect(page.getByRole("link", { name: /阅读原文|查看来源|查看阅读路径/ })).toHaveCount(0);
});

test("draft-only entities stay inaccessible rather than becoming a generic detail failure", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/subdisciplines/e2e-subdiscipline-31/`);
  expect(response.status()).toBe(404);
  await page.goto(`${base}/e2e-subdiscipline-31`);
  await expect(page.getByRole("heading", { name: "E2E子学科未公开条目", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "子学科资料暂时无法读取", exact: true })).toHaveCount(0);
});

for (const [worksPage, status] of [["999999", 404], ["-1", 400]] as const) {
  test(`real works_page=${worksPage} failure stays distinct from a missing subdiscipline`, async ({ page }) => {
    const response = await page.request.get(`${api}/catalog/subdisciplines/e2e-subdiscipline-01/?works_page=${worksPage}`);
    expect(response.status()).toBe(status);
    await page.goto(`${main}?works_page=${worksPage}`);
    await expect(page.getByRole("heading", { level: 1, name: "核心文献页码不可用", exact: true })).toBeVisible();
    await expect(page.getByRole("alert")).toBeVisible();
    const restart = page.getByRole("link", { name: "返回核心文献第一页", exact: true });
    await expect(restart).toHaveAttribute("href", `${main}#works`);
    await restart.click();
    await expect(page.getByRole("heading", { level: 1, name: "E2E子学科01", exact: true })).toBeVisible();
    await expect(detail(page, "核心文献")).toContainText("共 2 部文献 · 当前第 1—2 部");
    await expect(detail(page, "核心文献")).toBeInViewport();
  });
}
