import { expect, test, type Page } from "@playwright/test";
import type { AuditData, ResearchRecord } from "../lib/api/research.client";

// Synthetic data for the final acceptance stage. These cases are authored, not run during development.
const auditId = "20000000-0000-4000-8000-000000000001";
const issueId = "20000000-0000-4000-8000-000000000002";
const syntheticRecord = (): ResearchRecord<AuditData> => ({ id: auditId, revision: 1, status: "partial", completed_units: 1, total_units: 1,
  created_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:00:00Z", data: {
    filename: "synthetic-review.docx", filetype: "docx", manuscript_revision: 1, stage: "report", bibliography: [], warnings: [],
    occurrences: [{ id: issueId, raw: "[1]", quote: "合成测试引文，不能当作真实学术证据。", context: "测试稿件上下文，来源暂不可访问。",
      location: { part: "word/document.xml", paragraph: 0, start: 1, end: 4 }, entry_ids: [], decision: null,
      findings: [{ kind: "fulltext", status: "unverified", message: "该版本当前不可访问。", references: [] }] }] } });

async function mockAudit(page: Page) {
  const state = { owner: 1, record: syntheticRecord(), writes: [] as Record<string, unknown>[], conflict: false };
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Test Reader", reading_preferences: {} });
    if (path === `/api/reading/citation-audits/${auditId}/`) return respond(state.record);
    if (path === `/api/reading/citation-audits/${auditId}/command/`) {
      state.writes.push(route.request().postDataJSON());
      if (state.conflict) { state.record.revision = 2; return respond({ detail: "报告已有更新，请核对最新版本。" }, 409); }
      state.record.revision += 1;
      return respond(state.record);
    }
    if (path === "/api/reading/citation-audits/capabilities/") return respond({ max_upload_bytes: 12582912, max_pdf_pages: 1000, checks: [], scopes: [], analysis: { available: false, reason: "未配置本地模型。" } });
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

test("citation report keeps an unavailable original distinct from an error and sends only selected rows for batch review", async ({ page }) => {
  const state = await mockAudit(page);
  await page.goto(`/account/citation-audits/${auditId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "论文体检报告总览" })).toBeVisible();
  await page.getByRole("checkbox", { name: "选择本页引文" }).check();
  await page.getByRole("button", { name: "批量人工复核" }).click();
  const dialog = page.getByRole("dialog", { name: "批量人工复核" });
  await dialog.getByLabel("已核对", { exact: true }).check();
  await dialog.getByLabel("复核笔记或修正说明").fill("本人核对后的合成记录");
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  expect(state.writes.at(-1)).toEqual({ action: "decision", occurrence_ids: [issueId], decision: "accepted", note: "本人核对后的合成记录", expected_revision: 1 });
});

test("citation issue keeps draft after 409 and requires explicit adoption of the new revision", async ({ page }) => {
  const state = await mockAudit(page);
  await page.goto(`/account/citation-audits/${auditId}/issues/${issueId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("link", { name: "打开原文 PDF", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "记录人工决定" }).click();
  const dialog = page.getByRole("dialog", { name: "保存人工核验" });
  await dialog.getByLabel("复核笔记或修正说明").fill("必须保留的私人修正说明");
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  await expect(dialog.getByLabel("复核笔记或修正说明")).toHaveValue("必须保留的私人修正说明");
  await expect(dialog.getByRole("button", { name: "保存人工决定" })).toBeDisabled();
  expect(state.writes).toHaveLength(1);
});

test("batch review retains the chosen decision and notes after explicitly adopting a conflict revision", async ({ page }) => {
  const state = await mockAudit(page);
  await page.goto(`/account/citation-audits/${auditId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("checkbox", { name: "选择本页引文" }).check();
  await page.getByRole("button", { name: "批量人工复核" }).click();
  const dialog = page.getByRole("dialog", { name: "批量人工复核" });
  await dialog.getByLabel("已核对", { exact: true }).check();
  await dialog.getByLabel("复核笔记或修正说明").fill("冲突后必须保留的合成说明");
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  await expect(dialog.getByRole("button", { name: "保存人工决定" })).toBeDisabled();
  await dialog.getByRole("button", { name: "我已核对最新结果，沿用当前输入" }).click();
  await expect(dialog.getByLabel("复核笔记或修正说明")).toHaveValue("冲突后必须保留的合成说明");
  await expect(dialog.getByLabel("已核对", { exact: true })).toBeChecked();
  state.conflict = false;
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1]).toEqual({ action: "decision", occurrence_ids: [issueId], decision: "accepted", note: "冲突后必须保留的合成说明", expected_revision: 2 });
});

test("citation report clears private manuscript content when the cookie owner changes", async ({ page }) => {
  const state = await mockAudit(page);
  await page.goto(`/account/citation-audits/${auditId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("synthetic-review.docx", { exact: true })).toBeVisible();
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "体检资料暂时不可用" })).toBeVisible();
  await expect(page.getByText("synthetic-review.docx", { exact: true })).toHaveCount(0);
});

test("source preview rejects a page revision change before loading a PDF canvas", async ({ page }) => {
  const state = await mockAudit(page);
  const asset = "20000000-0000-4000-8000-000000000003";
  const revision = "20000000-0000-4000-8000-000000000004";
  state.record.data.occurrences[0].findings = [{ kind: "direct_quote", status: "text_match", references: [{
    asset_id: asset, document_revision_id: revision, pdf_page: 1, source_status: "available", title: "合成来源",
    quote: "仅为测试的原文片段", reader_url: `/reader/${asset}?page=1&revision=${revision}`,
  }] }];
  await page.route(`**/api/distribution/assets/${asset}/access/`, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    requested_asset_id: asset, served_asset_id: asset, url: "/never-requested-fixture.pdf", page_count: 1, sha256: "synthetic", ocr_status: "not_required", expires_in: null,
  }) }));
  await page.route(`**/api/catalog/assets/${asset}/pages/1/`, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    asset_id: asset, document_revision_id: "changed-revision", page_index: 1, blocks: [], text: "不得套用旧坐标", width: 500, height: 700,
  }) }));
  await page.goto(`/account/citation-audits/${auditId}/issues/${issueId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("暂时无法核对原文", { exact: true })).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.getByText("不得套用旧坐标", { exact: true })).toHaveCount(0);
});

test("print export includes rows outside the report view and clears its private snapshot on a session change", async ({ page }) => {
  await mockAudit(page);
  const exported = syntheticRecord();
  exported.data.occurrences.push({ ...exported.data.occurrences[0], id: "20000000-0000-4000-8000-000000000009",
    quote: "仅在完整导出中出现的合成引文", context: "此行不在当前报告视图内。",
    findings: [{ kind: "direct_quote", status: "unverified", references: [{ source_status: "source_unavailable", quote: "不得输出的撤回来源旧片段" }] }],
  });
  let exports = 0;
  await page.route(`**/api/reading/citation-audits/${auditId}/export/`, route => {
    exports += 1;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...exported, schema_version: 1 }) });
  });
  await page.addInitScript(() => { window.print = () => { document.body.dataset.syntheticPrintRequested = "true"; }; });
  await page.goto(`/account/citation-audits/${auditId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "论文体检报告总览" })).toBeVisible();
  await page.getByRole("textbox", { name: "搜索引文或参考文献" }).fill("筛选后不保留任何行");
  await expect(page.getByRole("heading", { name: "没有符合筛选条件的引文" })).toBeVisible();
  await page.getByRole("button", { name: "打印 / 保存 PDF" }).click();
  const snapshot = page.locator(".stl4-audit-print");
  await expect(snapshot).toContainText("仅在完整导出中出现的合成引文");
  await expect(snapshot).not.toContainText("不得输出的撤回来源旧片段");
  await expect(snapshot).toBeHidden();
  await expect(page.locator("body")).toHaveAttribute("data-synthetic-print-requested", "true");
  expect(exports).toBe(1);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(snapshot).toHaveCount(0);
  await expect(page.locator("body")).not.toHaveClass(/stl4-print-audit/);
});
