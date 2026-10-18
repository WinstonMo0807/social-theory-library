import { expect, test, type Page } from "@playwright/test";

// Synthetic browser cases. Written now; executed only at unified acceptance.
async function setup(page: Page, authenticated = false) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const body = path === "/api/auth/me/" ? { id: 91, display_name: "Synthetic", email: "synthetic@example.invalid", role: "reader", capabilities: [], reading_preferences: {} } : { count: 0, results: [] };
    return route.fulfill({ status: path === "/api/auth/me/" && !authenticated ? 401 : 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/about", { waitUntil: "domcontentloaded" });
}

test("mobile menu retains the original page and highlights its actual route", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "书库导航", exact: true });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "关于我们", exact: true })).toHaveAttribute("aria-current", "page");
  const bounds = await drawer.locator(".site-menu-panel").boundingBox();
  expect(bounds!.x).toBeGreaterThan(30);
  await expect(drawer.locator(".site-menu-backdrop")).toBeVisible();
  await expect(drawer.getByRole("link", { name: "管理后台", exact: true })).toHaveCount(0);
});

test("menu search submits the entered query through the real explorer route", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  await page.getByRole("searchbox", { name: "搜索书名、作者、概念、主题", exact: true }).fill("合成检索词");
  await page.getByRole("button", { name: "提交菜单搜索", exact: true }).click();
  await expect(page).toHaveURL(/\/explore\?q=/);
  expect(new URL(page.url()).searchParams.get("q")).toBe("合成检索词");
});

test("escape closes the menu, restores focus and preserves scroll", async ({ page }) => {
  await setup(page);
  await page.evaluate(() => { document.querySelector("main")!.setAttribute("style", "min-height:3000px"); window.scrollTo(0, 400); });
  // Open via keyboard without Playwright scrolling the header into view.
  await page.locator(".menu-button").evaluate((button: HTMLButtonElement) => { button.focus({ preventScroll: true }); button.click(); });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "打开菜单", exact: true })).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(400, 0);
});

test("account entry stores only a public location and offers an explicit return", async ({ page }) => {
  await setup(page, true);
  await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  await page.getByRole("dialog").getByRole("link", { name: "我的资料", exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("link", { name: "返回原页面", exact: true })).toHaveAttribute("href", "/about");
  await page.getByRole("link", { name: "返回原页面", exact: true }).click();
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("status").filter({ hasText: "已返回先前页面" })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("stl.navigation.public-return.v1"))).toBeNull();
});

test("untrusted return locations are not exposed as account links", async ({ page }) => {
  await setup(page, true);
  await page.evaluate(() => sessionStorage.setItem("stl.navigation.public-return.v1", JSON.stringify({ href: "//outside.invalid", y: 100, at: Date.now() })));
  await page.goto("/account", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("link", { name: "返回原页面", exact: true })).toHaveCount(0);
});
