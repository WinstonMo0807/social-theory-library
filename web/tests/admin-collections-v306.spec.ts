import { expect, test, type Page, type Route } from "@playwright/test";

// HTTP responses in this suite are explicit fixtures: this verifies real built
// page interaction/request contracts, not PostgreSQL, Worker or production.
const uuid = (value: number) => `00000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const publication = (index: number) => ({ editorial_state: "published", public_state: index % 3 === 0 ? "published" : "unpublished", catalog_revision_active: index % 3 === 0, listed_publicly: index % 3 === 0, public_url: index % 3 === 0 ? `/works/book-${index}` : "", detail: index % 3 === 0 ? "有效公开修订已生效" : "尚无有效公开修订", fulltext_ready: false });
const works = Array.from({ length: 41 }, (_, index) => ({ row_type: "work", id: uuid(index + 1), work_id: uuid(index + 1), title: `分页馆藏 ${String(index + 1).padStart(3, "0")} 长中文题名`, document_type: index % 2 ? "journal_article" : "book", language: "zh-CN", contributors: ["第一作者", "SecondAuthorWithLongUnbrokenName", "第三作者"], edition_count: 2, primary_edition: { id: uuid(index + 1001), label: "当前主版本 2026" }, publication: publication(index), health: { editorial: "ready", processing: "partial", publication: index % 3 === 0 ? "published" : "unpublished" }, asset_state: "ready", knowledge_status: "attention", curation_status: "attention", workbench_url: `/admin/library/works/${uuid(index + 1)}?edition=${uuid(index + 1001)}`, updated_at: "2026-09-13T04:00:00Z" }));
const queues = Array.from({ length: 65 }, (_, index) => ({ id: `edition:${uuid(index + 1001)}`, item_id: index % 3 === 0 ? uuid(index + 2001) : null, work_id: uuid(index + 1), edition_id: uuid(index + 1001), session_id: uuid(index + 3001), title: index === 64 ? "较早的文件校验异常" : `统一来源 ${String(index + 1).padStart(3, "0")}`, source_filename: index % 3 === 0 ? `original-${index}.pdf` : "", source_type: ["upload", "manual", "existing"][index % 3], workbench_url: `/admin/library/works/${uuid(index + 1)}?edition=${uuid(index + 1001)}`, publication: publication(index), current_step: index === 64 ? "file" : "work", current_step_label: index === 64 ? "核对文件校验" : "书目信息", overall_status: "attention", blockers_count: index === 64 ? 1 : 0, warnings_count: 1, unresolved_count: 1, updated_at: "2026-09-01T04:00:00Z" }));

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function paginate<T>(rows: T[], url: URL, pageSize: number) {
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(totalPages, Math.max(1, Number(url.searchParams.get("page") || 1)));
  return { count: rows.length, page, page_size: pageSize, total_pages: totalPages, next: page < totalPages ? "next" : null, previous: page > 1 ? "previous" : null, ordering: "-updated_at,id", results: rows.slice((page - 1) * pageSize, page * pageSize) };
}

async function setup(page: Page, options: { unauthenticated?: boolean; invalidWorkspace?: boolean } = {}) {
  const requests: URL[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    requests.push(url);
    const path = url.pathname;
    if (path === "/api/auth/me/") return json(route, options.unauthenticated ? { detail: "会话过期" } : { id: 1, role: "admin", display_name: "测试管理员", email: "admin@example.test", capabilities: ["access_back_office", "can_edit_metadata", "can_publish_work", "can_withdraw_work", "can_view_system_status", "can_view_audit_log", "can_configure_providers", "can_manage_ai", "can_manage_search_runtime", "can_manage_users", "can_view_query_lexicon", "can_view_semantic_index"], reading_preferences: {} }, options.unauthenticated ? 401 : 200);
    if (path === "/api/auth/token/refresh/") return json(route, {}, options.unauthenticated ? 401 : 200);
    if (path === "/api/catalog/admin/library/works/") {
      let rows = [...works];
      const workId = url.searchParams.get("work_id");
      const query = url.searchParams.get("q");
      if (workId) rows = rows.filter((row) => row.id === workId);
      if (query) rows = rows.filter((row) => row.title.includes(query));
      if (url.searchParams.get("document_type")) rows = rows.filter((row) => row.document_type === url.searchParams.get("document_type"));
      if (url.searchParams.get("ordering") === "-title") rows.reverse();
      if (url.searchParams.get("view") === "editions") return json(route, paginate(rows.flatMap((row) => [0, 1].map((version) => ({ ...row, row_type: "edition", id: uuid(Number(row.id.slice(-12)) + 1000 + version * 100), edition_id: uuid(Number(row.id.slice(-12)) + 1000 + version * 100), label: version ? "历史出版版本" : "当前主版本", is_primary: !version, publication: version ? { ...row.publication, public_state: "published", catalog_revision_active: true, listed_publicly: false, public_url: "" } : row.publication, workbench_url: `/admin/library/works/${row.id}?edition=${uuid(Number(row.id.slice(-12)) + 1000 + version * 100)}`, assets: ["pending", "valid", "invalid"].map((state, assetIndex) => ({ id: uuid(assetIndex + version * 100 + 9000), kind: "original", version: assetIndex + 1, status: "ready", validation_status: state, is_current: assetIndex === 1, original_filename: `保留历史原件-${state}.pdf`, page_count: 100, updated_at: row.updated_at })), current_reader_asset: null }))), url, 40));
      return json(route, paginate(rows, url, 40));
    }
    if (path === "/api/catalog/admin/workflows/queue/") {
      let rows = [...queues];
      if (url.searchParams.get("source")) rows = rows.filter((row) => row.source_type === url.searchParams.get("source"));
      if (url.searchParams.get("q")) rows = rows.filter((row) => row.title.includes(url.searchParams.get("q")!));
      if (url.searchParams.get("publication")) rows = rows.filter((row) => row.publication.public_state === url.searchParams.get("publication"));
      const counts = { all: rows.length, continue: rows.length, attention: rows.length, exception: rows.filter((row) => row.blockers_count).length, publication_ready: 0 };
      if (url.searchParams.get("category") === "exception") rows = rows.filter((row) => row.blockers_count);
      return json(route, { ...paginate(rows, url, 20), counts, continue_items: rows.slice(0, 12), attention_items: rows.slice(0, 12), exception_items: rows.filter((row) => row.blockers_count).slice(0, 12), publication_ready: [], recent_items: rows.slice(0, 12), candidate_review_count: 0 });
    }
    if (/\/api\/catalog\/admin\/library\/works\/[^/]+\/$/.test(path)) return json(route, { context: { work_id: options.invalidWorkspace ? uuid(99999) : path.split("/").at(-2), edition_id: url.searchParams.get("edition"), title: "指定版本" }, data: { work: { title: "指定版本" }, bibliography: {}, contributors: { items: [] }, classification: {}, knowledge: {} } });
    if (path.endsWith("/publication/prepare/")) return json(route, { changes: [], blocking: [], warnings: [], background_processing: [] });
    if (path === "/api/ingestion/dashboard/") return json(route, { documents: { total: 41, published: 14, withdrawn: 0 }, pdf_assets: 41, theory_schools: 0, scholars: 0, users: 1, needs_review: 0, processing: 0, recent_items: [], status_counts: {} });
    if (path === "/api/catalog/admin/usage-analytics/") return json(route, { anonymous_sessions: 0, events: {}, zero_result_searches: 0 });
    return json(route, { count: 0, results: [] });
  });
  return requests;
}

test("A11 41 works can be traversed with server paging and exact-version return links", async ({ page }) => {
  const requests = await setup(page);
  await page.goto("/admin/library?ordering=title");
  const list = page.getByRole("region", { name: "馆藏作品列表" });
  await expect(list.locator("article[data-record-id]")).toHaveCount(40);
  const firstPageIds = await list.locator("article[data-record-id]").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-record-id")));
  await page.getByRole("navigation", { name: "馆藏分页" }).getByRole("link", { name: "下一页" }).click();
  await expect(page).toHaveURL(/ordering=title.*page=2/);
  await expect(list.locator("article[data-record-id]")).toHaveCount(1);
  await expect(list.getByText("分页馆藏 041 长中文题名", { exact: true })).toBeVisible();
  const lastId = await list.locator("article[data-record-id]").getAttribute("data-record-id");
  expect(new Set([...firstPageIds, lastId]).size).toBe(41);
  const edit = new URL((await list.getByRole("link", { name: "编辑当前版本" }).getAttribute("href"))!, page.url());
  expect(edit.searchParams.get("edition")).toBe(uuid(1041));
  expect(edit.searchParams.get("return_to")).toContain("ordering=title&page=2");
  await page.goBack();
  await expect(list.locator("article[data-record-id]")).toHaveCount(40);
  expect(requests.some((url) => url.searchParams.get("page") === "2" && url.searchParams.get("ordering") === "title")).toBeTruthy();
});

test("A10 older anomaly after 31 tasks remains visible through server filtering", async ({ page }) => {
  const requests = await setup(page);
  await page.goto("/admin/review");
  await expect(page.getByRole("region", { name: "待办记录" }).locator("article")).toHaveCount(20);
  await page.getByRole("combobox", { name: "待办类型", exact: true }).selectOption("exception");
  await expect(page.getByText("较早的文件校验异常", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "待办记录" }).locator("article")).toHaveCount(1);
  await expect(page.getByRole("status").filter({ hasText: "当前条件共 1 项" })).toBeVisible();
  expect(requests.some((url) => url.pathname.endsWith("/workflows/queue/") && url.searchParams.get("category") === "exception")).toBeTruthy();
});

test("A12 publication desk spans API pages and includes manual and maintenance sources", async ({ page }) => {
  const requests = await setup(page);
  await page.goto("/admin/publication?source=manual");
  const list = page.getByRole("region", { name: "馆藏发布列表" });
  await expect(list.locator("article")).toHaveCount(20);
  await page.getByRole("navigation", { name: "发布列表分页" }).getByRole("link", { name: "下一页" }).click();
  await expect(list.locator("article")).toHaveCount(2);
  await expect(page.getByRole("status").filter({ hasText: "当前完整筛选共 22 项" })).toBeVisible();
  await page.getByRole("combobox", { name: "来源", exact: true }).selectOption("existing");
  await expect(list.locator("article")).toHaveCount(20);
  expect(requests.some((url) => url.searchParams.get("scope") === "publication" && url.searchParams.get("source") === "manual" && url.searchParams.get("page") === "2")).toBeTruthy();
  expect(requests.some((url) => url.searchParams.get("source") === "existing")).toBeTruthy();
  expect(requests.some((url) => url.pathname === "/api/ingestion/items/")).toBeFalsy();
});

test("A03 selected missing or mismatched identity never substitutes a different work", async ({ page }) => {
  await setup(page, { invalidWorkspace: true });
  await page.goto(`/admin/publication?selection=edition:${uuid(99999)}`);
  await expect(page.getByRole("alert").filter({ hasText: "未显示其他作品" })).toBeVisible();
  await expect(page.getByRole("region", { name: "当前版本公开预览" })).toHaveCount(0);
  await page.getByRole("region", { name: "馆藏发布列表" }).getByRole("link", { name: "预览与影响" }).first().click();
  await expect(page.getByRole("alert").filter({ hasText: "返回内容与指定作品或出版版本不一致" })).toBeVisible();
  await expect(page.getByRole("region", { name: "当前版本公开预览" })).toHaveCount(0);
});

test("A31 six task groups and Owner-only entries follow actual capabilities", async ({ page }) => {
  await setup(page);
  await page.goto("/admin/library");
  const nav = page.getByRole("complementary", { name: "后台导航" });
  for (const label of ["待办与上架", "馆藏", "知识与关联", "公开展示", "处理与服务", "系统管理"]) await expect(nav.locator(".admin-nav-group > summary").filter({ hasText: new RegExp(`^${label}$`) })).toBeVisible();
  await nav.locator("summary").filter({ hasText: /^系统管理$/ }).click();
  await expect(nav.getByRole("link", { name: "文件存储", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "备份", exact: true })).toHaveCount(0);
  await expect(nav.getByText("API 已连接", { exact: true })).toHaveCount(0);
});

test("A31 login redirect preserves Edition, return query and active section", async ({ page }) => {
  await setup(page, { unauthenticated: true });
  const target = `/admin/library/works/${uuid(1)}?edition=${uuid(1001)}&return_to=%2Fadmin%2Flibrary%3Fpage%3D2#file`;
  await page.goto(target);
  await expect(page).toHaveURL(/\/login\?next=/);
  expect(new URL(page.url()).searchParams.get("next")).toBe(target);
});

for (const width of [360, 390, 768, 1280, 1440]) {
  test(`A03/A04 edition files preserve content and keyboard access at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await setup(page);
    await page.goto(`/admin/library?view=editions&work_id=${uuid(1)}`);
    const list = page.getByRole("region", { name: "出版版本列表" });
    await expect(list.locator("article[data-row-type=edition]")).toHaveCount(2);
    await expect(list.getByText("PDF等待校验", { exact: true })).toHaveCount(2);
    await expect(list.getByText("PDF校验通过", { exact: true })).toHaveCount(2);
    await expect(list.getByText("PDF校验失败", { exact: true })).toHaveCount(2);
    await expect(list.getByText("已公开，作品列表显示其他版本", { exact: true })).toBeVisible();
    await expect(list.getByText("保留历史原件-invalid.pdf", { exact: true })).toHaveCount(2);
    const actions = list.getByRole("link", { name: "文件与阅读", exact: true });
    await actions.last().focus();
    await expect(actions.last()).toBeFocused();
    const href = new URL((await actions.last().getAttribute("href"))!, page.url());
    expect(href.searchParams.get("edition")).toBe(uuid(1101));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    const boxes = await actions.last().boundingBox();
    expect(boxes?.width).toBeGreaterThan(35);
    await page.screenshot({ path: testInfo.outputPath(`edition-files-${width}.png`), fullPage: true });
  });
}
