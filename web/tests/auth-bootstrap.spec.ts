import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";

type MockAuthOptions = {
  role?: "admin" | "editor" | "reviewer" | "reader";
  meStatus?: number;
  refreshStatus?: number;
  failedResource?: string;
  abortResource?: string;
  state?: {
    authenticated: boolean;
    role?: "admin" | "editor" | "reviewer" | "reader";
  };
};

const emptyPage = { count: 0, next: null, results: [] };

async function addOpaqueCookie(context: BrowserContext) {
  await context.addCookies([{
    name: "stl_access",
    value: "opaque-http-only-test-cookie",
    domain: "127.0.0.1",
    path: "/",
    httpOnly: true,
    secure: false,
    sameSite: "Lax",
  }]);
}

function fulfillJson(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page, options: MockAuthOptions = {}) {
  const role = options.role ?? "reader";
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const currentRole = options.state?.role ?? role;
    if (options.abortResource && path.includes(options.abortResource)) {
      await route.abort("failed");
      return;
    }
    if (options.failedResource && path.includes(options.failedResource)) {
      await fulfillJson(route, 500, { error: { detail: { detail: "resource failed" } } });
      return;
    }
    if (path === "/api/auth/me/") {
      const authenticated = options.state?.authenticated ?? true;
      const status = authenticated ? options.meStatus ?? 200 : 401;
      await fulfillJson(route, status, status === 200 ? {
        id: currentRole === "admin" ? 1 : 2,
        email: `${currentRole}@example.test`,
        display_name: currentRole === "admin" ? "Admin Tester" : "Reader Tester",
        role: currentRole,
        reading_preferences: {},
      } : { error: { detail: { detail: "authentication failed" } } });
      return;
    }
    if (path === "/api/auth/token/refresh/") {
      const authenticated = options.state?.authenticated ?? true;
      await fulfillJson(route, authenticated ? options.refreshStatus ?? 200 : 401, {});
      return;
    }
    if (path === "/api/auth/login/") {
      if (options.state) options.state.authenticated = true;
      await fulfillJson(route, 200, {
        session: "cookie",
        user: {
          role: currentRole,
          display_name: currentRole === "admin" ? "Admin Tester" : "Reader Tester",
        },
      });
      return;
    }
    if (path === "/api/auth/logout/") {
      if (options.state) options.state.authenticated = false;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/api/ingestion/dashboard/") {
      await fulfillJson(route, 200, {
        documents: { total: 0, published: 0, withdrawn: 0 },
        pdf_assets: 0,
        theory_schools: 0,
        scholars: 0,
        users: 0,
        needs_review: 0,
        processing: 0,
        recent_items: [],
        status_counts: {},
      });
      return;
    }
    if (path === "/api/catalog/admin/usage-analytics/") {
      await fulfillJson(route, 200, { anonymous_sessions: 0, events: {}, zero_result_searches: 0 });
      return;
    }
    if (path === "/api/catalog/hot-searches/") {
      await fulfillJson(route, 200, { results: [] });
      return;
    }
    if (path.startsWith("/api/reading/")) {
      await fulfillJson(route, 200, emptyPage);
      return;
    }
    await fulfillJson(route, 200, { results: [] });
  });
}

async function submitLogin(page: Page, email: string) {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("邮箱").fill(email);
  await page.locator('input[name="password"]').fill("Browser-Test-Password-2026");
  await page.getByRole("button", { name: "登录" }).click();
}

test("real Django cookie supports reload, logout and reader-to-admin switching", async ({ page, context }) => {
  await page.route("**/runtime-config.js", (route) => route.fulfill({
    status: 200,
    contentType: "application/javascript",
    body: "window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({ apiBase: 'http://127.0.0.1:8000/api' });",
  }));

  await submitLogin(page, "reader-e2e@example.test");
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText("Reader E2E", { exact: true }).first()).toBeVisible();
  const readerCookies = await context.cookies("http://127.0.0.1:8000/api/auth/token/refresh/");
  expect(readerCookies.find((cookie) => cookie.name === "stl_access")?.httpOnly).toBe(true);
  expect(readerCookies.find((cookie) => cookie.name === "stl_refresh")?.httpOnly).toBe(true);

  await page.evaluate(() => localStorage.removeItem("library_session_active"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("Reader E2E", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: /退出登录/ }).click();
  await expect(page).toHaveURL(/\/$/);

  await submitLogin(page, "admin-e2e@example.test");
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText("Admin E2E", { exact: true })).toBeVisible();
  await expect(page.getByText("Reader E2E", { exact: true })).toHaveCount(0);
});

test("reader login reaches Reader Center and survives reload", async ({ page }) => {
  const state = { authenticated: false, role: "reader" as const };
  await mockApi(page, { state });

  await submitLogin(page, "reader@example.test");

  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText("Reader Tester", { exact: true }).first()).toBeVisible();
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("Reader Tester", { exact: true }).first()).toBeVisible();
});

test("admin login reaches Admin directly", async ({ page }) => {
  const state = { authenticated: false, role: "admin" as const };
  await mockApi(page, { state });

  await submitLogin(page, "admin@example.test");

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText("管理后台", { exact: true })).toBeVisible();
  await expect(page.getByText("Admin Tester", { exact: true })).toBeVisible();
});

test("logout and reader-to-admin switching do not reuse the previous profile", async ({ page }) => {
  const state: NonNullable<MockAuthOptions["state"]> = {
    authenticated: false,
    role: "reader",
  };
  await mockApi(page, { state });
  await submitLogin(page, "reader@example.test");
  await expect(page.getByText("Reader Tester", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: /退出登录/ }).click();
  await expect(page).toHaveURL(/\/$/);
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBeNull();

  state.role = "admin";
  await submitLogin(page, "admin@example.test");
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText("Admin Tester", { exact: true })).toBeVisible();
  await expect(page.getByText("Reader Tester", { exact: true })).toHaveCount(0);
});

test("Admin direct link recovers a valid cookie without localStorage and survives reload", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await mockApi(page, { role: "admin" });

  await page.goto("/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("管理后台", { exact: true })).toBeVisible();
  await expect(page.getByText("Admin Tester", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");
  await page.evaluate(() => localStorage.removeItem("library_session_active"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("管理后台", { exact: true })).toBeVisible();
});

test("authenticated reader sees Admin forbidden state without logout", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await page.addInitScript(() => localStorage.setItem("library_session_active", "1"));
  await mockApi(page, { role: "reader" });

  await page.goto("/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("当前账户没有管理权限", { exact: true })).toBeVisible();
  expect(page.url()).toContain("/admin");
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");
});

test("role changes are revalidated when the protected tab regains focus", async ({ page, context }) => {
  const state: NonNullable<MockAuthOptions["state"]> = {
    authenticated: true,
    role: "admin",
  };
  await addOpaqueCookie(context);
  await mockApi(page, { state });
  await page.goto("/admin", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("管理后台", { exact: true })).toBeVisible();

  state.role = "reader";
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  await expect(page.getByText("当前账户没有管理权限", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");
});

test("auth 500 remains a temporary error and keeps the session", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await page.addInitScript(() => localStorage.setItem("library_session_active", "1"));
  await mockApi(page, { role: "admin", meStatus: 500 });

  await page.goto("/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("认证服务暂时不可用", { exact: true })).toBeVisible();
  expect(page.url()).toContain("/admin");
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");
});

test("unrecoverable 401 clears the hint and redirects to login", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await mockApi(page, { role: "reader", meStatus: 401, refreshStatus: 401 });
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.evaluate(() => localStorage.setItem("library_session_active", "1"));

  await page.goto("/account", { waitUntil: "domcontentloaded" });

  await expect(page).toHaveURL(/\/login\?next=%2Faccount|\/login\?next=\/account/);
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBeNull();
});

test("Reader Center resource 500 leaves other modules and authentication available", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await mockApi(page, { role: "reader", failedResource: "/reading/saved/" });

  await page.goto("/account", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Reader Tester", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("部分内容暂时无法加载", { exact: true })).toBeVisible();
  await expect(page.getByText(/文献收藏/)).toBeVisible();
  expect(page.url()).toContain("/account");
  expect(await page.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");
});

test("Reader Center resource network error does not log the reader out", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await mockApi(page, { role: "reader", abortResource: "/reading/history/" });

  await page.goto("/account", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Reader Tester", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("部分内容暂时无法加载", { exact: true })).toBeVisible();
  await expect(page.getByText(/^阅读历史：/)).toBeVisible();
  expect(page.url()).toContain("/account");
});

test("Reader notes deep link bootstraps from the cookie and survives a page reload", async ({ page, context }) => {
  await addOpaqueCookie(context);
  await mockApi(page, { role: "reader" });

  await page.goto("/account/notes/asset-1", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "作品笔记" })).toBeVisible();
  await page.evaluate(() => localStorage.removeItem("library_session_active"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "作品笔记" })).toBeVisible();
});

test("storage loss revalidates the server cookie while logout propagates to another tab", async ({ context }) => {
  const state = { authenticated: true };
  await addOpaqueCookie(context);
  const tabA = await context.newPage();
  const tabB = await context.newPage();
  await mockApi(tabA, { role: "admin", state });
  await mockApi(tabB, { role: "admin", state });
  await tabA.goto("/admin", { waitUntil: "domcontentloaded" });
  await tabB.goto("/admin", { waitUntil: "domcontentloaded" });
  await expect(tabB.getByText("管理后台", { exact: true })).toBeVisible();

  await tabA.evaluate(() => localStorage.removeItem("library_session_active"));
  await expect(tabB.getByText("管理后台", { exact: true })).toBeVisible();
  expect(await tabB.evaluate(() => localStorage.getItem("library_session_active"))).toBe("1");

  state.authenticated = false;
  await tabA.evaluate(() => localStorage.removeItem("library_session_active"));
  await expect(tabB).toHaveURL(/\/login\?next=%2Fadmin|\/login\?next=\/admin/);
});
