import { expect, test, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api";
const work = "30600000-0000-4000-8000-000000000310";
const edition = "30600000-0000-4000-8000-000000000311";
const asset = "30600000-0000-4000-8000-000000000313";
const node = "30600000-0000-4000-8000-000000000204";

async function openEditor(page: Page) {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.goto(`/admin/theories/${node}?section=timeline`);
  await expect(page.getByRole("button", { name: "保存事件", exact: true })).toBeEnabled();
}

async function chooseSource(page: Page) {
  await page.getByRole("combobox", { name: "出处馆藏", exact: true }).fill("V306阅读器布局与私人记录");
  await page.getByRole("option", { name: /V306阅读器布局与私人记录/ }).click();
  await expect(page.getByRole("combobox", { name: "出处出版版本", exact: true })).toBeEnabled();
}

test("A19 A27 A32 timeline source: select exact file, save privately, publish and read the actual PDF page", async ({ page }, info) => {
  test.setTimeout(150_000);
  await openEditor(page);
  const form = page.locator(".timeline-event-editor");
  const title = `V306可阅读出处 ${Date.now()}`;
  await form.getByRole("textbox", { name: "事件标题", exact: true }).fill(title);
  await form.getByRole("textbox", { name: "说明", exact: true }).fill("事件、出处文献与出版版本分别核对，不改变原有页面身份。");
  await form.getByRole("textbox", { name: "来源", exact: true }).fill("合成PDF中的真实第42页，非外部模型结果");
  await chooseSource(page);
  const editions = form.getByRole("combobox", { name: "出处出版版本", exact: true });
  await expect(editions).toHaveValue("");
  await editions.selectOption(edition);
  const files = form.getByRole("combobox", { name: "出处阅读文件", exact: true });
  await expect(files).toBeEnabled();
  await expect(files).toHaveValue("");
  await files.selectOption(asset);
  await form.getByRole("spinbutton", { name: "PDF 页序", exact: true }).fill("42");
  await form.getByRole("textbox", { name: "印刷页码", exact: true }).fill("第41页");
  await expect(form).not.toContainText("出处已更换，PDF 页序和印刷页码已清空");
  await form.getByRole("combobox", { name: "保存后的安排", exact: true }).selectOption("approved");
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 980 });
    await files.scrollIntoViewIfNeeded();
    await files.focus();
    await expect(files).toBeFocused();
    await expect.poll(() => files.evaluate((element) => {
      const r = element.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return r.x >= 0 && r.right <= innerWidth + 1 && Boolean(hit && (hit === element || element.contains(hit)));
    })).toBe(true);
    const overflows = await form.locator(".timeline-evidence-fields").evaluate((root) => [root, ...root.querySelectorAll("input, select, button, p, h3")].flatMap((element) => {
      const r = element.getBoundingClientRect();
      return r.width && r.height && (r.left < -1 || r.right > innerWidth + 1) ? [element.textContent || element.getAttribute("name")] : [];
    }));
    expect(overflows).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.screenshot({ path: info.outputPath(`timeline-source-${width}.png`) });
  }
  const savedResponse = page.waitForResponse((r) => r.url().endsWith("/catalog/admin/theory-timeline/") && r.request().method() === "POST");
  await form.getByRole("button", { name: "保存事件", exact: true }).click();
  const saved = await savedResponse;
  expect(saved.status(), await saved.text()).toBe(201);
  const record = await saved.json();
  expect(record.evidence_file).toMatchObject({ work_id: work, edition_id: edition, id: asset, reader_href: `/reader/${asset}?page=42` });
  expect(record.work).toBeNull();
  const publicApi = `${api}/catalog/theory-system/timeline/?q=${encodeURIComponent(title)}`;
  expect((await (await page.request.get(publicApi)).json()).count).toBe(0);
  await expect(form.getByRole("link", { name: "打开已保存的出处页" })).toHaveAttribute("href", `/reader/${asset}?page=42`);
  page.once("dialog", (dialog) => dialog.accept());
  const published = page.waitForResponse((r) => r.url().includes(record.editorial_revision.publish_url) && r.request().method() === "POST");
  await form.getByRole("button", { name: "确认发布已保存的修改", exact: true }).click();
  expect((await published).status()).toBe(200);
  await expect(form).toContainText("事件修改已发布");
  await page.goto(`/admin/theories/${node}?section=timeline&event=${record.id}`);
  await expect(form.getByRole("combobox", { name: "出处出版版本", exact: true })).toHaveValue(edition);
  await expect(form.getByRole("combobox", { name: "出处阅读文件", exact: true })).toHaveValue(asset);
  await expect(form.getByRole("spinbutton", { name: "PDF 页序", exact: true })).toHaveValue("42");
  await page.goto(`/theories/timeline?node=v306-layout-node&q=${encodeURIComponent(title)}`);
  const event = page.locator(".theory-timeline-list article").filter({ hasText: title });
  await expect(event).toContainText("合成PDF中的真实第42页");
  await event.getByRole("link", { name: "查看馆藏证据" }).click();
  await expect(page).toHaveURL(new RegExp(`/reader/${asset}\\?page=42`));
  await expect(page.locator(".pdf-canvas-stage canvas").first()).toBeVisible({ timeout: 40_000 });
  await expect(page.getByRole("textbox", { name: "页码", exact: true })).toHaveValue("42");
  await page.screenshot({ path: info.outputPath("timeline-source-reader-page42.png") });
});

test("A03 A11 A16 source search recovers, pages through editions and clears stale page references without writes", async ({ page }) => {
  await openEditor(page);
  const form = page.locator(".timeline-event-editor");
  const writes: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST") writes.push(request.url()); });
  const searchRoute = "**/catalog/admin/library/works/?q=*";
  await page.route(searchRoute, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "测试：馆内搜索暂不可用" }) }));
  await page.getByRole("combobox", { name: "出处馆藏", exact: true }).fill("V306阅读器布局与私人记录");
  await expect(page.getByRole("alert").filter({ hasText: "馆内搜索暂不可用" })).toBeVisible();
  await page.unroute(searchRoute);
  await page.getByRole("button", { name: "重试馆内搜索", exact: true }).click();
  await page.getByRole("option", { name: /V306阅读器布局与私人记录/ }).click();
  await expect(form.getByRole("navigation", { name: "出处版本分页" })).toContainText("共 41 个版本");
  await form.getByRole("combobox", { name: "出处出版版本", exact: true }).selectOption(edition);
  await form.getByRole("combobox", { name: "出处阅读文件", exact: true }).selectOption(asset);
  await form.getByRole("spinbutton", { name: "PDF 页序", exact: true }).fill("9");
  await form.getByRole("textbox", { name: "印刷页码", exact: true }).fill("viii");
  await form.getByRole("button", { name: "下一页版本", exact: true }).click();
  await expect(form.getByRole("navigation", { name: "出处版本分页" })).toContainText("第 2 页");
  await expect(form.getByRole("combobox", { name: "出处出版版本", exact: true })).toHaveValue(edition);
  await expect(form.getByRole("spinbutton", { name: "PDF 页序", exact: true })).toHaveValue("9");
  await form.getByRole("combobox", { name: "出处出版版本", exact: true }).selectOption("30600000-0000-4000-8000-000000000439");
  await expect(form).toContainText("这个出版版本没有阅读文件");
  await expect(form.getByRole("spinbutton", { name: "PDF 页序", exact: true })).toHaveValue("");
  await expect(form.getByRole("textbox", { name: "印刷页码", exact: true })).toHaveValue("");
  await expect(form).toContainText("出处已更换，PDF 页序和印刷页码已清空");
  expect(writes).toEqual([]);
});
