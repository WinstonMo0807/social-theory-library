import { expect, test } from "@playwright/test";

const baseline = process.env.V306_CAPTURE_BASELINE === "1";
const widths = [360,390,768,1280,1440];
const cases = [
  ["/scholars/v306-layout-scholar/timeline", ".timeline-detail-list", "timeline"],
  ["/topics/v306-layout-topic/timeline", ".timeline-detail-list", "timeline"],
  ["/scholars/v306-layout-scholar/concepts", ".definition-list", "concepts"],
  ["/theory-schools/v306-layout-legacy/concepts", ".definition-list", "concepts"],
] as const;

for (const width of widths) for (const [route, selector, structure] of cases) {
  test(`real ${structure} layout ${route} at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({width, height:1000});
    const response = await page.goto(route);
    expect(response?.status()).toBe(200);
    const content = page.locator(selector);
    await expect(content).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const geometry = await content.locator("article").first().evaluate((article) => {
      const children = [...article.children].map((node) => {
        const r = node.getBoundingClientRect(); const css = getComputedStyle(node);
        return {tag:node.tagName, x:r.x, y:r.y, right:r.right, bottom:r.bottom, width:r.width, height:r.height, text:node.textContent, overflow:css.overflow, maxHeight:css.maxHeight};
      });
      const r = article.getBoundingClientRect();
      return {children,x:r.x,right:r.right,width:r.width,columns:getComputedStyle(article).gridTemplateColumns};
    });
    await testInfo.attach("column-measurements", {body:JSON.stringify(geometry,null,2), contentType:"application/json"});
    await page.screenshot({path:testInfo.outputPath(`${baseline ? "before" : "after"}-${width}.png`),fullPage:true});
    if (baseline) return; // Baseline is evidence of the old geometry, not a pass.
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    for (const child of geometry.children) {
      expect(child.width).toBeGreaterThan(0);
      expect(child.right).toBeLessThanOrEqual(geometry.right+1);
      expect(child.overflow).not.toBe("hidden");
      expect(child.height).toBeGreaterThan(0);
    }
    if (structure === "timeline") {
      const [year, body] = geometry.children;
      expect(geometry.columns.split(" ")).toHaveLength(2);
      expect(body.x).toBeGreaterThan(year.right);
      expect(body.y).toBeCloseTo(year.y, 0);
      expect(body.right).toBeCloseTo(geometry.right, 0);
    } else {
      const [number, label, body, source] = geometry.children;
      expect(label.x).toBeGreaterThan(number.right);
      expect(source.x).toBeGreaterThanOrEqual(label.x-1);
      expect(source.y).toBeGreaterThanOrEqual(body.bottom-1);
      expect(source.text).toContain("长出处");
    }
  });
}

test("reader HTTP reasons remain distinct and recovery preserves anchors", async ({page}) => {
  test.skip(baseline, "Baseline capture only covers the pre-change geometry");
  for (const [status, kind] of [[401,"authentication"],[403,"forbidden"],[404,"unavailable"],[409,"waiting"],[429,"rate_limited"],[503,"service_unavailable"]] as const) {
    const route=`/reader/30600000-0000-4000-8000-000000${String(status).padStart(6,"0")}?page=21&q=long&passage=anchor`;
    await page.goto(route);
    await expect(page.locator(`[data-reader-failure="${kind}"]`)).toBeVisible();
    if (status!==403) {
      await page.getByRole("button",{name:"重试阅读请求",exact:true}).click();
      await expect(page).toHaveURL(new RegExp("page=21.*passage=anchor"));
    } else {
      expect(await page.getByRole("link",{name:"登录并返回原阅读位置"}).getAttribute("href")).toContain(encodeURIComponent(route));
    }
  }
});
