import { expect, test, type Page } from "@playwright/test";
import type { AdminFeedbackDetail, FeedbackHandlingInput } from "../lib/api/admin-feedback.client";

// Synthetic contracts only. Do not interpret these fixtures as live feedback or visual acceptance.
const id = "82000000-0000-4000-8000-000000000001", other = "82000000-0000-4000-8000-000000000002";
const stamp = "2026-10-18T00:00:00Z", base = "/api/catalog/admin/public-feedback/";

async function setup(page: Page) {
  const fixture = {
    owner: 1, denied: false, fail: 0, refreshes: 0, commands: [] as FeedbackHandlingInput[], queries: [] as string[],
    row: { id, category: "function", status: "submitted", excerpt: "合成反馈正文", body: "合成反馈正文：请核对分页。",
      created_at: stamp, updated_at: stamp, revision: 1, follow_up: false, contact: "synthetic@example.invalid", path: "/help", consent_at: stamp,
      consent_version: "feedback-processing-20261018", note: "", handled_by: "", can_follow_up: true,
      history: { count: 0, page: 1, page_size: 10, results: [] }, source: { status: "page", canonical_path: "/help", title: "使用帮助与反馈", authors: [],
        cover_url: "", source_type: "", version_label: "", location: "", updated_at: null, checked_at: stamp, reader_url: "", notice: "合成站内页面" } } as AdminFeedbackDetail,
  };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const response = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return response({ id: fixture.owner, role: "admin", display_name: "Synthetic", capabilities: ["access_back_office", "can_manage_users"], reading_preferences: {} });
    if (path === "/api/auth/token/refresh/") { fixture.refreshes += 1; return response({ detail: "合成会话不可刷新" }, 401); }
    if (path.startsWith(base) && fixture.denied) return response({ detail: "合成权限已撤销" }, 403);
    if (path === base) {
      fixture.queries.push(url.search);
      const pageNumber = Number(url.searchParams.get("page") || 1);
      return response({ count: 21, page: pageNumber, page_size: 20, counts: { total: 21, submitted: 20, reviewing: 1, resolved: 0 },
        results: [{ ...fixture.row, ...(pageNumber === 2 ? { id: other, excerpt: "合成第二页反馈" } : {}) }] });
    }
    if (path === `${base}${id}/`) {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON() as FeedbackHandlingInput; fixture.commands.push(body);
        if (fixture.fail) return response({ detail: "合成保存暂不可确认" }, fixture.fail);
        if (body.expected_revision !== fixture.row.revision) return response({ detail: "合成记录已变化" }, 409);
        fixture.row = { ...fixture.row, ...body, revision: fixture.row.revision + 1, handled_by: "合成管理员" };
        return response({ request_id: body.request_id, accepted_revision: fixture.row.revision, record: fixture.row });
      }
      return response(fixture.row);
    }
    return response({ count: 0, results: [] });
  });
  await page.goto("/admin/support/feedback", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "反馈处理", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "反馈列表", exact: true })).toContainText("合成反馈正文");
  return fixture;
}

async function selectFirst(page: Page) {
  await page.getByRole("region", { name: "反馈列表", exact: true }).getByRole("button", { name: /合成反馈正文/ }).click();
  await expect(page.getByRole("heading", { name: "反馈详情", exact: true })).toBeVisible();
}

test("server totals and pagination are independent of the visible page", async ({ page }) => {
  const fixture = await setup(page);
  await expect(page.getByRole("navigation", { name: "反馈状态" })).toContainText("全部反馈21");
  await page.getByRole("navigation", { name: "反馈列表分页" }).getByRole("button", { name: "下一页" }).click();
  await expect(page.getByRole("region", { name: "反馈列表", exact: true })).toContainText("合成第二页反馈");
  expect(fixture.queries.some(query => query.includes("page=2"))).toBeTruthy();
});

test("unknown save freezes input and retries the same nonce and revision", async ({ page }) => {
  const fixture = await setup(page); await selectFirst(page); fixture.fail = 503;
  await page.getByLabel("处理说明", { exact: true }).fill("合成处理：已核对分页");
  await page.getByRole("button", { name: "保存处理记录", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible();
  await expect(page.getByLabel("处理说明", { exact: true })).toBeDisabled();
  fixture.fail = 0;
  await page.getByRole("button", { name: "重试原请求", exact: true }).click();
  await expect(page.getByText("处理记录已保存。", { exact: true })).toBeVisible();
  expect(fixture.commands).toHaveLength(2);
  expect(fixture.commands[0].request_id).toBe(fixture.commands[1].request_id);
  expect(fixture.commands[0].expected_revision).toBe(fixture.commands[1].expected_revision);
});

for (const status of [408, 429]) test(`intermediary ${status} keeps the handling nonce for retry`, async ({ page }) => {
  const fixture = await setup(page); await selectFirst(page); fixture.fail = status;
  await page.getByLabel("处理说明", { exact: true }).fill("合成处理：等待原请求确认");
  await page.getByRole("button", { name: "保存处理记录", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible();
  fixture.fail = 0;
  await page.getByRole("button", { name: "重试原请求", exact: true }).click();
  await expect(page.getByText("处理记录已保存。", { exact: true })).toBeVisible();
  expect(fixture.commands).toHaveLength(2);
  expect(fixture.commands[1]).toEqual(fixture.commands[0]);
});

test("a rejected admin mutation is not silently replayed after authentication refresh", async ({ page }) => {
  const fixture = await setup(page); await selectFirst(page); fixture.fail = 401;
  await page.getByLabel("处理说明", { exact: true }).fill("合成处理：会话即将失效");
  await page.getByRole("button", { name: "保存处理记录", exact: true }).click();
  await expect(page.getByLabel("处理说明", { exact: true })).toHaveCount(0);
  expect(fixture.commands).toHaveLength(1);
  expect(fixture.refreshes).toBe(0);
});

test("concurrent handling keeps input until the new revision is explicitly acknowledged", async ({ page }) => {
  const fixture = await setup(page); await selectFirst(page);
  await page.getByLabel("处理说明", { exact: true }).fill("合成未保存说明");
  fixture.row = { ...fixture.row, revision: 2, note: "另一位管理员的合成说明", status: "reviewing" };
  await page.getByRole("button", { name: "保存处理记录", exact: true }).click();
  await expect(page.getByText("其他管理员已修改此记录。你的输入仍保留，请核对最新处理后再继续。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("处理说明", { exact: true })).toHaveValue("合成未保存说明");
  await expect(page.getByRole("button", { name: "保存处理记录", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "已核对，保留输入并采用最新修订", exact: true }).click();
  await page.getByRole("button", { name: "保存处理记录", exact: true }).click();
  expect(fixture.commands[1].expected_revision).toBe(2);
});

test("session changes remove contact and retained draft before another owner reads", async ({ page }) => {
  const fixture = await setup(page); await selectFirst(page);
  await page.getByLabel("处理说明", { exact: true }).fill("合成私有草稿");
  fixture.owner = 2; fixture.denied = true;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByText("synthetic@example.invalid", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("处理说明", { exact: true })).toHaveCount(0);
  expect(fixture.commands).toHaveLength(0);
});

test("an unavailable private source is never offered as a clickable context link", async ({ page }) => {
  const fixture = await setup(page); fixture.row.path = ""; fixture.row.source = { ...fixture.row.source, status: "unavailable", canonical_path: "", title: "来源当前不可用" };
  await selectFirst(page);
  await expect(page.getByRole("link", { name: "查看公开页面" })).toHaveCount(0);
  await expect(page.getByText("未提供可用的公开页面", { exact: true })).toBeVisible();
});
