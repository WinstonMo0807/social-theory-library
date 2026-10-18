import { expect, test, type Page } from "@playwright/test";
import type { OCRCommand, OCRWorkspace } from "../lib/api/ocr-workspace.client";

// Synthetic, local contract cases for unified acceptance. No OCR/provider calls.
const id = "80000000-0000-4000-8000-000000000001", fingerprint = "a".repeat(64);
async function setup(page: Page) {
  const fixture: { state: OCRWorkspace; commands: OCRCommand[]; conflict: boolean } = {
    state: { asset: { id, edition_id: "e", work_id: "w", title: "合成文字质检", page_count: 2, sha256: "synthetic", preview_url: "", source_current: true }, source_version: "2026-10-18T00:00:00Z", expected_revision: 0,
      pages: [1, 2].map(pdf_page => ({ pdf_page, printed_label: String(pdf_page), text_source: "embedded", confidence: 1, is_text_manual: pdf_page === 2, char_count: 4, source_fingerprint: fingerprint, status: pdf_page === 2 ? "manual" : "completed", reason: "合成来源状态" })),
      count: 2, list_page: 1, next_page: null, counts: { completed: 1, manual: 1 }, parsed_page_count: 2, missing_page_count: 0,
      detail: { pdf_page: 1, text: "合成原文", original_text: "合成原文", parsed: true, manual: false, manual_revision_id: null, manual_revision: null, latest: null, source_fingerprint: fingerprint, history: [], history_count: 0, history_page: 1, history_next_page: null },
      jobs: [], active_job_id: "", paused: false, can_run: true, denied_reason: "", provider_label: "合成配置的 OCR 服务", checked_at: "2026-10-18T00:00:00Z", settings: { languages: "中文、英语", layout: "版面分析", manual_text: "保留", service_verified: false } },
    commands: [], conflict: false,
  };
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/auth/me/") return respond({ id: 1, role: "admin", display_name: "Synthetic Admin", capabilities: ["access_back_office", "can_edit_metadata", "can_publish_work", "can_retry_jobs"], reading_preferences: {} });
    if (url.pathname === `/api/ingestion/ocr-workspace/${id}/`) {
      if (route.request().method() === "GET") {
        const number = Number(url.searchParams.get("pdf_page") || 1);
        return respond({ ...fixture.state, detail: { ...fixture.state.detail, pdf_page: number, manual: number === 2 } });
      }
      const command = route.request().postDataJSON() as OCRCommand;
      fixture.commands.push(command);
      if (fixture.conflict) { fixture.state.expected_revision += 1; return respond({ detail: "合成并发冲突" }, 409); }
      if (command.action === "save") {
        const row = { id: "80000000-0000-4000-8000-000000000002", revision: ++fixture.state.expected_revision, pdf_page: 1, text: command.text!, original_text: fixture.state.detail.text, note: command.note || "", confirmed: command.confirmed || false, review_only: false, source_fingerprint: fingerprint, created_at: "2026-10-18T00:00:00Z", applied_at: null, applied_asset_id: null, publication: null };
        fixture.state.detail.latest = row; fixture.state.detail.history = [row];
      }
      return respond(fixture.state);
    }
    return respond({ count: 0, results: [] });
  });
  await page.goto(`/admin/library/assets/${id}/ocr`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("textbox", { name: "人工修订文字" })).toBeVisible();
  return fixture;
}

test("manual input saves a candidate and leaves current text intact", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("textbox", { name: "人工修订文字" }).fill("合成人工修订");
  await page.getByRole("checkbox", { name: /我已对照原页/ }).check();
  await page.getByRole("button", { name: "保存修订候选", exact: true }).click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0]).toMatchObject({ action: "save", text: "合成人工修订", confirmed: true, source_fingerprint: fingerprint });
  expect(fixture.state.detail.text).toBe("合成原文");
});

test("conflict preserves draft and requires renewed confirmation after rebase", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("textbox", { name: "人工修订文字" }).fill("保留输入");
  await page.getByRole("checkbox", { name: /我已对照原页/ }).check();
  fixture.conflict = true;
  await page.getByRole("button", { name: "保存修订候选", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "人工修订文字" })).toHaveValue("保留输入");
  await page.getByRole("button", { name: "对照最新文字", exact: true }).click();
  await page.getByRole("button", { name: "保留输入并采用最新基准", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /我已对照原页/ })).not.toBeChecked();
});

test("changing physical page does not discard an unsaved correction", async ({ page }) => {
  await setup(page);
  await page.getByRole("textbox", { name: "人工修订文字" }).fill("尚未保存文字");
  await page.getByRole("button", { name: /第 2 页/ }).click();
  await expect(page.getByRole("heading", { name: "放弃未保存修订？" })).toBeVisible();
  await page.getByRole("button", { name: "继续编辑", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "人工修订文字" })).toHaveValue("尚未保存文字");
});

test("page retry sends only the chosen physical page after explicit service confirmation", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("button", { name: "重做本页", exact: true }).click();
  await expect(page.getByRole("button", { name: "开始识别", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: "我确认所选文件、页码和服务范围" }).check();
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0]).toMatchObject({ action: "start", page_indexes: [1], confirmed: true });
});

test("protected manual page cannot be overwritten by the page retry control", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: /第 2 页/ }).click();
  await expect(page.getByRole("button", { name: "重做本页", exact: true })).toBeDisabled();
  await expect(page.getByText("已有人工确认，重新识别不会覆盖。修改确认文字仍需保存新修订并采用。")).toBeVisible();
});

test("task settings reach the actual start command", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("tab", { name: "处理设置" }).click();
  await page.getByRole("checkbox", { name: "简体中文", exact: true }).uncheck();
  await page.getByRole("checkbox", { name: "繁体中文", exact: true }).uncheck();
  await page.getByRole("checkbox", { name: "请求版面分析", exact: true }).uncheck();
  await page.getByRole("combobox", { name: "待校对置信度阈值" }).selectOption("0.85");
  await page.getByRole("button", { name: "重新识别全部未受保护页", exact: true }).click();
  await page.getByRole("checkbox", { name: "我确认所选文件、页码和服务范围" }).check();
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0]).toMatchObject({ action: "start", task_options: { languages: ["en"], layout: false, quality_threshold: .85, skip_reviewed: true } });
});

test("batch manual review requires confirmation and binds each selected text version", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("checkbox", { name: "选择第 1 页", exact: true }).check();
  await page.getByRole("button", { name: "标记所选页已核验", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存人工核验记录", exact: true })).toBeDisabled();
  await page.getByRole("textbox", { name: "批量核验说明" }).fill("已逐页对照合成原页");
  await page.getByRole("checkbox", { name: "我已逐页对照原页和当前文字，确认本次所选页面" }).check();
  await page.getByRole("button", { name: "保存人工核验记录", exact: true }).click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0]).toMatchObject({ action: "review", expected_revision: 0, confirmed: true, pages: [{ pdf_page: 1, source_fingerprint: fingerprint }] });
  expect(fixture.state.jobs).toEqual([]);
  expect(fixture.state.detail.text).toBe("合成原文");
});

test("batch review conflict keeps its explanation and selected source intact", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("checkbox", { name: "选择第 1 页", exact: true }).check();
  await page.getByRole("button", { name: "标记所选页已核验", exact: true }).click();
  await page.getByRole("textbox", { name: "批量核验说明" }).fill("保留核验依据");
  await page.getByRole("checkbox", { name: "我已逐页对照原页和当前文字，确认本次所选页面" }).check();
  fixture.conflict = true;
  await page.getByRole("button", { name: "保存人工核验记录", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "批量核验说明" })).toHaveValue("保留核验依据");
  expect(fixture.commands[0].pages).toEqual([{ pdf_page: 1, source_fingerprint: fingerprint }]);
});
