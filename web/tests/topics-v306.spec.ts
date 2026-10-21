import { expect, test, type Page } from "@playwright/test";
import type { PublicTopicDetail, TopicDirectory } from "../lib/api/topics.types";

// Definitions for the disposable acceptance runner only. All topic records and
// source text come from seed_topics and its actual extracted synthetic PDF.
const api = "http://127.0.0.1:8105/api", slug = "stl4-topic-technology", path = `/topics/${slug}`;
async function detail(page: Page, query = "") {
  const response = await page.request.get(`${api}/catalog/topics/${slug}/${query}`);
  expect(response.status(), `seed_topics(actor) is required: ${await response.text()}`).toBe(200);
  return await response.json() as PublicTopicDetail;
}
async function directory(page: Page, query: string) {
  const response = await page.request.get(`${api}/catalog/topics/?${query}`);
  expect(response.status()).toBe(200); return await response.json() as TopicDirectory;
}
test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use only the disposable cataloging runner.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
});

test("directory retains confirmed alias matches, disambiguation, and exact pagination", async ({ page }) => {
  const query = new URLSearchParams({ q: "TOPIC69 已确认别名", page_size: "1" }).toString(), data = await directory(page, query);
  expect(data.count).toBeGreaterThan(1); expect(data.disambiguation.length).toBeGreaterThan(1); expect(data.results).toHaveLength(1);
  await page.goto(`/topics?view=directory&${query}`);
  const results = page.getByRole("region", { name: "公开主题结果", exact: true });
  await expect(results).toContainText(`找到 ${data.count} 个相关主题`);
  await expect(page.getByRole("complementary", { name: "主题名称重叠提示", exact: true })).toContainText(data.overlap_notice);
  await expect(results.locator("article[data-topic-id]")).toHaveCount(1);
  await expect(results.locator("article[data-topic-id]")).toContainText("别名命中：TOPIC69 已确认别名");
  await page.getByRole("navigation", { name: "主题分页", exact: true }).getByRole("link", { name: "下一页", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("navigation", { name: "主题分页", exact: true })).toContainText(`第 2 / ${data.total_pages} 页`);
});

test("hierarchy search and grid-list controls preserve the selected public subtree", async ({ page }) => {
  const data = await directory(page, "q=TOPIC"), parent = data.hierarchy.find(row => row.slug === "stl4-topic-society")!, second = data.hierarchy.find(row => row.slug === "stl4-topic-overlap")!;
  expect(parent).toBeTruthy(); expect(parent.descendant_count).toBeGreaterThan(0);
  await page.goto("/topics?view=directory&q=TOPIC");
  const filters = page.getByRole("form", { name: "主题层级筛选", exact: true });
  await filters.getByRole("checkbox", { name: new RegExp(parent.name) }).check();
  await filters.getByRole("checkbox", { name: new RegExp(second.name) }).check();
  await expect(filters.getByRole("checkbox", { name: "全部主题", exact: true })).not.toBeChecked();
  await filters.getByRole("button", { name: "应用筛选", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`parent=${parent.id}`));
  expect(new URL(page.url()).searchParams.getAll("parent")).toEqual(expect.arrayContaining([parent.id, second.id]));
  const selectedQuery = new URLSearchParams({ q: "TOPIC", parent: parent.id }); selectedQuery.append("parent", second.id);
  const filtered = await directory(page, selectedQuery.toString());
  await expect(page.getByRole("region", { name: "公开主题结果", exact: true })).toContainText(`找到 ${filtered.count} 个相关主题`);
  await page.getByRole("link", { name: `移除主题筛选：${second.name}`, exact: true }).click();
  expect(new URL(page.url()).searchParams.getAll("parent")).toEqual([parent.id]);
  await page.getByRole("link", { name: "列表展示主题", exact: true }).click(); await expect(page).toHaveURL(/layout=list/);
  await page.getByRole("searchbox", { name: "搜索主题、概念或问题关键词", exact: true }).fill("TOPIC71");
  await page.getByRole("search").getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`parent=${parent.id}`)); await expect(page).toHaveURL(/layout=list/);
});

test("question expansion exposes real sources and counts without confusing discussions with reader activity", async ({ page }) => {
  const data = await detail(page, "?section=questions&page_size=1"); expect(data.questions.results.length).toBe(1);
  const question = data.questions.results[0];
  await page.goto(`${path}/questions?page_size=1`);
  const row = page.locator(`[data-question-id="${question.id}"]`);
  await expect(row).toContainText(`${question.discussion_count} 条讨论材料 · ${question.work_count} 部相关作品`);
  await row.locator("summary").focus(); await page.keyboard.press("Enter");
  if (question.summary) await expect(row).toContainText(question.summary);
  if (question.count_notice) await expect(row).toContainText(question.count_notice);
  await expect(row.locator("a").first()).toHaveAttribute("href", question.href);
  await page.getByRole("link", { name: "理论争论", exact: true }).click(); await expect(page).toHaveURL(/question_type=debate/);
});

test("catalog-only and explicit planned works stay distinct and cannot offer fabricated full text", async ({ page }) => {
  const noText = await detail(page, "?section=works&availability=no_fulltext"), planned = await detail(page, "?section=works&availability=planned");
  expect(noText.works.count).toBeGreaterThan(0); expect(planned.works.count).toBeGreaterThan(0);
  await page.goto(`${path}/works?availability=no_fulltext`);
  const cards = page.locator('article[data-source-status="no_fulltext"]'); await expect(cards).toHaveCount(noText.works.results.length);
  await expect(cards.first()).toContainText("暂无全文"); await expect(cards.getByRole("link", { name: "在线阅读", exact: true })).toHaveCount(0);
  await page.getByRole("navigation", { name: "作品全文状态", exact: true }).getByRole("link", { name: /^计划补充/ }).click();
  await expect(page.locator('article[data-source-status="planned"]')).toHaveCount(planned.works.results.length);
  await expect(page.locator('article[data-source-status="planned"]').first()).toContainText("馆藏补充计划中");
  await expect(page.locator('article[data-source-status="planned"]').getByRole("link", { name: "在线阅读", exact: true })).toHaveCount(0);
  await expect(page.locator('article[data-source-status="planned"]').getByRole("button", { name: /加入书架/ })).toHaveCount(0);
  await page.goto(path); await page.getByRole("link", { name: "基础阅读", exact: true }).click(); await expect(page).toHaveURL(/reading=foundational/);
});

test("withdrawn relations retain a safe position and old section routes remain readable", async ({ page }) => {
  const data = await detail(page), unavailable = data.unavailable_links.find(row => row.kind === "scholar")!;
  expect(unavailable).toBeTruthy(); await page.goto(`${path}/scholars`);
  const row = page.locator(`[data-unavailable-id="${unavailable.id}"]`); await expect(row).toContainText("原关联内容当前不可用");
  await expect(page.locator("main")).not.toContainText("TOPIC71 撤回学者");
  await row.getByText("查看说明", { exact: true }).click(); await expect(row).toContainText(unavailable.notice);
  await page.goto(`${path}/reading-paths`); await expect(page.getByRole("navigation", { name: "主题内容", exact: true }).getByRole("link", { name: "研究路径", exact: true })).toHaveAttribute("aria-current", "page");
  await page.goto(`${path}/timeline`); await expect(page.getByRole("heading", { name: "概念时间线", exact: true })).toBeVisible();
  await page.goto(`${path}/methods`); await expect(page.getByRole("heading", { name: "研究方法", exact: true })).toBeVisible();
});

test("evidence keeps the precise document revision, actual sequence, and topic return route", async ({ page }) => {
  const data = await detail(page, "?section=evidence&page_size=1"); expect(data.evidence.count).toBeGreaterThan(0);
  const item = data.evidence.results[0]; await page.goto(`${path}/passages?page_size=1`);
  const source = page.locator(`#curated-${item.id || item.source_id}`); await expect(source).toContainText(item.source.text);
  const reader = new URL((await source.getByRole("link", { name: "查看完整文献", exact: true }).getAttribute("href"))!, "http://127.0.0.1:3105");
  expect(reader.pathname).toBe(`/reader/${item.source.asset_id}`); expect(reader.searchParams.get("revision")).toBe(item.source.document_revision_id);
  expect(reader.searchParams.get("return_to")).toContain(`/topics/${slug}/evidence`);
  await expect(source.getByRole("link", { name: "在主题中提问", exact: true })).toHaveAttribute("href", data.research_href);
  await source.getByRole("button", { name: "引用", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "引用、选材与导出", exact: true })).toBeVisible();
});

test("mobile hierarchy dialog is keyboard accessible and the latest detail keeps guide-question-work order", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/topics?view=directory&q=TOPIC");
  const trigger = page.getByRole("button", { name: /^主题分类/ }); await trigger.click();
  const dialog = page.getByRole("dialog", { name: "筛选主题", exact: true }); await expect(dialog).toBeVisible();
  const branch = dialog.getByRole("checkbox", { name: /TOPIC69 合成社会主题/ }); await branch.focus(); await page.keyboard.press("Space"); await expect(branch).toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: "全部主题", exact: true })).not.toBeChecked();
  await dialog.getByRole("checkbox", { name: "全部主题", exact: true }).check(); await expect(branch).not.toBeChecked();
  await page.keyboard.press("Escape"); await expect(dialog).not.toBeVisible(); await expect(trigger).toBeFocused();
  await page.goto(path);
  const positions = await page.locator('[data-module-id="topic-guide"], [data-module-id="topic-framework"], [data-module-id="topic-works"]').evaluateAll(rows => rows.map(row => ({ id: row.getAttribute("data-module-id"), top: row.getBoundingClientRect().top })));
  expect(positions.map(row => row.id)).toEqual(["topic-guide", "topic-framework", "topic-works"]);
  expect(positions[0].top).toBeLessThan(positions[1].top); expect(positions[1].top).toBeLessThan(positions[2].top);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("empty topics invite anonymous recommendations and API faults remain separate from empty results", async ({ page }) => {
  await page.goto("/topics/stl4-topic-empty");
  await expect(page.getByRole("heading", { name: "该主题下的内容仍在补充中", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "提交推荐", exact: true }).click(); await expect(page).toHaveURL(/\/feedback\?/);
  expect(new URL(page.url()).searchParams.get("path")).toBe("/topics/stl4-topic-empty");
  await expect(page.getByRole("heading", { name: "提交反馈", exact: true })).toBeVisible();
  const invalid = await page.request.get(`${api}/catalog/topics/?sort=invalid`); expect(invalid.status()).toBe(400);
  await page.goto("/topics?view=directory&sort=invalid");
  await expect(page.getByRole("alert")).toContainText("主题目录暂时无法读取");
  await expect(page.getByRole("alert").getByRole("button", { name: "重试读取", exact: true })).toBeVisible();
  await expect(page.locator("article[data-topic-id]")).toHaveCount(0);
});

async function editor(page: Page) {
  await page.goto("/login"); await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click(); await expect(page).toHaveURL(/\/admin$/);
}

test("admin topic preview updates unsaved statements without requesting private reading data", async ({ page }) => {
  const data = await detail(page); await editor(page);
  const privateRequests: string[] = [];
  page.on("request", request => { if (/\/reading\/(source-follows|saved-topics|saved-works)\//.test(request.url())) privateRequests.push(request.url()); });
  await page.goto(`/admin/topics/${data.id}?section=identity`);
  const preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]'), fields = page.locator(".fixed-editor-fields");
  const statement = "TOPIC71 本地未保存的问题陈述，仅用于隔离预览。";
  await fields.getByLabel("问题陈述", { exact: true }).fill(statement);
  await expect(preview.locator('[data-module-id="topic-identity"]')).toContainText(statement);
  await expect(preview.getByRole("button", { name: "关注主题", exact: true })).toBeDisabled();
  await expect(preview.getByRole("button", { name: "进入核心问题", exact: true })).toBeDisabled();
  await preview.getByRole("navigation", { name: "面包屑", exact: true }).getByRole("link", { name: "主题", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/topics/${data.id}`));
  await expect(preview.getByRole("heading", { name: data.name, exact: true })).toBeVisible();
  expect(privateRequests).toEqual([]); expect((await detail(page)).problem_statement).toBe(data.problem_statement);
});

test("unsaved topic quote cancels obsolete projection and retries without publishing the selection", async ({ page }) => {
  const data = await detail(page); expect(data.featured_quote).toBeTruthy(); await editor(page);
  await page.goto(`/admin/topics/${data.id}?section=sources`);
  const preview = page.frameLocator('iframe[title="当前输入的公开页面预览"]'), fields = page.locator(".fixed-editor-fields");
  const select = fields.getByLabel("首屏原文引语", { exact: true }); await expect(select).toBeEnabled();
  const savedQuote = await select.inputValue(); expect(savedQuote).toBe(data.featured_quote!.id);
  let mode: "hold" | "fail" | "pass" = "hold", release = () => {};
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/catalog/admin/knowledge-preview/topic/${data.id}/`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { curation?: { featured_source_id?: string | null } };
    if (body.curation?.featured_source_id || mode === "pass") return route.continue();
    if (mode === "fail") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "隔离主题预览暂不可用" }) });
    const response = await route.fetch(); await delayed;
    await route.fulfill({ response }).catch(() => undefined); // The obsolete request may already be cancelled.
  });
  try {
    await select.selectOption("");
    await expect(preview.getByRole("status")).toContainText("正在读取当前对象的受控预览");
    await expect(preview.locator('[data-module-id="topic-quote"]')).toHaveCount(0);
    await select.selectOption(savedQuote);
    await expect(preview.locator('[data-module-id="topic-quote"]')).toContainText(data.featured_quote!.source.text); release();
    mode = "fail"; await select.selectOption("");
    await expect(preview.getByRole("alert")).toContainText("本次选择尚未核对");
    mode = "pass"; await page.getByRole("button", { name: "重新核对预览", exact: true }).click();
    await expect(preview.locator('[data-module-id="topic-identity"]')).toContainText(data.name);
    await expect(preview.locator('[data-module-id="topic-quote"]')).toHaveCount(0);
    expect((await detail(page)).featured_quote?.id).toBe(savedQuote);
  } finally { release(); }
});
