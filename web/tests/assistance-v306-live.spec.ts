import { expect, test, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api";
const scholarId = "30600000-0000-4000-8000-000000000611";
const candidateId = (last: string) => `30600000-0000-4000-8000-00000000062${last}`;
async function login(page: Page, role = "owner") {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
}

test("A15 A24 A32 real candidate decisions preserve reasons, draft isolation and event denominator", async ({ page, browser, baseURL }, info) => {
  test.setTimeout(120_000);
  await login(page);
  await page.goto(`/admin/knowledge?object_type=scholar&object_id=${scholarId}`);
  await page.locator("#studio-fields > summary").click();
  const field = page.locator("#studio-fields > .knowledge-studio-list > article").filter({ has: page.locator("header > strong", { hasText: /^机构$/ }) });
  await field.getByRole("button", { name: "查找建议", exact: true }).click();
  const popover = field.getByRole("region", { name: "机构建议", exact: true });
  const reject = popover.locator(":scope > article").filter({ hasText: "待拒绝测试单位" });
  await reject.getByRole("button", { name: "不采用", exact: true }).click();
  await reject.getByRole("combobox", { name: "不采用理由", exact: true }).selectOption("other");
  await expect(reject.getByRole("button", { name: "确认不采用并记录理由" })).toBeDisabled();
  await reject.getByRole("button", { name: "取消", exact: true }).click();
  expect((await (await page.request.get(`${api}/catalog/admin/field-enrichment/candidates/${candidateId("2")}/`)).json()).status).toBe("pending");
  await reject.getByRole("button", { name: "不采用", exact: true }).click();
  await reject.getByRole("combobox", { name: "不采用理由", exact: true }).selectOption("person_mismatch");
  await reject.getByLabel("补充说明（可选）", { exact: true }).fill("资料属于同名的另一位学者");
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const button = reject.getByRole("button", { name: "确认不采用并记录理由" });
    await button.scrollIntoViewIfNeeded();
    await button.click({ trial: true });
    expect(await reject.evaluate((root) => [...root.querySelectorAll("select, textarea, button")].every((el) => { const r=el.getBoundingClientRect(); return !r.width || r.left >= -1 && r.right <= innerWidth+1; }))).toBe(true);
    await page.screenshot({ path: info.outputPath(`candidate-reason-${width}.png`) });
  }
  const denied = page.waitForResponse((r) => r.url().endsWith(`/candidates/${candidateId("2")}/decision/`) && r.request().method() === "POST");
  await reject.getByRole("button", { name: "确认不采用并记录理由" }).click();
  const deniedResponse = await denied;
  expect(deniedResponse.status(), await deniedResponse.text()).toBe(200);
  expect((await deniedResponse.json()).review_reason).toBe("人物不符：资料属于同名的另一位学者");
  const adopt = popover.locator(":scope > article").filter({ hasText: "待采用测试单位" });
  const accepted = page.waitForResponse((r) => r.url().endsWith(`/candidates/${candidateId("1")}/decision/`) && r.request().method() === "POST");
  await adopt.getByRole("button", { name: "采用机构", exact: true }).click();
  const acceptedResponse = await accepted;
  expect(acceptedResponse.status(), await acceptedResponse.text()).toBe(200);
  expect((await (await page.request.get(`${api}/catalog/scholars/v306-assistance/`)).json()).affiliations).toEqual([]);
  await page.reload();
  const history = page.locator(".assistance-history");
  await history.locator(":scope > summary").click();
  await expect(history).toContainText("处理过的 2 条建议中，采用了 1 条");
  await expect(history).toContainText("不表示建议内容一定正确");
  await history.getByText("追溯候选与人工复核记录", { exact: true }).click();
  const record = history.locator("article").filter({ hasText: candidateId("2") });
  await expect(record).toContainText("人物不符：资料属于同名的另一位学者");
  const detail = page.waitForResponse((r) => r.url().endsWith(`/candidates/${candidateId("2")}/`) && r.request().method() === "GET");
  await record.getByRole("button", { name: "读取原始候选" }).click();
  expect((await detail).status()).toBe(200);
  await expect(history.locator('div[aria-live="polite"]')).toContainText("人物不符：资料属于同名的另一位学者");
  await expect(history).toContainText("相关操作事件 2 条");
  expect((await (await page.request.get(`${api}/catalog/admin/field-enrichment/candidates/${candidateId("3")}/`)).json()).status).toBe("pending");
  const readerContext = await browser.newContext({ baseURL });
  try {
    await login(await readerContext.newPage(), "reader");
    expect((await readerContext.request.get(`${api}/catalog/admin/field-enrichment/candidates/${candidateId("2")}/`)).status()).toBe(403);
  } finally { await readerContext.close(); }
});

test("A15 manual cataloging shows a new candidate without replacing a locked value and records rejection", async ({ page }) => {
  await login(page);
  const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=${encodeURIComponent("V306人工锁与建议")}`)).json();
  expect(list.count).toBe(1);
  const work = list.results[0];
  await page.goto(`/admin/library/works/${work.id}?edition=${work.primary_edition.id}#work`);
  await expect(page.getByLabel("馆藏简介", { exact: true })).toHaveValue("人工保留的简介");
  await page.getByRole("button", { name: "查找简介", exact: true }).click();
  const panel = page.getByRole("region", { name: "简介建议", exact: true });
  await expect(panel).toContainText("来源未支持的新简介");
  await expect(page.getByLabel("馆藏简介", { exact: true })).toHaveValue("人工保留的简介");
  await panel.getByRole("button", { name: "不采用", exact: true }).click();
  await panel.getByRole("combobox", { name: "不采用理由", exact: true }).selectOption("unreliable_source");
  const saved = page.waitForResponse((r) => r.url().endsWith("/field-assistant/reject/") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "确认不采用并记录理由" }).click();
  const response = await saved;
  expect(response.status(), await response.text()).toBe(200);
  expect(response.request().postDataJSON().reason).toBe("来源不可靠");
  await expect(panel).toContainText("已记录不采用：来源不可靠");
  await page.reload();
  await expect(page.getByLabel("馆藏简介", { exact: true })).toHaveValue("人工保留的简介");
});

test("A23 expired health stays unknown and reading failures recover without triggering probes", async ({ page }) => {
  await login(page);
  const writes: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/functional-health/") && request.method() === "POST") writes.push(request.url()); });
  const observed = page.waitForResponse((r) => r.url().endsWith("/functional-health/") && r.request().method() === "GET");
  await page.goto("/admin/processing");
  const response = await observed;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.overall_status).toBe("unknown");
  expect(body.page_load_performs_live_probes).toBe(false);
  expect(body.capabilities.flatMap((row: { dependencies: Array<{ stale: boolean }> }) => row.dependencies).every((row: { stale: boolean }) => row.stale)).toBe(true);
  const panel = page.locator(".functional-health-panel");
  await expect(panel.getByText("整体待检查", { exact: true })).toBeVisible();
  await page.route("**/api/catalog/admin/functional-health/", (route) => route.abort("failed"));
  await panel.getByRole("button", { name: "刷新结果", exact: true }).click();
  await expect(panel.getByRole("button", { name: "重新刷新", exact: true })).toBeVisible();
  await expect(panel.getByText("整体待检查", { exact: true })).toBeVisible();
  await page.unroute("**/api/catalog/admin/functional-health/");
  const recovered = page.waitForResponse((r) => r.url().endsWith("/functional-health/") && r.ok());
  await panel.getByRole("button", { name: "重新刷新", exact: true }).click();
  expect((await recovered).status()).toBe(200);
  await expect(panel.getByRole("button", { name: "刷新结果", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "故障与恢复", exact: true }).click();
  await expect(panel.getByText("已过期，待重新检测", { exact: true }).first()).toBeVisible();
  expect(writes).toEqual([]);
});
