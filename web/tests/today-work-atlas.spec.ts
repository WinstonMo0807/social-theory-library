import { expect, test, type Page } from "@playwright/test";

// Isolated UI contracts only. Real queue, permissions and SQL are covered by
// test_today_work_atlas_20261022.py during the final acceptance phase.
const id = "11111111-1111-4111-8111-111111111111";
const counts = { all: 1, editing: 1, intake: 0, catalog: 0, problems: 0, publication: 0 };
const row = { id: `topic:${id}`, object_id: id, object_type: "topic", title: "验收用主题草稿", label: "主题", updated_at: "2026-10-22T00:00:00Z", url: `/admin/topics/${id}`, state: "draft", state_label: "已保存 · 未发布", category: "editing", kind: "curation", action_label: "继续编辑", summary: "继续已有编辑", thumbnail_url: "" };
const data = { results: [row], count: 1, page: 1, page_size: 20, total_pages: 1, counts, checked_at: "2026-10-22T00:00:00Z", restricted: false, owner_basis: "我的工作按发起或编辑记录筛选。", ordering: "-updated_at", can_upload: true, can_create_issue: true };

async function setup(page: Page, result: typeof data = data, fail = false) {
  await page.context().addCookies([{ name: "stl_access", value: "opaque-today-work-test", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me/") return route.fulfill({ json: { id: 1, email: "today@example.test", display_name: "验收编辑", role: result.restricted ? "editor" : "admin", capabilities: ["access_back_office", "can_edit_metadata", "can_upload", "can_publish_work", ...(result.restricted ? [] : ["can_view_system_status", "can_manage_users"])], reading_preferences: {} } });
    if (url.pathname === "/api/catalog/admin/today-work/") return route.fulfill({ status: fail ? 503 : 200, json: fail ? { detail: "工作记录暂不可读取" } : result });
    if (url.pathname === "/api/catalog/admin/search/") return route.fulfill({ status: fail ? 503 : 200, json: fail ? { detail: "搜索暂不可读取" } : { ...result, counts: { all: result.count, catalog: 0, curation: result.count, processing: 0 } } });
    if (url.pathname === "/api/catalog/admin/work-notices/") return route.fulfill({ status: fail ? 503 : 200, json: fail ? { detail: "提醒暂不可读取" } : { count: 1, checked_at: data.checked_at, results: [{ ...row, state: "failed", state_label: "处理失败" }] } });
    return route.fulfill({ json: { results: [] } });
  });
}

test("exact continuation retains the queue filters in return_to", async ({ page }) => {
  await setup(page);
  await page.goto("/admin?category=editing&owner=me&page=2");
  const link = page.getByRole("list", { name: "待处理任务" }).getByRole("link", { name: "继续编辑" });
  const href = await link.getAttribute("href");
  const url = new URL(href!, "https://test.invalid");
  expect(url.pathname).toBe(`/admin/topics/${id}`);
  expect(url.searchParams.get("return_to")).toBe("/admin?category=editing&owner=me&page=2");
});

test("filters and ordering are sent to the queue instead of slicing a sample", async ({ page }) => {
  await setup(page);
  await page.goto("/admin");
  const request = page.waitForRequest(req => req.url().includes("/today-work/") && new URL(req.url()).searchParams.get("state") === "failed");
  await page.getByLabel("任务状态", { exact: true }).selectOption("failed");
  await request;
  await page.getByRole("button", { name: "按更新时间从旧到新排序" }).click();
  await expect(page).toHaveURL(/ordering=updated_at/);
});

test("read failure has retry and never shows a completed empty queue", async ({ page }) => {
  await setup(page, data, true);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "暂时无法获取任务列表" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新加载", exact: true })).toBeVisible();
  await expect(page.getByText("暂无待处理的任务", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "今日工作分类" })).toContainText("—");
});

test("empty queue exposes real entry points without example materials", async ({ page }) => {
  await setup(page, { ...data, results: [], count: 0, counts: { ...counts, all: 0, editing: 0 } });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "暂无待处理的任务" })).toBeVisible();
  await expect(page.getByRole("link", { name: "创建特别策划", exact: true })).toHaveAttribute("href", "/admin/recommendations#create-issue");
  await expect(page.getByText(row.title)).toHaveCount(0);
});

test("restricted scope shows permission guidance and locks maintenance", async ({ page }) => {
  await setup(page, { ...data, restricted: true });
  await page.goto("/admin");
  await expect(page.getByText("未授权内容不计入列表", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "申请权限" })).toHaveAttribute("href", "/feedback?category=usage");
  await expect(page.locator('.stl4-nav-locked').filter({ hasText: "运行维护" })).toBeVisible();
  await expect(page.getByLabel("任务类型", { exact: true }).locator('option[value="processing"]')).toHaveCount(0);
});

test("mobile task actions and keyboard navigation remain reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto("/admin");
  await expect(page.getByRole("navigation", { name: "移动端管理导航" })).toBeVisible();
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "后台导航" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "后台导航" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "待处理任务" }).getByRole("link", { name: "继续编辑" })).toBeVisible();
});

test("global search preserves its own return path and existing query", async ({ page }) => {
  await setup(page);
  await page.goto("/admin/search?q=检索词&kind=curation&page=2");
  await expect(page.getByLabel("搜索后台书名、作者、主题或任务编号")).toHaveValue("检索词");
  const href = await page.getByRole("list", { name: "搜索结果" }).getByRole("link", { name: row.title }).getAttribute("href");
  expect(new URL(href!, "https://test.invalid").searchParams.get("return_to")).toBe("/admin/search?q=%E6%A3%80%E7%B4%A2%E8%AF%8D&kind=curation&page=2");
});

test("notice badge opens real rows and failure remains visible", async ({ page }) => {
  await setup(page);
  await page.goto("/admin");
  await page.getByLabel("工作提醒，1项需要处理").click();
  const panel = page.getByRole("region", { name: "工作提醒", exact: true });
  await expect(panel).toContainText("处理失败");
  await expect(panel.getByRole("link", { name: "查看待处理问题" })).toHaveAttribute("href", "/admin?category=problems");
  await page.route("**/api/catalog/admin/work-notices/", route => route.fulfill({ status: 503, json: { detail: "提醒暂不可读取" } }));
  await panel.getByRole("button", { name: "刷新工作提醒" }).click();
  await expect(page.getByLabel("工作提醒读取失败")).toBeVisible();
  await expect(panel.getByRole("alert")).toContainText("提醒暂不可读取");
  await expect(panel.getByText("当前没有需要处理的提醒。", { exact: true })).toHaveCount(0);
});

test("mobile global search expands from the top icon", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto("/admin");
  const input = page.getByLabel("搜索后台书名、作者、主题或任务编号");
  await expect(input).toBeHidden();
  await page.getByRole("button", { name: "打开后台搜索" }).click();
  await expect(input).toBeVisible();
  await input.fill("主题");
  await page.locator("#admin-global-search").getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/search\?q=/);
});
