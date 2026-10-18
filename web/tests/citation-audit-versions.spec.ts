import { expect, test, type Page } from "@playwright/test";
import type { AuditData, ResearchRecord } from "../lib/api/research.client";

// Synthetic version workflow cases for the later unified acceptance stage; not run during implementation.
const baseId = "40000000-0000-4000-8000-000000000001";
const nextId = "40000000-0000-4000-8000-000000000002";
const timestamp = "2026-10-18T00:00:00Z";
const audit = (id = baseId): ResearchRecord<AuditData> => ({
  id, revision: 1, status: "partial", created_at: timestamp, updated_at: timestamp,
  data: { filename: id === baseId ? "synthetic-v1.docx" : "synthetic-v2.docx", filetype: "docx", manuscript_revision: id === baseId ? 1 : 2,
    parsed: true, bibliography: [], occurrences: [], checks: ["citation_identification"], scope: "public_library" },
});

async function mockVersions(page: Page) {
  const state = { records: new Map([[baseId, audit()], [nextId, audit(nextId)]]), uploads: [] as string[], conflict: false };
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: 1, role: "reader", display_name: "Test Reader", reading_preferences: {} });
    if (path === "/api/reading/citation-audits/capabilities/") return respond({ max_upload_bytes: 12582912, max_pdf_pages: 1000, checks: [], scopes: [] });
    const recordId = path.match(/\/citation-audits\/([^/]+)\//)?.[1];
    const record = recordId ? state.records.get(recordId) : undefined;
    if (record && path.endsWith("/versions/")) {
      if (route.request().method() === "POST") {
        state.uploads.push(route.request().postData() || "");
        if (state.conflict) { record.revision = 2; return respond({ detail: "合成报告已更新，请核对。" }, 409); }
        return respond(state.records.get(nextId), 202);
      }
      return respond({ current_id: record.id, versions: Array.from(state.records.values()).map(row => ({ id: row.id, revision: row.revision,
        manuscript_revision: row.data.manuscript_revision, filename: row.data.filename, status: row.status,
        created_at: timestamp, finished_at: timestamp, parent_audit_id: row.id === nextId ? baseId : null })), notice: "合成版本记录，原稿分别保留。" });
    }
    if (record && path.endsWith(`/${record.id}/`)) return respond(record);
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

test("new manuscript upload defaults to changed-only and retains file and options after 409", async ({ page }) => {
  const state = await mockVersions(page);
  await page.goto(`/account/citation-audits/${baseId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "上传新版本", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "上传新的稿件版本" });
  await expect(dialog.getByRole("checkbox", { name: /仅重新核验变化内容/ })).toBeChecked();
  await dialog.getByLabel("选择新版本稿件").setInputFiles({ name: "revised-synthetic.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("Synthetic manuscript bytes; no real academic content.") });
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存新版本并开始核验" }).click();
  await expect(dialog.getByText("revised-synthetic.docx", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: /仅重新核验变化内容/ })).toBeChecked();
  await expect(dialog.getByRole("button", { name: "保存新版本并开始核验" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "已核对当前报告，继续使用所选稿件" })).toBeVisible();
  expect(state.uploads).toHaveLength(1);
  expect(state.uploads[0]).toMatch(/name="check_changed_only"\r?\n\r?\ntrue/);
  expect(state.uploads[0]).toMatch(/name="expected_revision"\r?\n\r?\n1/);
});

test("pending comparison has no invented change counts and can open the preserved original version", async ({ page }) => {
  const state = await mockVersions(page);
  state.records.get(nextId)!.data.version_lineage = { parent_audit_id: baseId, parent_revision: 1, ancestor_ids: [baseId], check_changed_only: true };
  state.records.get(nextId)!.data.version_comparison = { status: "pending", base_audit_id: baseId };
  await page.goto(`/account/citation-audits/${nextId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("新稿尚未完成解析比较，变化数量待确定。", { exact: true })).toBeVisible();
  await expect(page.locator(".stl4-audit-version-counts")).toHaveCount(0);
  await page.getByRole("combobox", { name: "选择稿件版本" }).selectOption(baseId);
  await expect(page).toHaveURL(new RegExp(`/account/citation-audits/${baseId}$`));
  await expect(page.getByText("synthetic-v1.docx", { exact: true })).toBeVisible();
});

test("completed comparison presents only returned counts and clears a selected manuscript on session change", async ({ page }) => {
  const state = await mockVersions(page);
  state.records.get(nextId)!.data.version_comparison = { status: "completed", base_audit_id: baseId, total_occurrences: 9,
    changed_occurrences: 2, reused_occurrences: 7, notice: "合成比较说明。" };
  await page.goto(`/account/citation-audits/${nextId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".stl4-audit-version-counts")).toContainText("发生变化2");
  await expect(page.locator(".stl4-audit-version-counts")).toContainText("沿用结果7");
  await expect(page.locator(".stl4-audit-version-counts")).not.toContainText("新增引文");
  await page.getByRole("button", { name: "上传新版本", exact: true }).click();
  await page.getByLabel("选择新版本稿件").setInputFiles({ name: "private-next-version.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF Synthetic fixture") });
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByText("private-next-version.pdf", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "上传新的稿件版本" })).toHaveCount(0);
});
