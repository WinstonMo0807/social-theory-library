import { expect, test, type Page } from "@playwright/test";
import type { PublicSourceStatus, SourceFollow, SourceCommand, SourceCommandResult } from "../lib/api/source-follows.client";

// Synthetic contracts only. These scenarios are authored, not run before unified acceptance.
const assetId = "71000000-0000-4000-8000-000000000001", followId = "71000000-0000-4000-8000-000000000002";
const path = `/reader/${assetId}`, stamp = "2026-10-19T00:00:00Z";
const source = (available = true): PublicSourceStatus => ({ path, canonical_path: path, status: available ? "available" : "unavailable",
  title: available ? "合成公开来源" : "来源当前不可用", authors: available ? ["合成作者"] : [], cover_url: "", source_type: available ? "PDF 阅读文件" : "",
  version_label: "", location: "", updated_at: available ? stamp : null, checked_at: stamp, can_subscribe: available, reader_url: available ? path : "",
  notice: available ? "合成公开状态" : "当前无法核对公开来源。", work_id: null, edition_id: null, asset_id: available ? assetId : null, catalog_revision_id: null, document_revision_id: null });
const follow = (): SourceFollow => ({ id: followId, owner_id: "1", path, active: true, revision: 1, created_at: stamp, updated_at: stamp,
  last_checked_at: stamp, check_error: "", unread_count: 1, updates_paused: false, source: source(), notice: "只保存本人站内更新。",
  history: { count: 1, page: 1, page_size: 20, results: [{ id: "synthetic-event", action: "changed", before_status: "unavailable", after_status: "available", observed_at: stamp, revision: 1 }] } });

async function setup(page: Page, empty = false) {
  const state = { owner: 1, row: empty ? null : follow(), posts: [] as SourceCommand[], receipts: new Map<string, SourceCommandResult>(), fail: false, conflict: false };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url());
    const respond = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (url.pathname === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Synthetic", reading_preferences: {} });
    if (url.pathname === "/api/reading/source-status/") return respond(state.row?.source ?? source());
    if (url.pathname === "/api/reading/source-follows/by-request/") return respond(state.receipts.get(url.searchParams.get("request_id") || "") ?? { detail: "尚未找到回执" }, state.receipts.has(url.searchParams.get("request_id") || "") ? 200 : 404);
    if (url.pathname === "/api/reading/source-follows/") {
      if (request.method() === "POST") {
        expect(request.headers()["x-reader-owner"]).toBe("1");
        const body = request.postDataJSON() as SourceCommand;
        state.posts.push(body);
        if (state.fail) { state.fail = false; return respond({ detail: "合成服务中断" }, 500); }
        if (state.conflict) { state.conflict = false; if (state.row) state.row.revision += 1; return respond({ detail: "来源关注已变化，请重新读取。" }, 409); }
        state.row ||= follow();
        state.row = { ...state.row, active: body.action === "unsubscribe" ? false : body.action === "subscribe" ? true : state.row.active,
          unread_count: body.action === "mark_read" ? 0 : state.row.unread_count, revision: state.row.revision + 1 };
        const result = { owner_id: "1", record: state.row, receipt: { request_id: body.request_id, applied_revision: state.row.revision, deleted: false } };
        state.receipts.set(body.request_id, result);
        return respond(result);
      }
      return respond({ owner_id: "1", count: state.row ? 1 : 0, page: 1, page_size: 20, results: state.row ? [state.row] : [], notice: "仅提供本人站内更新，不发送邮件。" });
    }
    if (url.pathname === `/api/reading/source-follows/${followId}/`) return respond(state.row);
    return respond({ count: 0, results: [] });
  });
  return state;
}

test("empty subscription inbox contains no atlas example source or false counts", async ({ page }) => {
  await setup(page, true); await page.goto("/account/source-updates");
  await expect(page.getByRole("heading", { name: "还没有订阅来源" })).toBeVisible();
  await expect(page.getByText("共 0 项来源记录")).toBeVisible();
  await expect(page.getByText("合成公开来源")).toHaveCount(0);
});

test("uncertain mutation retains same request and revision", async ({ page }) => {
  const state = await setup(page); state.fail = true;
  await page.goto("/account/source-updates");
  await page.getByRole("button", { name: "取消订阅", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "取消订阅", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "核对原操作" }).click();
  await expect(page.getByText("已取消订阅", { exact: true })).toBeVisible();
  expect(state.posts).toHaveLength(2); expect(state.posts[1]).toEqual(state.posts[0]);
});

test("revision conflict reloads current state without replaying cancellation", async ({ page }) => {
  const state = await setup(page); state.conflict = true;
  await page.goto("/account/source-updates");
  await page.getByRole("button", { name: "取消订阅", exact: true }).click();
  await expect(page.getByText("来源关注已变化，请重新读取。", { exact: true })).toBeVisible();
  expect(state.posts).toHaveLength(1); expect(state.row?.active).toBe(true);
});

test("withdrawn source removes old title and reader link but remains cancellable", async ({ page }) => {
  const state = await setup(page); if (state.row) state.row.source = source(false);
  await page.goto("/account/source-updates");
  await expect(page.getByText("合成公开来源")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "打开当前原文" })).toHaveCount(0);
  await page.getByRole("button", { name: "取消订阅", exact: true }).click();
  await expect(page.getByRole("button", { name: "重新订阅更新" })).toBeDisabled();
});

test("history shows observed state timestamps and private retention pause", async ({ page }) => {
  const state = await setup(page); if (state.row) state.row.updates_paused = true;
  await page.goto("/account/source-updates");
  await expect(page.getByText(/已暂停保存更新/)).toBeVisible();
  await page.getByRole("button", { name: "查看状态历史" }).click();
  const dialog = page.getByRole("dialog", { name: "来源状态历史" });
  await expect(dialog.getByText("观察到来源变化")).toBeVisible();
  await expect(dialog.getByText("暂不可用 → 当前可用")).toBeVisible();
});

test("owner changes before mutation prevent sending previous owner's command", async ({ page }) => {
  const state = await setup(page); await page.goto("/account/source-updates");
  await expect(page.getByText("合成公开来源", { exact: true })).toBeVisible();
  state.owner = 2;
  await page.getByRole("button", { name: "取消订阅", exact: true }).click();
  await expect(page.getByText("合成公开来源", { exact: true })).toHaveCount(0);
  expect(state.posts).toHaveLength(0);
});
