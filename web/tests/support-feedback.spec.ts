import { expect, test, type Page } from "@playwright/test";
import { safeFeedbackPath, feedbackPathFromInput, type FeedbackInput } from "../lib/api/feedback.client";

// Synthetic cases only. Run against a local app at unified acceptance, never production.
const receiptId = "70000000-0000-4000-8000-000000000001";
async function setup(page: Page) {
  const state = { status: 201, requests: [] as FeedbackInput[], refreshes: 0 };
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ detail: "合成访客" }, 401);
    if (path === "/api/auth/token/refresh/") { state.refreshes += 1; return respond({ detail: "不应自动刷新写请求" }, 401); }
    if (path === "/api/reading/source-status/") return respond({ path: "/help", canonical_path: "/help", status: "page", title: "合成公开页面", authors: [],
      cover_url: "", source_type: "", version_label: "", location: "", updated_at: null, checked_at: "2026-10-18T12:00:00Z",
      can_subscribe: false, reader_url: "", work_id: null, edition_id: null, asset_id: null, catalog_revision_id: null, document_revision_id: null, notice: "合成页面" });
    if (path === "/api/catalog/feedback/") {
      const input = route.request().postDataJSON() as FeedbackInput; state.requests.push(input);
      if (state.status >= 400) return respond({ detail: state.status === 409 ? "此请求编号已用于另一条反馈" : "合成服务暂时失败" }, state.status);
      return respond({ id: receiptId, request_id: input.request_id, status: "submitted", created_at: "2026-10-18T12:00:00Z", message: "反馈已接收，这是合成回执。" }, state.status);
    }
    return respond({ count: 0, results: [] });
  });
  return state;
}
const feedback = (page: Page) => page.locator(".stl4-feedback-form");
test("address-bar feedback input retains only a same-origin public path", () => {
  const origin = "http://192.168.1.20:3000";
  expect(feedbackPathFromInput(`${origin}/reader/abc?page=12&token=private#selection`, origin)).toBe("/reader/abc?page=12");
  for (const value of ["https://other.invalid/help", `${origin}/account/notes`, `${origin}/admin`, `${origin}/works/%2e%2e/help`, "http://user:password@192.168.1.20:3000/help", "javascript:alert(1)", "//other.invalid/help"]) {
    expect(feedbackPathFromInput(value, origin)).toBe("");
  }
});
async function fillFeedback(page: Page, text = "合成测试问题：该页面的页码说明需要核对。") {
  await feedback(page).getByRole("textbox", { name: "问题描述" }).fill(text);
  await feedback(page).getByRole("checkbox").check();
}

test("public feedback paths discard private routes, tokens and encoded traversal", () => {
  for (const path of ["//other.invalid/x", "https://other.invalid", "/account/notes", "/admin/library", "/works/%2e%2e/account", "/works/%252e%252e/account", "/reader\\secret", "/login", "/help/./reading", "/help/%20reading", "/help/%FF", "/help/%252525252e"]) expect(safeFeedbackPath(path)).toBe("");
  expect(safeFeedbackPath("/reader/70000000-0000-4000-8000-000000000001?page=12&token=do-not-send&q=private#quote")).toBe("/reader/70000000-0000-4000-8000-000000000001?page=12");
  expect(safeFeedbackPath("/explore?q=do-not-send")).toBe("/explore");
  expect(safeFeedbackPath("/help/%72eading")).toBe("/help/reading");
  expect(safeFeedbackPath("/reader/abc?page=1&%70age=2")).toBe("/reader/abc");
  expect(safeFeedbackPath("/reader/abc?page=999999")).toBe("/reader/abc?page=999999");
  expect(safeFeedbackPath("/reader/abc?page=1000000")).toBe("/reader/abc");
});

test("FAQ filters real help entries and offers a useful no-answer path", async ({ page }) => {
  await setup(page); await page.goto("/help?section=faq", { waitUntil: "domcontentloaded" });
  await page.getByRole("searchbox", { name: "搜索问题或关键词" }).fill("页码");
  await expect(page.locator(".stl4-support-faq details")).toContainText(["印刷页码和 PDF 页码为什么不同？"]);
  await page.getByText("印刷页码和 PDF 页码为什么不同？", { exact: true }).click();
  await expect(page.locator(".stl4-support-faq details[open]")).toContainText("PDF 物理页");
  await page.getByRole("searchbox", { name: "搜索问题或关键词" }).fill("zz-no-synthetic-answer-zz");
  await expect(page.getByRole("heading", { name: "没有找到答案？" })).toBeVisible();
  await expect(page.getByRole("link", { name: "提交问题" })).toHaveAttribute("href", "/feedback?category=usage");
  await page.getByRole("button", { name: "显示全部问题" }).click();
  await expect(page.locator(".stl4-support-faq details")).toHaveCount(8);
});

test("article anchors and citation controls copy an expressly labelled example", async ({ page }) => {
  await setup(page);
  await page.addInitScript(() => { const capture: string[] = []; Object.defineProperty(window, "supportCopied", { value: capture }); Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (text: string) => { capture.push(text); } } }); });
  await page.goto("/help/citation", { waitUntil: "domcontentloaded" });
  await page.locator(".stl4-help-toc").getByRole("link", { name: "复制引用", exact: true }).click();
  await expect(page).toHaveURL(/#copy$/);
  const example = page.getByLabel("引用格式操作示例");
  await example.getByRole("button", { name: "MLA", exact: true }).click();
  await example.getByLabel("PDF 页码（示例）").fill("23");
  await example.getByRole("button", { name: "复制示例", exact: true }).click();
  const copied = await page.evaluate(() => (window as unknown as { supportCopied: string[] }).supportCopied);
  expect(copied[0]).toContain("引用格式示例，非真实文献"); expect(copied[0]).toContain("PDF 页序：23");
});

test("mobile help uses disclosure navigation and keeps all categories reachable", async ({ page }) => {
  await setup(page); await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/help", { waitUntil: "domcontentloaded" });
  const nav = page.getByRole("navigation", { name: "手机帮助栏目", exact: true });
  await expect(nav.locator("details")).toHaveCount(6);
  await nav.getByText("常见问题", { exact: true }).click();
  await expect(nav.getByRole("link", { name: "浏览常见问题" })).toBeVisible();
  await nav.getByRole("link", { name: "浏览常见问题" }).click();
  await expect(page).toHaveURL(/section=faq/);
});

test("anonymous feedback requires explicit consent, respects 500 characters and shows an actual receipt", async ({ page }) => {
  const state = await setup(page); await page.goto("/feedback", { waitUntil: "domcontentloaded" });
  await expect(feedback(page).getByRole("textbox", { name: "问题描述" })).toHaveAttribute("maxlength", "500");
  await feedback(page).getByRole("textbox", { name: "问题描述" }).fill("合成访客问题，联系邮箱不填写。");
  await expect(feedback(page).getByRole("button", { name: "提交反馈", exact: true })).toBeDisabled();
  await feedback(page).getByRole("checkbox").check();
  await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click();
  await expect(page.getByRole("region", { name: "反馈提交结果" })).toContainText(receiptId);
  expect(state.requests).toHaveLength(1); expect(state.requests[0]).toMatchObject({ contact: "", path: "", consent: true });
  expect(state.requests[0].request_id).toMatch(/^[0-9a-f-]{36}$/i);
});

test("unknown result retains the submitted payload and nonce across retry", async ({ page }) => {
  const state = await setup(page); state.status = 503; await page.goto("/feedback", { waitUntil: "domcontentloaded" }); await fillFeedback(page);
  await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click();
  await expect(feedback(page).getByRole("alert")).toContainText("原请求已保留");
  await expect(feedback(page).getByRole("textbox", { name: "问题描述" })).toBeDisabled();
  state.status = 200; await feedback(page).getByRole("button", { name: "重试本次提交", exact: true }).click();
  await expect(page.getByRole("heading", { name: "提交成功", exact: true })).toBeVisible();
  expect(state.requests).toHaveLength(2); expect(state.requests[1]).toEqual(state.requests[0]);
});

test("related page normalization strips secrets and removal sends no context", async ({ page }) => {
  const state = await setup(page); await page.goto("/feedback?path=%2Faccount%2Fnotes", { waitUntil: "domcontentloaded" });
  await expect(feedback(page)).toContainText("未关联该地址");
  await feedback(page).getByRole("button", { name: "关联公开页面", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择相关页面" });
  await dialog.getByRole("button", { name: "首页", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "首页", exact: true })).toHaveAttribute("aria-pressed", "true");
  await dialog.getByText("手动填写网址", { exact: true }).click();
  await dialog.getByLabel("本站页面地址").fill("/reader/70000000-0000-4000-8000-000000000001?page=8&token=secret&q=private");
  await dialog.getByRole("button", { name: "关联页面", exact: true }).click();
  await expect(page.locator(".stl4-feedback-related")).toContainText("?page=8");
  await expect(page.locator(".stl4-feedback-related")).not.toContainText("secret");
  await feedback(page).getByRole("button", { name: "移除相关页面" }).click();
  await fillFeedback(page); await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(1); expect(state.requests[0].path).toBe("");
});

test("409 keeps editable input and a changed payload receives a new request id", async ({ page }) => {
  const state = await setup(page); state.status = 409; await page.goto("/feedback", { waitUntil: "domcontentloaded" }); await fillFeedback(page);
  await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click();
  await expect(feedback(page).getByRole("alert")).toContainText("此请求编号");
  await expect(feedback(page).getByRole("textbox", { name: "问题描述" })).toBeEnabled();
  await feedback(page).getByRole("textbox", { name: "问题描述" }).fill("合成修改后的反馈，输入未被错误清空。"); state.status = 201;
  await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click(); await expect(page.getByRole("heading", { name: "提交成功", exact: true })).toBeVisible();
  expect(state.requests[1].request_id).not.toBe(state.requests[0].request_id);
});

test("cancelling an unsaved draft can be declined without data loss", async ({ page }) => {
  await setup(page); await page.goto("/feedback", { waitUntil: "domcontentloaded" }); await fillFeedback(page, "这条合成反馈暂不放弃。");
  page.once("dialog", dialog => dialog.dismiss()); await feedback(page).getByRole("button", { name: "取消", exact: true }).click();
  await expect(page).toHaveURL(/\/feedback$/); await expect(feedback(page).getByRole("textbox", { name: "问题描述" })).toHaveValue("这条合成反馈暂不放弃。");
});

test("session changes clear sensitive feedback and a 401 write never refreshes or replays", async ({ page }) => {
  const state = await setup(page); state.status = 401; await page.goto("/feedback", { waitUntil: "domcontentloaded" }); await fillFeedback(page);
  await feedback(page).getByRole("textbox", { name: "联系方式（可选）" }).fill("synthetic@example.invalid");
  await feedback(page).getByRole("button", { name: "提交反馈", exact: true }).click(); await expect(feedback(page).getByRole("alert")).toBeVisible();
  expect(state.requests).toHaveLength(1); expect(state.refreshes).toBe(0);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(feedback(page).getByRole("textbox", { name: "问题描述" })).toHaveValue("");
  await expect(feedback(page).getByRole("textbox", { name: "联系方式（可选）" })).toHaveValue("");
  await expect(feedback(page).getByRole("checkbox")).not.toBeChecked();
});
