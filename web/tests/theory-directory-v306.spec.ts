import { expect, test } from "@playwright/test";

// Definitions for final acceptance only. SSR reads the disposable real API.
const api = "http://127.0.0.1:8105/api";
const path = "/theories/directory";
const parent = "45000000-0000-4000-8000-000000000071";
const theory = "e2e-theory-theory";
const results = "section[aria-labelledby='directory-results-heading']";

test.beforeEach(async ({ baseURL }) => {
  expect(baseURL).toBe("http://127.0.0.1:3105");
});

test("directory shows actual hierarchy and opens only its public direct children", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/theory-system/directory/?parent=${parent}`);
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ count: 2, parent: { id: parent, name: "E2E已确认层级" } });
  await page.goto(path);
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1, name: "理论目录", exact: true })).toBeVisible();
  await expect(page.locator(results).getByRole("link", { name: "E2E未公开层级条目", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "展开E2E已确认层级的2个直属条目", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`parent=${parent}`));
  await expect(page.locator(results)).toContainText("共 2 个公开条目");
  await expect(page.locator(results)).toContainText("此处列出直属条目");
  await expect(page.locator(results).getByRole("link", { name: "E2E理论传统", exact: true })).toBeVisible();
  await expect(page.locator(results).getByRole("link", { name: "E2E目录子流派", exact: true })).toBeVisible();
});

test("selecting a theory preserves filters and exposes actual scholars, concepts and evidence", async ({ page }) => {
  await page.goto(`${path}?type=theory_tradition&discipline=e2e-theory-discipline&parent=${parent}`);
  await page.locator(results).getByRole("link", { name: "E2E理论传统", exact: true }).click();
  const detail = page.getByRole("complementary", { name: "所选条目详情", exact: true });
  await expect(detail.getByRole("heading", { level: 2, name: "E2E理论传统", exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("discipline")).toBe("e2e-theory-discipline");
  expect(new URL(page.url()).searchParams.get("parent")).toBe(parent);
  expect(new URL(page.url()).searchParams.get("selected")).toBe(theory);
  await expect(detail.getByRole("region", { name: "相关学者", exact: true }).getByRole("link", { name: /E2E代表学者甲/ })).toBeVisible();
  await expect(detail.getByRole("region", { name: "关联概念", exact: true }).getByRole("link", { name: "E2E测试概念", exact: true }))
    .toHaveAttribute("href", "/theories/nodes/e2e-theory-concept");
  await expect(detail.getByRole("link", { name: "查看原文依据", exact: true })).toHaveAttribute("href", /\/reader\/.+[?&]revision=/);
  await detail.getByRole("link", { name: "返回上级", exact: true }).click();
  await expect(page).not.toHaveURL(/selected=/);
  expect(new URL(page.url()).searchParams.has("parent")).toBe(false);
  expect(new URL(page.url()).searchParams.get("discipline")).toBe("e2e-theory-discipline");
});

test("search result expansion clears the parent-name query before loading real children", async ({ page }) => {
  await page.goto(`${path}?q=${encodeURIComponent("E2E已确认层级")}`);
  await expect(page.locator(results)).toContainText("共 1 个公开条目");
  await page.getByRole("link", { name: "展开E2E已确认层级的2个直属条目", exact: true }).click();
  await expect(page.locator(results)).toContainText("共 2 个公开条目");
  expect(new URL(page.url()).searchParams.has("q")).toBe(false);
  await expect(page.getByRole("searchbox", { name: "搜索理论、概念或学者", exact: true })).toHaveValue("");
});

test("draft selection has an explicit unavailable state while the real directory remains usable", async ({ page }) => {
  await page.goto(`${path}?selected=e2e-directory-draft`);
  const detail = page.getByRole("complementary", { name: "所选条目详情", exact: true });
  await expect(detail.getByRole("heading", { name: "来源未发布或已不可用", exact: true })).toBeVisible();
  await expect(detail.getByRole("link", { name: "查看条目详情", exact: true })).toHaveCount(0);
  await expect(page.locator(results).getByRole("link", { name: "E2E理论传统", exact: true })).toBeVisible();
  await detail.getByRole("link", { name: "显示已有内容", exact: true }).click();
  await expect(detail.getByRole("heading", { name: "选择一个条目", exact: true })).toBeVisible();
});

test("a zero search is distinct from an unavailable parent or invalid page", async ({ page }) => {
  await page.goto(`${path}?q=E2E-no-such-directory-entry`);
  await expect(page.locator(results).getByRole("status")).toContainText("没有匹配结果");
  await expect(page.locator(results).getByRole("alert")).toHaveCount(0);
  for (const query of ["parent=e2e-directory-draft", "page=999999"]) {
    await page.goto(`${path}?${query}`);
    await expect(page.locator(results).getByRole("alert")).toContainText("目录来源当前不可用");
    await expect(page.locator(results).getByRole("status")).toHaveCount(0);
  }
});

test("the desktop directory has three columns and a keyboard reachable selection", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(path);
  const navigation = page.getByRole("complementary", { name: "学科与条目类型", exact: true });
  const detail = page.getByRole("complementary", { name: "所选条目详情", exact: true });
  const [a, b, c] = await Promise.all([navigation.boundingBox(), page.locator(results).boundingBox(), detail.boundingBox()]);
  expect(a && b && c).toBeTruthy();
  expect(a!.x + a!.width).toBeLessThanOrEqual(b!.x);
  expect(b!.x + b!.width).toBeLessThanOrEqual(c!.x);
  const link = page.locator(results).getByRole("link", { name: "E2E理论传统", exact: true });
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(detail.getByRole("heading", { name: "E2E理论传统", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("mobile detail closes with Escape and the same entry can open again", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${path}?parent=${parent}`);
  const link = page.locator(results).getByRole("link", { name: "E2E理论传统", exact: true });
  await link.click();
  const drawer = page.getByRole("dialog", { name: "所选条目详情", exact: true });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("heading", { name: "E2E理论传统", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(page).not.toHaveURL(/selected=/);
  expect(new URL(page.url()).searchParams.get("parent")).toBe(parent);
  await link.click();
  await expect(drawer).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("directory browsing modes pass only filters supported by the destination", async ({ page }) => {
  await page.goto(`${path}?discipline=e2e-theory-discipline&q=E2E`);
  const modes = page.getByRole("navigation", { name: "理论浏览方式", exact: true });
  await expect(modes.getByRole("link", { name: "目录", exact: true })).toHaveAttribute("aria-current", "page");
  for (const [label, route] of [["时间线", "/theories/timeline"], ["关系图", "/theories/graph"]]) {
    const href = await modes.getByRole("link", { name: label, exact: true }).getAttribute("href");
    const url = new URL(href!, "http://127.0.0.1:3105");
    expect(url.pathname).toBe(route);
    expect(url.searchParams.get("discipline")).toBe("e2e-theory-discipline");
    expect(url.searchParams.get("q")).toBe(label === "时间线" ? "E2E" : null);
  }
});
