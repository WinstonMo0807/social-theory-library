import { expect, test, type Page } from "@playwright/test";
import type { AuditCapabilities, AuditData, AuditTextPage, PrivateCitationSourceData, ResearchRecord } from "../lib/api/research.client";

// Synthetic owner-only fixtures. Authored for the final acceptance stage; no real manuscripts.
const auditId = "23000000-0000-4000-8000-000000000001";
const occurrenceId = "23000000-0000-4000-8000-000000000002";
const sourceId = "23000000-0000-4000-8000-000000000003";
const emptyId = "23000000-0000-4000-8000-000000000004";
const timestamp = "2026-10-18T00:00:00Z";
const originalText = `${"前".repeat(199)}😀合成引文${"后".repeat(20)}`;
const capabilities: AuditCapabilities = {
  max_upload_bytes: 12582912, max_pdf_pages: 1000,
  checks: [{ id: "citation_identification", label: "引文识别", available: true, required: true, description: "解析" }],
  scopes: [{ id: "public_library", label: "仅馆藏资源", available: true, description: "公开馆藏" }, { id: "private_materials", label: "馆藏及本人选定材料", available: true, description: "公开馆藏与明确选择的私人文件" }],
  ocr: { available: true, reason: "合成环境能力", service_verified: false },
};
const source = (id = sourceId, chars = 100): ResearchRecord<PrivateCitationSourceData> => ({
  id, revision: 1, generation: 1, status: chars ? "completed" : "partial", created_at: timestamp, updated_at: timestamp,
  data: { purpose: "private_source", filename: chars ? "synthetic-source.docx" : "empty-source.docx", title: chars ? "可用合成来源" : "无文字合成来源", filetype: "docx", parsed: true, source_generation: 1, segment_count: chars ? 1 : 0, matchable_segment_count: chars ? 1 : 0, manuscript_stats: { char_count: chars, paragraph_count: chars ? 1 : 0 } },
});
const audit = (): ResearchRecord<AuditData> => ({
  id: auditId, revision: 1, generation: 1, status: "partial", created_at: timestamp, updated_at: timestamp,
  data: { filename: "synthetic-manuscript.docx", filetype: "docx", manuscript_revision: 1, parsed: true, stage: "report", checks: ["citation_identification"], scope: "public_library", bibliography: [],
    occurrences: [{ id: occurrenceId, raw: "[1]", quote: "合成引文", context: "保持不变的合成原稿上下文", entry_ids: [], decision: null,
      location: { part: "word/document.xml", paragraph: 9, start: 4200, end: 4204 }, findings: [] }] },
});

async function mockParsing(page: Page) {
  const state = {
    record: audit(), sources: [source(), source(emptyId, 0)], conflict: false, sourceUploadFails: false,
    writes: [] as Record<string, unknown>[], uploads: [] as string[], sourceUploads: [] as string[],
    manuscriptQueries: [] as URLSearchParams[], sourceDetailGeneration: 1, textGeneration: 1, textStatus: "completed",
  };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: 1, role: "reader", display_name: "Synthetic Reader", reading_preferences: {} });
    if (path === "/api/reading/citation-audits/capabilities/") return respond(capabilities);
    if (path === `/api/reading/citation-audits/${auditId}/`) return respond(state.record);
    if (path === `/api/reading/citation-audits/${auditId}/manuscript/`) {
      state.manuscriptQueries.push(url.searchParams);
      const textPage: AuditTextPage = { audit_id: auditId, manuscript_revision: 1, generation: 1, status: state.record.status, revision: state.record.revision,
        count: 41, page: 3, next_page: null, units: [{ id: "unit-41", index: 40, text: originalText, location: { part: "word/document.xml", paragraph: 9, start: 4000, end: 4224 } }] };
      return respond(textPage);
    }
    if (path === `/api/reading/citation-audits/${auditId}/command/`) {
      const body = request.postDataJSON(); state.writes.push(body);
      if (state.conflict) { state.record.revision = 2; return respond({ detail: "合成冲突，报告已有更新。" }, 409); }
      if (body.action === "decision") state.record.data.occurrences[0].decision = { value: body.decision, note: body.note, corrected_text: body.corrected_text, at: timestamp };
      if (body.action === "sources") { state.record.data.private_source_ids = body.private_source_ids; state.record.data.scope = body.private_source_ids.length ? "private_materials" : "public_library"; }
      state.record.revision += 1;
      return respond(state.record);
    }
    if (path === "/api/reading/citation-audits/") {
      if (request.method() === "POST") { state.uploads.push(request.postDataBuffer()?.toString("utf8") || ""); return respond({ ...state.record, status: "queued" }, 202); }
      return respond({ count: 0, results: [], next: null });
    }
    if (path === "/api/reading/citation-sources/") {
      if (request.method() === "POST") {
        state.sourceUploads.push(request.postDataBuffer()?.toString("utf8") || "");
        if (state.sourceUploadFails) return respond({ detail: "合成来源暂未保存，输入仍保留。" }, 503);
        return respond(source(), 202);
      }
      return respond({ count: state.sources.length, results: state.sources, next: null });
    }
    if (path === `/api/reading/citation-sources/${sourceId}/`) { const current = source(); current.generation = state.sourceDetailGeneration; current.data.source_generation = state.sourceDetailGeneration; return respond(current); }
    if (path === `/api/reading/citation-sources/${sourceId}/segments/`) return respond({ source_id: sourceId, revision: 1, generation: state.textGeneration, status: state.textStatus,
      count: 1, page: 1, next_page: null, units: [{ id: "private-unit", index: 0, text: "禁止显示的旧批次解析文字", location: { part: "word/document.xml", paragraph: 0, start: 0, end: 20 } }] });
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

const manuscript = { name: "synthetic-manuscript.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("Synthetic DOCX fixture only") };
const privateFile = { ...manuscript, name: "new-private-source.docx" };
const multipartField = (body: string, name: string) => [...body.matchAll(new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]+)`, "g"))].map(match => match[1]);
async function openPicker(page: Page) {
  await page.goto("/account/citation-audits", { waitUntil: "domcontentloaded" });
  await page.getByRole("radio", { name: /馆藏及本人选定材料/ }).check();
  return page.getByRole("region", { name: "本人来源文件", exact: true });
}

test("parse workbench locates the real DOCX segment and highlights absolute offsets without inventing Word pages", async ({ page }) => {
  const state = await mockParsing(page);
  await page.goto(`/account/citation-audits/${auditId}/parse?occurrence=${occurrenceId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "引文解析与核对", exact: true })).toBeVisible();
  await expect(page.locator(".stl4-audit-parsed-paper mark")).toHaveText("合成引文");
  await expect(page.locator(".stl4-audit-parsed-paper")).toContainText(originalText);
  await expect(page.getByText("第 3 组", { exact: true })).toBeVisible();
  await expect(page.getByLabel("稿件 PDF 页码")).toHaveCount(0);
  expect(state.manuscriptQueries.some(query => query.get("occurrence_id") === occurrenceId)).toBe(true);
  expect(state.writes).toHaveLength(0);
});

test("parse correction survives a 409 and stays separate from the original text", async ({ page }) => {
  const state = await mockParsing(page);
  await page.goto(`/account/citation-audits/${auditId}/parse`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "校正文字与人工复核", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "校正文字与人工复核", exact: true });
  await dialog.getByLabel("已记录修正", { exact: true }).check();
  await dialog.getByLabel("本人校正的引文文字").fill("本人独立校正稿");
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  await expect(dialog.getByLabel("本人校正的引文文字")).toHaveValue("本人独立校正稿");
  await expect(dialog.getByRole("button", { name: "保存人工决定" })).toBeDisabled();
  await dialog.getByRole("button", { name: "我已核对最新结果，沿用当前输入" }).click();
  state.conflict = false;
  await dialog.getByRole("button", { name: "保存人工决定" }).click();
  await expect(dialog).not.toBeVisible();
  expect(state.writes[1]).toMatchObject({ action: "decision", occurrence_id: occurrenceId, expected_revision: 2, corrected_text: "本人独立校正稿" });
  expect(state.record.data.occurrences[0].quote).toBe("合成引文");
  await expect(page.locator(".stl4-audit-parsed-paper")).toContainText(originalText);
  await expect(page.locator(".stl4-audit-parsed-paper")).not.toContainText("本人独立校正稿");
});

test("only explicitly selected sources with real text enter the manuscript request", async ({ page }) => {
  const state = await mockParsing(page);
  const unread = source("23000000-0000-4000-8000-000000000005");
  unread.data.title = "存在文字但包含未解图像"; unread.data.matchable_segment_count = 0;
  state.sources.push(unread);
  const picker = await openPicker(page);
  await expect(picker.getByRole("checkbox", { name: /无文字合成来源/ })).toBeDisabled();
  await expect(picker.getByRole("checkbox", { name: /存在文字但包含未解图像/ })).toBeDisabled();
  await expect(picker.getByRole("checkbox", { name: /可用合成来源/ })).not.toBeChecked();
  await picker.getByRole("checkbox", { name: /可用合成来源/ }).check();
  await page.getByLabel("选择待检查稿件").setInputFiles(manuscript);
  await page.getByRole("button", { name: "提交检查", exact: true }).click();
  await expect.poll(() => state.uploads.length).toBe(1);
  expect(multipartField(state.uploads[0], "scope")).toEqual(["private_materials"]);
  expect(multipartField(state.uploads[0], "private_source_ids")).toEqual([sourceId]);
  expect(state.uploads[0]).not.toContain(emptyId);
  expect(state.uploads[0]).not.toContain(unread.id);
});

test("a private candidate remains a suggestion until the owner confirms its bibliography relationship", async ({ page }) => {
  const state = await mockParsing(page);
  const entryId = "23000000-0000-4000-8000-000000000006";
  state.record.data.bibliography = [{ id: entryId, raw: "合成书目，非真实学术资料", identity_status: "needs_review", candidates: [],
    private_candidates: [{ source_id: sourceId, kind: "private_source", source_status: "available", title: "可用合成来源", filename: "synthetic-source.docx" }] }];
  await page.goto(`/account/citation-audits/${auditId}/parse?entry=${entryId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "确认对应此私人来源", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "确认书目对应的私人来源" });
  await expect(dialog).toContainText("合成书目，非真实学术资料");
  expect(state.writes).toHaveLength(0);
  await dialog.getByRole("button", { name: "确认私人来源并重查" }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0]).toEqual({ action: "match_private", entry_id: entryId, source_id: sourceId, expected_revision: 1 });
});

test("private upload preserves file and request identity on failure without selecting the saved source", async ({ page }) => {
  const state = await mockParsing(page), picker = await openPicker(page);
  await picker.locator("summary").click();
  await picker.getByLabel("来源文件", { exact: true }).setInputFiles(privateFile);
  await expect(picker.getByRole("checkbox", { name: "允许扫描文字识别" })).not.toBeChecked();
  state.sourceUploadFails = true;
  await picker.getByRole("button", { name: "保存并解析来源" }).click();
  await expect(picker.getByRole("alert")).toContainText("合成来源暂未保存");
  await expect(picker.getByText(/new-private-source.docx/)).toBeVisible();
  state.sourceUploadFails = false;
  await picker.getByRole("button", { name: "保存并解析来源" }).click();
  await expect(picker.getByRole("status")).toContainText("来源文件已保存");
  expect(state.sourceUploads).toHaveLength(2);
  expect(multipartField(state.sourceUploads[0], "request_id")[0]).toBeTruthy();
  expect(multipartField(state.sourceUploads[1], "request_id")).toEqual(multipartField(state.sourceUploads[0], "request_id"));
  expect(multipartField(state.sourceUploads[0], "scan_ocr")).toEqual(["false"]);
  await expect(picker.getByRole("checkbox", { name: /可用合成来源/ })).not.toBeChecked();
});

test("a source-scope conflict keeps selected sources until the owner explicitly adopts the latest revision", async ({ page }) => {
  const state = await mockParsing(page);
  await page.goto(`/account/citation-audits/${auditId}/parse`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "补充本人来源", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择本次用于核对的来源" });
  await dialog.getByRole("checkbox", { name: /可用合成来源/ }).check();
  state.conflict = true;
  await dialog.getByRole("button", { name: "保存来源范围并重查" }).click();
  await expect(dialog.getByRole("checkbox", { name: /可用合成来源/ })).toBeChecked();
  await expect(dialog.getByRole("button", { name: "保存来源范围并重查" })).toBeDisabled();
  await dialog.getByRole("button", { name: "核对最新报告后继续" }).click();
  state.conflict = false;
  await dialog.getByRole("button", { name: "保存来源范围并重查" }).click();
  await expect(dialog).not.toBeVisible();
  expect(state.writes[1]).toMatchObject({ action: "sources", expected_revision: 2, private_source_ids: [sourceId] });
  expect(state.record.data.occurrences[0].context).toBe("保持不变的合成原稿上下文");
});

test("private references with a changed generation never reveal the previous report quote", async ({ page }) => {
  const state = await mockParsing(page);
  state.sourceDetailGeneration = 2;
  state.record.data.occurrences[0].findings = [{ kind: "private_quote", status: "text_match", private_references: [{
    source_id: sourceId, source_generation: 1, unit_id: "private-unit", content_hash: "synthetic", source_status: "available", quote: "不得回显的旧私人片段", filename: "synthetic-source.docx",
  }] }];
  await page.goto(`/account/citation-audits/${auditId}/issues/${occurrenceId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".stl4-audit-private-reference")).toContainText("旧片段不再显示");
  await expect(page.getByText("不得回显的旧私人片段", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看本人来源原稿" })).toHaveCount(0);
});

test("a source retry cannot present old parsed text as the current batch", async ({ page }) => {
  const state = await mockParsing(page), picker = await openPicker(page);
  state.textStatus = "running";
  await picker.getByRole("button", { name: "查看来源", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "可用合成来源", exact: true });
  await expect(dialog).toContainText("旧批次文字暂不显示");
  await expect(dialog).not.toContainText("禁止显示的旧批次解析文字");
});

test("a same-owner explicit session change clears local source input and allows a fresh upload after revalidation", async ({ page }) => {
  const state = await mockParsing(page);
  let picker = await openPicker(page);
  await picker.locator("summary").click();
  await picker.getByLabel("来源文件", { exact: true }).setInputFiles(privateFile);
  await picker.getByLabel("来源题名（可选）").fill("会话变化前的本地输入");
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("radio", { name: /仅馆藏资源/ })).toBeChecked();
  await page.getByRole("radio", { name: /馆藏及本人选定材料/ }).check();
  picker = page.getByRole("region", { name: "本人来源文件", exact: true });
  await picker.locator("summary").click();
  await expect(picker.getByLabel("来源题名（可选）")).toHaveValue("");
  await expect(picker.getByRole("button", { name: "保存并解析来源" })).toBeDisabled();
  await picker.getByLabel("来源文件", { exact: true }).setInputFiles(privateFile);
  await picker.getByRole("button", { name: "保存并解析来源" }).click();
  await expect.poll(() => state.sourceUploads.length).toBe(1);
  await expect(picker.getByRole("status")).toContainText("来源文件已保存");
});

for (const [kind, decision] of [["public", "accepted"], ["private", "corrected"]] as const) {
  test(`${kind} source invalidation requires review while retaining the previous ${decision} decision`, async ({ page }) => {
    const state = await mockParsing(page), row = state.record.data.occurrences[0];
    row.decision = { value: decision, note: "保留的前次人工记录", at: timestamp, ...(decision === "corrected" ? { corrected_text: "保留的前次本人校正" } : {}) };
    row.findings = [{ kind: kind === "private" ? "private_quote" : "direct_quote", status: "unverified", source_status: "source_unavailable",
      ...(kind === "private" ? { private_references: [{ source_id: sourceId, source_generation: 1, unit_id: "private-unit", content_hash: "synthetic", source_status: "source_unavailable", quote: "不得显示的撤回私人片段" }] }
        : { references: [{ source_status: "source_unavailable", quote: "不得显示的撤回馆藏片段" }] }) }];
    await page.goto(`/account/citation-audits/${auditId}`, { waitUntil: "domcontentloaded" });
    const result = page.locator(".stl4-audit-table tbody tr");
    await expect(result.locator(".stl4-audit-state")).toHaveAttribute("data-state", "unverified");
    await expect(result).toContainText("核对依据已变化或不可用，需重新核对");
    await expect(page.getByRole("navigation", { name: "报告分类" }).getByRole("button", { name: /本人已核对/ })).toContainText("0");
    await expect(page.getByRole("navigation", { name: "报告分类" }).getByRole("button", { name: /本人已修正/ })).toContainText("0");
    await result.getByRole("link", { name: "核验详情" }).click();
    await expect(page.locator(".stl4-audit-decision-pane")).toContainText("核对依据已变化或不可用，需重新核对");
    await expect(page.locator(".stl4-audit-owner-note")).toContainText("保留的前次人工记录");
    if (decision === "corrected") await expect(page.locator(".stl4-audit-owner-note")).toContainText("保留的前次本人校正");
    await expect(page.getByText(/不得显示的撤回/)).toHaveCount(0);
    expect(state.writes).toHaveLength(0);
  });
}
