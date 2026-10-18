import { expect, test, type Page } from "@playwright/test";

// Synthetic API fixtures only. Run with the other acceptance tests after full implementation.
const planId = "10000000-0000-4000-8000-000000000001";
const itemId = "10000000-0000-4000-8000-000000000002";
const sample = () => ({ id: planId, revision: 1, status: "completed", enhancement_status: "not_requested",
  created_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:00:00Z",
  data: { goal: "测试计划问题", background: "", use_confirmed_memories: false, confirmed_memory_ids: [],
    planning_policy: { budget_minutes: 60, session_minutes: 30, reading_level: "beginner" },
    items: [{ id: itemId, work_id: itemId, title: "合成测试材料", stage: "初读", reason: "测试来源", status: "pending", available: false, estimated_minutes: 30 }],
    prerequisites: [] } });

async function mockPlan(page: Page) {
  const state = { owner: 1, record: sample(), writes: [] as Record<string, unknown>[], conflict: false };
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Test Reader", reading_preferences: {} });
    if (path === `/api/reading/reading-plans/${planId}/`) {
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        state.writes.push(body);
        if (state.conflict) return respond({ detail: "内容已更新，请保留输入并读取最新版本。" }, 409);
        if (body.preview) return respond(state.record);
        state.record = { ...state.record, revision: state.record.revision + 1 };
      }
      return respond(state.record);
    }
    if (path === "/api/reading/research-memories/") return respond({ count: 0, results: [], next: null });
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

test("plan preview does not write until confirmed and unavailable materials have no reader link", async ({ page }) => {
  const state = await mockPlan(page);
  await page.goto(`/account/plans/${planId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "我的阅读计划" })).toBeVisible();
  await expect(page.getByRole("link", { name: "开始阅读" })).toHaveCount(0);
  await page.getByRole("button", { name: "预览调整 →" }).click();
  await expect(page.getByRole("dialog", { name: "预览未完成部分的调整" })).toBeVisible();
  expect(state.writes).toEqual([{ expected_revision: 1, optimize_order: true, preview: true }]);
  await page.getByRole("button", { name: "保留当前计划" }).click();
  expect(state.record.revision).toBe(1);
  await page.getByRole("button", { name: "预览调整 →" }).click();
  await page.getByRole("button", { name: "应用调整并保存" }).click();
  await expect(page.getByText("已保存，计划安排已按当前规则更新。", { exact: true })).toBeVisible();
  expect(state.writes.at(-1)).toEqual({ expected_revision: 1, optimize_order: true });
});

test("plan settings keep the user's text after a revision conflict and never opt in memories by default", async ({ page }) => {
  const state = await mockPlan(page);
  await page.goto(`/account/plans/${planId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "计划设置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "设置阅读目标与时间" });
  await expect(dialog.getByRole("checkbox", { name: "使用选定的已确认笔记" })).not.toBeChecked();
  await dialog.getByLabel("用一个简短问题或主题，说明你希望通过阅读解决什么").fill("需要保留的本地问题");
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog.getByRole("alert")).toContainText("内容已更新");
  await expect(dialog.getByLabel("用一个简短问题或主题，说明你希望通过阅读解决什么")).toHaveValue("需要保留的本地问题");
  expect(state.writes.at(-1)?.use_confirmed_memories).toBe(false);
  expect(state.writes.at(-1)?.confirmed_memory_ids).toEqual([]);
});

test("private workspace rejects a changed cookie owner before reading a plan", async ({ page }) => {
  const state = await mockPlan(page);
  await page.goto(`/account/plans/${planId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("合成测试材料", { exact: true })).toBeVisible();
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "阅读计划暂时不可用" })).toBeVisible();
  await expect(page.getByText("合成测试材料", { exact: true })).toHaveCount(0);
});
