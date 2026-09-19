import { expect, test, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api";
const pathId = "30600000-0000-4000-8000-000000000205";

test.beforeEach(async ({ page, baseURL }) => {
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  // HTTP NAS browsers expose getRandomValues, but not secure-context randomUUID.
  await page.addInitScript(() => Object.defineProperty(crypto, "randomUUID", { value: undefined, configurable: true }));
  await page.context().route("**/runtime-config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
});

async function expectUncoveredFocus(page: Page) {
  expect(await page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const center = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(center && (element.contains(center) || center.contains(element)));
  })).toBe(true);
}

test("cover workbench shows saved PDF candidates, manual page, upload and default at two widths", async ({ page }, info) => {
  test.setTimeout(150_000);
  const failures: string[] = [];
  page.on("response", response => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });
  const bound = await (await page.request.get(`${api}/catalog/admin/intake/30600000-0000-4000-8000-000000000314/`)).json();
  const url = `${api}/catalog/admin/editions/${bound.context.edition_id}/cover/`;
  await page.goto(`/admin/library/works/${bound.context.work_id}?edition=${bound.context.edition_id}#work`);
  const cover = page.getByRole("region", { name: "当前版本封面", exact: true });
  await cover.getByRole("button", { name: "准备封面候选", exact: true }).click();
  await expect(cover.locator("article").first()).toBeVisible();
  // Reload proves ordinary reads show existing candidates without a new lookup.
  await page.reload();
  await expect(cover.locator("article").first()).toBeVisible();
  const initial = await (await page.request.get(url)).json();
  expect(initial.results.length).toBeGreaterThan(0);
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    await cover.scrollIntoViewIfNeeded();
    await expect.poll(() => cover.locator("article img").first().evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    expect(await cover.evaluate(element => Array.from(element.querySelectorAll("button,input,img")).every(child => {
      const box = child.getBoundingClientRect();
      return box.left >= 0 && box.right <= innerWidth + 1 && box.width >= 40;
    }))).toBe(true);
    await page.screenshot({ path: `../output/playwright/v306-cover-${width}.png` });
    await info.attach(`cover-${width}`, { path: `../output/playwright/v306-cover-${width}.png`, contentType: "image/png" });
  }
  const pageNumber = Math.min(2, initial.page_count);
  await cover.getByRole("spinbutton", { name: "封面PDF页码" }).fill(String(pageNumber));
  await cover.getByRole("button", { name: "预览这一页", exact: true }).click();
  const choose = cover.getByRole("button", { name: "用这一页作封面", exact: true });
  await expect(choose).toBeVisible();
  await choose.click();
  await expect(cover.getByRole("img", { name: "当前保存的封面", exact: true })).toBeVisible();
  const selected = await (await page.request.get(url)).json();
  expect(selected.results.find((row: { selected: boolean }) => row.selected).page_index).toBe(pageNumber);
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 600; canvas.height = 800;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#486155"; ctx.fillRect(0, 0, 600, 800);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await cover.getByLabel("上传封面图片", { exact: true }).setInputFiles({ name: "cover-test.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await cover.getByRole("button", { name: "上传并保存封面", exact: true }).click();
  await expect(cover.getByText("封面图片已保存；已有公开版本会等到正式发布后更新。", { exact: true })).toBeVisible();
  expect((await (await page.request.get(url)).json()).results.every((row: { selected: boolean }) => !row.selected)).toBe(true);
  await cover.getByRole("button", { name: "使用默认样式，不选封面", exact: true }).click();
  await expect(cover.getByText("已选择默认样式，不要求提供封面。原图及历史仍保留。", { exact: true })).toBeVisible();
  expect((await (await page.request.get(url)).json()).is_default).toBe(true);
  await page.reload();
  await expect(cover.getByText("当前使用默认样式。", { exact: true })).toBeVisible();
  await expect(page.locator(".workflow-recommendation-image")).not.toHaveAttribute("open", "");
  expect(failures).toEqual([]);
});

test("A04 actual FileBody shows each PDF validation state and full content at five widths", async ({ page }, info) => {
  test.setTimeout(180_000);
  const bound = await (await page.request.get(`${api}/catalog/admin/intake/30600000-0000-4000-8000-000000000314/`)).json();
  const records = [{ state: 'valid', work: bound.context.work_id, edition: bound.context.edition_id, label: '已通过', tone: 'success' }];
  for (const state of ['pending', 'invalid']) {
    const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=V306-PDF-${state}&view=editions`)).json();
    expect(list.count).toBe(1);
    records.push({ state, work: list.results[0].work_id, edition: list.results[0].edition_id, label: state === 'pending' ? '等待校验' : '未通过', tone: state === 'pending' ? 'pending' : 'error' });
  }
  for (const record of records) {
    const prepared = await (await page.request.get(`${api}/catalog/admin/editions/${record.edition}/publication/prepare/`)).json();
    if (record.state !== 'valid') expect(prepared.blocking.join(' ')).toMatch(record.state === 'pending' ? /等待验证/ : /验证失败/);
    await page.goto(`/admin/library/works/${record.work}?edition=${record.edition}#file`);
    const files = page.locator('#workflow-section-file');
    const validation = files.locator('[data-pdf-validation]');
    await expect(validation).toHaveText(record.label);
    await expect(validation).toHaveAttribute('data-pdf-validation', record.state);
    await expect(validation).toHaveAttribute('data-tone', record.tone);
    await expect(files.getByRole('button', { name: '确认本节内容', exact: true })).toHaveCount(0);
    for (const width of [360, 390, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await validation.scrollIntoViewIfNeeded();
      await expect(validation).toBeVisible();
      expect(await files.locator('.workflow-file-summary dl').evaluate(element => {
        const box = element.getBoundingClientRect();
        return box.left >= 0 && box.right <= innerWidth && Array.from(element.querySelectorAll('dd')).every(cell => cell.scrollWidth <= cell.clientWidth + 1);
      })).toBe(true);
      await page.screenshot({ path: info.outputPath(`file-${record.state}-${width}.png`) });
    }
  }
});

test("current work title and grouped steps stay readable in the dark editing directory at all five widths", async ({ page }, info) => {
  await page.goto("/admin/cataloging/new");
  const title = "当前报告的完整长题名 LongUnbrokenResearchDocumentTitleForContrastAndWrapping";
  await page.getByLabel("作品题名", { exact: true }).fill(title);
  await page.getByRole("button", { name: "创建草稿并开始编目", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/cataloging\/[a-f0-9-]+#work/);
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    if (width <= 820) await page.getByRole("button", { name: "打开编辑目录", exact: true }).click();
    const rail = page.locator(".workflow-step-rail");
    await expect(rail.getByRole("heading", { name: title, exact: true })).toBeVisible();
    const checks = await rail.evaluate(element => {
      const luminance = (value: string) => {
        const rgb = value.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(channel => {
          const srgb = channel / 255;
          return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
        });
        return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
      };
      const background = luminance(getComputedStyle(element).backgroundColor);
      const box = element.getBoundingClientRect();
      return Array.from(element.querySelectorAll("header h2, h3")).map(heading => {
        const foreground = luminance(getComputedStyle(heading).color);
        const rect = heading.getBoundingClientRect();
        return { text: heading.textContent, contrast: (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05), contained: rect.left >= box.left && rect.right <= box.right };
      });
    });
    for (const check of checks) {
      expect(check.contrast, `${width}px ${check.text}`).toBeGreaterThanOrEqual(4.5);
      expect(check.contained, check.text || "").toBe(true);
    }
    await info.attach(`directory-contrast-${width}`, { body: JSON.stringify(checks), contentType: "application/json" });
    await rail.screenshot({ path: info.outputPath(`readable-directory-${width}.png`) });
    if (width <= 820) await page.getByRole("button", { name: "关闭编辑目录", exact: true }).click();
  }
});

for (const width of [360, 390, 768, 1280, 1440]) {
  test(`all expanded admin menu groups remain scrollable and keyboard reachable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 720 });
    await page.goto("/admin/knowledge");
    const open = page.getByRole("button", { name: "打开后台菜单", exact: true });
    if (width < 960) {
      await expect(open).toBeVisible();
      await open.click();
      await expect(page.locator("#admin-navigation")).toHaveAttribute("aria-modal", "true");
    }
    const sidebar = page.locator("#admin-navigation");
    const groups = sidebar.locator("details.admin-nav-group");
    await expect(groups).toHaveCount(6);
    for (const group of await groups.all()) {
      if (await group.getAttribute("open") === null) await group.locator("summary").click();
    }
    const controls = sidebar.locator("nav a, nav summary");
    for (const control of await controls.all()) {
      await control.focus();
      await expect(control).toBeFocused();
      await expectUncoveredFocus(page);
    }
    const geometry = await sidebar.evaluate((element) => {
      const nav = element.querySelector("nav")!.getBoundingClientRect();
      const footer = element.querySelector("footer")!.getBoundingClientRect();
      return { navBottom: nav.bottom, footerTop: footer.top, bottom: footer.bottom, viewport: innerHeight };
    });
    expect(geometry.navBottom).toBeLessThanOrEqual(geometry.footerTop + 1);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewport);
    await page.screenshot({ path: testInfo.outputPath(`expanded-menu-${width}.png`) });
  });
}

test("settings tabs preserve unsaved input, expose one panel, retain deep links and support keyboard", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const config = await (await page.request.get(`${api}/catalog/site-config/`)).json();
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) writes.push(request.url());
  });
  await page.goto("/admin/settings#backups");
  const tabs = page.getByRole("tablist", { name: "设置栏目" });
  await expect(tabs.getByRole("tab", { name: "备份", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toHaveCount(1);
  await tabs.getByRole("tab", { name: "网站内容", exact: true }).click();
  const name = page.getByRole("textbox", { name: "网站名称", exact: true });
  await expect(name).toHaveValue(config.site_name);
  await name.fill("尚未保存的书库名称");
  await tabs.getByRole("tab", { name: "荐书邮箱", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toHaveCount(1);
  await tabs.getByRole("tab", { name: "网站内容", exact: true }).click();
  await expect(name).toHaveValue("尚未保存的书库名称");
  await tabs.getByRole("tab", { name: "网站内容", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(tabs.getByRole("tab", { name: "AI 提示词", exact: true })).toBeFocused();
  await expectUncoveredFocus(page);
  await expect(page).toHaveURL(/#prompts$/);
  await page.keyboard.press("Home");
  await expect(tabs.getByRole("tab", { name: "网站内容", exact: true })).toBeFocused();
  await expect(name).toHaveValue("尚未保存的书库名称");
  await page.screenshot({ path: testInfo.outputPath("settings-390.png"), fullPage: true });
  expect(writes, "switching settings must not save or test paid services").toEqual([]);
});

test("mobile book editor uses an actual modal directory with focus restoration and no hidden tab stops", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/admin/intake/30600000-0000-4000-8000-000000000314?return_to=%2Fadmin%2Freview");
  const opener = page.getByRole("button", { name: "打开编辑目录", exact: true });
  await expect(opener).toBeVisible();
  const directory = page.getByRole("dialog", { name: "编辑目录", exact: true });
  await expect(directory).toHaveCount(0);
  await opener.click();
  await expect(directory).toBeVisible();
  const controls = directory.locator("button:visible:not(:disabled),a[href]:visible");
  await controls.last().focus();
  await page.keyboard.press("Tab");
  await expect(controls.first()).toBeFocused();
  await expectUncoveredFocus(page);
  await page.keyboard.press("Shift+Tab");
  await expect(controls.last()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(controls.first()).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath("book-directory-390.png") });
  await page.keyboard.press("Escape");
  await expect(directory).toHaveCount(0);
  await expect(opener).toBeFocused();
  for (let i = 0; i < 8; i += 1) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.closest("dialog:not([open])") === null)).toBe(true);
    await expectUncoveredFocus(page);
  }
  await opener.click();
  await directory.locator("nav button").last().click();
  await expect(directory).toHaveCount(0);
  expect(new URL(page.url()).pathname).toContain("30600000-0000-4000-8000-000000000314");
});

test("recommendation confirmation can be cancelled and slow repeated clicks publish exactly once", async ({ page }) => {
  await page.goto("/admin/recommendations");
  const policies = await (await page.request.get(`${api}/catalog/admin/recommendations/`)).json();
  const scholars = policies.find((row: { placement: string }) => row.placement === "home_scholars");
  await page.locator(".recommendation-policy-list > button").filter({ hasText: scholars.title }).click();
  const random = page.getByRole("button", { name: "预览新一组推荐", exact: true });
  const posts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/recommendations/") && request.url().includes("/refresh/")) posts.push(request.url());
  });
  const publicBefore = await (await page.request.get(`${api}/catalog/recommendations/`)).json();
  await random.click();
  const preview = page.getByRole("region", { name: "待发布推荐预览" });
  await expect(preview).toBeVisible();
  const publicAfterPreview = await (await page.request.get(`${api}/catalog/recommendations/`)).json();
  expect(publicAfterPreview.placements.home_scholars.current?.id).toBe(publicBefore.placements.home_scholars.current?.id);
  const publish = page.getByRole("button", { name: "确认发布这一组", exact: true });
  page.once("dialog", (dialog) => dialog.dismiss());
  await publish.click();
  expect(posts).toEqual([]);
  const first = page.locator(".recommendation-candidates input").first();
  await expect(first).toBeVisible();
  if (!await first.isChecked()) await first.check();
  await page.getByRole("button", { name: "预览选中的推荐", exact: true }).click();
  await expect(publish).toBeEnabled();
  const previewNames = await preview.locator("li").allTextContents();
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/admin/recommendations/home_scholars/refresh/", async (route) => {
    await waiting;
    await route.continue();
  });
  page.once("dialog", (dialog) => dialog.accept());
  const response = page.waitForResponse((row) => row.url().includes("/home_scholars/refresh/") && row.request().method() === "POST");
  try {
    await publish.evaluate((element: HTMLButtonElement) => { element.click(); element.click(); });
    await expect(publish).toBeDisabled();
    await expect(random).toBeDisabled();
    await expect.poll(() => posts.length).toBe(1);
  } finally { release(); }
  const result = await response;
  expect(result.status(), await result.text()).toBe(200);
  const saved = await result.json();
  await expect(preview).toHaveCount(0);
  const publicResult = await (await page.request.get(`${api}/catalog/recommendations/`)).json();
  expect(publicResult.placements.home_scholars.current.id).toBe(saved.current.id);
  expect(publicResult.placements.home_scholars.current.items.map((row: { target: { id: string } }) => row.target.id)).toEqual(saved.current.items.map((row: { target: { id: string } }) => row.target.id));
  expect(saved.current.items.map((row: { target: { name?: string; preferred_name?: string; title?: string } }) => row.target.preferred_name || row.target.name || row.target.title)).toEqual(previewNames);
  expect(posts).toHaveLength(1);
});

test("recommendation switching never offers the previous category while the new list is loading", async ({ page }) => {
  await page.goto("/admin/recommendations");
  await expect(page.locator(".recommendation-candidates input").first()).toBeVisible();
  const oldLabel = await page.locator(".recommendation-candidates label").first().innerText();
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  let requested = false;
  await page.route("**/catalog/admin/scholars/?*", async (route) => {
    requested = true;
    await waiting;
    await route.continue();
  });
  try {
    await page.locator(".recommendation-policy-list > button").filter({ hasText: "首页学者" }).click();
    await expect.poll(() => requested).toBe(true);
    await expect(page.locator(".recommendation-candidates input")).toHaveCount(0);
    await expect(page.getByText("正在读取可推荐内容…", { exact: true })).toBeVisible();
  } finally { release(); }
  await expect(page.locator(".recommendation-candidates input").first()).toBeVisible();
  await expect(page.locator(".recommendation-candidates")).not.toContainText(oldLabel);
  const allowed = await (await page.request.get(`${api}/catalog/admin/scholars/?editorial_status=published`)).json();
  const names = allowed.results.map((row: { preferred_name: string }) => row.preferred_name);
  for (const label of await page.locator(".recommendation-candidates label span").allTextContents()) expect(names).toContain(label);
});

test("reading path save keeps public content unchanged and previews the actual saved draft", async ({ page }) => {
  const before = await (await page.request.get(`${api}/catalog/admin/theory-system/reading-paths/${pathId}/`)).json();
  const publicUrl = `${api}/catalog/theory-system/reading-paths/${before.slug}/`;
  const oldPublic = await (await page.request.get(publicUrl)).json();
  await page.goto(`/admin/reading-paths?path=${pathId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue(before.title);
  const draftText = `仅供预览的阅读介绍 ${Date.now()}`;
  await page.getByRole("textbox", { name: "路径介绍", exact: true }).fill(draftText);
  await page.getByRole("button", { name: "保存本页阅读安排", exact: true }).click();
  await expect(page.getByText("阅读路径的编辑草稿已保存，确认发布后更新公开页面。", { exact: true })).toBeVisible();
  expect((await (await page.request.get(publicUrl)).json()).introduction).toBe(oldPublic.introduction);
  const link = page.getByRole("link", { name: "预览已保存内容" });
  await expect(link).toHaveAttribute("href", `/admin/preview/knowledge/reading_path/${pathId}`);
  const [preview] = await Promise.all([page.waitForEvent("popup"), link.click()]);
  await expect(preview.getByText(draftText, { exact: true }).first()).toBeVisible();
  await preview.close();
});
