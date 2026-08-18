import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const outputRoot = path.resolve("output/playwright/compact-editorial-density");
const fullMatrix = process.env.DENSITY_FULL_MATRIX === "true";

const desktopViewports = [
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1600, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
  { width: 3840, height: 2160 },
] as const;

const requestedVisualViewports = desktopViewports.filter(({ width }) =>
  [1440, 1920, 2560, 3840].includes(width),
);

const corePages = [
  {
    name: "home",
    route: "/",
    search: ".home-hero-search",
    firstFold: ".home-stat-ledger",
    firstFoldMode: "starts" as const,
  },
  {
    name: "theories",
    route: "/theories",
    search: ".theory-system-search",
    firstFold: ".theory-discipline-grid",
    firstFoldMode: "complete" as const,
    requiredItems: 3,
  },
  {
    name: "theory-schools",
    route: "/theory-schools",
    search: ".theory-world-hero-search",
    firstFold: ".discipline-matrix",
    firstFoldMode: "complete" as const,
    requiredItems: 3,
  },
  {
    name: "scholars",
    route: "/scholars",
    search: ".directory-hero form",
    searchControl: ".directory-hero .search-field",
    firstFold: ".scholar-recommendations",
    firstFoldMode: "complete" as const,
    reveal: ".directory-results",
  },
  {
    name: "topics",
    route: "/topics",
    search: ".topic-hub-search",
    firstFold: ".topic-entry-guide",
    firstFoldMode: "complete" as const,
    requiredItems: 3,
  },
] as const;

function safeName(route: string) {
  return route === "/"
    ? "home"
    : route.replace(/^\//, "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

async function waitForEditorialPage(page: Page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.waitForLoadState("domcontentloaded");
      await page.locator("[data-ui-scope]").first().waitFor({ state: "attached" });
      await page.evaluate(() => document.fonts.ready);
      return;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (attempt === 2 || !message.includes("Execution context was destroyed")) throw error;
    }
  }
}

async function box(page: Page, selector: string) {
  const result = await page.locator(selector).first().boundingBox();
  expect(result, `${selector} should be rendered`).not.toBeNull();
  return result!;
}

async function assertHealthySurface(page: Page, expectedScope: "editorial-v2" | "explore-frozen") {
  await expect(page.locator("[data-ui-scope]").first()).toHaveAttribute("data-ui-scope", expectedScope);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    brokenImages: [...document.images]
      .filter((image) => image.complete && image.naturalWidth === 0)
      .map((image) => image.currentSrc || image.src),
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  expect(dimensions.brokenImages).toEqual([]);
}

async function dynamicPublicRoutes(request: APIRequestContext) {
  const apiBase = (process.env.DENSITY_API_BASE_URL ?? "https://books.winstonmo.com/api").replace(/\/$/, "");
  const endpoints = [
    "/catalog/works/?format=json",
    "/catalog/scholars/?format=json",
    "/catalog/topics/?format=json",
    "/catalog/theory-schools/?format=json",
    "/catalog/subdisciplines/?format=json",
    "/catalog/theory-system/overview/?format=json",
  ];
  const responses = await Promise.all(endpoints.map((endpoint) => request.get(`${apiBase}${endpoint}`)));
  for (const [index, response] of responses.entries()) {
    expect(response.ok(), endpoints[index]).toBeTruthy();
  }
  const [works, scholars, topics, schools, subdisciplines, overview] = await Promise.all(
    responses.map((response) => response.json()),
  );
  const workSlug = works.results?.[0]?.edition?.public_slug;
  const workId = works.results?.[0]?.id;
  const assetId = works.results?.[0]?.edition?.readable_asset?.id;
  const scholarSlug = scholars.results?.[0]?.slug;
  const topicSlug = topics.results?.[0]?.slug;
  const schoolSlug = schools.results?.[0]?.slug;
  const subdisciplineSlug = subdisciplines.results?.[0]?.slug;
  const disciplineSlug = overview.disciplines?.[0]?.slug;
  const nodeSlug = overview.recent?.nodes?.[0]?.slug;
  const readingPathSlug = overview.reading_paths?.[0]?.slug;

  return [
    workSlug && `/works/${encodeURIComponent(workSlug)}`,
    workId && `/explore/semantic/${encodeURIComponent(workId)}`,
    assetId && `/reader/${encodeURIComponent(assetId)}`,
    scholarSlug && `/scholars/${encodeURIComponent(scholarSlug)}`,
    scholarSlug && `/scholars/${encodeURIComponent(scholarSlug)}/biography`,
    scholarSlug && `/scholars/${encodeURIComponent(scholarSlug)}/timeline`,
    scholarSlug && `/scholars/${encodeURIComponent(scholarSlug)}/works`,
    scholarSlug && `/scholars/${encodeURIComponent(scholarSlug)}/concepts`,
    topicSlug && `/topics/${encodeURIComponent(topicSlug)}`,
    topicSlug && `/topics/${encodeURIComponent(topicSlug)}/scholars`,
    topicSlug && `/topics/${encodeURIComponent(topicSlug)}/timeline`,
    topicSlug && `/topics/${encodeURIComponent(topicSlug)}/concepts`,
    schoolSlug && `/theory-schools/${encodeURIComponent(schoolSlug)}`,
    schoolSlug && `/theory-schools/${encodeURIComponent(schoolSlug)}/scholars`,
    schoolSlug && `/theory-schools/${encodeURIComponent(schoolSlug)}/concepts`,
    subdisciplineSlug && `/subdisciplines/${encodeURIComponent(subdisciplineSlug)}`,
    disciplineSlug && `/theories/disciplines/${encodeURIComponent(disciplineSlug)}`,
    nodeSlug && `/theories/nodes/${encodeURIComponent(nodeSlug)}`,
    readingPathSlug && `/theories/reading-paths/${encodeURIComponent(readingPathSlug)}`,
  ].filter((route): route is string => Boolean(route));
}

test("core knowledge entrances satisfy the compact first-fold contract", async ({ page }) => {
  await mkdir(path.join(outputRoot, "core"), { recursive: true });

  for (const item of corePages) {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    const onPageError = (error: Error) => pageErrors.push(error.message);
    const onConsole = (message: { type(): string; text(): string }) => {
      const text = message.text();
      if (message.type() === "error" && !/^Failed to load resource:.*404 \(Not Found\)$/i.test(text)) {
        consoleErrors.push(text);
      }
    };
    page.on("pageerror", onPageError);
    page.on("console", onConsole);
    await page.setViewportSize(desktopViewports[0]);

    const response = await page.goto(item.route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), item.route).toBeLessThan(400);
    await waitForEditorialPage(page);

    for (const viewport of desktopViewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
      await assertHealthySurface(page, "editorial-v2");

      const header = await box(page, ".site-header");
      expect(header.height).toBeGreaterThanOrEqual(56);
      expect(header.height).toBeLessThanOrEqual(68);

      const search = await box(page, item.search);
      expect(search.width).toBeGreaterThanOrEqual(480);
      expect(search.width).toBeLessThanOrEqual(622);
      const searchControl = await box(page, "searchControl" in item ? item.searchControl : item.search);
      expect(searchControl.height).toBeGreaterThanOrEqual(44);
      expect(searchControl.height).toBeLessThanOrEqual("searchControl" in item ? 48 : 50);

      const firstFold = await box(page, item.firstFold);
      if (item.firstFoldMode === "complete") {
        expect(firstFold.y + firstFold.height, `${item.route} primary entry must fit`).toBeLessThanOrEqual(viewport.height + 1);
      } else {
        expect(firstFold.y, `${item.route} overview must begin in the first fold`).toBeLessThan(viewport.height);
      }
      if ("requiredItems" in item) {
        await expect(page.locator(`${item.firstFold} > *`)).toHaveCount(item.requiredItems);
      }
      if ("reveal" in item) {
        const reveal = await box(page, item.reveal);
        expect(reveal.y, `${item.route} directory heading should be revealed`).toBeLessThan(viewport.height);
      }

      const shell = await box(page, ".page-shell");
      if (viewport.width === 1920) expect(shell.width).toBeGreaterThanOrEqual(1680);
      if (viewport.width === 2560) expect(shell.width).toBeGreaterThanOrEqual(2000);
      if (viewport.width === 3840) expect(shell.width).toBeGreaterThanOrEqual(2160);

      if (requestedVisualViewports.some((candidate) => candidate.width === viewport.width)) {
        await page.screenshot({
          path: path.join(outputRoot, "core", `${item.name}-${viewport.width}x${viewport.height}.png`),
          fullPage: false,
        });
      }
    }
    page.off("pageerror", onPageError);
    page.off("console", onConsole);
    expect(pageErrors, `${item.route} page errors`).toEqual([]);
    expect(consoleErrors, `${item.route} console errors`).toEqual([]);
  }
});

test("tablet and mobile keep the editorial pages usable without overflow", async ({ page }) => {
  const responsiveViewports = [{ width: 834, height: 1112 }, { width: 390, height: 844 }];
  for (const item of corePages) {
    await page.setViewportSize(responsiveViewports[0]);
    const response = await page.goto(item.route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), item.route).toBeLessThan(400);
    await waitForEditorialPage(page);
    for (const viewport of responsiveViewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
      await assertHealthySurface(page, "editorial-v2");
      await expect(page.locator(item.search)).toBeVisible();
      await expect(page.locator(item.firstFold)).toBeVisible();
    }
  }
});

test("Explore preserves its frozen route scope across wide screens", async ({ page }) => {
  await mkdir(path.join(outputRoot, "explore"), { recursive: true });
  const routes = [
    "/explore",
    "/explore/original?q=%E4%B9%A1%E5%9C%9F%E4%B8%AD%E5%9B%BD",
    "/explore/opinions?q=%E5%B7%AE%E5%BA%8F%E6%A0%BC%E5%B1%80",
    "/explore/ask",
  ];
  for (const route of routes) {
    await page.setViewportSize(requestedVisualViewports[0]);
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), route).toBeLessThan(400);
    await waitForEditorialPage(page);
    for (const viewport of requestedVisualViewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
      await assertHealthySurface(page, "explore-frozen");
      await page.screenshot({
        path: path.join(outputRoot, "explore", `${safeName(route)}-${viewport.width}x${viewport.height}.png`),
        fullPage: false,
      });
    }
  }
});

test("every public route family renders at each requested visual width", async ({ page, request }) => {
  test.skip(!fullMatrix, "Set DENSITY_FULL_MATRIX=true for the release visual matrix.");
  await mkdir(path.join(outputRoot, "route-matrix"), { recursive: true });
  const fixedRoutes = [
    "/",
    "/about",
    "/scholars",
    "/topics",
    "/subdisciplines",
    "/theories",
    "/theories/directory",
    "/theories/graph",
    "/theories/timeline",
    "/theory-schools",
    "/theory-schools/graph",
    "/theory-schools/timeline",
    "/login",
    "/register",
    "/reset-password",
    "/account",
    "/admin",
  ];
  const routes = [...fixedRoutes, ...(await dynamicPublicRoutes(request))];

  for (const route of routes) {
    await page.setViewportSize(requestedVisualViewports[0]);
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), route).toBeLessThan(400);
    await waitForEditorialPage(page);
    for (const viewport of requestedVisualViewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
      const scope = route.startsWith("/explore") ? "explore-frozen" : "editorial-v2";
      await assertHealthySurface(page, scope);
      await page.screenshot({
        path: path.join(outputRoot, "route-matrix", `${safeName(route)}-${viewport.width}x${viewport.height}.png`),
        fullPage: false,
      });
    }
  }
});
