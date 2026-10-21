import { expect, test, type Page } from "@playwright/test";
import type { TimelineEventDetail, TimelinePage } from "../lib/api/timeline.types";

// Final acceptance definitions only: SSR and browser requests use the real
// disposable API. No event/source response is fabricated or modified here.
const api = "http://127.0.0.1:8105/api";
const path = "/theories/timeline";
const fixtureId = (number: number) => `56000000-0000-4000-8000-${String(number).padStart(12, "0")}`;
const ids = {
  publication: fixtureId(101), translation: fixtureId(102), concept: fixtureId(103),
  range: fixtureId(104), approximate: fixtureId(105), undated: fixtureId(106),
  draft: fixtureId(107), legacy: fixtureId(108), hiddenTargets: fixtureId(109),
  scanSource: fixtureId(110), endOnly: fixtureId(111), pageLast: fixtureId(225),
};
const sources = {
  leftEdition: "41300000-0000-4000-8000-000000000101",
  leftAsset: "41300000-0000-4000-8000-000000000103",
  rightEdition: "41300000-0000-4000-8000-000000000201",
  rightAsset: "41300000-0000-4000-8000-000000000203",
  scanEdition: "41300000-0000-4000-8000-000000000301",
  scanAsset: "41300000-0000-4000-8000-000000000303",
};
type Parameters = Record<string, string | string[]>;

function query(parameters: Parameters = {}) {
  const result = new URLSearchParams({ q: "TL56CASE" });
  for (const [key, value] of Object.entries(parameters)) {
    result.delete(key);
    for (const item of Array.isArray(value) ? value : [value]) result.append(key, item);
  }
  return result.toString();
}

async function timeline(page: Page, parameters: Parameters = {}): Promise<TimelinePage> {
  const response = await page.request.get(`${api}/catalog/theory-system/timeline/?${query(parameters)}`);
  expect(response.status(), `The real isolated timeline endpoint must be available: ${await response.text()}`).toBe(200);
  return response.json();
}

async function event(page: Page, id: string): Promise<TimelineEventDetail> {
  const response = await page.request.get(`${api}/catalog/theory-system/timeline/${id}/`);
  expect(response.status(), "seed_timeline(actor) must run after the actual parallel PDF publication.").toBe(200);
  return response.json();
}

test.beforeEach(async ({ baseURL, page }) => {
  expect(baseURL, "Use the disposable local acceptance configuration.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
});

test("real public events and year groups exclude the unpublished event without hiding independent approved rows", async ({ page }) => {
  const data = await timeline(page);
  expect(data.count, "Missing or incomplete TL56 fixture must fail acceptance.").toBe(10);
  expect(data.scope_count).toBe(10);
  expect(data.results.map(row => row.id)).not.toContain(ids.draft);
  expect(data.results.map(row => row.id)).toContain(ids.hiddenTargets);
  const sameYear = data.year_groups.find(group => group.year === 1867);
  expect(sameYear).toMatchObject({ year: 1867, count: 3 });
  expect(Object.fromEntries(sameYear!.event_types.map(type => [type.event_type, type.count])))
    .toEqual({ publication: 1, translation: 1, concept_proposed: 1 });
  expect(data.bounds.undated_count).toBe(1);
  const hidden = await event(page, ids.hiddenTargets);
  expect(hidden.scholars).toEqual([]);
  expect(hidden.topics).toEqual([]);
  expect(hidden.subject_status).toBe("unavailable");
  expect(hidden.subject_edition).toBeNull();
  expect(hidden.subject_work).toBeNull();
  expect(JSON.stringify(hidden)).not.toContain("TL56未公开版本不得出现");
  expect(hidden.relations.some(row => [fixtureId(24), fixtureId(43)].includes(row.id))).toBe(false);
  const draft = await page.request.get(`${api}/catalog/theory-system/timeline/${ids.draft}/`);
  expect(draft.status()).toBe(404);
  await page.goto(`${path}?${query()}`);
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "学科与概念时间线", level: 1, exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "时间线事件", exact: true })).toContainText("TL56CASE 合成原版发表");
  await expect(page.locator("main")).not.toContainText("TL56CASE 未公开事件不得出现");
  await page.goto(`${path}?${query({ focus: ids.hiddenTargets })}`);
  const detail = page.getByRole("region", { name: "所选事件详情", exact: true });
  await expect(detail).toContainText("事件版本当前不可用");
  await expect(detail).not.toContainText("合成原作·参考页 1");
  await expect(detail.getByRole("link", { name: "阅读作品", exact: true })).toHaveCount(0);
  await expect(detail.getByRole("link", { name: "查看书目信息", exact: true })).toHaveCount(0);
  await expect(page.locator('main a[href="/works/parallel-fixture-left"]')).toHaveCount(0);
});

test("subject edition and exact source remain independent, including the non-primary scanned edition", async ({ page }) => {
  for (const [id, edition, asset, sourceEdition, pdfPage] of [
    [ids.publication, sources.leftEdition, sources.rightAsset, sources.rightEdition, 2],
    [ids.translation, sources.rightEdition, sources.leftAsset, sources.leftEdition, 1],
    [ids.concept, sources.scanEdition, sources.rightAsset, sources.rightEdition, 2],
  ] as const) {
    const data = await event(page, id);
    expect(data.subject_status).toBe("available");
    expect(data.subject_edition?.edition_id).toBe(edition);
    expect(data.evidence_source).toMatchObject({ asset_id: asset, edition_id: sourceEdition, pdf_page: pdfPage });
    expect(data.evidence_source?.quote).toContain("PARALLEL");
    expect(data.evidence_source?.document_revision_id).toBeTruthy();
    const sourceUrl = new URL(data.evidence_source!.reader_href, "http://127.0.0.1:3105");
    expect(sourceUrl.pathname).toBe(`/reader/${asset}`);
    expect(sourceUrl.searchParams.get("page")).toBe(String(pdfPage));
    expect(sourceUrl.searchParams.get("revision")).toBe(data.evidence_source!.document_revision_id);
  }
  const scanEvent = await event(page, ids.concept);
  expect(scanEvent.subject_edition?.detail_href).toBe("/works/parallel-fixture-scan");
  expect(scanEvent.subject_edition?.version_label).toBe("合成扫描本·尚无文字");
  await page.goto(`${path}?${query({ focus: ids.concept })}`);
  await expect(page.locator("main")).toContainText("合成扫描本·尚无文字");
  await expect(page.locator('main a[href="/works/parallel-fixture-scan"]')).toBeVisible();
  const detail = page.getByRole("region", { name: "所选事件详情", exact: true });
  await detail.getByRole("tab", { name: "原文片段", exact: true }).click();
  await expect(detail.getByRole("link", { name: "打开来源原文", exact: true }))
    .toHaveAttribute("href", scanEvent.evidence_source!.reader_href);
  await expect(detail.getByRole("tabpanel")).toContainText("此处引用来自独立的证据版本");
  const collected = await timeline(page, { has_collection: "true" });
  expect(collected.results.map(row => row.id).sort())
    .toEqual([ids.publication, ids.translation, ids.concept, ids.scanSource].sort());
});

test("same-year selection exposes all three actual events and preserves the selected event through browser history", async ({ page }) => {
  const year = await timeline(page, { year: "1867" });
  expect(year.count).toBe(3);
  expect(year.scope_count).toBe(10);
  expect(year.results.map(row => row.id).sort()).toEqual([ids.publication, ids.translation, ids.concept].sort());
  await page.goto(`${path}?${query({ year: "1867" })}`);
  const events = page.getByRole("region", { name: "时间线事件", exact: true });
  for (const title of ["TL56CASE 合成原版发表", "TL56CASE 合成译本发表", "TL56CASE 合成概念使用"]) {
    await expect(events.getByRole("link", { name: new RegExp(title) })).toBeVisible();
  }
  await events.getByRole("link", { name: /TL56CASE 合成译本发表/ }).click();
  await expect(page).toHaveURL(new RegExp(`focus=${ids.translation}`));
  expect(new URL(page.url()).searchParams.has("year")).toBe(false);
  await page.goBack();
  await expect(page).toHaveURL(/year=1867/);
  await expect(events.getByRole("link", { name: /TL56CASE 合成概念使用/ })).toBeVisible();
});

test("overlap filtering retains a genuine uncertain range and does not move it to the queried year", async ({ page }) => {
  const data = await timeline(page, { year_from: "1910", year_to: "1910" });
  expect(data.results.map(row => row.id)).toEqual([ids.range]);
  expect(data.results[0]).toMatchObject({
    start_year: 1908, end_year: 1912, date_precision: "range", date_label: "约1910年（1908—1912）",
  });
  expect(data.year_groups).toEqual([{
    year: 1908, count: 1, event_types: [{ event_type: "concept_proposed", count: 1 }],
  }]);
  expect(data.bounds).toMatchObject({ min_year: 1908, max_year: 1912 });
  await page.goto(`${path}?${query({ year_from: "1910", year_to: "1910", focus: ids.range })}`);
  await expect(page.locator("main")).toContainText("约1910年（1908—1912）");
  await expect(page.locator("main")).toContainText("TL56CASE 合成时间范围");
});

test("undated, end-only and approximate events keep their distinct date meanings", async ({ page }) => {
  const undated = await timeline(page, { year: "undated" });
  expect(undated.results.map(row => row.id)).toEqual([ids.undated]);
  const endOnly = await timeline(page, { year: "1924" });
  expect(endOnly.results.map(row => row.id)).toEqual([ids.endOnly]);
  expect(endOnly.results[0]).toMatchObject({ start_year: null, end_year: 1924, date_precision: "unknown" });
  const approximate = await event(page, ids.approximate);
  expect(approximate).toMatchObject({ start_year: 1936, date_precision: "approximate", date_label: "约1936年" });
  expect(approximate.subject_status).toBe("unspecified");
  expect(approximate.subject_edition).toBeNull();
  await page.goto(`${path}?${query({ year: "undated" })}`);
  await expect(page.getByRole("region", { name: "时间线事件", exact: true })).toContainText("年代待考");
  await expect(page.locator("main")).not.toContainText("公元 0 年");
  await page.goto(`${path}?${query({ focus: ids.approximate })}`);
  const detail = page.getByRole("region", { name: "所选事件详情", exact: true });
  await expect(detail).toContainText("未明确事件的出版版本");
  await expect(detail).not.toContainText("事件版本当前不可用");
});

test("multiple topics and authors use OR within each group and AND across groups without duplicate events", async ({ page }) => {
  const topics = ["e2e-timeline-topic-a", "e2e-timeline-topic-b"];
  const authors = ["e2e-timeline-scholar-a", "e2e-timeline-scholar-b"];
  const data = await timeline(page, { topic: [...topics, topics[0]], author: authors, sort: "desc" });
  const unique = new Set(data.results.map(row => row.id));
  expect(unique.size).toBe(data.results.length);
  expect(unique.has(ids.concept)).toBe(true);
  expect(unique.has(ids.hiddenTargets)).toBe(false);
  expect(unique.has(ids.legacy)).toBe(false);
  const intersection = await timeline(page, { topic: topics[0], author: authors[1] });
  expect(intersection.results.map(row => row.id).sort()).toEqual([ids.concept, ids.range].sort());
  const inaccessible = await timeline(page, { topic: "e2e-timeline-topic-hidden", author: "e2e-timeline-scholar-hidden" });
  expect(inaccessible.count).toBe(0);
  await page.goto(`${path}?${query({ topic: topics, author: authors, sort: "desc" })}`);
  const form = page.getByRole("form", { name: "筛选时间线", exact: true });
  await expect(form).toContainText("TL56主题甲");
  await expect(form).toContainText("TL56主题乙");
  await expect(form).toContainText("TL56作者甲");
  await expect(form).toContainText("TL56作者乙");
  await form.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page).toHaveURL(/scale=100/);
  const current = new URL(page.url()).searchParams;
  expect(current.getAll("topic").flatMap(value => value.split(",")).sort()).toEqual(topics.sort());
  expect(current.getAll("author").flatMap(value => value.split(",")).sort()).toEqual(authors.sort());
  await form.getByRole("checkbox", { name: "作品出版", exact: true }).check();
  await form.getByRole("checkbox", { name: "译本出版", exact: true }).check();
  await form.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page).toHaveURL(/event_type=/);
  const filtered = await timeline(page, { topic: topics, author: authors, event_type: ["publication", "translation"] });
  expect(filtered.results.map(row => row.id).sort()).toEqual([ids.publication, ids.translation, ids.scanSource].sort());
  await expect(page.getByRole("region", { name: "时间线事件", exact: true }).getByRole("link"))
    .toHaveCount(filtered.results.length);
  expect(new URL(page.url()).searchParams.getAll("event_type").flatMap(value => value.split(",")).sort())
    .toEqual(["publication", "translation"]);
});

test("pagination preserves whole-scope year counts and focus locates a real event beyond the first page", async ({ page }) => {
  const first = await timeline(page, { q: "TL56PAGE" });
  const second = await timeline(page, { q: "TL56PAGE", page: "2" });
  expect(first).toMatchObject({ count: 26, scope_count: 26, page: 1, page_size: 24, total_pages: 2 });
  expect(second).toMatchObject({ count: 26, scope_count: 26, page: 2, total_pages: 2 });
  expect(first.results).toHaveLength(24);
  expect(second.results).toHaveLength(2);
  expect(first.year_groups).toEqual(second.year_groups);
  expect(first.year_groups.reduce((sum, group) => sum + group.count, 0)).toBe(26);
  expect(first.year_groups.every(group => group.event_types.length === 1
    && group.event_types[0].event_type === "publication" && group.event_types[0].count === group.count)).toBe(true);
  expect(first.bounds).toMatchObject({ min_year: 1950, max_year: 1975, undated_count: 0 });
  const focused = await timeline(page, { q: "TL56PAGE", focus: ids.pageLast });
  expect(focused).toMatchObject({ page: 2, focus_id: ids.pageLast });
  expect(focused.results.map(row => row.id)).toContain(ids.pageLast);
  await page.goto(`${path}?${query({ q: "TL56PAGE" })}`);
  await page.getByRole("navigation", { name: "时间线分页", exact: true }).getByRole("link", { name: "下一页", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("region", { name: "时间线事件", exact: true })).toContainText("TL56PAGE 分页事件26");
  await page.goto(`${path}?${query({ q: "TL56PAGE", focus: ids.pageLast })}`);
  await expect(page.getByRole("region", { name: "时间线事件", exact: true })).toContainText("TL56PAGE 分页事件26");
});

test("descending order reverses dated events while keeping undated events distinct", async ({ page }) => {
  const asc = await timeline(page, { q: "TL56PAGE", sort: "asc" });
  const desc = await timeline(page, { q: "TL56PAGE", sort: "desc" });
  expect(asc.results[0].start_year).toBe(1950);
  expect(desc.results[0].start_year).toBe(1975);
  for (const sort of ["asc", "desc"]) {
    const withUndated = await timeline(page, { sort });
    expect(withUndated.results.at(-1)?.id).toBe(ids.undated);
  }
  await page.goto(`${path}?${query({ q: "TL56PAGE" })}`);
  await page.getByLabel("事件排序", { exact: true }).selectOption("desc");
  await expect(page).toHaveURL(/sort=desc/);
  const events = page.getByRole("region", { name: "时间线事件", exact: true });
  await expect(events.getByRole("link").filter({ hasText: "TL56PAGE 分页事件26" })).toBeVisible();
});

test("an image-only source has no published excerpt and cannot borrow a different readable edition", async ({ page }) => {
  const data = await event(page, ids.scanSource);
  expect(data.source_status).toBe("unavailable");
  expect(data.evidence_source).toBeNull();
  expect(data.evidence_text).toBe("");
  expect(data.reader_href).toBeNull();
  expect(data.subject_edition?.edition_id).toBe(sources.leftEdition);
  await page.goto(`${path}?${query({ focus: ids.scanSource })}`);
  await page.getByRole("tab", { name: "原文片段", exact: true }).click();
  await expect(page.getByRole("tabpanel")).not.toContainText("PARALLEL");
});

test("real zero matches and an unavailable selected event remain different states", async ({ page }) => {
  const empty = await timeline(page, { q: "TL56-no-such-event" });
  expect(empty).toMatchObject({ count: 0, scope_count: 0, results: [], year_groups: [] });
  const emptyDiscipline = await timeline(page, { discipline: "e2e-timeline-empty" });
  expect(emptyDiscipline).toMatchObject({ count: 0, scope_count: 0, results: [], year_groups: [] });
  const unavailable = await page.request.get(`${api}/catalog/theory-system/timeline/?${query({ focus: ids.draft })}`);
  expect(unavailable.status()).toBe(404);
  const invalid = await page.request.get(`${api}/catalog/theory-system/timeline/?${query({ year_from: "2000", year_to: "1800" })}`);
  expect(invalid.status()).toBe(400);
  await page.goto(`${path}?${query({ q: "TL56-no-such-event" })}`);
  await expect(page.getByRole("region", { name: "时间线事件", exact: true }).getByRole("status")).toBeVisible();
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  await page.goto(`${path}?${query({ focus: ids.draft })}`);
  await expect(page.locator("main").getByRole("alert")).toBeVisible();
});

test("mobile selection, tabs and filtering remain operable without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${path}?${query({ year: "1867" })}`);
  const events = page.getByRole("region", { name: "时间线事件", exact: true });
  await events.getByRole("link", { name: /TL56CASE 合成原版发表/ }).click();
  await expect(page).toHaveURL(new RegExp(`focus=${ids.publication}`));
  const detailsTab = page.getByRole("tab", { name: "事件详情", exact: true });
  const sourceTab = page.getByRole("tab", { name: "原文片段", exact: true });
  await detailsTab.focus();
  await detailsTab.press("ArrowLeft");
  await expect(sourceTab).toBeFocused();
  await expect(sourceTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toContainText("PARALLEL");
  await sourceTab.press("Home");
  await expect(detailsTab).toBeFocused();
  await expect(detailsTab).toHaveAttribute("aria-selected", "true");
  await detailsTab.press("End");
  await expect(sourceTab).toBeFocused();
  await sourceTab.press("ArrowRight");
  await expect(detailsTab).toBeFocused();
  await expect(page.getByRole("tabpanel")).toContainText("合成时间线事件");
  const form = page.getByRole("form", { name: "筛选时间线", exact: true });
  await form.getByRole("radio", { name: "自定义", exact: true }).check();
  await form.getByLabel("起始年份", { exact: true }).fill("1908");
  await form.getByLabel("结束年份", { exact: true }).fill("1912");
  await form.getByRole("checkbox", { name: "概念使用", exact: true }).check();
  await form.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page).toHaveURL(/scale=custom/);
  await expect(events.getByRole("link")).toHaveCount(1);
  await expect(events).toContainText("TL56CASE 合成时间范围");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("failed topic loading preserves the selected filter and retries the real public candidate API", async ({ page }) => {
  await page.goto(`${path}?${query({ topic: "e2e-timeline-topic-a" })}`);
  const form = page.getByRole("form", { name: "筛选时间线", exact: true });
  const candidatePattern = "**/api/catalog/topics/?*";
  await page.route(candidatePattern, route => route.abort("failed"));
  await form.getByLabel("选择主题", { exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("主题候选暂时无法读取");
  await expect(form.getByRole("button", { name: "移除主题 TL56主题甲", exact: true })).toBeVisible();
  await expect(form.getByRole("checkbox", { name: "TL56主题乙", exact: true })).toHaveCount(0);
  await page.unroute(candidatePattern);
  const response = page.waitForResponse(url => url.url().includes("/api/catalog/topics/") && url.status() === 200);
  await form.getByRole("button", { name: "重试主题候选", exact: true }).click();
  await response;
  await form.getByRole("textbox", { name: "搜索主题", exact: true }).fill("TL56");
  const searchResponse = page.waitForResponse(url => url.url().includes("/api/catalog/topics/?")
    && new URL(url.url()).searchParams.get("q") === "TL56" && url.status() === 200);
  await form.getByRole("button", { name: "搜索主题候选", exact: true }).click();
  await searchResponse;
  await expect(form.getByRole("checkbox", { name: "TL56主题甲", exact: true })).toBeChecked();
  await expect(form.getByRole("checkbox", { name: "TL56主题未公开", exact: true })).toHaveCount(0);
  await form.getByRole("checkbox", { name: "TL56主题乙", exact: true }).check();
  await form.getByLabel("选择主题", { exact: true }).click();
  await form.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page).toHaveURL(/e2e-timeline-topic-b/);
  expect(new URL(page.url()).searchParams.getAll("topic").flatMap(value => value.split(",")).sort())
    .toEqual(["e2e-timeline-topic-a", "e2e-timeline-topic-b"]);
});

test("legacy timeline URL preserves actual old event identity and current query filters", async ({ page }) => {
  const data = await event(page, ids.legacy);
  expect(data.id).toBe(ids.legacy);
  await page.goto(`/theory-schools/timeline?${query({ focus: ids.legacy, sort: "desc" })}`);
  await expect(page).toHaveURL(new RegExp(`/theory-schools/timeline\\?.*focus=${ids.legacy}`));
  expect(new URL(page.url()).searchParams.get("sort")).toBe("desc");
  expect(new URL(page.url()).searchParams.get("q")).toBe("TL56CASE");
  await expect(page.locator("main")).toContainText("TL56CASE 合成历史条目事件");
  await page.getByText("展开更多事件资料", { exact: true }).click();
  await expect(page.locator('main a[href="/theory-schools/e2e-timeline-legacy"]')).toBeVisible();
});
