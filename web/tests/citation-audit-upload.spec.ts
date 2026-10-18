import { expect, test, type Page } from "@playwright/test";

// Synthetic API fixtures only. Execute during the final acceptance pass.
const auditId = "20000000-0000-4000-8000-000000000001";
const capabilities = {
  max_upload_bytes: 12 * 1024 * 1024, max_pdf_pages: 1000,
  checks: [
    { id: "citation_identification", label: "引文识别", available: true, required: true, description: "识别引文" },
    { id: "bibliography_identity", label: "书目身份", available: true, description: "匹配书目候选" },
    { id: "version_page", label: "版本页码", available: true, description: "核对版本和原文" },
    { id: "scan_ocr", label: "扫描文字识别", available: false, description: "当前服务未配置" },
    { id: "deep_analysis", label: "深入分析", available: false, description: "需在报告中选择原文" },
  ],
  scopes: [
    { id: "public_library", label: "仅馆藏资源", available: true, description: "使用公开馆藏" },
    { id: "private_materials", label: "馆藏及本人选定材料", available: false, description: "尚未接入本人材料" },
  ],
};

async function mockUpload(page: Page) {
  const state = { owner: 1, fail: true, requests: [] as string[], submitted: false };
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Test Reader", reading_preferences: {} });
    if (path === "/api/reading/citation-audits/capabilities/") return respond(capabilities);
    if (path === "/api/reading/citation-audits/") {
      if (route.request().method() === "POST") {
        state.requests.push(route.request().postDataBuffer()?.toString("utf8") || "");
        if (state.fail) return respond({ detail: "合成测试提交失败，输入仍保留。" }, 503);
        state.submitted = true;
        return respond({ id: auditId, revision: 1, status: "queued", created_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:00:00Z", data: { filename: "synthetic-manuscript.pdf", filetype: "pdf", bibliography: [], occurrences: [], stage: "queued" } }, 202);
      }
      return respond({ count: 0, results: [], next: null });
    }
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

const manuscript = { name: "synthetic-manuscript.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\nSynthetic fixture only") };
const requestId = (body: string) => body.match(/name="request_id"\r\n\r\n([^\r]+)/)?.[1];

test("audit upload retains the selected file and idempotency key after failure", async ({ page }) => {
  const state = await mockUpload(page);
  await page.goto("/account/citation-audits", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "引文体检：提交与任务" })).toBeVisible();
  await page.getByLabel("选择待检查稿件").setInputFiles(manuscript);
  await expect(page.getByRole("checkbox", { name: /扫描文字识别/ })).toBeDisabled();
  await expect(page.getByRole("radio", { name: /馆藏及本人选定材料/ })).toBeDisabled();
  await page.getByRole("button", { name: "提交检查", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("合成测试提交失败");
  await expect(page.getByText("synthetic-manuscript.pdf", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "提交检查", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(2);
  expect(requestId(state.requests[0])).toBeTruthy();
  expect(requestId(state.requests[1])).toBe(requestId(state.requests[0]));
  expect(state.requests[0]).toContain("citation_identification");
  expect(state.requests[0]).toContain("bibliography_identity");
  expect(state.requests[0]).toContain("version_page");
  expect(state.requests[0]).not.toContain("scan_ocr");
  expect(state.requests[0]).toContain("public_library");
});

test("audit check dependencies are explicit and a successful submit cannot duplicate itself", async ({ page }) => {
  const state = await mockUpload(page);
  state.fail = false;
  await page.goto("/account/citation-audits", { waitUntil: "domcontentloaded" });
  await page.getByLabel("选择待检查稿件").setInputFiles(manuscript);
  await page.getByRole("checkbox", { name: /书目身份/ }).uncheck();
  await expect(page.getByRole("checkbox", { name: /版本页码/ })).not.toBeChecked();
  await page.getByRole("checkbox", { name: /版本页码/ }).check();
  await expect(page.getByRole("checkbox", { name: /书目身份/ })).toBeChecked();
  await page.getByRole("button", { name: "提交检查", exact: true }).click();
  await expect(page.getByRole("button", { name: "已提交检查", exact: true })).toBeDisabled();
  await expect(page.getByRole("link", { name: "查看任务" })).toHaveAttribute("href", `/account/citation-audits/${auditId}/parse`);
  expect(state.requests).toHaveLength(1);
});

test("audit upload clears local manuscript metadata when the cookie owner changes", async ({ page }) => {
  const state = await mockUpload(page);
  await page.goto("/account/citation-audits", { waitUntil: "domcontentloaded" });
  await page.getByLabel("选择待检查稿件").setInputFiles(manuscript);
  await expect(page.getByText("synthetic-manuscript.pdf", { exact: true })).toBeVisible();
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "登录状态需要重新验证" })).toBeVisible();
  await expect(page.getByText("synthetic-manuscript.pdf", { exact: true })).toHaveCount(0);
  expect(state.requests).toHaveLength(0);
});
