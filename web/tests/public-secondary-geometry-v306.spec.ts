import { expect, test } from "@playwright/test";

// Complements F10: it measures real public components, including text that a
// clipped hero can conceal without changing document.scrollWidth.
const viewports = [360, 390, 768, 860, 1280, 1440];
const pages = [
  { route: "/theories/nodes/v306-layout-node", selector: ".theory-node-hero", texts: ".theory-node-intro h1, .theory-node-intro h2, .theory-core-question p, .theory-node-hero-side dt, .theory-node-hero-side dd, .theory-node-relations strong, .theory-node-relations p, .theory-node-reading-order li strong" },
  { route: "/theories/reading-paths/v306-layout-path", selector: ".reading-path-hero", texts: ".reading-path-hero h1, .reading-path-hero dd, .stage-copy .eyebrow, .stage-copy h2, .stage-target strong" },
] as const;

for (const width of viewports) for (const entry of pages) {
  test(`secondary full text and nested grid ${entry.route} at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    expect((await page.goto(entry.route))?.status()).toBe(200);
    await expect(page.locator(entry.selector)).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const textGeometry = await page.locator(entry.texts).evaluateAll((elements) => elements.map((element) => {
      const box = element.getBoundingClientRect();
      const range = document.createRange(); range.selectNodeContents(element);
      const text = range.getBoundingClientRect();
      const parent = element.parentElement!.getBoundingClientRect();
      return { tag: element.tagName, label: element.textContent?.slice(0, 120), x: box.x, right: box.right,
        width: box.width, height: box.height, textX: text.x, textRight: text.right,
        parentX: parent.x, parentRight: parent.right, overflow: getComputedStyle(element).overflow };
    }));
    await testInfo.attach("nested-text-geometry", { body: JSON.stringify(textGeometry, null, 2), contentType: "application/json" });
    await page.screenshot({ path: testInfo.outputPath(`secondary-${width}.png`), fullPage: true });
    expect(textGeometry.length).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    for (const item of textGeometry) {
      expect(item.width, `${item.tag} ${item.label}`).toBeGreaterThan(0);
      expect(item.textRight, `text clipped or overflows ${item.tag} ${item.label}`).toBeLessThanOrEqual(item.right + 2);
      expect(item.right, `child exceeds parent ${item.tag} ${item.label}`).toBeLessThanOrEqual(item.parentRight + 2);
      expect(item.textX, `text starts outside ${item.tag} ${item.label}`).toBeGreaterThanOrEqual(item.x - 2);
    }
    if (entry.route.includes("reading-paths")) {
      // The isolated fixture must contain a real published item, not just an
      // empty ReadingPathStage. Missing test content cannot silently pass.
      const stages = page.locator(".reading-path-stages > article");
      await expect(stages.first()).toBeVisible();
      const rows = await stages.evaluateAll((articles) => articles.map((article) => {
        const boundary = article.getBoundingClientRect();
        return { right: boundary.right, x: boundary.x, children: [...article.children].map((child) => {
          const rect = child.getBoundingClientRect(); return { x: rect.x, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width };
        }) };
      }));
      await testInfo.attach("reading-stage-columns", { body: JSON.stringify(rows, null, 2), contentType: "application/json" });
      for (const row of rows) for (const child of row.children) {
        expect(child.right).toBeLessThanOrEqual(row.right + 2);
        expect(child.x).toBeGreaterThanOrEqual(row.x - 2);
        expect(child.width).toBeGreaterThan(0);
      }
      const stageLink = stages.first().locator(".stage-target a").first();
      await stageLink.scrollIntoViewIfNeeded(); await stageLink.focus();
      expect(await stageLink.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hit = document.elementFromPoint(Math.min(window.innerWidth - 1, rect.x + rect.width / 2), Math.min(window.innerHeight - 1, rect.y + rect.height / 2));
        return hit === element || element.contains(hit);
      }), "stage navigation must not be covered by sticky regions").toBe(true);
    }
  });
}

for (const width of [360, 390, 768, 1280, 1440]) for (const route of ["/scholars/v306-layout-scholar", "/topics/v306-layout-topic"]) {
  test(`scholar/topic full headings and footer stay usable ${route} at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    expect((await page.goto(route))?.status()).toBe(200);
    await expect(page.locator("main h1").first()).toBeVisible();
    const result = await page.locator("main h1, .scholar-hero .biography, .scholar-timeline > p > span, .concept-row p, .bourdieu-map > span, .topic-problem-hero .tag-list a, .site-footer > strong, .site-footer > nav, .site-footer > p").evaluateAll((items) => items.map((element) => {
      const rect = element.getBoundingClientRect(); const range = document.createRange(); range.selectNodeContents(element); const text = range.getBoundingClientRect();
      return { label: element.textContent?.slice(0, 100), right: rect.right, textRight: text.right, width: rect.width };
    }));
    await testInfo.attach("heading-footer-geometry", { body: JSON.stringify(result, null, 2), contentType: "application/json" });
    for (const item of result) {
      expect(item.width).toBeGreaterThan(0); expect(item.right, item.label).toBeLessThanOrEqual(width + 1);
      expect(item.textRight, item.label).toBeLessThanOrEqual(item.right + 2);
    }
    if (route.includes("scholars")) {
      const map = page.locator(".bourdieu-map");
      const boxes = await map.locator(":scope > span").evaluateAll((items) => items.map((item) => {
        const rect = item.getBoundingClientRect();
        const parent = item.parentElement!.getBoundingClientRect();
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, parentRight: parent.right };
      }));
      expect(boxes.length).toBeGreaterThan(1);
      for (let i = 0; i < boxes.length; i += 1) {
        expect(boxes[i].right).toBeLessThanOrEqual(boxes[i].parentRight + 1);
        for (let j = i + 1; j < boxes.length; j += 1) {
          const a = boxes[i], b = boxes[j];
          expect(Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1, "concept boxes must not overlap").toBe(false);
        }
      }
      await map.screenshot({ path: testInfo.outputPath(`concept-map-${width}.png`) });
    }
    const links = page.locator('.site-footer nav a');
    await expect(links).toHaveCount(3);
    await links.first().scrollIntoViewIfNeeded(); await links.first().focus();
    await page.keyboard.press("Tab"); await expect(links.nth(1)).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
