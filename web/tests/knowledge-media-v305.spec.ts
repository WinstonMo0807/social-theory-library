import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const api = "http://127.0.0.1:8105/api/catalog";
const cases = [
  { type: "knowledge_node", id: "30500000-0000-4000-8000-000000000101", name: "E2E理论配图", editor: "/admin/theory-nodes?node=30500000-0000-4000-8000-000000000101", endpoint: "nodes", slug: "e2e-node-image", field: "summary" },
  { type: "reading_path", id: "30500000-0000-4000-8000-000000000102", name: "E2E路径配图", editor: "/admin/reading-paths?path=30500000-0000-4000-8000-000000000102", endpoint: "reading-paths", slug: "e2e-path-image", field: "introduction" },
];

test("direct node opening protects input until the real record is ready", async ({ page }) => {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("curator-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/admin/theory-system/nodes/${cases[0].id}/`, async (route) => { await waiting; await route.continue(); });
  await page.goto(cases[0].editor);
  const form = page.locator("form.theory-node-editor");
  try {
    await expect(form).toHaveAttribute("inert", "");
    await expect(page.getByLabel("简介", { exact: true })).toBeDisabled();
    await expect(page.getByText("正在读取指定节点，载入后即可编辑。", { exact: true })).toBeVisible();
  } finally { release(); }
  await expect(form).not.toHaveAttribute("inert", "");
  await expect(page.getByLabel("标准中文名", { exact: true })).toHaveValue(cases[0].name);
});

for (const object of cases) {
  test(`${object.type} image joins metadata draft, publishes and clears without replacing reading structure`, async ({ page }) => {
    const failures: string[] = [];
    page.on("response", (response) => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });
    await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({apiBase:"http://127.0.0.1:8105/api"});' }));
    await page.goto("/login");
    await page.getByLabel("邮箱", { exact: true }).fill("curator-v305@example.test");
    await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(page).toHaveURL(/\/admin$/);
    const editorApi = `${api}/admin/theory-system/${object.endpoint}/${object.id}/`;
    const description = `${object.name}等待图片一起发布的说明`;
    await page.goto(object.editor);
    const descriptionInput = page.getByRole("textbox", { name: object.type === "knowledge_node" ? "简介" : "路径介绍", exact: true });
    await descriptionInput.fill(description);
    await expect(descriptionInput).toHaveValue(description);
    await page.getByRole("button", { name: object.type === "knowledge_node" ? "保存为编辑草稿" : "保存阅读路径", exact: true }).click();
    await expect(page.getByText(object.type === "knowledge_node" ? "修改已保存为编辑草稿。公开页继续读取原正式内容，确认发布后才会更新。" : "阅读路径的编辑草稿已保存，确认发布后更新公开页面。", { exact: true })).toBeVisible();
    const panel = page.getByRole("region", { name: "页面图片", exact: true });
    await expect(panel).toContainText("当前没有选择图片。");
    await panel.getByRole("link", { name: "从媒体库选择页面图片", exact: true }).click();
    const data = await page.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.width = 1200; canvas.height = 800;
      const context = canvas.getContext("2d")!; context.fillStyle = "#3f5360"; context.fillRect(0, 0, 1200, 800);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await page.getByLabel("图片文件", { exact: true }).setInputFiles({ name: `${object.type}.png`, mimeType: "image/png", buffer: Buffer.from(data, "base64") });
    await page.getByLabel("图片说明", { exact: true }).fill("E2E页面配图");
    await page.getByRole("button", { name: "上传图片", exact: true }).click();
    await page.getByRole("button", { name: `用作${object.name}的页面图片`, exact: true }).click();
    await expect(page.getByText("图片已保存到编辑草稿。请返回对象页面确认发布，原图保留。", { exact: true })).toBeVisible();
    const mediaState = await (await page.request.get(`${api}/admin/knowledge-media/${object.type}/${object.id}/`)).json();
    const publicImage = `${api}/knowledge-media/${object.type}/${object.id}/file/`;
    expect((await page.request.get(publicImage)).status()).toBe(404);
    await page.getByRole("link", { name: "返回编辑页面", exact: true }).click();
    await expect(panel.getByRole("img", { name: "E2E页面配图", exact: true })).toBeVisible();
    await expect.poll(() => panel.getByRole("img").evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(640);
    await page.getByRole("button", { name: "确认并发布", exact: true }).click();
    await expect(panel).toContainText("当前显示已保存图片。");
    await expect(descriptionInput).toHaveValue(description);
    expect((await page.request.get(publicImage)).status()).toBe(200);
    const published = await (await page.request.get(`${api}/theory-system/${object.endpoint}/${object.slug}/`)).json();
    expect(published[object.field]).toBe(description);
    expect(published.cover_media.alt_text).toBe("E2E页面配图");
    await page.goto(`/theories/${object.endpoint}/${object.slug}`);
    const image = page.getByRole("img", { name: "E2E页面配图", exact: true });
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
    const banner = page.locator(".theory-system-banner.has-image");
    const bannerBox = await banner.boundingBox();
    const imageBox = await image.boundingBox();
    expect(imageBox!.height).toBeGreaterThanOrEqual(bannerBox!.height - 3);
    await mkdir("output/playwright", { recursive: true });
    await page.screenshot({ path: `output/playwright/${object.type}-media-public.png` });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await image.evaluate((element) => { const box = element.getBoundingClientRect(); return box.left >= 0 && box.right <= window.innerWidth; })).toBe(true);
    await page.screenshot({ path: `output/playwright/${object.type}-media-mobile.png` });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(object.editor);
    await panel.getByRole("button", { name: "清除页面图片", exact: true }).click();
    await page.getByRole("button", { name: "保存清除图片草稿", exact: true }).click();
    await expect(panel).toContainText("当前没有选择图片。");
    expect((await page.request.get(publicImage)).status()).toBe(200);
    await page.getByRole("button", { name: "确认并发布", exact: true }).click();
    await expect(panel).toContainText("当前显示已保存图片。");
    expect((await page.request.get(publicImage)).status()).toBe(404);
    expect((await page.request.get(mediaState.preview_url.replace("/api/catalog", api))).status()).toBe(200);
    if (object.type === "reading_path") {
      const restored = await (await page.request.get(editorApi)).json();
      expect(restored.stages).toHaveLength(1);
      expect(restored.stages[0].id).toBe("30500000-0000-4000-8000-000000000103");
      expect(restored.stages[0].name).toBe("保留原阅读阶段");
    }
    expect(failures).toEqual([]);
  });
}
