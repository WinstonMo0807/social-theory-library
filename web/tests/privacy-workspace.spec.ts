import { expect, test, type Page } from "@playwright/test";
import type { PrivacyItem, PrivacyOperation, PrivacySummary } from "../lib/api/privacy.client";

test("mixed note types keep distinct selection even when their IDs match", async ({ page }) => {
  const state = await mockPrivacy(page);
  state.summary.erase_counts.personal_notes = 2;
  const rows: PrivacyItem[] = (["annotations", "bookmarks"] as const).map((category, index) => ({
    id: itemId, category, revision: stamp, title: `合成资料 ${index + 1}`, updated_at: stamp, source: {}, impact: "仅所选资料。",
  }));
  await page.route("**/api/reading/privacy/items/**", route => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ owner_id: "1", count: 2, page: 1, page_size: 20, results: rows }) }));
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: /^笔记、摘录与书签/ }).click();
  const first = page.getByRole("checkbox", { name: "选择：合成资料 1", exact: true });
  const second = page.getByRole("checkbox", { name: "选择：合成资料 2", exact: true });
  await first.check();
  await expect(second).not.toBeChecked();
  await second.check();
  await first.uncheck();
  await expect(second).toBeChecked();
  await page.getByRole("button", { name: "提交删除预览", exact: true }).click();
  await expect.poll(() => state.requests.find(row => row.path === "/api/reading/privacy/operations/")?.body.targets)
    .toEqual([{ category: "bookmarks", id: itemId, revision: stamp }]);
});

// Synthetic state-machine cases; intentionally not executed before unified acceptance.
const itemId = "51000000-0000-4000-8000-000000000001";
const operationId = "51000000-0000-4000-8000-000000000002";
const stamp = "2026-10-18T00:00:00Z";
const operation = (kind: "export" | "erase", status: PrivacyOperation["status"]): PrivacyOperation => ({
  id: operationId, owner_id: "1", revision: 1, kind, status, created_at: stamp, updated_at: stamp, finished_at: null,
  total: 1, completed: 0, failed: 0, remaining: 1, categories: kind === "export" ? ["notes"] : ["reading_history"], results: [],
  preview: kind === "erase" ? [{ id: itemId, category: "reading_history", revision: stamp, impact: { message: "删除此条历史，阅读进度与原件保留。", scope_count: 0, memories: [] } }] : [],
  error_code: "", download_available: false, notice: "仅处理本人选择的资料。取消不会恢复已删除项目。",
});

async function mockPrivacy(page: Page, empty = false) {
  const row: PrivacyItem = { id: itemId, category: "reading_history", revision: stamp, title: "合成私人阅读记录", updated_at: stamp, source: {}, impact: "阅读进度保留。" };
  const summary: PrivacySummary = { owner_id: "1", revision: 1, retention: { reading_history: true, search_history: false, personal_notes: true, followed_topics: true, source_follows: true, saved_knowledge: true },
    automatic_memory_use: false, confirmed_notes: empty ? 0 : 1, authorized_contexts: 0,
    export_counts: { collaboration: 0, article_comments: 0, research: 0, notes: empty ? 0 : 1, plans: 0, audits: 0, source_follows: 0, saved_knowledge: 0 },
    erase_counts: { collaboration: 0, article_comments: 0, reading_history: empty ? 0 : 1, search_history: 0, personal_notes: 0, reading_plans: 0, followed_topics: 0, source_follows: 0, saved_knowledge: 0 },
    operations: [], preference_history: [], max_operation_items: 500, export_formats: ["json"], notice: "只处理本人资料。" };
  const state = { owner: 1, summary, job: null as PrivacyOperation | null, failNextCreate: false,
    switchOwnerAt: null as string | null, unauthorizedAt: null as string | null, refreshCount: 0,
    protectedRequests: [] as Array<{ path: string; method: string; owner: string | null }>,
    requests: [] as Array<{ path: string; body: Record<string, unknown> }> };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Synthetic", reading_preferences: {} });
    if (path === "/api/auth/token/refresh/") { state.refreshCount += 1; return respond({}); }
    if (request.method() !== "GET") state.requests.push({ path, body: request.postDataJSON() });
    if (path.startsWith("/api/reading/privacy/") && (request.method() !== "GET" || path.endsWith("/download/"))) {
      const owner = request.headers()["x-reader-owner"] ?? null;
      state.protectedRequests.push({ path, method: request.method(), owner });
      // The auth/me preflight already succeeded as A. Only the eventual
      // protected request now sees B, exactly the server's owner-header boundary.
      if (state.switchOwnerAt === path) { state.owner = 2; state.switchOwnerAt = null; }
      if (state.unauthorizedAt === path) { state.unauthorizedAt = null; return respond({ detail: "登录已过期。" }, 401); }
      if (owner !== null && owner !== String(state.owner)) return respond({ detail: "登录账户已变化，请重新读取当前账户的资料。" }, 403);
    }
    if (path === "/api/reading/privacy/") {
      if (request.method() === "PATCH") { const body = request.postDataJSON(); if (body.expected_revision !== summary.revision) return respond({ detail: "设置已更新，选择仍保留。" }, 409); summary.retention = body.retention; summary.revision += 1; }
      return respond({ ...summary, operations: state.job ? [state.job] : [] });
    }
    if (path === "/api/reading/privacy/items/") return respond({ owner_id: "1", count: empty || url.searchParams.get("category") !== "reading_history" ? 0 : 1, page: 1, page_size: 20, results: empty || url.searchParams.get("category") !== "reading_history" ? [] : [row] });
    if (path === "/api/reading/privacy/operations/") {
      if (request.method() === "POST") {
        if (state.failNextCreate) { state.failNextCreate = false; return respond({ detail: "临时中断，请重试。" }, 500); }
        const body = request.postDataJSON(); state.job = operation(body.kind, body.kind === "erase" ? "preview" : "queued");
        return respond(state.job, 202);
      }
      return respond({ count: state.job ? 1 : 0, next: null, previous: null, results: state.job ? [state.job] : [] });
    }
    if (path === `/api/reading/privacy/operations/${operationId}/command/` && state.job) {
      const body = request.postDataJSON();
      if (body.expected_revision !== state.job.revision) return respond({ detail: "任务已有新修订，请重新核对。" }, 409);
      state.job = { ...state.job, revision: state.job.revision + 1, status: body.action === "cancel" ? "canceled" : body.action === "retry" && state.job.kind === "erase" ? "preview" : "queued" };
      return respond(state.job);
    }
    if (path === `/api/reading/privacy/operations/${operationId}/download/`) return respond({ owner_id: "1", operation_id: operationId,
      records: [{ category: "notes", record: { body: "合成测试笔记" } }], unavailable_since_preparation: [] });
    if (path === `/api/reading/privacy/operations/${operationId}/`) return respond(state.job);
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

test("empty account keeps export disabled and does not display atlas example counts", async ({ page }) => {
  await mockPrivacy(page, true);
  await page.goto("/account/settings/privacy");
  await expect(page.getByRole("button", { name: "准备导出", exact: true })).toBeDisabled();
  await expect(page.getByText("无可导出内容", { exact: true })).toBeVisible();
  await expect(page.getByText("128 条", { exact: true })).toHaveCount(0);
  await expect(page.getByText("暂无阅读历史。", { exact: true })).toBeVisible();
});

test("long-term search history starts off and saving retention never grants note usage", async ({ page }) => {
  const state = await mockPrivacy(page);
  await page.goto("/account/settings/privacy");
  const checkbox = page.getByRole("checkbox", { name: /搜索记录 仅在开启后/ });
  await expect(checkbox).not.toBeChecked();
  await checkbox.check();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByText("隐私设置已保存，现有资料仍然保留。", { exact: true })).toBeVisible();
  expect(state.requests.at(-1)?.body).toMatchObject({ expected_revision: 1, retention: { search_history: true } });
  expect(state.summary.automatic_memory_use).toBe(false);
  expect(state.requests.some(row => row.path.includes("/usage/"))).toBe(false);
});

test("export retry preserves its nonce after an uncertain server failure", async ({ page }) => {
  const state = await mockPrivacy(page);
  state.failNextCreate = true;
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: "准备导出", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("临时中断");
  await page.getByRole("button", { name: "准备导出", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "导出资料" })).toBeVisible();
  const requests = state.requests.filter(row => row.path === "/api/reading/privacy/operations/");
  expect(requests).toHaveLength(2);
  expect(requests[1].body.request_id).toBe(requests[0].body.request_id);
  expect(requests[1].body).toMatchObject({ kind: "export", categories: ["research", "notes"] });
});

test("delete first previews exact record revision and waits for explicit acknowledgement", async ({ page }) => {
  const state = await mockPrivacy(page);
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: "预览影响", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "删除资料与影响" });
  const confirm = dialog.getByRole("button", { name: "确认删除所选资料", exact: true });
  await expect(confirm).toBeDisabled();
  expect(state.requests.at(-1)?.body).toMatchObject({ kind: "erase", targets: [{ category: "reading_history", id: itemId, revision: stamp }] });
  expect(state.requests.some(row => row.path.endsWith("/command/"))).toBe(false);
  await dialog.getByRole("checkbox", { name: /我已核对所选资料/ }).check();
  await confirm.click();
  await expect(dialog.getByText("删除任务已提交，已完成的项目不能撤销。", { exact: true })).toBeVisible();
  expect(state.requests.at(-1)?.body).toEqual({ expected_revision: 1, action: "confirm" });
});

test("an updated impact preview requires acknowledging the new revision", async ({ page }) => {
  const state = await mockPrivacy(page);
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: "预览影响", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "删除资料与影响" });
  await dialog.getByRole("checkbox", { name: /我已核对所选资料/ }).check();
  state.job!.revision += 1;
  state.job!.preview[0].impact.scope_count = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(dialog.getByText("涉及 2 个笔记使用范围，将撤销对应授权。", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "确认删除所选资料", exact: true })).toBeDisabled();
  expect(state.requests.some(row => row.path.endsWith("/command/"))).toBe(false);
});

test("partial jobs show real failures and recover only after an explicit retry", async ({ page }) => {
  const state = await mockPrivacy(page);
  state.job = { ...operation("export", "partial"), total: 2, completed: 1, failed: 1, remaining: 0, download_available: true,
    results: [{ category: "memories", id: itemId, status: "failed", error_code: "preparation_failed" }] };
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: "查看任务", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导出资料" });
  await expect(dialog.getByText("已完成 1 / 2 项，1 项未完成。", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "查看成功文件", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "重试未完成项", exact: true }).click();
  expect(state.requests.at(-1)?.body).toEqual({ expected_revision: 1, action: "retry" });
});

test("cookie owner changes clear private items and open deletion preview", async ({ page }) => {
  const state = await mockPrivacy(page);
  await page.goto("/account/settings/privacy/export");
  await page.getByRole("button", { name: "预览影响", exact: true }).click();
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("dialog", { name: "删除资料与影响" })).toHaveCount(0);
  await expect(page.getByText("合成私人阅读记录", { exact: true })).toHaveCount(0);
});

test("mobile tabs expose the same real export and delete operations", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPrivacy(page);
  await page.goto("/account/settings/privacy");
  const tabs = page.getByRole("navigation", { name: "隐私资料分区" });
  await tabs.getByRole("button", { name: "导出资料", exact: true }).click();
  await expect(page.getByRole("button", { name: "准备导出", exact: true })).toBeVisible();
  await tabs.getByRole("button", { name: "删除资料", exact: true }).click();
  await expect(page.getByRole("button", { name: "预览影响", exact: true })).toBeVisible();
});

for (const action of ["preferences", "prepare", "command", "download"] as const) {
  for (const fault of ["owner-switch", "401"] as const) {
    test(`${action} pins owner A after preflight and does not replay through ${fault}`, async ({ page }) => {
      const state = await mockPrivacy(page);
      if (action === "download") {
        state.job = { ...operation("export", "completed"), completed: 1, remaining: 0, download_available: true };
      }
      let downloaded = false;
      page.on("download", () => { downloaded = true; });
      await page.goto(`/account/settings/privacy${action === "preferences" ? "" : "/export"}`);
      let path: string, button;
      if (action === "preferences") {
        await page.getByRole("checkbox", { name: /搜索记录 仅在开启后/ }).check();
        path = "/api/reading/privacy/";
        button = page.getByRole("button", { name: "保存设置", exact: true });
      } else if (action === "prepare") {
        path = "/api/reading/privacy/operations/";
        button = page.getByRole("button", { name: "准备导出", exact: true });
      } else if (action === "command") {
        await page.getByRole("button", { name: "预览影响", exact: true }).click();
        const dialog = page.getByRole("dialog", { name: "删除资料与影响" });
        await dialog.getByRole("checkbox", { name: /我已核对所选资料/ }).check();
        path = `/api/reading/privacy/operations/${operationId}/command/`;
        button = dialog.getByRole("button", { name: "确认删除所选资料", exact: true });
      } else {
        await page.getByRole("button", { name: "查看任务", exact: true }).click();
        path = `/api/reading/privacy/operations/${operationId}/download/`;
        button = page.getByRole("dialog", { name: "导出资料" }).getByRole("button", { name: "查看成功文件", exact: true });
      }
      await expect(button).toBeEnabled();
      const baseline = state.protectedRequests.length;
      const jobBefore = state.job ? structuredClone(state.job) : null;
      if (fault === "owner-switch") state.switchOwnerAt = path;
      else state.unauthorizedAt = path;
      await button.click();
      await expect(page.getByText("登录账户暂时无法确认，私人内容已收起。", { exact: true })).toBeVisible();
      expect(state.protectedRequests.slice(baseline)).toEqual([{ path, method: action === "preferences" ? "PATCH" : action === "download" ? "GET" : "POST", owner: "1" }]);
      expect(state.refreshCount).toBe(0);
      expect(state.summary.revision).toBe(1);
      expect(state.summary.retention.search_history).toBe(false);
      expect(state.job).toEqual(jobBefore);
      expect(downloaded).toBe(false);
      await expect(page.getByText("合成私人阅读记录", { exact: true })).toHaveCount(0);
    });
  }
}
