import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Only selects the development API origin; no business request is mocked.
  await page.route("**/runtime-config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:'http://127.0.0.1:8105/api'});",
  }));
});

async function login(page: Page, role: "curator" | "reader" | "administrator") {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
}

test("editor dashboard never requests admin-only statistics", async ({ page }) => {
  const statisticsRequests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/usage-analytics/")) statisticsRequests.push(request.url()); });
  const queueLoaded = page.waitForResponse((response) => response.url().includes("/admin/workflows/queue/") && response.ok());
  await login(page, "curator");
  await queueLoaded;
  await expect(page.getByRole("heading", { name: "今日工作", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "继续处理", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "匿名使用统计", exact: true })).toHaveCount(0);
  await expect(page.locator('a[href="/admin/analytics"]')).toHaveCount(0);
  await page.goto("/admin/analytics");
  await expect(page.getByRole("heading", { name: "当前账户没有统计查看权限", exact: true })).toBeVisible();
  expect(statisticsRequests).toEqual([]);
  const direct = await page.request.get("http://127.0.0.1:8105/api/catalog/admin/usage-analytics/?days=30");
  expect(direct.status()).toBe(403);
});

test("ordinary administrator dashboard reads real usage statistics", async ({ page }) => {
  const statisticsLoaded = page.waitForResponse((response) => response.url().includes("/usage-analytics/") && response.ok());
  await login(page, "administrator");
  const response = await statisticsLoaded;
  expect((await response.json()).anonymous_sessions).toBe(0);
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "匿名使用统计", exact: true }) });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("0", { exact: true })).toHaveCount(2);
});

test("queue transport failure is visible and retries the real API", async ({ page }) => {
  // Explicit failure injection, never a fabricated successful business payload.
  const queueUrl = "**/api/catalog/admin/workflows/queue/";
  await page.route(queueUrl, (route) => route.abort("failed"));
  await login(page, "curator");
  await expect(page.getByRole("alert").filter({ hasText: "工作队列读取失败" })).toBeVisible();
  await expect(page.getByText("当前没有中断的馆藏工作。", { exact: true })).toHaveCount(0);
  await page.unroute(queueUrl);
  const queueLoaded = page.waitForResponse((response) => response.url().includes("/admin/workflows/queue/") && response.ok());
  await page.getByRole("button", { name: "重试工作队列", exact: true }).click();
  await queueLoaded;
  await expect(page.getByRole("heading", { name: "继续处理", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试工作队列", exact: true })).toHaveCount(0);
});

test("non-superuser creates a real manual session, saves and reopens it", async ({ page }) => {
  const serverErrors: string[] = [];
  page.on("response", (response) => { if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`); });
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
  expect(serverErrors).toEqual([]);
});

test("a reader cannot open cataloging or submit a manual catalog", async ({ page }) => {
  await login(page, "reader");
  await page.goto("/admin/cataloging/new");
  await expect(page.getByText("当前账户没有管理权限", { exact: true })).toBeVisible();
  const response = await page.request.get("http://127.0.0.1:8105/api/catalog/admin/cataloging-sessions/");
  expect(response.status()).toBe(403);
});

test("media upload keeps a private original and creates a responsive preview", async ({ page }) => {
  await login(page, "curator");
  await page.goto("/admin/media");
  const image = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 800;
    canvas.height = 1200;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#334455";
    context.fillRect(0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("图片文件", { exact: true }).setInputFiles({ name: "e2e-media.png", mimeType: "image/png", buffer: Buffer.from(image, "base64") });
  await page.getByLabel("图片说明", { exact: true }).fill("E2E 媒体原图");
  await page.getByRole("button", { name: "上传图片", exact: true }).click();
  await expect(page.getByRole("heading", { name: "媒体资料与预览", exact: true })).toBeVisible();
  await page.getByLabel("许可", { exact: true }).fill("仅用于本地测试");
  await page.getByLabel("水平焦点", { exact: true }).press("Home");
  await page.getByLabel("水平焦点", { exact: true }).press("ArrowRight");
  await page.getByRole("combobox", { name: "预览用途", exact: true }).selectOption("hero");
  await page.getByRole("button", { name: "保存资料并生成预览", exact: true }).click();
  await expect(page.getByText("媒体资料已保存。此操作不会直接更改公开书目。", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "E2E 媒体原图", exact: true }).last()).toHaveJSProperty("naturalWidth", 640);
  const result = await page.request.get("http://127.0.0.1:8105/api/catalog/admin/media/");
  const rows = await result.json();
  expect(rows[0].width).toBe(800);
  expect(rows[0].height).toBe(1200);
  expect(rows[0].license).toBe("仅用于本地测试");
  expect(rows[0].renditions.length).toBeGreaterThanOrEqual(2);
  expect(rows[0].file).toBeUndefined();
  await page.goto("/admin/cataloging/new");
  await page.getByLabel("作品题名", { exact: true }).fill("E2E 媒体关联书目");
  await page.getByRole("button", { name: "创建草稿并开始编目" }).click();
  await expect(page).toHaveURL(/\/admin\/cataloging\/[a-f0-9-]+#work/);
  const sessionId = new URL(page.url()).pathname.split("/").at(-1);
  const sessionResponse = await page.request.get(`http://127.0.0.1:8105/api/catalog/admin/cataloging-sessions/${sessionId}/?workspace=0`);
  const { session } = await sessionResponse.json();
  await page.goto(`/admin/media?edition=${session.edition_id}`);
  await page.getByRole("button", { name: /E2E 媒体原图/ }).click();
  await page.getByRole("button", { name: "用作当前作品封面", exact: true }).click();
  await expect(page.getByText("封面已保存到书目草稿。请返回工作台核对后发布。", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "返回编目工作台", exact: true })).toBeVisible();
  await page.goto(`/admin/media?edition=${session.edition_id}&slot=recommendation`);
  await page.getByRole("button", { name: /E2E 媒体原图/ }).click();
  await page.getByRole("button", { name: "用作当前作品推荐图例", exact: true }).click();
  await expect(page.getByText("推荐图例已保存到书目草稿。请返回工作台核对后发布。", { exact: true })).toBeVisible();
  const imagePreview = await page.request.get(`http://127.0.0.1:8105/api/catalog/admin/page-preview/editions/${session.edition_id}/`);
  const imageWork = (await imagePreview.json()).work;
  expect(imageWork.recommendation_media.primary_rendition_id).not.toBe(imageWork.cover_media.primary_rendition_id);
  await page.getByRole("link", { name: "返回编目工作台", exact: true }).click();
  const imageEditor = page.getByRole("region", { name: "推荐图例编辑", exact: true });
  await expect(imageEditor).toBeVisible();
  await expect(imageEditor.getByRole("img", { name: "当前草稿推荐图例", exact: true })).toHaveJSProperty("naturalWidth", 640);
  await imageEditor.getByRole("button", { name: "移除图例选择", exact: true }).click();
  await expect(page.getByText("图例选择已保存，原文件仍保留。", { exact: true })).toBeVisible();
  const afterClear = await page.request.get(`http://127.0.0.1:8105/api/catalog/admin/page-preview/editions/${session.edition_id}/`);
  const clearedWork = (await afterClear.json()).work;
  expect(clearedWork.cover_media.primary_rendition_id).toBe(imageWork.cover_media.primary_rendition_id);
  expect(clearedWork.recommendation_media.primary_rendition_id).toBe(clearedWork.cover_media.primary_rendition_id);
});
