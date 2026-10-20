import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { KnowledgeNodeDetail, TheoryConceptUsage } from "../lib/api/knowledge.types";
import type { KnowledgeSaveCommand, KnowledgeSaveState } from "../lib/api/knowledge-actions.client";

// Final acceptance only. Both SSR and the browser use the disposable real API,
// seeded by seed_theory() after the actual parallel PDF extraction/publication.
// Business responses and page HTML are never fabricated. One case loses only
// the response after a real save, then verifies the server's original receipt.
const api = "http://127.0.0.1:8105/api";
const ids = {
  theory: "45000000-0000-4000-8000-000000000011",
  concept: "45000000-0000-4000-8000-000000000012",
  usageA: "45000000-0000-4000-8000-000000000041",
  usageB: "45000000-0000-4000-8000-000000000042",
  usageC: "45000000-0000-4000-8000-000000000043",
  distinct: "45000000-0000-4000-8000-000000000052",
};
const conceptPath = "/theories/nodes/e2e-theory-concept";
const theoryPath = "/theories/nodes/e2e-theory-theory";
const search = (page: Page) => page.getByRole("search", { name: "搜索理论流派与概念", exact: true });
const card = (page: Page, id: string) => page.locator(`article[id="usage-${id}"]`);
const comparison = (page: Page) => page.getByRole("dialog", { name: "用法对比（2）", exact: true });

async function transport(page: Page) {
  await page.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use the isolated loopback acceptance configuration.").toBeTruthy();
  expect(new URL(baseURL!).origin).toBe("http://127.0.0.1:3105");
  await transport(page);
});

async function conceptUses(page: Page) {
  const response = await page.request.get(`${api}/catalog/content-placements/node/${ids.concept}/`);
  expect(response.status(), "seed_theory() must publish real extracted spans before acceptance.").toBe(200);
  const value = await response.json() as { public_detail: { usages: TheoryConceptUsage[]; unavailable_usage_count: number } };
  expect(value.public_detail.unavailable_usage_count).toBe(0);
  expect(value.public_detail.usages.map(row => row.id).sort()).toEqual([ids.usageA, ids.usageB, ids.usageC].sort());
  for (const usage of value.public_detail.usages) {
    expect(usage.source.document_revision_id).toBeTruthy();
    expect(usage.source.text).toContain("PARALLEL");
    expect(usage.source.reader_url).toBe(`/reader/${usage.source.asset_id}?page=${usage.source.page_start}&revision=${usage.source.document_revision_id}`);
  }
  return value.public_detail.usages;
}

async function login(page: Page, role = "reader") {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.ok()).toBeTruthy();
  return String((await response.json() as { id: number }).id);
}

for (const path of ["/theories", "/theory-schools"]) {
  test(`${path} renders the PDF45 hierarchy from real published collection data`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1, name: "理论流派", exact: true })).toBeVisible();
    const disciplines = page.getByRole("region", { name: "主要学科领域", exact: true });
    await expect(disciplines.getByRole("link", { name: /E2E理论学科/ })).toBeVisible();
    const collection = page.getByRole("region", { name: "馆藏理论流派", exact: true });
    await expect(collection.getByRole("link", { name: /E2E理论传统/ })).toHaveAttribute("href", theoryPath);
    await expect(collection.getByRole("link", { name: /E2E测试概念|E2E未公开概念|E2E理论配图/ })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "进一步浏览", exact: true })).toBeVisible();
    await expect(search(page)).toHaveAttribute("action", path);
    await expect(page.locator("main").getByText(/推荐轨|推荐阅读路径|学科总数|理论总数/)).toHaveCount(0);
    await expect(page.locator('picture img[src="/visual/stl4/theory/hero-desktop.webp"]')).toBeVisible();
  });
}

for (const query of ["E2E测试概念", "E2E概念别名", "E2E代表学者甲"]) {
  test(`overview search finds public concepts by ${query} without requiring collection works`, async ({ page }) => {
    await page.goto("/theories");
    await search(page).getByRole("searchbox", { name: "流派名称、核心概念或代表学者" }).fill(query);
    await search(page).getByRole("button", { name: "搜索", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`q=${encodeURIComponent(query)}`));
    const result = page.getByRole("region", { name: "搜索结果", exact: true });
    const concept = result.getByRole("link", { name: /E2E测试概念/ });
    await expect(concept).toContainText("核心概念");
    await expect(concept).toHaveAttribute("href", conceptPath);
    await concept.click();
    await expect(page.getByRole("heading", { level: 1, name: /E2E测试概念/ })).toBeVisible();
  });
}

test("draft-only search remains a truthful zero-result state", async ({ page }) => {
  await page.goto("/theories?q=E2E未公开概念");
  const result = page.getByRole("region", { name: "搜索结果", exact: true });
  await expect(result).toContainText("没有找到符合条件的公开理论条目");
  await expect(result).toContainText("共 0 个公开条目");
  await expect(result.locator('a[href="/theories/nodes/e2e-theory-draft"]')).toHaveCount(0);
  await expect(result.getByRole("alert")).toHaveCount(0);
});

test("an empty published discipline stays empty and can clear its filter", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/theory-system/nodes/?type=theory_tradition&has_works=true&discipline=e2e-theory-empty`);
  expect(response.status()).toBe(200);
  expect((await response.json() as { count: number }).count).toBe(0);
  await page.goto("/theories?discipline=e2e-theory-empty");
  const collection = page.getByRole("region", { name: "馆藏理论流派", exact: true });
  await expect(collection).toContainText("当前学科暂无关联公开馆藏的理论流派");
  await expect(collection).toContainText("学科：E2E空学科");
  await expect(collection.getByRole("alert")).toHaveCount(0);
  await collection.getByRole("link", { name: "清除筛选", exact: true }).click();
  await expect(page).toHaveURL(/\/theories$/);
  await expect(collection.getByRole("link", { name: /E2E理论传统/ })).toBeVisible();
});

test("a real out-of-range API page is shown as a read failure rather than empty collection", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/theory-system/nodes/?type=theory_tradition&has_works=true&page=999999`);
  expect(response.status()).toBe(404);
  await page.goto("/theories?page=999999");
  const collection = page.getByRole("region", { name: "馆藏理论流派", exact: true });
  await expect(collection.getByRole("alert")).toContainText("当前状态不能判断馆藏是否为空");
  await expect(collection.getByRole("status")).toHaveCount(0);
  await expect(collection.getByRole("link", { name: "重新载入馆藏理论", exact: true })).toHaveAttribute("href", "/theories?page=999999");
  await expect(page.getByRole("region", { name: "主要学科领域", exact: true }).getByRole("link", { name: /E2E理论学科/ })).toBeVisible();
});

test("further browsing preserves actual directory routes and type filters", async ({ page }) => {
  for (const [title, href, heading] of [
    ["理论传统", "/theories/directory?type=theory_tradition", "理论传统"],
    ["子学科", "/subdisciplines", "子学科"],
    ["关键争论", "/theories/directory?type=debate", "理论争论"],
  ]) {
    await page.goto("/theories");
    const link = page.getByRole("navigation", { name: "进一步浏览", exact: true }).getByRole("link", { name: new RegExp(`^${title}`) });
    await expect(link).toHaveAttribute("href", href);
    await link.click();
    expect(`${new URL(page.url()).pathname}${new URL(page.url()).search}`).toBe(href);
    await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
  }
});

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`PDF45 layout keeps usable native controls and card geometry at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/theories");
    const picture = page.locator('picture:has(img[src="/visual/stl4/theory/hero-desktop.webp"])');
    const heading = page.getByRole("heading", { level: 1, name: "理论流派", exact: true });
    const pictureBox = await picture.boundingBox(), headingBox = await heading.boundingBox();
    expect(pictureBox).not.toBeNull(); expect(headingBox).not.toBeNull();
    if (viewport.width < 700) {
      expect(pictureBox!.y + pictureBox!.height).toBeLessThanOrEqual(headingBox!.y);
      await expect(picture.locator("img")).toHaveJSProperty("currentSrc", "http://127.0.0.1:3105/visual/stl4/theory/hero-mobile.webp");
    } else {
      const textRight = await heading.evaluate(element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return range.getBoundingClientRect().right;
      });
      expect(pictureBox!.x).toBeGreaterThan(textRight);
      expect(pictureBox!.width).toBeGreaterThan(500);
    }
    const cards = page.getByRole("region", { name: "主要学科领域", exact: true }).getByRole("link");
    expect(await cards.count()).toBeGreaterThanOrEqual(3);
    const a = await cards.nth(0).boundingBox(), b = await cards.nth(1).boundingBox(), c = await cards.nth(2).boundingBox();
    expect(a && b && c).toBeTruthy();
    if (viewport.width < 700) {
      expect(Math.abs(a!.x - b!.x)).toBeLessThan(2);
      expect(b!.y).toBeGreaterThanOrEqual(a!.y + a!.height);
      expect(c!.y).toBeGreaterThanOrEqual(b!.y + b!.height);
    } else {
      expect(Math.abs(a!.y - b!.y)).toBeLessThan(2);
      expect(Math.abs(b!.y - c!.y)).toBeLessThan(2);
      expect(b!.x).toBeGreaterThan(a!.x);
      expect(c!.x).toBeGreaterThan(b!.x);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    const input = search(page).getByRole("searchbox");
    await input.focus();
    await page.keyboard.press("Tab");
    await expect(search(page).getByRole("button", { name: "搜索", exact: true })).toBeFocused();
  });
}

test("three real uses enforce two selections, expose exact source detail, and allow replacement", async ({ page }) => {
  const usages = await conceptUses(page);
  await page.goto(conceptPath);
  const section = page.locator("#usages");
  await expect(section.getByRole("checkbox")).toHaveCount(3);
  await card(page, ids.usageA).getByRole("checkbox").check();
  await card(page, ids.usageB).getByRole("checkbox").check();
  // Use click: the third box intentionally stays unchecked.
  await card(page, ids.usageC).getByRole("checkbox").click();
  await expect(card(page, ids.usageC).getByRole("checkbox")).not.toBeChecked();
  await expect(section.getByRole("status")).toHaveText("已选择两个用法。请先移除其中一个，再选择其他用法。");
  await expect(section.getByRole("checkbox", { checked: true })).toHaveCount(2);
  await section.getByRole("button", { name: "开始比较（2）", exact: true }).click();
  await expect(comparison(page)).toBeVisible();
  for (const id of [ids.usageA, ids.usageB]) {
    const usage = usages.find(row => row.id === id)!;
    await expect(comparison(page).getByText(usage.source.text, { exact: true })).toBeVisible();
    await expect(comparison(page).locator(`a[href="${usage.source.reader_url}"]`)).toHaveAttribute("target", "_blank");
  }
  await expect(comparison(page).getByRole("row", { name: /解释对象/ })).toContainText("合成解释对象A");
  await expect(comparison(page).getByRole("row", { name: /解释对象/ })).toContainText("合成解释对象B");
  await comparison(page).getByRole("button", { name: "替换用法", exact: true }).click();
  await section.getByRole("button", { name: "移除E2E用法B", exact: true }).click();
  await card(page, ids.usageC).getByRole("checkbox").check();
  await card(page, ids.usageC).getByRole("button", { name: "查看用法细节", exact: true }).click();
  const details = page.getByRole("dialog", { name: "E2E用法C", exact: true });
  await expect(details).toContainText("合成解释对象C");
  await expect(details.locator("blockquote")).toHaveText(usages.find(row => row.id === ids.usageC)!.source.text);
  await details.getByRole("button", { name: "比较所选用法", exact: true }).click();
  await expect(comparison(page)).toBeVisible();
  expect(new URL(page.url()).searchParams.get("compare")?.split(",")).toEqual([ids.usageA, ids.usageC]);
  await expect(comparison(page).getByRole("row", { name: /用法标题/ })).not.toContainText("E2E用法B");
});

test("comparison URL restores validated selections and ignores a second compare parameter", async ({ page }) => {
  await conceptUses(page);
  await page.goto(`${conceptPath}?compare=${ids.usageA},${ids.usageB}&compare=${ids.usageC}`);
  await expect(comparison(page)).toBeVisible();
  await expect(comparison(page).getByRole("row", { name: /用法标题/ })).toContainText("E2E用法A");
  await expect(comparison(page).getByRole("row", { name: /用法标题/ })).toContainText("E2E用法B");
  await page.reload();
  await expect(comparison(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(comparison(page)).not.toBeVisible();
  expect(new URL(page.url()).searchParams.has("compare")).toBe(false);
  await page.goto(`${conceptPath}?compare=${ids.usageA},${randomUUID()}`);
  await expect(comparison(page)).not.toBeVisible();
  await expect(page.locator("#usages").getByRole("status")).toContainText("部分用法当前不可读取");
  await expect(page.locator("#usages").getByRole("checkbox", { checked: true })).toHaveCount(1);
});

test("author/context filters and normalized alias counts reflect only the three confirmed uses", async ({ page }) => {
  await conceptUses(page);
  await page.goto(conceptPath);
  const section = page.locator("#usages");
  await section.getByLabel("作者", { exact: true }).selectOption({ label: "E2E代表学者甲" });
  await expect(section.locator("article[id^='usage-']")).toHaveCount(2);
  await section.getByLabel("语境", { exact: true }).selectOption({ label: "合成语境B" });
  await expect(section).toContainText("当前筛选下没有已公开用法");
  await section.getByRole("button", { name: "清除筛选", exact: true }).click();
  await expect(section.locator("article[id^='usage-']")).toHaveCount(3);
  await page.locator("summary").filter({ hasText: "更多译名" }).click();
  const aliases = page.getByRole("table", { name: "已收录的译名与别名", exact: true });
  const alias = aliases.getByRole("row", { name: /ＰＡＲＡＬＬＥＬ/ });
  await expect(alias.getByRole("cell").last()).toHaveText("3");
  await expect(aliases.getByRole("row", { name: /E2E概念别名/ }).getByRole("cell").last()).toHaveText("0");
});

test("relationship graph, list and evidence retain the same real source and keyboard selection", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/theory-system/nodes/e2e-theory-theory/`);
  expect(response.status()).toBe(200);
  const node = await response.json() as KnowledgeNodeDetail;
  const relation = node.direct_relations.find(row => row.id === ids.distinct)!;
  expect(relation).toBeDefined();
  expect(relation.evidence).toHaveLength(1);
  const evidence = relation.evidence![0];
  expect(evidence.quote).toContain("PARALLEL");
  expect(evidence.reader_href).toContain("revision=");
  await page.goto(theoryPath);
  const section = page.locator("#relations");
  await expect(section).toContainText("这条关系尚无可公开定位的原文依据");
  await section.getByRole("button", { name: "区别学派（1）", exact: true }).click();
  const nodeButton = section.locator("svg").getByRole("button", { name: "查看E2E关键争论的批判依据", exact: true });
  await nodeButton.focus();
  await page.keyboard.press("Enter");
  await expect(nodeButton).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Space");
  await expect(section.locator("blockquote")).toHaveText(evidence.quote);
  for (const mode of ["关系列表", "关系依据", "关系图谱"]) {
    await section.getByRole("button", { name: mode, exact: true }).click();
    await expect(section.getByRole("button", { name: mode, exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(section.locator("blockquote")).toHaveText(evidence.quote);
    await expect(section.getByRole("link", { name: "核对这条关系的原文", exact: true })).toHaveAttribute("href", evidence.reader_href!);
  }
  await expect(section.getByRole("link", { name: "打开完整图谱", exact: true })).toHaveAttribute("href", "/theories/graph?center=e2e-theory-theory");
});

test("a public node with no relationships renders the actual graph empty state", async ({ page }) => {
  const response = await page.request.get(`${api}/catalog/theory-system/nodes/e2e-node-image/`);
  expect(response.status()).toBe(200);
  expect((await response.json() as KnowledgeNodeDetail).direct_relations).toHaveLength(0);
  await page.goto("/theories/nodes/e2e-node-image");
  await expect(page.locator("#relations")).toContainText("此分类尚无已确认并公开的关系");
  await expect(page.locator("#relations svg")).toHaveCount(0);
});

test("a lost save response recovers the same owner nonce without repeating the mutation", async ({ page, browser, baseURL }) => {
  const owner = await login(page);
  const endpoint = `${api}/reading/saved-knowledge/${ids.concept}/`;
  const initial = await page.request.get(endpoint, { headers: { "X-Reader-Owner": owner } });
  expect(initial.status()).toBe(200);
  const before = await initial.json() as KnowledgeSaveState;
  if (before.saved) {
    const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken")?.value;
    expect(csrf, "The real fixture login must establish CSRF protection.").toBeTruthy();
    const reset = await page.request.post(endpoint, {
      headers: { "X-Reader-Owner": owner, "X-CSRFToken": csrf!, Origin: baseURL!, Referer: `${baseURL}${conceptPath}` },
      data: { saved: false, expected_version: before.version, request_id: randomUUID() } });
    expect(reset.status()).toBe(200);
  }
  const privacy = await page.request.get(`${api}/reading/privacy/`, { headers: { "X-Reader-Owner": owner } });
  expect(privacy.status()).toBe(200);
  expect((await privacy.json() as { retention: { saved_knowledge: boolean } }).retention.saved_knowledge).toBe(true);
  const writes: KnowledgeSaveCommand[] = [], receipts: string[] = [];
  await page.route(`**/api/reading/saved-knowledge/${ids.concept}/**`, async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === "POST") {
      writes.push(request.postDataJSON() as KnowledgeSaveCommand);
      expect(request.headers()["x-reader-owner"]).toBe(owner);
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      const applied = await response.json() as KnowledgeSaveState;
      expect(applied.saved).toBe(true);
      expect(applied.receipt?.request_id).toBe(writes[0].request_id);
      if (writes.length === 1) return route.fulfill({ response, status: 503,
        contentType: "application/json", body: JSON.stringify({ detail: "Synthetic lost response after the real commit." }) });
      return route.fulfill({ response });
    }
    if (url.searchParams.has("request_id")) receipts.push(url.searchParams.get("request_id")!);
    await route.continue();
  });
  await page.goto(conceptPath);
  await expect(page.getByRole("button", { name: "收藏", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "收藏", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  await expect(page.getByRole("alert")).toContainText("结果暂未确认");
  expect(writes).toHaveLength(1);
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(page.getByRole("button", { name: "已收藏", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "已核对原操作，当前收藏状态已更新。" })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(receipts).toEqual([writes[0].request_id]);
  const receipt = await page.request.get(`${endpoint}?request_id=${writes[0].request_id}`, { headers: { "X-Reader-Owner": owner } });
  expect(receipt.status()).toBe(200);
  expect(await receipt.json()).toMatchObject({ saved: true, owner_id: owner, receipt: { request_id: writes[0].request_id, applied_saved: true } });
  const outsider = await browser.newContext({ baseURL });
  try {
    const other = await outsider.newPage();
    await transport(other);
    const otherOwner = await login(other, "owner");
    const otherState = await other.request.get(`${endpoint}?request_id=${writes[0].request_id}`, { headers: { "X-Reader-Owner": otherOwner } });
    expect(otherState.status()).toBe(200);
    expect(await otherState.json()).toMatchObject({ saved: false, receipt: null, owner_id: otherOwner });
    const wrongOwner = await other.request.get(endpoint, { headers: { "X-Reader-Owner": owner } });
    expect(wrongOwner.status()).toBe(403);
  } finally {
    await outsider.close();
  }
});

test("anonymous visitors retain source access, an explicit login save link and current node citation", async ({ page }) => {
  await conceptUses(page);
  await page.goto(conceptPath);
  await expect(page.getByRole("link", { name: "收藏", exact: true })).toHaveAttribute("href", `/login?next=${encodeURIComponent(conceptPath)}`);
  await expect(card(page, ids.usageA).getByRole("link", { name: "查看原文", exact: true })).toHaveAttribute("target", "_blank");
  await page.getByRole("button", { name: "引用", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "引用此条目", exact: true });
  await expect(dialog.getByRole("textbox", { name: "条目引用", exact: true })).toHaveValue(/E2E测试概念/);
  await expect(dialog.getByRole("textbox", { name: "条目引用", exact: true })).not.toHaveValue(/E2E用法A|PARALLEL LEFT SEGMENT/);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "引用", exact: true })).toBeFocused();
});
