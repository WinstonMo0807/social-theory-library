import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8105/api/catalog";

test("main Studio shows actual public modules and edits through a protected draft before explicit publication", async ({ page }) => {
  await page.context().route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("curator-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const slug = `studio-v306-${Date.now()}`;
  const csrf = (await page.context().cookies(api)).find((cookie) => cookie.name === "csrftoken")?.value;
  expect(csrf, "normal login must establish the CSRF cookie before test setup writes").toBeTruthy();
  const created = await page.request.post(`${api}/admin/scholars/`, {
    headers: { "X-CSRFToken": csrf!, Origin: "http://127.0.0.1:3105", Referer: "http://127.0.0.1:3105/admin/knowledge" },
    data: { preferred_name: "主入口操作学者", slug, short_description: "原公开简介", editorial_status: "published" },
  });
  expect(created.status()).toBe(201);
  const scholar = await created.json();
  const studioUrl = `/admin/knowledge?object_type=scholar&object_id=${scholar.id}`;
  await page.goto(studioUrl);
  const tree = page.getByRole("region", { name: "公开页面管理", exact: true });
  await expect(tree).toBeVisible();
  await expect(tree).toContainText("身份与名称");
  await expect(tree.getByRole('combobox',{name:'选择页面'})).toBeVisible();
  expect(await tree.innerText()).not.toMatch(/契约|内容覆盖|Canonical|source_revision|Legacy fallback/);
  await page.screenshot({path:'../output/playwright/v306-usability-content-manager.png',fullPage:true});
  const history=page.locator('.assistance-history');
  await history.locator('summary').first().click();
  await expect(history).toContainText("不表示建议内容一定正确");
  // Reproduce a slow first detail read. The editor must not expose a blank
  // form which overwrites input when the requested object finally arrives.
  let releaseDetail!: () => void;
  const heldDetail = new Promise<void>((resolve) => { releaseDetail = resolve; });
  await page.route(`**/api/catalog/admin/scholars/${scholar.id}/`, async (route) => {
    if (route.request().method() === "GET") await heldDetail;
    await route.continue();
  });
  await page.getByRole("link", { name: "编辑资料", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^页面简介/ })).toHaveCount(0);
  releaseDetail();
  await expect(page.getByRole("textbox", { name: /^页面简介/ })).toHaveValue("原公开简介");
  await page.getByRole("textbox", { name: /^页面简介/ }).fill("从主Studio进入编辑后的新简介");
  const savedResponse = page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/admin/scholars/${scholar.id}/`));
  await page.getByRole("button", { name: "保存本页学者资料", exact: true }).click();
  const saved = await savedResponse;
  expect(saved.status()).toBe(202);
  expect(saved.request().postDataJSON().short_description).toBe("从主Studio进入编辑后的新简介");
  await expect.poll(async () => (await (await page.request.get(`${api}/admin/knowledge-workspace/?selected_type=scholar&selected_id=${scholar.id}`)).json()).studio.selection.public_control.draft_published_diff.some((row: { field: string }) => row.field === "short_description")).toBe(true);
  expect((await (await page.request.get(`${api}/scholars/${slug}/`)).json()).short_description).toBe("原公开简介");
  await page.goto(studioUrl);
  await expect(tree).toContainText("从主Studio进入编辑后的新简介");
  const [preview] = await Promise.all([page.waitForEvent("popup"), tree.getByRole("link", { name: "预览简介与学术位置", exact: true }).click()]);
  await expect(preview.getByText("从主Studio进入编辑后的新简介", { exact: true }).first()).toBeVisible();
  await preview.close();
  await page.getByRole("button", { name: "确认发布本次编辑", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`${api}/scholars/${slug}/`)).json()).short_description).toBe("从主Studio进入编辑后的新简介");
  await page.goto(`/scholars/${slug}`);
  await expect(page.getByText("从主Studio进入编辑后的新简介", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "output/playwright/v306-studio-public-result.png", fullPage: true });
});

test("Studio never substitutes a different object when the requested identity is missing", async ({ page }) => {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("curator-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.goto("/admin/knowledge?object_type=scholar&object_id=30600000-0000-4000-8000-000000009999");
  await expect(page.getByRole("heading", { name: "无法找到指定对象", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "公开页面管理", exact: true })).toHaveCount(0);
});

test("knowledge diagnostics are read-only and return to the same object in the sole Studio", async ({ page }) => {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("administrator-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const writes: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/catalog/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) writes.push(request.url()); });
  const id = "30600000-0000-4000-8000-000000000201";
  await page.goto(`/admin/system-health/knowledge?object_type=scholar&object_id=${id}`);
  await expect(page.getByRole("region", { name: "当前知识对象诊断", exact: true })).toContainText(id);
  await expect(page.getByRole("button", { name: /发布|采用/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "返回当前对象工作台", exact: true })).toHaveAttribute("href", `/admin/knowledge?object_type=scholar&object_id=${id}`);
  expect(writes).toEqual([]);
  await page.getByRole("link", { name: "返回当前对象工作台", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`object_id=${id}`));
  await expect(page.getByRole("region", { name: "公开页面管理", exact: true })).toBeVisible();
});
