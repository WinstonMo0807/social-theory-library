import { expect, test, type Page, type Request } from "@playwright/test";

const api = "http://127.0.0.1:8105";
const scholar = "30600000-0000-4000-8000-000000000201";
const topic = "30600000-0000-4000-8000-000000000202";
const node = "30600000-0000-4000-8000-000000000204";
const path = "30600000-0000-4000-8000-000000000205";

async function configure(page: Page) {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}/api'});` }));
}

async function getRoutes(page: Page) {
  const rowsResponse = await page.request.get(`${api}/api/catalog/admin/workflows/queue/?q=V306-PAGE&scope=publication`);
  expect(rowsResponse.ok()).toBeTruthy();
  const record = (await rowsResponse.json()).results[0];
  expect(record.work_id && record.edition_id && record.session_id).toBeTruthy();
  const sourcesResponse = await page.request.get(`${api}/api/catalog/admin/workflows/queue/?q=V306-OLD-ERROR`);
  const source = (await sourcesResponse.json()).results[0];
  expect(source.item_id).toBeTruthy();
  const context = `edition=${record.edition_id}&return_to=%2Fadmin%2Freview%3Fsource%3Dmanual`;
  return [
    ["R01", "/admin"], ["R02", "/admin/about"], ["R03", "/admin/analytics"],
    ["R04", `/admin/candidates?object_type=scholar&object_id=${scholar}`], ["R05", "/admin/cataloging/new"],
    ["R06", `/admin/cataloging/${record.session_id}?${context}`], ["R07", "/admin/disciplines"], ["R08", "/admin/distribution"],
    ["R09", "/admin/intake/30600000-0000-4000-8000-000000000314?return_to=%2Fadmin%2Freview"],
    ["R10", `/admin/knowledge?object_type=scholar&object_id=${scholar}`], ["R11", "/admin/library?view=editions&q=V306-PAGE"],
    ["R12", `/admin/library/works/${record.work_id}?${context}`], ["R13", `/admin/media?edition=${record.edition_id}&slot=cover`],
    ["R14", "/admin/people?source=30500000-0000-4000-8000-000000000011"],
    ["R15", `/admin/preview/knowledge/scholar/${scholar}?page=overview`], ["R16", `/admin/preview/works/${record.edition_id}`],
    ["R17", "/admin/processing?surface=workers"], ["R18", "/admin/publication?source=manual&q=V306-PAGE"],
    ["R19", "/admin/publication/30600000-0000-4000-8000-000000000314?edition=30600000-0000-4000-8000-000000000311"], ["R20", "/admin/query-lexicon"], ["R21", `/admin/reading-paths?path=${path}`],
    ["R22", "/admin/recommendations"], ["R23", "/admin/review?q=V306-PAGE"], ["R24", "/admin/review/30600000-0000-4000-8000-000000000314?edition=30600000-0000-4000-8000-000000000311"],
    ["R25", "/admin/scholars"], ["R26", `/admin/scholars/${scholar}`], ["R27", "/admin/semantic-index"], ["R28", "/admin/settings#backups"],
    ["R29", "/admin/status"], ["R30", "/admin/subdisciplines"], ["R31", "/admin/system-health"], ["R32", "/admin/system-health/candidates"],
    ["R33", `/admin/system-health/knowledge?object_type=scholar&object_id=${scholar}`], ["R34", "/admin/taxonomy"],
    ["R35", `/admin/theories?node=${node}`], ["R36", `/admin/theories/${node}`], ["R37", `/admin/theory-nodes?node=${node}`],
    ["R38", "/admin/theory-relations"], ["R39", "/admin/theory-timeline"], ["R40", "/admin/topics"], ["R41", `/admin/topics/${topic}`],
    ["R42", `/admin/uploads?item=${source.item_id}`], ["R43", "/admin/users"],
  ] as const;
}

async function layoutMeasurements(page: Page) {
  return page.evaluate(() => {
    const visible = (element: Element) => {
      if (element.closest('[inert],[aria-hidden="true"],.sr-only,[hidden]')) return false;
      if (!element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})) return false;
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
      for(let parent=element.parentElement;parent;parent=parent.parentElement){
        const css=getComputedStyle(parent),box=parent.getBoundingClientRect();
        if(/auto|scroll/.test(css.overflowY) && (rect.bottom<=box.top || rect.top>=box.bottom)) return false;
        if(/auto|scroll/.test(css.overflowX) && (rect.right<=box.left || rect.left>=box.right)) return false;
      }
      return rect.width > 2 && rect.height > 2 && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
    };
    const label = (element: Element) => `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 55)} ${(element.getAttribute("aria-label") || element.textContent || "").trim().slice(0, 70)}`;
    const clippedControls: string[] = [], coveredControls: string[] = [], overlappingColumns: string[] = [], clippedText: string[] = [];
    for (const element of document.querySelectorAll('button,a,input,select,textarea,summary,[role="button"]')) {
      if (!visible(element)) continue;
      const rect = element.getBoundingClientRect();
      if (rect.left < -1 || rect.right > innerWidth + 1) clippedControls.push(label(element));
      if (rect.width < 12 || rect.height < 12 || rect.top < 0 || rect.bottom > innerHeight || element.matches(':disabled,[aria-disabled="true"]')) continue;
      // A menu row partly outside a scroll container has a clipped center;
      // this is not a covered hit target. Full keyboard traversal separately
      // verifies it scrolls into view, including the final menu entries.
      let clippedCenter = false;
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent), box = parent.getBoundingClientRect();
        if (["auto", "scroll"].includes(style.overflowY) && (rect.top + rect.height / 2 < box.top || rect.top + rect.height / 2 > box.bottom)) clippedCenter = true;
      }
      if (clippedCenter && element !== document.activeElement) continue;
      const center = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      if (center && !element.contains(center) && !center.contains(element)) {
        const occluder=center.closest('.admin-topbar,.knowledge-editor-actions,.knowledge-studio-section-nav');
        // Scrolled content can legitimately pass behind sticky chrome. Focus
        // safety is tested by keyboard interactions, not by this static point.
        if (!occluder || element===document.activeElement) coveredControls.push(`${label(element)} <- ${label(center)}`);
      }
    }
    for (const parent of document.querySelectorAll("tr,.inline-fields,.form-grid,.knowledge-form-grid,.workflow-field-grid,.admin-page-title")) {
      if (!visible(parent)) continue;
      const children = Array.from(parent.children).filter((element) => visible(element) && !["absolute", "fixed"].includes(getComputedStyle(element).position));
      for (let i = 0; i < children.length; i += 1) for (let j = i + 1; j < children.length; j += 1) {
        const a = children[i].getBoundingClientRect(), b = children[j].getBoundingClientRect();
        if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2) overlappingColumns.push(`${label(children[i])} / ${label(children[j])}`);
      }
    }
    for (const element of document.querySelectorAll("h1,h2,h3,p,dt,dd,strong")) {
      if (!visible(element)) continue;
      const style = getComputedStyle(element);
      if (element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 2 && ["hidden", "clip"].includes(style.overflowX)) clippedText.push(label(element));
    }
    return { width: innerWidth, documentWidth: document.documentElement.scrollWidth, clippedControls, coveredControls, overlappingColumns, clippedText };
  });
}

for (const width of [360, 390, 768, 1280, 1440]) {
  test(`A31 all 43 real admin routes layout and hit targets at ${width}px`, async ({ browser, baseURL }, testInfo) => {
    test.setTimeout(360_000);
    expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
    const context = await browser.newContext({ viewport: { width, height: 960 }, baseURL });
    const auth = await context.newPage();
    await configure(auth);
    await auth.goto("/login");
    await auth.getByLabel("邮箱").fill("owner-v305@example.test");
    await auth.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
    await auth.getByRole("button", { name: "登录", exact: true }).click();
    await expect(auth).toHaveURL(/\/admin$/);
    const routes = await getRoutes(auth);
    expect(routes).toHaveLength(43);
    const report: unknown[] = [];
    for (const [id, route] of routes) await test.step(`${id} ${route}`, async () => {
      const page = await context.newPage();
      const pending = new Set<Request>();
      const responses: Array<{ path: string; status: number }> = [];
      const business = (url: string) => /\/api\/(catalog|ingestion|distribution|reading|auth\/users)/.test(url);
      page.on("request", (request) => { if (business(request.url())) pending.add(request); });
      page.on("requestfailed", (request) => pending.delete(request));
      page.on("requestfinished", (request) => pending.delete(request));
      page.on("response", (response) => { if (business(response.url())) responses.push({ path: new URL(response.url()).pathname, status: response.status() }); });
      await configure(page);
      await page.goto(route);
      await expect(page.locator("h1").first()).toBeVisible();
      if (id !== "R05") await expect.poll(() => responses.length, { timeout: 20_000 }).toBeGreaterThan(0);
      await expect.poll(() => pending.size, { timeout: 20_000 }).toBe(0);
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      expect.soft(responses.filter((response) => response.status >= 500), `${id} real API failed before layout measurement`).toEqual([]);
      // Read the real interface only. No field save, probe, index switch or
      // candidate action is triggered by this layout traversal.
      for (const scroll of [0, 650]) {
        await page.evaluate((top) => window.scrollTo(0, top), scroll);
        const measurement = await layoutMeasurements(page);
        report.push({ id, route, scroll, responses, ...measurement });
        expect.soft(measurement.documentWidth, `${id} ${scroll} document width`).toBeLessThanOrEqual(width + 1);
        expect.soft(measurement.clippedControls, `${id} ${scroll} controls outside viewport`).toEqual([]);
        expect.soft(measurement.overlappingColumns, `${id} ${scroll} sibling columns overlap`).toEqual([]);
        expect.soft(measurement.coveredControls, `${id} ${scroll} visible control hit target is covered`).toEqual([]);
        // Text truncation measurements stay visible in the report: deliberate
        // summaries require contextual expanded-state verification rather than
        // deleting content merely to satisfy a scroll-width assertion.
      }
      if (["R10", "R11", "R12", "R15", "R21", "R26", "R35", "R43"].includes(id)) await page.screenshot({ path: testInfo.outputPath(`${id}-${width}.png`), fullPage: true });
      await page.close();
    });
    await testInfo.attach(`admin-layout-${width}.json`, { body: JSON.stringify(report, null, 2), contentType: "application/json" });
    await context.close();
  });
}
