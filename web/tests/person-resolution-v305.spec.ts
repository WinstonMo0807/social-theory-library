import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const api = "http://127.0.0.1:8105/api/catalog/admin/people";
const source = (index: number) => `30500000-0000-4000-8000-${String(index).padStart(11, "0")}1`;
const target = (index: number) => `30500000-0000-4000-8000-${String(index).padStart(11, "0")}2`;
const pairUrl = (index: number) => `/admin/people?source=${source(index)}&target=${target(index)}`;

async function runtime(page: Page) {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
}

test.beforeEach(async ({ page }) => { await runtime(page); });

async function login(page: Page, role = "owner") {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

async function review(page: Page, index: number) {
  await page.goto(pairUrl(index));
  await expect(page.getByRole("button", { name: "核对完成，准备合并", exact: true })).toBeEnabled();
}

async function merge(page: Page) {
  await page.getByRole("button", { name: "核对完成，准备合并", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "确认合并人物", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认是同一人物并合并", exact: true }).click();
}

for (const role of ["curator", "administrator"]) {
  test(`${role} can discover unprofiled people but never requests owner-only preview`, async ({ page }) => {
    const protectedRequests: string[] = [];
    page.on("request", (request) => { if (/\/people\/.*(?:merge-preview|merge-records)/.test(request.url())) protectedRequests.push(request.url()); });
    await login(page, role);
    await page.goto("/admin/people");
    await page.getByRole("textbox", { name: "查找馆内人物", exact: true }).fill("E2E网络重试来源");
    await page.getByRole("button", { name: "查找", exact: true }).click();
    await page.getByRole("link", { name: /E2E网络重试来源.*检查重复记录/ }).click();
    await expect(page.getByRole("region", { name: "疑似重复人物", exact: true })).toContainText("E2E网络重试保留");
    await page.goto(pairUrl(3));
    await expect(page.getByText("当前账户可以查重。影响预览、合并与撤回仅向书库所有者开放。", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "核对完成，准备合并" })).toHaveCount(0);
    expect(protectedRequests).toEqual([]);
    expect((await page.request.get(`${api}/${source(3)}/merge-preview/?target_person=${target(3)}`)).status()).toBe(403);
  });
}

test("owner sees conflicts and cannot force two scholar profiles into one", async ({ page }) => {
  await login(page);
  await page.goto(pairUrl(2));
  await expect(page.getByRole("region", { name: "合并影响预览", exact: true })).toContainText("双方都有学者档案");
  await expect(page.getByRole("button", { name: "核对完成，准备合并", exact: true })).toBeDisabled();
  const result = await page.request.get(`${api}/${source(2)}/duplicates/`);
  expect((await result.json()).source.authority_status).toBe("verified");
});

test("owner merges, reloads the saved operation and rolls back through the real API", async ({ page }) => {
  const serverErrors: string[] = [];
  page.on("response", (response) => { if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`); });
  await login(page);
  await review(page, 1);
  const business = page.getByRole("region", { name: "作品职责与公开位置", exact: true });
  await expect(business.getByText("E2E完整操作作品", { exact: true })).toBeVisible();
  await expect(business).toContainText("作者");
  await expect(business.getByRole("link", { name: "核对当前版本与署名", exact: true })).toHaveAttribute("href", /edition=[a-f0-9-]+#contributors/);
  const preview = page.getByRole("region", { name: "合并影响预览", exact: true });
  await preview.getByText("规范名称变体", { exact: false }).click();
  await expect(preview.getByText("E2E完整操作旧译名", { exact: true })).toBeVisible();
  await mkdir("output/playwright", { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1080 });
  await preview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "output/playwright/person-merge-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await preview.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "output/playwright/person-merge-mobile.png" });
  await page.setViewportSize({ width: 1440, height: 1080 });
  await merge(page);
  await expect(page).toHaveURL(/record=[a-f0-9-]+/);
  await expect(page.getByRole("heading", { name: "人物合并已记录", exact: true })).toBeVisible();
  const url = page.url();
  const recordId = new URL(url).searchParams.get("record");
  const merged = await page.request.get(`${api}/${source(1)}/duplicates/`);
  expect((await merged.json()).source.authority_status).toBe("merged");
  await page.reload();
  await expect(page.getByRole("button", { name: "准备撤回本次合并", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "准备撤回本次合并", exact: true }).click();
  await page.getByRole("button", { name: "确认撤回本次合并", exact: true }).click();
  await expect(page.getByRole("heading", { name: "本次合并已撤回", exact: true })).toBeVisible();
  const restored = await page.request.get(`${api}/${source(1)}/duplicates/`);
  expect((await restored.json()).source.authority_status).toBe("verified");
  const operation = await page.request.get(`${api}/merge-records/${recordId}/`);
  expect((await operation.json()).status).toBe("rolled_back");
  await page.goto(`/admin/people?source=${source(1)}`);
  await expect(page.getByRole("link", { name: /已撤回的合并/ })).toHaveAttribute("href", new URL(url).pathname + new URL(url).search);
  expect(serverErrors).toEqual([]);
});

test("a lost successful response retries exactly the same merge and preserves one history record", async ({ page }) => {
  await login(page);
  await review(page, 3);
  const bodies: unknown[] = [];
  const mergeUrl = `**/people/${source(3)}/merge/`;
  await page.route(mergeUrl, async (route) => {
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed"); // Committed API result is deliberately lost.
    } else await route.continue();
  });
  await merge(page);
  await expect(page.getByRole("button", { name: "重试同一次合并", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "核对完成，准备合并", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "刷新操作记录", exact: true }).click();
  await expect(page.getByRole("link", { name: /已执行的合并/ })).toBeVisible();
  await page.getByRole("button", { name: "重试同一次合并", exact: true }).click();
  await expect(page).toHaveURL(/record=[a-f0-9-]+/);
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toEqual(bodies[1]);
  const history = await page.request.get(`${api}/merge-records/?source_person=${source(3)}`);
  expect(await history.json()).toHaveLength(1);
});

test("a stale browser preview cannot repeat a merge committed from another tab", async ({ page, context }) => {
  await login(page);
  await review(page, 4);
  const other = await context.newPage();
  await runtime(other);
  await review(other, 4);
  await merge(other);
  await expect(other).toHaveURL(/record=[a-f0-9-]+/);
  await merge(page);
  await expect(page.getByRole("button", { name: "重新预览并核对", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "合并影响预览", exact: true })).toContainText("人物或引用已变化");
  await page.getByRole("button", { name: "重新预览并核对", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对完成，准备合并", exact: true })).toBeDisabled();
  const history = await page.request.get(`${api}/merge-records/?source_person=${source(4)}`);
  expect(await history.json()).toHaveLength(1);
  await other.close();
});

test("failed duplicate discovery stays an error and retries instead of showing no duplicates", async ({ page }) => {
  await login(page, "curator");
  const path = `**/people/${source(1)}/duplicates/**`;
  await page.route(path, (route) => route.abort("failed"));
  await page.goto(`/admin/people?source=${source(1)}`);
  await expect(page.getByRole("alert")).toContainText("无法连接书库服务");
  await expect(page.getByText("未找到名称或标识符匹配的其他人物。这不代表馆内没有重复记录。", { exact: true })).toHaveCount(0);
  await page.unroute(path);
  await page.getByRole("button", { name: "重新读取", exact: true }).click();
  await expect(page.getByRole("region", { name: "疑似重复人物", exact: true })).toContainText("E2E完整操作保留");
});

test("a lost rollback response is resolved by rereading the operation without repeating the write", async ({ page }) => {
  await login(page);
  await review(page, 5);
  await merge(page);
  await expect(page).toHaveURL(/record=[a-f0-9-]+/);
  const recordId = new URL(page.url()).searchParams.get("record");
  await expect(page.getByRole("button", { name: "准备撤回本次合并", exact: true })).toBeEnabled();
  let calls = 0;
  await page.route(`**/people/merge-records/${recordId}/rollback/`, async (route) => {
    calls += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await page.getByRole("button", { name: "准备撤回本次合并", exact: true }).click();
  await page.getByRole("button", { name: "确认撤回本次合并", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请重新读取操作");
  await expect(page.getByRole("button", { name: "准备撤回本次合并", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "重新读取操作及撤回条件", exact: true }).click();
  await expect(page.getByRole("heading", { name: "本次合并已撤回", exact: true })).toBeVisible();
  expect(calls).toBe(1);
  const restored = await page.request.get(`${api}/${source(5)}/duplicates/`);
  expect((await restored.json()).source.authority_status).toBe("verified");
});
