import { expect, test, type Page } from "@playwright/test";
import type { PublicTheoryGraph } from "../lib/api/graph.types";

// Real disposable API and extracted timeline PDFs. Only request failures and
// delays are controlled below; no graph, source or business response is mocked.
const api = "http://127.0.0.1:8105/api";
const id = (value: number) => `52000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const center = id(101), fourth = id(104), isolated = id(106), hidden = id(105);
const edgeFirst = `KnowledgeRelation:${id(201)}`, edgeSecond = `KnowledgeRelation:${id(202)}`;
const sourceAsset = "41300000-0000-4000-8000-000000000103";
const sourceEdition = "41300000-0000-4000-8000-000000000101";
function query(changes: Record<string, string> = {}) { return new URLSearchParams({ center, center_kind: "knowledge_node", ...changes }).toString(); }
function path(changes: Record<string, string> = {}) { return `/theories/graph?${query(changes)}`; }
async function graph(page: Page, changes: Record<string, string> = {}): Promise<PublicTheoryGraph> {
  const response = await page.request.get(`${api}/catalog/theory-system/graph/?${query(changes)}`);
  expect(response.status(), `seed_graph(actor) must run after the timeline fixture: ${await response.text()}`).toBe(200);
  return response.json();
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use only the disposable acceptance environment.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
});

test("the actual three-layer neighborhood retains typed identities without exposing hidden or draft content", async ({ page }) => {
  const first = await graph(page), expanded = await graph(page, { depth: "3" });
  expect(first.nodes.some(node => node.entity_id === fourth)).toBe(false);
  expect(expanded.nodes.find(node => node.entity_id === fourth)).toMatchObject({ kind: "knowledge_node", depth: 3 });
  expect(expanded.edges.map(edge => edge.id)).toContain(edgeFirst);
  expect(expanded.nodes.map(node => node.entity_id)).not.toContain(hidden);
  expect(JSON.stringify(expanded)).not.toContain("GRAPH52 草稿正文不得公开");
  expect(expanded.candidate_edges).toEqual([]);
  expect(expanded.candidate_count).toBeNull();
  expect(expanded.counts.edges).toBe(expanded.edges.length);
  expect(expanded.truncated).toBe(false);
  for (const [kind, selected] of [["topic", "56000000-0000-4000-8000-000000000011"],
    ["scholar", "56000000-0000-4000-8000-000000000041"], ["subdiscipline", id(151)]] as const) {
    const selectedGraph = await graph(page, { center_kind: kind, center: selected });
    expect(selectedGraph.center).toBe(`${kind}:${selected}`);
    expect(selectedGraph.nodes.find(node => node.is_center)).toMatchObject({ kind, entity_id: selected });
  }
  await page.goto(path());
  await expect(page.getByRole("heading", { name: "知识地图与学科目录", level: 1, exact: true })).toBeVisible();
  await page.getByRole("form", { name: "图谱范围筛选", exact: true }).getByRole("radio", { name: "3 层邻居", exact: true }).check();
  await page.getByRole("button", { name: "应用范围", exact: true }).click();
  await expect(page).toHaveURL(/depth=3/);
  await expect(page.getByRole("group", { name: "知识关系图，可选择节点或关系", exact: true })
    .getByRole("button", { name: "查看GRAPH52 第四节点，3层关系", exact: true })).toBeVisible();
});

test("relationship evidence retains the exact source edition and current revision and rejects changed-case quotations", async ({ page }) => {
  const data = await graph(page, { depth: "2" });
  const source = data.edges.find(edge => edge.id === edgeFirst)!.evidence[0];
  expect(source).toMatchObject({ asset_id: sourceAsset, edition_id: sourceEdition, pdf_page: 1 });
  expect(source.quote).toContain("PARALLEL LEFT SEGMENT");
  expect(source.document_revision_id).toBeTruthy();
  const href = new URL(source.reader_href, "http://127.0.0.1:3105");
  expect(href.pathname).toBe(`/reader/${sourceAsset}`);
  expect(href.searchParams.get("revision")).toBe(source.document_revision_id);
  expect(data.edges.find(edge => edge.id === edgeSecond)?.evidence).toEqual([]);
  await page.goto(path());
  const edge = page.getByRole("group", { name: "知识关系图，可选择节点或关系", exact: true })
    .getByRole("button", { name: "GRAPH52 中心概念 受到影响 GRAPH52 第二层概念", exact: true });
  await edge.focus();
  await edge.press("Enter");
  const inspector = page.getByRole("region", { name: "选中关系详情", exact: true });
  await expect(inspector).toContainText("PARALLEL LEFT SEGMENT");
  await expect(inspector.getByRole("link", { name: "查看原文", exact: true })).toHaveAttribute("href", source.reader_href);
  await expect(inspector).toContainText("已发布");
});

test("related holdings paginate thirteen actual published versions without substituting a different book", async ({ page }) => {
  const first = await graph(page), second = await graph(page, { works_page: "2" });
  expect(first.related_works_count).toBe(13);
  expect(first.related_works).toHaveLength(12);
  expect(second.related_works).toHaveLength(1);
  expect(first.related_works_total_pages).toBe(2);
  expect(first.related_works.every(work => work.id === id(501) && work.title === "GRAPH52 合成图谱书目")).toBe(true);
  expect(first.related_works.map(work => work.edition_id)).not.toContain(second.related_works[0].edition_id);
  await page.goto(path({ view: "works" }));
  await expect(page.getByRole("tabpanel")).toContainText("共 13 个版本");
  await expect(page.getByRole("tabpanel").getByRole("link", { name: "查看此版书目", exact: true })).toHaveCount(12);
  await page.getByRole("navigation", { name: "图谱相关文献分页", exact: true }).getByRole("button", { name: "下一页", exact: true }).click();
  await expect(page).toHaveURL(/works_page=2/);
  await expect(page.getByRole("tabpanel").getByRole("link", { name: "查看此版书目", exact: true })).toHaveCount(1);
});

test("failed requests and cancellation retain the last loaded graph and allow a real retry", async ({ page }) => {
  await page.goto(path());
  const pattern = "**/api/catalog/theory-system/graph/**";
  await page.route(pattern, route => route.abort("failed"));
  await page.getByRole("button", { name: "展开一层关系", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("当前图谱未能读取");
  await expect(page.locator("main")).toContainText("当前显示 1 层邻居");
  await page.unroute(pattern);
  await page.getByRole("button", { name: "重试读取", exact: true }).click();
  await expect(page).toHaveURL(/depth=2/);
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  let release = () => {};
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route(pattern, async route => { await pending; await route.continue().catch(() => {}); });
  await page.getByRole("button", { name: "展开一层关系", exact: true }).click();
  await expect(page.getByRole("tabpanel").getByRole("status")).toContainText("正在读取知识关系");
  await page.getByRole("button", { name: "取消读取", exact: true }).click();
  release();
  await page.unroute(pattern);
  await expect(page.getByText("已取消本次读取，保留上次已加载的范围。", { exact: true })).toBeVisible();
  await expect(page.locator("main")).toContainText("当前显示 2 层邻居");
  await expect(page).toHaveURL(/depth=2/);
});

test("mobile starts with the relationship list, opens a keyboard-accessible detail sheet and has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path());
  const listTab = page.getByRole("tab", { name: "关系列表", exact: true });
  await expect(listTab).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tabpanel").getByRole("button").filter({ hasText: "GRAPH52 第二层概念" }).click();
  const dialog = page.getByRole("dialog", { name: "图谱详情", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("PARALLEL LEFT SEGMENT");
  await dialog.getByRole("button", { name: "关闭图谱详情", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await listTab.focus();
  await listTab.press("Home");
  await expect(page.getByRole("tab", { name: "关系图谱", exact: true })).toBeFocused();
  await page.getByRole("tab", { name: "关系图谱", exact: true }).press("End");
  await expect(page.getByRole("tab", { name: "相关文献", exact: true })).toBeFocused();
  await expect(page.getByRole("tab", { name: "相关文献", exact: true })).toHaveAttribute("aria-selected", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("isolated and unavailable centers remain distinguishable", async ({ page }) => {
  const empty = await graph(page, { center: isolated });
  expect(empty.state).toBe("isolated");
  expect(empty.edges).toEqual([]);
  await page.goto(path({ center: isolated }));
  await expect(page.locator("main")).toContainText("当前范围内尚无已发布的关系");
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  await page.goto(path({ center: hidden }));
  await expect(page.locator("main").getByRole("alert")).toContainText("当前中心或筛选范围不可用");
  await expect(page.locator("main")).not.toContainText("隐藏名称不得出现");
});

test("candidate overlay requires editorial permission and never changes the confirmed edge count", async ({ page }) => {
  const denied = await page.request.get(`${api}/catalog/theory-system/graph/?${query({ include_candidates: "true" })}`);
  expect(denied.status()).toBe(403);
  await page.goto(path());
  await expect(page.getByRole("checkbox", { name: "查看待审核候选", exact: true })).toHaveCount(0);
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const plain = await graph(page), overlay = await graph(page, { include_candidates: "true" });
  expect(overlay.counts).toEqual(plain.counts);
  expect(overlay.candidate_edges.map(edge => edge.id)).toEqual([`KnowledgeRelation:${id(205)}`]);
  expect(overlay.candidate_count).toBe(1);
  expect(overlay.candidate_edges[0]).toMatchObject({ status: "pending", source_status: "unverified", evidence: [] });
  expect(JSON.stringify(overlay)).not.toContain("隐藏名称不得出现");
  await page.goto(path());
  await page.getByRole("checkbox", { name: "查看待审核候选", exact: true }).check();
  await expect(page).toHaveURL(/include_candidates=true/);
  await expect(page.getByRole("group", { name: "知识关系图，可选择节点或关系", exact: true })
    .getByRole("button", { name: /^待审核候选：GRAPH52 中心概念/ })).toBeVisible();
});
