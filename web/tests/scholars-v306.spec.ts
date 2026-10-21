import { expect, test, type Page } from "@playwright/test";
import type { PublicScholarDetail, PublicScholarDirectory } from "../lib/api/scholars.types";

// Only the disposable runner's published synthetic records and extracted PDF
// are used. These are definitions for the final acceptance run, not live data.
const api = "http://127.0.0.1:8105/api", slug = "e2e-scholar-public";
const path = `/scholars/${slug}`, endpoint = `${api}/catalog/scholars/${slug}/`;
const profileId = "61000000-0000-4000-8000-000000000001";
const editionId = "61000000-0000-4000-8000-000000000032";
const fieldId = "topic:61000000-0000-4000-8000-000000000021";

async function detail(page: Page, query = "") {
  const response = await page.request.get(`${endpoint}${query}`);
  expect(response.status(), `seed_scholars(actor) must run in the disposable environment: ${await response.text()}`).toBe(200);
  return await response.json() as PublicScholarDetail;
}
async function directory(page: Page, query: string) {
  const response = await page.request.get(`${api}/catalog/scholars/?${query}`);
  expect(response.status()).toBe(200); return await response.json() as PublicScholarDirectory;
}
async function editor(page: Page) {
  await page.goto("/login"); await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click(); await expect(page).toHaveURL(/\/admin$/);
}
test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Run only against the disposable cataloging environment.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", handler => handler.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
});

test("directory searches confirmed aliases and displays the public total with actual pagination", async ({ page }) => {
  const data = await directory(page, "q=SCHOLAR63&page_size=1&sort=birth");
  expect(data.count).toBe(3); expect(data.results).toHaveLength(1);
  await page.goto("/scholars?view=directory&q=SCHOLAR63&page_size=1&sort=birth");
  const results = page.getByRole("region", { name: "公开学者结果" });
  await expect(results).toContainText("找到 3 位学者");
  await expect(results.locator("article[data-scholar-id]")).toHaveCount(1);
  await page.getByRole("navigation", { name: "学者分页", exact: true }).getByRole("link", { name: "下一页" }).click();
  await expect(page).toHaveURL(/page=2/); await expect(results).toContainText("第 2 / 3 页");
  await page.getByRole("searchbox", { name: "搜索学者姓名、原文名或研究领域" }).fill("SCHOLAR63 正式译名");
  await page.getByRole("search").getByRole("button", { name: "搜索", exact: true }).click();
  await expect(results.locator(`[data-scholar-id="${profileId}"]`)).toContainText("别名命中：SCHOLAR63 正式译名");
  await expect(results).not.toContainText("私有待审译名");
});

test("field and school filtering preserve exact identities and empty results stay empty", async ({ page }) => {
  const data = await directory(page, new URLSearchParams({ field: fieldId }).toString());
  expect(data.results.map(row => row.id)).toEqual([profileId]);
  await page.goto("/scholars?view=directory&q=SCHOLAR63");
  const filters = page.getByRole("form", { name: "学者筛选", exact: true });
  await filters.getByRole("checkbox", { name: /SCHOLAR63 合成研究领域/ }).check();
  await filters.getByRole("checkbox", { name: /SCHOLAR63 合成理论传统/ }).check();
  await filters.getByRole("button", { name: "应用筛选" }).click();
  await expect(page.getByRole("region", { name: "公开学者结果" }).locator("article[data-scholar-id]")).toHaveCount(1);
  await page.getByRole("link", { name: "列表展示学者" }).click(); await expect(page).toHaveURL(/layout=list/);
  await page.getByRole("searchbox").fill("SCHOLAR63 不存在的规范姓名");
  await page.getByRole("search").getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByRole("heading", { name: "未找到与“SCHOLAR63 不存在的规范姓名”相关的学者" })).toBeVisible();
  await expect(page.getByRole("region", { name: "公开学者结果" }).locator("article[data-scholar-id]")).toHaveCount(0);
});

test("namesakes stay distinct and sparse profiles do not receive a substitute portrait or quotation", async ({ page }) => {
  const data = await detail(page); expect(data.disambiguation).toHaveLength(1);
  await page.goto(path); await page.getByText("区分同名学者（另有 1 位公开档案）", { exact: true }).click();
  const namesake = page.locator('[data-scholar-id="61000000-0000-4000-8000-000000000002"]');
  await expect(namesake).toContainText("Synthetic Scholar 2"); await expect(namesake).toContainText("1880 — 1940");
  await namesake.getByRole("heading").getByRole("link").click(); await expect(page).toHaveURL(/e2e-scholar-namesake$/);
  await page.goto("/scholars/e2e-scholar-sparse");
  await expect(page.getByRole("heading", { name: "SCHOLAR63 稀疏档案", exact: true })).toBeVisible();
  await expect(page.locator('[aria-label="SCHOLAR63 稀疏档案暂无肖像"]')).toBeVisible();
  await expect(page.getByText("资料仍待补充", { exact: true })).toBeVisible();
  await expect(page.locator('[data-module-id="scholar-quote"]')).toHaveCount(0);
  await expect(page.locator('[data-module-id="scholar-works"]')).toContainText("尚无与这位学者明确关联的公开出版版本");
});

test("chapter contributions lead to exact current document and outline identities without claiming whole-book authorship", async ({ page }) => {
  const data = await detail(page, "?section=works&role=author"), work = data.works.results.find(row => row.edition_id === editionId)!;
  expect(work).toBeTruthy(); const own = work.contributions.find(row => row.person_id === data.person.id)!;
  expect(own.scope.kind).toBe("chapter"); expect(own.scope.chapters).toHaveLength(1);
  const chapter = own.scope.chapters[0];
  expect(chapter.reader_href).toContain(chapter.asset_id); expect(chapter.reader_href).toContain(chapter.document_revision_id);
  await page.goto(`${path}/works?role=author`);
  const card = page.locator(`[data-edition-id="${editionId}"]`);
  await expect(card).toContainText("隔离验收版"); await expect(card.getByRole("link", { name: "阅读原文", exact: true })).toHaveCount(0);
  await card.getByText("章节贡献与准确来源（1）", { exact: true }).click();
  await expect(card).toContainText("SCHOLAR66 第一章");
  await expect(card.getByRole("link", { name: "阅读此章节", exact: true })).toHaveAttribute("href", chapter.reader_href);
  await expect(card.getByRole("link", { name: "作者与编者", exact: true })).toHaveAttribute("href", `${work.href}#scholars`);
  await page.goto("/scholars/e2e-scholar-namesake/works?role=editor");
  await expect(page.locator(`[data-edition-id="${editionId}"]`)).toContainText("编者");
});

test("featured quotation and profile sources expose verified source links and retain legacy section routes", async ({ page }) => {
  const data = await detail(page); expect(data.featured_quote?.source.reader_url).toBeTruthy();
  await page.goto(path);
  const quote = page.locator('[data-module-id="scholar-quote"]');
  await expect(quote).toContainText(data.featured_quote!.source.text);
  await expect(quote.getByRole("link", { name: "核对原文" })).toHaveAttribute("href", data.featured_quote!.source.reader_url);
  await page.goto(`${path}/biography`);
  await expect(page.locator('[data-module-id="scholar-sources"]').getByRole("link", { name: "隔离验收资料说明" })).toHaveAttribute("href", "https://example.org/synthetic-scholar");
  await expect(page.getByRole("navigation", { name: "学者内容" }).getByRole("link", { name: "人物资料来源" })).toHaveAttribute("aria-current", "page");
  await page.goto(`${path}/timeline`);
  await expect(page.getByRole("link", { name: "打开完整时间线" })).toHaveAttribute("href", `/theories/timeline?author=${data.id}`);
});

test("formal relationships retain direction and evidence while anonymous readers cannot inspect candidates", async ({ page }) => {
  const data = await detail(page, "?section=relations"); expect(data.relations.count).toBe(1); expect(data.candidate_relations).toBeNull();
  await page.goto(`${path}/network`);
  await expect(page.getByRole("checkbox", { name: "查看未确认关系" })).toHaveCount(0);
  const relationship = page.locator(`[data-relation-id="${data.relations.results[0].id}"]`);
  await relationship.locator("summary").press("Enter"); await expect(relationship).toContainText("合成记录，仅用于验收。");
  await expect(page.locator("main")).not.toContainText("SCHOLAR66 待审关系");
  await expect(page.getByRole("link", { name: "查看学术关系图", exact: true }).first()).toHaveAttribute("href", data.graph_href);
  const forbidden = await page.request.get(`${endpoint}?section=relations&include_candidates=true`); expect(forbidden.status()).toBe(403);
});

test("authorized candidate inspection stays separate from the published relationship count", async ({ page }) => {
  await editor(page); const data = await detail(page, "?section=relations&include_candidates=true");
  expect(data.candidate_access.allowed).toBe(true); expect(data.candidate_relations?.count).toBe(1);
  await page.goto(`${path}/relations`);
  await page.getByRole("checkbox", { name: "查看未确认关系" }).check();
  await page.getByRole("button", { name: "更新显示", exact: true }).click();
  const candidate = page.locator(`[data-relation-id="${data.candidate_relations!.results[0].id}"]`);
  await expect(candidate).toContainText("关系未确认"); await candidate.locator("summary").click();
  await expect(candidate).toContainText("SCHOLAR66 待审关系");
  await expect(page.locator('[data-module-id="scholar-network"]')).not.toContainText("SCHOLAR66 待审关系");
});

test("mobile filter dialog supports keyboard dismissal and profile content stays within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/scholars?view=directory&q=SCHOLAR63");
  const trigger = page.getByRole("button", { name: /筛选条件（0）/ }); await trigger.click();
  const dialog = page.getByRole("dialog", { name: "筛选学者", exact: true }); await expect(dialog).toBeVisible();
  await dialog.getByRole("checkbox", { name: /SCHOLAR63 合成研究领域/ }).focus(); await page.keyboard.press("Space");
  await expect(dialog.getByRole("checkbox", { name: /SCHOLAR63 合成研究领域/ })).toBeChecked();
  await page.keyboard.press("Escape"); await expect(dialog).not.toBeVisible(); await expect(trigger).toBeFocused();
  await trigger.click(); await dialog.getByRole("checkbox", { name: /SCHOLAR63 合成研究领域/ }).check();
  await dialog.getByRole("button", { name: "应用筛选" }).click();
  await expect(page.getByRole("region", { name: "公开学者结果" }).locator("article[data-scholar-id]")).toHaveCount(1);
  await page.goto(path); await expect(page.getByRole("heading", { name: "SCHOLAR63 合成学者", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("invalid actual API filters show a recoverable error instead of fabricated results", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/scholars/?field=not-a-public-field`); expect(response.status()).toBe(400);
  await page.goto("/scholars?view=directory&field=not-a-public-field");
  await expect(page.getByRole("alert")).toContainText("学者目录暂时无法读取");
  await expect(page.getByRole("button", { name: "重试读取", exact: true })).toBeVisible();
  await expect(page.locator("article[data-scholar-id]")).toHaveCount(0);
  await page.getByRole("alert").getByRole("link", { name: "清除筛选" }).click();
  await expect(page.getByRole("heading", { name: "学者索引", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "公开学者结果" })).toBeVisible();
});

test("author and editor link opens the exact edition contributor panel on desktop and mobile", async ({ page }) => {
  const data = await detail(page, "?section=works"), work = data.works.results.find(row => row.edition_id === editionId)!;
  await page.goto(`${path}/works`);
  const link = page.locator(`[data-edition-id="${editionId}"]`).getByRole("link", { name: "作者与编者", exact: true });
  const popupPromise = page.waitForEvent("popup"); await link.click(); const popup = await popupPromise;
  await expect(popup).toHaveURL(new RegExp(`${work.href}#scholars$`));
  const contributors = popup.getByRole("region", { name: "当前出版版本的责任者", exact: true });
  await expect(contributors).toBeVisible(); await expect(contributors).toContainText("章节作者"); await expect(contributors).toContainText("编者");
  await popup.close(); await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`${path}/works`);
  await link.click(); await expect(page).toHaveURL(new RegExp(`${work.href}#scholars$`));
  await expect(page.getByRole("region", { name: "当前出版版本的责任者", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "SCHOLAR66 第一章", exact: true })).toHaveAttribute("href", work.contributions.find(row => row.person_id === data.person.id)!.scope.chapters[0].reader_href);
});

test("admin preview reflects unsaved identity and prevents follow or research navigation", async ({ page }) => {
  await editor(page);
  const privateRequests: string[] = [];
  page.on("request", request => { if (request.url().includes("/reading/source-follows/")) privateRequests.push(request.url()); });
  await page.goto(`/admin/scholars/${profileId}?section=identity`);
  const preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]'), fields = page.locator(".fixed-editor-fields");
  const description = "SCHOLAR66 本地未保存简介，仅用于预览验收。";
  await fields.getByLabel("页面简介", { exact: true }).fill(description);
  await expect(preview.locator('[data-module-id="scholar-identity"]')).toContainText(description);
  await expect(preview.getByRole("button", { name: "关注学者", exact: true })).toBeDisabled();
  await expect(preview.getByRole("button", { name: "围绕此学者开展研究", exact: true })).toBeDisabled();
  await expect(preview.getByRole("button", { name: "查看学术关系图", exact: true })).toBeDisabled();
  await preview.getByRole("link", { name: "学者", exact: true }).click();
  await expect(preview.getByRole("heading", { name: "SCHOLAR63 合成学者", exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/admin/scholars/${profileId}`));
  expect(privateRequests).toEqual([]);
});

test("unsaved quote preview cancels obsolete selection reads and retries without losing form input", async ({ page }) => {
  await editor(page); await page.goto(`/admin/scholars/${profileId}?section=identity`);
  const preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]'), fields = page.locator(".fixed-editor-fields");
  const description = "SCHOLAR66 核对请求期间保留的本地简介。";
  await fields.getByLabel("页面简介", { exact: true }).fill(description);
  await expect(preview.locator('[data-module-id="scholar-identity"]')).toContainText(description);
  await page.getByRole("navigation", { name: "编辑区域", exact: true }).getByRole("button", { name: "资料来源与路径", exact: true }).click();
  const select = fields.getByLabel("首屏原文引语", { exact: true });
  await expect(select).toBeEnabled(); const savedQuote = await select.inputValue(); expect(savedQuote).not.toBe("");
  let mode: "hold" | "fail" | "pass" = "hold", release = () => {};
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/catalog/admin/knowledge-preview/scholar/${profileId}/?*`, async route => {
    if (new URL(route.request().url()).searchParams.get("featured_source_id") !== "" || mode === "pass") return route.continue();
    if (mode === "fail") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "隔离预览读取暂不可用" }) });
    const response = await route.fetch(); await delayed;
    await route.fulfill({ response }).catch(() => undefined); // The browser may already have cancelled this obsolete read.
  });
  try {
    await select.selectOption("");
    await expect(preview.getByRole("status")).toContainText("正在核对本次选择");
    await expect(preview.locator('[data-module-id="scholar-quote"]')).toHaveCount(0);
    await select.selectOption(savedQuote);
    await expect(preview.locator('[data-module-id="scholar-quote"]')).toBeVisible(); release();
    await expect(preview.locator('[data-module-id="scholar-identity"]')).toContainText(description);
    mode = "fail"; await select.selectOption("");
    await expect(preview.getByRole("alert")).toContainText("本次选择尚未核对");
    mode = "pass"; await page.getByRole("button", { name: "重新核对预览", exact: true }).click();
    await expect(preview.locator('[data-module-id="scholar-identity"]')).toContainText(description);
    await expect(preview.locator('[data-module-id="scholar-quote"]')).toHaveCount(0);
    expect((await detail(page)).featured_quote?.id).toBe(savedQuote);
  } finally { release(); }
});

test("new manually selected public reading path appears before saving and removal preserves server associations", async ({ page }) => {
  await editor(page); const original = await detail(page);
  await page.goto(`/admin/scholars/${profileId}?section=paths`);
  const preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]'), fields = page.locator(".fixed-editor-fields");
  const title = "PATH58 从材料进入理论";
  await fields.getByRole("combobox", { name: "人工编排的相关阅读路径", exact: true }).fill(title);
  const received = page.waitForResponse(response => response.url().includes(`/knowledge-preview/scholar/${profileId}/?`) && Boolean(new URL(response.url()).searchParams.get("reading_path_ids")) && response.status() === 200);
  await fields.getByRole("option", { name: new RegExp(title) }).click();
  const payload = await (await received).json() as { perspective: { data: PublicScholarDetail } };
  expect(payload.perspective.data.paths.results.some(row => row.title === title)).toBe(true);
  await expect(preview.locator('[data-module-id="scholar-reading-paths"]')).toContainText(title);
  await fields.getByRole("button", { name: "移除已选择的阅读路径", exact: true }).click();
  await expect(preview.locator('[data-module-id="scholar-reading-paths"]')).not.toContainText(title);
  expect((await detail(page)).paths).toEqual(original.paths);
});
