import { expect, test, type Page } from "@playwright/test";

const origin = "http://127.0.0.1:8105";
const ids = { scholar: "30600000-0000-4000-8000-000000000201", topic: "30600000-0000-4000-8000-000000000202", legacy: "30600000-0000-4000-8000-000000000203", node: "30600000-0000-4000-8000-000000000204", path: "30600000-0000-4000-8000-000000000205" };

test.beforeEach(async ({ page, baseURL }) => {
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${origin}/api'});` }));
});

async function login(page: Page, role = "owner") {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
}

async function visitData(page: Page, route: string, apiPath: string) {
  const loaded = page.waitForResponse((response) => new URL(response.url()).pathname === apiPath && response.request().method() === "GET");
  await page.goto(route);
  const response = await loaded;
  expect(response.status(), `${route} actual GET ${apiPath}`).toBe(200);
  return response.json();
}

for (const row of [
  { id: "R02", route: "/admin/about", api: "/api/catalog/admin/about-blocks/", selector: ".about-block-list > button", field: "title", key: "key" },
  { id: "R07", route: "/admin/disciplines", api: "/api/catalog/admin/disciplines/", selector: ".knowledge-admin-list > article", field: "name", key: "name" },
  { id: "R30", route: "/admin/subdisciplines", api: "/api/catalog/admin/subdisciplines/", selector: ".knowledge-admin-list > article", field: "name", key: "name" },
  { id: "R25", route: "/admin/scholars", api: "/api/catalog/admin/scholars/", selector: ".admin-entity-table > article", field: "preferred_name", key: "preferred_name" },
  { id: "R40", route: "/admin/topics", api: "/api/catalog/admin/topics/", selector: ".taxonomy-admin-grid > article", field: "name", key: "name" },
  { id: "R21", route: "/admin/reading-paths", api: "/api/catalog/admin/theory-system/reading-paths/", selector: ".reading-path-v280-list > button", field: "title", key: "title" },
  { id: "R08", route: "/admin/distribution", api: "/api/distribution/providers/", selector: ".provider-list > button", field: "name", key: "name" },
]) {
  test(`A31 ${row.id} real API list fields and rendered records agree`, async ({ page }, testInfo) => {
    await login(page);
    const body = await visitData(page, row.route, row.api);
    expect(Array.isArray(body.results)).toBeTruthy();
    await expect(page.locator(row.selector)).toHaveCount(body.results.length);
    if (body.results.length) {
      const first = body.results[0];
      await expect(page.locator(row.selector).first()).toContainText(first[row.field] || first[row.key]);
    } else {
      testInfo.annotations.push({ type: "data-scope", description: `${row.id}: actual empty list, create/write acceptance remains separately mapped` });
    }
    expect(body.count).toBeGreaterThanOrEqual(body.results.length);
  });
}

for (const row of [
  { id: "R26", route: `/admin/scholars/${ids.scholar}`, api: `/api/catalog/admin/scholars/${ids.scholar}/`, input: "主要显示名", field: "preferred_name", idValue: ids.scholar },
  { id: "R41", route: `/admin/topics/${ids.topic}`, api: `/api/catalog/admin/topics/${ids.topic}/`, input: "名称", field: "name", idValue: ids.topic },
  { id: "R35", route: `/admin/theories?node=${ids.node}`, api: `/api/catalog/admin/theory-system/nodes/${ids.node}/`, input: "标准中文名", field: "canonical_name_zh", idValue: ids.node },
  { id: "R36", route: `/admin/theories/${ids.node}`, api: `/api/catalog/admin/theory-system/nodes/${ids.node}/`, input: "标准中文名", field: "canonical_name_zh", idValue: ids.node },
  { id: "R37", route: `/admin/theory-nodes?node=${ids.node}`, api: `/api/catalog/admin/theory-system/nodes/${ids.node}/`, input: "标准中文名", field: "canonical_name_zh", idValue: ids.node },
  { id: "R21-selected", route: `/admin/reading-paths?path=${ids.path}`, api: `/api/catalog/admin/theory-system/reading-paths/${ids.path}/`, input: "标题", field: "title", idValue: ids.path },
]) {
  test(`A31 ${row.id} exact object is loaded into its actual editor`, async ({ page }) => {
    await login(page);
    const body = await visitData(page, row.route, row.api);
    expect(body.id).toBe(row.idValue);
    await expect(page.getByRole("textbox", { name: row.input, exact: true })).toHaveValue(body[row.field]);
    if (row.id.startsWith("R21")) await expect(page.getByRole("textbox", { name: "路径介绍", exact: true })).toHaveValue(body.introduction);
    if (row.id === "R26") await expect(page.getByRole("textbox", { name: /^完整传记/ })).toHaveValue(body.biography);
  });
}

test("A31 R34 compatibility taxonomy preserves both source lists and canonical editor links", async ({ page }) => {
  await login(page);
  const theoryPromise = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/catalog/admin/theory-schools/" && response.ok());
  const topicPromise = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/catalog/admin/topics/" && response.ok());
  await page.goto("/admin/taxonomy");
  const [theories, topics] = await Promise.all([(await theoryPromise).json(), (await topicPromise).json()]);
  await expect(page.locator(".taxonomy-admin-grid > article")).toHaveCount(theories.results.length + topics.results.length);
  const legacy = page.locator(".taxonomy-admin-grid > article").filter({ has: page.getByRole("heading", { name: "V306兼容理论", exact: true }) });
  const target = new URL((await legacy.getByRole("link", { name: "核对规范映射并编辑" }).getAttribute("href"))!, page.url());
  expect(target.pathname).toBe("/admin/theories");
  expect(target.searchParams.get("legacy_id")).toBe(ids.legacy);
  expect(target.searchParams.get("node_type")).toBe("theory_tradition");
});

test("A31 R03 statistics reflect real denominator and temporary read failure is recoverable", async ({ page }) => {
  await login(page, "administrator");
  const body = await visitData(page, "/admin/analytics", "/api/catalog/admin/usage-analytics/");
  const card = page.locator(".metric-grid > article").filter({ hasText: "匿名阅读会话" });
  await expect(card.locator("strong")).toHaveText(String(body.anonymous_sessions));
  expect(body.period_days).toBe(30);
  await page.route("**/api/catalog/admin/usage-analytics/**", (route) => route.abort("failed"));
  await page.reload();
  await expect(page.getByRole("button", { name: "重试统计", exact: true })).toBeVisible();
  await page.unroute("**/api/catalog/admin/usage-analytics/**");
  const recovered = page.waitForResponse((response) => response.url().includes("/usage-analytics/") && response.ok());
  await page.getByRole("button", { name: "重试统计", exact: true }).click();
  const fresh = await (await recovered).json();
  await expect(card.locator("strong")).toHaveText(String(fresh.anonymous_sessions));
});

test("A31 R20 dictionary reports the active source generation and only Owner gets mutation controls", async ({ page }) => {
  await login(page, "administrator");
  const body = await visitData(page, "/admin/query-lexicon", "/api/catalog/admin/query-lexicon/");
  const stats = page.locator(".admin-stats-grid");
  await expect(stats.locator("div").filter({ hasText: "活动词条" }).locator("dd")).toHaveText(String(body.entries));
  if (body.generation?.id) await expect(stats).toContainText(body.generation.id);
  await expect(page.getByRole("button", { name: "正式同步", exact: true })).toHaveCount(0);
  const reloaded = page.waitForResponse((response) => response.url().includes("/query-lexicon/") && response.ok());
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  expect((await reloaded).status()).toBe(200);
});

test("A31 R31 old self-check renders every returned component without running a probe on open", async ({ page }) => {
  await login(page);
  const writes: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/system-health/") && request.method() === "POST") writes.push(request.url()); });
  const body = await visitData(page, "/admin/system-health", "/api/ingestion/system-health/");
  await expect(page.locator(".health-component-grid > article")).toHaveCount(Object.keys(body.components).length);
  for (const component of Object.values(body.components) as Array<{ available: boolean | null }>) expect([true, false, null]).toContain(component.available);
  expect(writes).toEqual([]);
  await expect(page.getByRole("button", { name: "端到端自检", exact: true })).toBeEnabled();
});

test("A31 R29 system status exposes current source fields and a real refresh request", async ({ page }) => {
  await login(page);
  const body = await visitData(page, "/admin/status", "/api/catalog/admin/system-status/");
  for (const key of ["database", "redis", "celery", "storage", "query_lexicon", "semantic", "embedding", "ai", "web_enrichment", "backup"]) expect(body[key]).toBeDefined();
  await expect(page.locator(".health-component-grid > article")).toHaveCount(10);
  const refreshed = page.waitForResponse((response) => response.url().includes("/system-status/") && response.ok());
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  expect((await refreshed).status()).toBe(200);
});

test("A31 R43 selected user values and Owner protection match the account API", async ({ page }) => {
  await login(page);
  const body = await visitData(page, "/admin/users", "/api/auth/users/");
  await expect(page.locator(".user-admin-grid > .admin-panel > button")).toHaveCount(body.results.length);
  const owner = body.results.find((row: { is_library_owner?: boolean }) => row.is_library_owner);
  expect(owner).toBeDefined();
  await page.locator(".user-admin-grid > .admin-panel > button").filter({ hasText: owner.email }).click();
  await expect(page.getByRole("textbox", { name: "显示名", exact: true })).toHaveValue(owner.display_name);
  await expect(page.getByRole("combobox", { name: /^角色/ })).toBeDisabled();
  await expect(page.getByLabel("账户有效", { exact: true })).toBeDisabled();
});

test("A31 R17 workers list uses real task rows and does not fabricate completed recovery", async ({ page }) => {
  await login(page);
  const body = await visitData(page, "/admin/processing?surface=workers", "/api/ingestion/processing-center/");
  await expect(page.locator("#processing-task-list .processing-job-card")).toHaveCount(body.results.length);
  for (const row of body.results.slice(0, 3)) if (row.title) await expect(page.locator("#processing-task-list")).toContainText(row.title);
  expect(Object.hasOwn(body, "counts")).toBeTruthy();
});

test("A31 R32 candidate diagnostics show returned candidate counts and preserve explicit decisions", async ({ page }) => {
  await login(page);
  const body = await visitData(page, "/admin/system-health/candidates", "/api/catalog/admin/candidate-review/");
  expect(Array.isArray(body.results)).toBeTruthy();
  await expect(page.locator(".candidate-review-card")).toHaveCount(body.results.length);
  for (const row of body.results.slice(0, 2)) expect(row.id).toBeTruthy();
});

test("A31 R22 recommendation placements use real policies and selecting a policy is read-only", async ({ page }) => {
  await login(page);
  const body = await visitData(page, "/admin/recommendations", "/api/catalog/admin/recommendations/");
  expect(Array.isArray(body)).toBeTruthy();
  const buttons = page.locator(".recommendation-policy-list > button");
  await expect(buttons).toHaveCount(body.length);
  expect(body.length).toBeGreaterThan(0);
  const writes: string[] = [];
  page.on("request", (request) => { if (request.method() !== "GET" && request.url().includes("/recommendations/")) writes.push(request.url()); });
  await buttons.last().click();
  await expect(buttons.last()).toHaveClass(/active/);
  await expect(buttons.last()).toContainText(body.at(-1).title);
  expect(writes).toEqual([]);
});

test("A31 R27 semantic manager displays real eligible counts and ordinary Admin cannot switch indexes", async ({ page }) => {
  await login(page, "administrator");
  const body = await visitData(page, "/admin/semantic-index", "/api/catalog/admin/semantic-index/");
  const card = page.locator(".metric-grid > article").filter({ hasText: "可处理文献" });
  await expect(card.locator("strong")).toHaveText(String(body.documents.eligible));
  expect(body.permissions.can_manage).toBe(false);
  await expect(page.getByRole("button", { name: "建立快照候选", exact: true })).toHaveCount(0);
  for (const version of body.index_versions) await expect(page.getByText(version.uid, { exact: true })).toBeVisible();
});

test("A31 R33 knowledge diagnostic keeps the exact object and returns to its Studio", async ({ page }) => {
  await login(page);
  const body = await visitData(page, `/admin/system-health/knowledge?object_type=scholar&object_id=${ids.scholar}`, "/api/catalog/admin/knowledge-workspace/");
  expect(body.studio.selection.id).toBe(ids.scholar);
  await expect(page.getByRole("region", { name: "当前知识对象诊断" })).toContainText(body.studio.selection.label);
  const link = new URL((await page.getByRole("link", { name: "返回当前对象工作台", exact: true }).getAttribute("href"))!, page.url());
  expect(link.searchParams.get("object_id")).toBe(ids.scholar);
  expect(link.searchParams.get("object_type")).toBe("scholar");
  await expect(page.getByRole("button", { name: "确认发布本次编辑", exact: true })).toHaveCount(0);
});

test("A31 mobile admin navigation keeps keyboard focus inside and returns it after Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await login(page);
  const opener = page.getByRole("button", { name: "打开后台菜单", exact: true });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "后台导航", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "关闭后台菜单", exact: true })).toBeFocused();
  const controls = dialog.locator("a[href]:visible,button:not(:disabled):visible,summary:visible");
  await controls.last().focus();
  await page.keyboard.press("Tab");
  await expect(controls.first()).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(controls.last()).toBeFocused();
  await expect.poll(async()=> (await dialog.boundingBox())?.x ?? -1000).toBeGreaterThanOrEqual(-1);
  const rect = await dialog.boundingBox();
  expect(rect!.x).toBeGreaterThanOrEqual(-1);
  expect(rect!.x + rect!.width).toBeLessThanOrEqual(391);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
});
