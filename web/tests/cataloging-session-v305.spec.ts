import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Only selects the development API origin; no business request is mocked.
  await page.route("**/runtime-config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:'http://127.0.0.1:8105/api'});",
  }));
});

async function login(page: Page, role: "curator" | "reader") {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "curator" ? /\/admin$/ : /\/account$/);
}

test("non-superuser creates a real manual session, saves and reopens it", async ({ page }) => {
  await login(page, "curator");
  await page.goto("/admin/cataloging/new");
  await page.getByLabel("作品题名", { exact: true }).fill("E2E 无文件编目");
  await page.getByRole("button", { name: "创建草稿并开始编目" }).click();
  await expect(page).toHaveURL(/\/admin\/cataloging\/[a-f0-9-]+#work/);
  const url = page.url();
  await expect(page.getByRole("heading", { name: "E2E 无文件编目", exact: true, level: 1 })).toBeVisible();
  await page.getByLabel("副题名", { exact: true }).fill("保存后仍在");
  await page.getByRole("button", { name: "保存草稿", exact: true }).first().click();
  await expect(page.getByText("草稿已保存。", { exact: true })).toBeVisible();
  await page.goto("/admin/library");
  await page.goto(url);
  await expect(page.getByLabel("副题名", { exact: true })).toHaveValue("保存后仍在");
  const sessionId = new URL(url).pathname.split("/").at(-1);
  const response = await page.request.get(`http://127.0.0.1:8105/api/catalog/admin/cataloging-sessions/${sessionId}/`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.session.upload_item_id).toBeNull();
  expect(payload.workspace.context.publication_state).toBe("draft");

  await page.goto(`${url.split("#")[0]}#contributors`);
  await page.getByRole("button", { name: "智能查找", exact: true }).first().click();
  await page.getByLabel("新学者名称", { exact: true }).fill("E2E 人工新建作者");
  await page.getByRole("button", { name: "创建学者并关联", exact: true }).click();
  await expect(page.getByText("已新建馆内草稿对象并关联当前作品。", { exact: true })).toBeVisible();
  const withAuthor = await page.request.get(`http://127.0.0.1:8105/api/catalog/admin/cataloging-sessions/${sessionId}/`);
  const authored = await withAuthor.json();
  expect(authored.session.upload_item_id).toBeNull();
  expect(authored.workspace.data.contributors.items).toHaveLength(1);
  expect(authored.workspace.data.contributors.items[0].display_name).toBe("E2E 人工新建作者");
  await page.goto(`${url.split("#")[0]}#publication`);
  await page.getByRole("button", { name: "发布前检查", exact: true }).click();
  const diff = page.getByRole("region", { name: "发布内容差异" });
  await expect(diff).toBeVisible();
  await expect(diff.getByText("E2E 人工新建作者", { exact: true })).toBeVisible();
  await expect(diff.getByText("准备发布", { exact: true })).toBeVisible();
});

test("a reader cannot open cataloging or submit a manual catalog", async ({ page }) => {
  await login(page, "reader");
  await page.goto("/admin/cataloging/new");
  await expect(page.getByText("当前账户没有管理权限", { exact: true })).toBeVisible();
  const response = await page.request.get("http://127.0.0.1:8105/api/catalog/admin/cataloging-sessions/");
  expect(response.status()).toBe(403);
});
