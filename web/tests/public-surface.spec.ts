import { expect, test } from "@playwright/test";

const strictRepairChecks = process.env.EXPECT_REPAIRED_PUBLIC === "true";
const garbledPdfAssetId = process.env.GARBLED_PDF_ASSET_ID ?? "";
const garbledPdfPage = Number.parseInt(process.env.GARBLED_PDF_TEST_PAGE ?? "21", 10);

test.describe("public library read-only smoke", () => {
  test("home and core public navigation remain available", async ({ page }) => {
    const response = await page.goto("/", { waitUntil: "domcontentloaded" });
    expect(response?.status()).toBeLessThan(400);
    await expect(page).toHaveTitle(/社会理论书库/);
    await expect(page.getByRole("link", { name: "探索" }).first()).toBeVisible();
    await expect(page.getByText("最近入库", { exact: true }).first()).toBeVisible();
  });

  test("catalog, semantic fallback and reader range delivery stay readable", async ({ request }) => {
    const worksResponse = await request.get(
      "/api/catalog/works/?ordering=-editions__first_published_at&format=json",
    );
    expect(worksResponse.ok()).toBeTruthy();
    const works = await worksResponse.json();
    expect(Array.isArray(works.results)).toBeTruthy();

    const semanticResponse = await request.get(
      "/api/catalog/semantic-search/?q=%E5%9B%BD%E5%AE%B6&format=json",
    );
    expect(semanticResponse.ok()).toBeTruthy();
    const semantic = await semanticResponse.json();
    expect(Array.isArray(semantic.results)).toBeTruthy();
    expect(JSON.stringify(semantic)).not.toMatch(/Traceback|NameResolutionError|ConnectError/);

    const readableAsset = works.results?.[0]?.edition?.readable_asset;
    test.skip(!readableAsset?.id, "Public catalog currently has no readable asset.");

    const accessResponse = await request.get(
      `/api/distribution/assets/${readableAsset.id}/access/?format=json`,
    );
    expect(accessResponse.ok()).toBeTruthy();
    const access = await accessResponse.json();
    expect(access.supports_range).toBe(true);
    expect(access.page_count).toBeGreaterThan(0);
    expect(typeof access.url).toBe("string");

    const fileResponse = await request.get(access.url, {
      headers: { Range: "bytes=0-1023" },
    });
    expect(fileResponse.status()).toBe(206);
    expect(fileResponse.headers()["content-type"]).toContain("application/pdf");
    expect(fileResponse.headers()["content-range"]).toMatch(/^bytes 0-1023\//);

    if (strictRepairChecks) {
      expect(access.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(access.rendition).toBeTruthy();
      expect(access.ocr_status).toBeTruthy();
      expect(access.served_asset_id).toBeTruthy();
    }
  });

  test("strict mode proves the latest-entry panel uses current published data", async ({ page, request }) => {
    test.skip(!strictRepairChecks, "Set EXPECT_REPAIRED_PUBLIC=true after deploying the repaired source.");
    const worksResponse = await request.get(
      "/api/catalog/works/?ordering=-editions__first_published_at&format=json",
    );
    expect(worksResponse.ok()).toBeTruthy();
    const works = await worksResponse.json();
    test.skip(!works.results?.length, "Public catalog has no published work to assert.");

    await page.goto("/", { waitUntil: "domcontentloaded" });
    const recentSection = page.locator("section").filter({ hasText: "最近入库" }).first();
    await expect(recentSection).toContainText(works.results[0].title);
  });

  test("strict mode covers every public route family", async ({ request }) => {
    test.skip(!strictRepairChecks, "Set EXPECT_REPAIRED_PUBLIC=true after deploying the repaired source.");
    test.setTimeout(120_000);

    const fixedRoutes = [
      "/",
      "/about",
      "/explore",
      "/explore/original?q=%E4%B9%A1%E5%9C%9F%E4%B8%AD%E5%9B%BD",
      "/explore/opinions?q=%E5%B7%AE%E5%BA%8F%E6%A0%BC%E5%B1%80",
      "/explore/ask",
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
    ];
    for (const route of fixedRoutes) {
      const response = await request.get(route);
      expect(response.status(), route).toBeLessThan(400);
      expect(response.headers()["content-type"], route).toContain("text/html");
      const html = await response.text();
      expect(html, route).not.toMatch(/Internal Server Error|Application error|Traceback/);
    }

    const [worksResponse, scholarsResponse, topicsResponse, theoriesResponse, subdisciplinesResponse, overviewResponse] = await Promise.all([
      request.get("/api/catalog/works/?format=json"),
      request.get("/api/catalog/scholars/?format=json"),
      request.get("/api/catalog/topics/?format=json"),
      request.get("/api/catalog/theory-schools/?format=json"),
      request.get("/api/catalog/subdisciplines/?format=json"),
      request.get("/api/catalog/theory-system/overview/?format=json"),
    ]);
    for (const response of [worksResponse, scholarsResponse, topicsResponse, theoriesResponse, subdisciplinesResponse, overviewResponse]) {
      expect(response.ok()).toBeTruthy();
    }

    const works = await worksResponse.json();
    const scholars = await scholarsResponse.json();
    const topics = await topicsResponse.json();
    const theories = await theoriesResponse.json();
    const subdisciplines = await subdisciplinesResponse.json();
    const overview = await overviewResponse.json();
    const dynamicRoutes = [
      works.results?.[0]?.edition?.public_slug ? `/works/${encodeURIComponent(works.results[0].edition.public_slug)}` : "",
      works.results?.[0]?.id ? `/explore/semantic/${encodeURIComponent(works.results[0].id)}` : "",
      scholars.results?.[0]?.slug ? `/scholars/${encodeURIComponent(scholars.results[0].slug)}` : "",
      topics.results?.[0]?.slug ? `/topics/${encodeURIComponent(topics.results[0].slug)}` : "",
      theories.results?.[0]?.slug ? `/theory-schools/${encodeURIComponent(theories.results[0].slug)}` : "",
      subdisciplines.results?.[0]?.slug ? `/subdisciplines/${encodeURIComponent(subdisciplines.results[0].slug)}` : "",
      overview.disciplines?.[0]?.slug ? `/theories/disciplines/${encodeURIComponent(overview.disciplines[0].slug)}` : "",
      overview.reading_paths?.[0]?.slug ? `/theories/reading-paths/${encodeURIComponent(overview.reading_paths[0].slug)}` : "",
    ].filter(Boolean);
    for (const route of dynamicRoutes) {
      const response = await request.get(route);
      expect(response.status(), route).toBeLessThan(400);
      expect(response.headers()["content-type"], route).toContain("text/html");
      expect(await response.text(), route).not.toMatch(/Internal Server Error|Application error|Traceback/);
    }
  });

  test("strict mode serves the redesigned Explore assets and assistant contract", async ({ request }) => {
    test.skip(!strictRepairChecks, "Set EXPECT_REPAIRED_PUBLIC=true after deploying the repaired source.");

    for (const resource of [
      "/explore/explore-architecture-hero-v1.webp",
      "/explore/explore-magnifier-v1.webp",
      "/explore/explore-door-v1.webp",
      "/explore/explore-dialogue-v1.webp",
    ]) {
      const response = await request.get(resource);
      expect(response.ok(), `${resource} must be deployed with the Explore build`).toBeTruthy();
      expect(response.headers()["content-type"], resource).toContain("image/webp");
      expect((await response.body()).byteLength, resource).toBeGreaterThan(1000);
    }

    const assistantStatus = await request.get("/api/reading/library-assistant/status/");
    expect([401, 403]).toContain(assistantStatus.status());
    expect(assistantStatus.status()).not.toBe(404);
  });

  test("strict mode serves Chinese CMaps and renders the known legacy PDF", async ({ page, request }) => {
    test.skip(!strictRepairChecks, "Set EXPECT_REPAIRED_PUBLIC=true after deploying the repaired source.");
    test.setTimeout(90_000);

    for (const resource of [
      "/pdfjs/cmaps/GB-EUC-H.bcmap",
      "/pdfjs/cmaps/GBK-EUC-H.bcmap",
      "/pdfjs/cmaps/Adobe-GB1-UCS2.bcmap",
      "/pdfjs/standard_fonts/FoxitSerif.pfb",
      "/pdfjs/pdf.worker.min.js",
    ]) {
      const response = await request.get(resource);
      expect(response.ok(), `${resource} must be deployed with the web build`).toBeTruthy();
      expect((await response.body()).byteLength).toBeGreaterThan(100);
    }

    test.skip(!garbledPdfAssetId, "Set GARBLED_PDF_ASSET_ID to the verified public legacy PDF.");
    const cmapWarnings: string[] = [];
    const pdfFileRequests: string[] = [];
    page.on("console", (message) => {
      if (/cMapUrl|CMap|translateFont failed/i.test(message.text())) cmapWarnings.push(message.text());
    });
    page.on("request", (request) => {
      if (request.url().includes(`/api/distribution/assets/${garbledPdfAssetId}/file/`)) {
        pdfFileRequests.push(request.headers()["range"] ?? "");
      }
    });
    await page.goto(`/reader/${garbledPdfAssetId}?page=${garbledPdfPage}`, {
      waitUntil: "domcontentloaded",
    });
    const pageShell = page.locator(`.pdf-page-shell[data-page-number="${garbledPdfPage}"]`);
    await expect(pageShell).toBeVisible({ timeout: 60_000 });
    const canvas = pageShell.locator("canvas");
    await expect(canvas).toBeVisible({ timeout: 60_000 });
    await expect.poll(async () => canvas.evaluate((node) => ({
      width: (node as HTMLCanvasElement).width,
      height: (node as HTMLCanvasElement).height,
      busy: node.closest(".pdf-canvas-stage")?.getAttribute("aria-busy"),
    }))).toMatchObject({
      width: expect.any(Number),
      height: expect.any(Number),
      busy: "false",
    });
    const dimensions = await canvas.evaluate((node) => ({
      width: (node as HTMLCanvasElement).width,
      height: (node as HTMLCanvasElement).height,
    }));
    expect(dimensions.width).toBeGreaterThan(300);
    expect(dimensions.height).toBeGreaterThan(400);
    expect(cmapWarnings).toEqual([]);
    const rangedPdfRequests = pdfFileRequests.filter((range) => /^bytes=\d+-\d+$/.test(range));
    expect(rangedPdfRequests.length).toBeGreaterThan(0);
  });
});
