import { expect, test, type Page } from "@playwright/test";
import type { AdminCalibration, CalibrationAction, CalibrationCommand } from "../lib/api/parallel-calibration-admin.client";

// Synthetic UI contracts only. These do not establish live service or visual acceptance.
const id = "83000000-0000-4000-8000-000000000001", left = "83000000-0000-4000-8000-000000000002";
const right = "83000000-0000-4000-8000-000000000003", stamp = "2026-10-20T00:00:00Z";
const base = "/api/reading/parallel-calibrations/admin/";

async function setup(page: Page, canPublish = true, available = true) {
  const source = (asset: string, title: string) => ({ title, version_label: "合成版本说明", authors: ["合成作者"], reader_url: `/reader/${asset}?page=1&revision=${id}` });
  const fixture = {
    owner: 1, denied: false, fail: 0, refreshes: 0, commands: [] as Array<CalibrationCommand & { action: CalibrationAction }>,
    receipts: new Map<string, number>(),
    row: {
      id, revision: 1, request_id: id, status: "submitted", scope: "passages",
      created_at: stamp, updated_at: stamp, source_available: available, notice: available ? "" : "合成来源已经失效",
      review_note: "", reviewer_id: null, pair_sources: available ? { left: source(left, "合成原作"), right: source(right, "合成译作") } : null,
      data: {
        left_asset_id: left, right_asset_id: right, left_document_revision_id: id, right_document_revision_id: id,
        basis: "合成投稿依据：逐段核对两个版本。",
        alignments: [{
          id, status: "confirmed", left: { source_status: available ? "available" : "unavailable", title: "合成原作",
            quote: available ? "Synthetic original paragraph" : "", pdf_page: 1, reader_url: available ? `/reader/${left}?page=1&revision=${id}&passage=${id}` : null },
          right: { source_status: available ? "available" : "unavailable", title: "合成译作",
            quote: available ? "合成译作段落" : "", pdf_page: 2, reader_url: available ? `/reader/${right}?page=2&revision=${id}` : null },
        }],
      },
    } as AdminCalibration,
  };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const response = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return response({ id: fixture.owner, role: "admin", display_name: "Synthetic",
      capabilities: ["access_back_office", "can_review_candidate", ...(canPublish ? ["can_publish_authority"] : [])], reading_preferences: {} });
    if (path === "/api/auth/token/refresh/") { fixture.refreshes += 1; return response({ detail: "合成会话不可刷新" }, 401); }
    if (path.startsWith(base) && fixture.denied) return response({ detail: "合成审核权限已撤销" }, 403);
    if (path === base) return response({ count: 1, next: null, previous: null, results: [fixture.row] });
    if (path === `${base}${id}/`) return response(fixture.row);
    const action = path.match(/\/(review|publish|reject)\/$/)?.[1] as CalibrationAction | undefined;
    if (path.startsWith(`${base}${id}/`) && action && request.method() === "POST") {
      const command = request.postDataJSON() as CalibrationCommand;
      fixture.commands.push({ ...command, action });
      if (fixture.fail === 401) return response({ detail: "合成会话已失效" }, 401);
      let applied = fixture.receipts.get(command.request_id);
      if (applied === undefined) {
        if (command.expected_revision !== fixture.row.revision) return response({ detail: "合成并发修订冲突" }, 409);
        fixture.row = { ...fixture.row, revision: fixture.row.revision + 1, reviewer_id: 1,
          status: action === "review" ? "reviewed" : action === "publish" ? "published" : "rejected", review_note: command.note };
        applied = fixture.row.revision;
        fixture.receipts.set(command.request_id, applied);
      }
      // Simulate an accepted write whose response cannot be confirmed.
      if (fixture.fail) return response({ detail: "合成响应暂不可确认" }, fixture.fail);
      return response({ ...fixture.row, request_id: command.request_id, applied_revision: applied });
    }
    return response({ count: 0, results: [] });
  });
  await page.goto("/admin/support/parallel-calibrations", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "公共校准", exact: true })).toBeVisible();
  await page.getByRole("region", { name: "公共校准列表", exact: true }).getByRole("button", { name: available ? /合成原作/ : /来源当前不可用/ }).click();
  await expect(page.getByRole("heading", { name: "核对公共校准", exact: true })).toBeVisible();
  return fixture;
}

test("review and publish are separate revision-checked actions with a scope confirmation", async ({ page }) => {
  const fixture = await setup(page);
  await expect(page.getByRole("link", { name: "查看原文位置" }).first()).toHaveAttribute("href", `/reader/${left}?page=1&revision=${id}&passage=${id}`);
  await expect(page.getByRole("button", { name: "发布公共校准", exact: true })).toBeDisabled();
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成审核：已核对两个版本");
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByRole("button", { name: "发布公共校准", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "发布公共校准", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "确认公开这条校准" });
  await expect(dialog).toContainText("所选段落");
  expect(fixture.commands).toHaveLength(1);
  await expect(dialog.getByRole("button", { name: "继续核对" })).toBeFocused();
  await dialog.getByRole("button", { name: "确认发布", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(fixture.commands.map(({ action, expected_revision }) => [action, expected_revision])).toEqual([["review", 1], ["publish", 2]]);
});

for (const status of [503, 408, 429]) test(`unknown ${status} freezes the command and replays the same accepted request`, async ({ page }) => {
  const fixture = await setup(page); fixture.fail = status;
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成审核说明保留");
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible();
  await expect(page.getByLabel("本次处理说明", { exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "退回校准", exact: true })).toBeDisabled();
  fixture.fail = 0;
  await page.getByRole("button", { name: "重试原请求", exact: true }).click();
  await expect(page.getByText("确认审核已保存。当前状态：已审核。", { exact: true })).toBeVisible();
  expect(fixture.commands).toHaveLength(2);
  expect(fixture.commands[1]).toEqual(fixture.commands[0]);
  expect(fixture.row.revision).toBe(2);
});

test("a concurrent revision preserves the note until the reviewer adopts the current revision", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成待保存说明");
  fixture.row = { ...fixture.row, revision: 2, review_note: "另一位管理员的合成说明" };
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByText("校准已有新修订，你的说明仍保留。请核对上方最新状态和处理说明。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("本次处理说明", { exact: true })).toHaveValue("合成待保存说明");
  await expect(page.getByRole("button", { name: "确认审核", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "已核对，采用最新修订继续", exact: true }).click();
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByText("确认审核已保存。当前状态：已审核。", { exact: true })).toBeVisible();
  expect(fixture.commands[1].expected_revision).toBe(2);
});

test("a reviewer without publishing capability cannot publish an approved contribution", async ({ page }) => {
  await setup(page, false);
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByText("确认审核已保存。当前状态：已审核。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "发布公共校准", exact: true })).toBeDisabled();
  await expect(page.getByText("当前账户可以审核和退回，发布需具有公开发布权限的管理员处理。")).toBeVisible();
});

test("withdrawn sources hide original text and links while allowing a reasoned rejection", async ({ page }) => {
  const fixture = await setup(page, true, false);
  await expect(page.getByText("Synthetic original paragraph", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /核对当前原文|查看原文位置/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "确认审核", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "退回校准", exact: true })).toBeDisabled();
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成退回理由：来源已撤下");
  await page.getByRole("button", { name: "退回校准", exact: true }).click();
  await expect(page.getByText("退回校准已保存。当前状态：已退回。", { exact: true })).toBeVisible();
  expect(fixture.commands[0].action).toBe("reject");
});

test("unauthorized mutation clears the content without replaying after token refresh", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 401;
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成私人处理草稿");
  await page.getByRole("button", { name: "确认审核", exact: true }).click();
  await expect(page.getByLabel("本次处理说明", { exact: true })).toHaveCount(0);
  expect(fixture.commands).toHaveLength(1);
  expect(fixture.refreshes).toBe(0);
});

test("account changes discard a retained review draft and recheck access", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByLabel("本次处理说明", { exact: true }).fill("合成未保存审核说明");
  fixture.owner = 2; fixture.denied = true;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByLabel("本次处理说明", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Synthetic original paragraph", { exact: true })).toHaveCount(0);
  expect(fixture.commands).toHaveLength(0);
});
