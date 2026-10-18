import { expect, test, type Page } from "@playwright/test";
import type { CitationPreviewStatus } from "../lib/api/citation-preview.client";

// Synthetic fixtures, authored only. Conversion/runtime validation belongs to final acceptance.
const id = "25000000-0000-4000-8000-000000000001";
const timestamp = "2026-10-18T00:00:00Z";
async function previewFixture(page: Page) {
  const state = { owner: 1, conflict: false, loseResponse: false, requests: [] as Record<string, unknown>[],
    preview: { audit_id: id, audit_revision: 1, source_generation: 1, manuscript_revision: 1, content_hash: "a".repeat(64),
      preview_generation: 0, preview_revision: 0, status: "not_generated", enabled: true, page_count: null,
      converter_version: null, fonts_version: null, poll_after_ms: null, message: "", notice: "合成分页预览不代表本机 Word 排版，不推测页码。" } as CitationPreviewStatus };
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const response = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/api/auth/me/") return response({ id: state.owner, role: "reader", display_name: "Synthetic", reading_preferences: {} });
    if (state.owner !== 1 && path.includes(`/citation-audits/${id}/`)) return response({ detail: "当前账户不可访问前次稿件" }, 404);
    if (path === `/api/reading/citation-audits/${id}/`) return response({ id, revision: 1, generation: 1, status: "completed", created_at: timestamp, updated_at: timestamp,
      data: { filename: "synthetic.docx", filetype: "docx", manuscript_revision: 1, parsed: true, scope: "public_library", checks: ["citation_identification"], occurrences: [], bibliography: [], stage: "report" } });
    if (path === `/api/reading/citation-audits/${id}/manuscript/`) return response({ audit_id: id, manuscript_revision: 1, generation: 1, revision: 1, status: "completed", count: 1, page: 1, next_page: null,
      units: [{ id: "synthetic-unit", index: 0, text: "真实位置的合成解析文字", location: { part: "word/document.xml", paragraph: 7, start: 0, end: 13 } }] });
    if (path === `/api/reading/citation-audits/${id}/preview/`) {
      if (request.method() === "POST") {
        const body = request.postDataJSON(); state.requests.push(body);
        if (state.conflict) { state.preview.preview_revision += 1; return response({ detail: "合成预览修订冲突" }, 409); }
        if (state.loseResponse) return response({ detail: "合成响应丢失" }, 503);
        state.preview = { ...state.preview, preview_revision: state.preview.preview_revision + 1,
          preview_generation: state.preview.preview_generation + 1, status: body.action === "cancel" ? "canceled" : "queued", poll_after_ms: null };
      }
      return response(state.preview);
    }
    return response({ count: 0, next: null, results: [] });
  });
  return state;
}
const open = (page: Page) => page.goto(`/account/citation-audits/${id}/parse`, { waitUntil: "domcontentloaded" });

test("DOCX paginated preview queues privately and keeps actual parsed paragraphs while waiting", async ({ page }) => {
  const state = await previewFixture(page); await open(page);
  await expect.poll(() => state.requests.length).toBe(1);
  expect(state.requests[0]).toMatchObject({ action: "generate", expected_preview_revision: 0, source_generation: 1 });
  expect(state.requests[0].request_id).toBeTruthy();
  await expect(page.getByRole("region", { name: "稿件解析预览" })).toContainText("真实位置的合成解析文字");
  await expect(page.getByLabel("派生预览页码")).toHaveCount(0);
  await page.getByRole("button", { name: "取消分页预览", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(2);
  expect(state.requests[1].action).toBe("cancel");
});

test("unconfigured or failed converter falls back to actual text without claiming page layout", async ({ page }) => {
  const state = await previewFixture(page);
  state.preview.enabled = false; state.preview.message = "分页预览服务尚未启用";
  await open(page);
  await expect(page.getByText("分页预览服务尚未启用", { exact: true })).toBeVisible();
  await expect(page.locator(".stl4-audit-parsed-paper")).toContainText("真实位置的合成解析文字");
  expect(state.requests).toHaveLength(0);
  state.preview.enabled = true; state.preview.status = "failed"; state.preview.message = "此稿件包含外部关联内容，未联网读取";
  await page.getByRole("button", { name: "重新读取预览", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("未联网读取");
  await expect(page.locator(".stl4-audit-parsed-paper")).toContainText("真实位置的合成解析文字");
});

test("lost preview request reuses idempotency key, conflict requires the refreshed revision", async ({ page }) => {
  const state = await previewFixture(page); state.loseResponse = true; await open(page);
  await expect(page.getByRole("alert")).toContainText("合成响应丢失");
  state.loseResponse = false;
  await page.getByRole("button", { name: "生成分页预览", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(2);
  expect(state.requests[0].request_id).toBe(state.requests[1].request_id);
  state.conflict = true;
  await page.getByRole("button", { name: "取消分页预览", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("合成预览修订冲突");
  state.conflict = false;
  await page.getByRole("button", { name: "取消分页预览", exact: true }).click();
  expect(state.requests.at(-1)?.expected_preview_revision).toBe(state.preview.preview_revision - 1);
});

test("session change clears preview and parsed fallback belonging to the previous owner", async ({ page }) => {
  const state = await previewFixture(page); await open(page);
  await expect(page.locator(".stl4-audit-parsed-paper")).toContainText("真实位置的合成解析文字");
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByText("真实位置的合成解析文字", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("派生预览页码")).toHaveCount(0);
});
