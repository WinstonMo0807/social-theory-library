import { randomUUID } from "node:crypto";
import { expect, request, test, type Page } from "@playwright/test";
import type { GraphViewData, GraphViewResponse } from "../lib/api/graph-views.client";

// Uses only the disposable cataloging API and its real graph/account fixtures.
// Fault injection loses or delays genuine responses; it never fabricates a
// graph, private record, receipt, owner or successful business response.
const api = "http://127.0.0.1:8105/api";
const collection = `${api}/reading/graph-views/`;
const center = "52000000-0000-4000-8000-000000000101";
const graphPath = `/theories/graph?center_kind=knowledge_node&center=${center}`;
const password = "E2E-Local-Only-305-passphrase";
const dialog = (page: Page) => page.getByRole("dialog", { name: "我的图谱视图", exact: true });
const data = (title: string): GraphViewData => ({ title, view: {
  center_kind: "knowledge_node", center, depth: 2, limit: 60, edge_limit: 150,
  node_type: [], relation_type: [], discipline: "", start_year: null, end_year: null,
  has_collection: null, selected_node: `knowledge_node:${center}`, selected_edge: "",
  view_mode: "list", zoom: 1.25, offset: { x: 34, y: -18 },
} });

async function headers(page: Page) {
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.status()).toBe(200);
  const owner = String((await response.json()).id);
  const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken");
  expect(csrf).toBeTruthy();
  return { "X-Reader-Owner": owner, "X-CSRFToken": csrf!.value };
}

async function create(page: Page, title: string) {
  const body = { request_id: randomUUID(), data: data(title) };
  const response = await page.request.post(collection, { headers: await headers(page), data: body });
  expect(response.status(), await response.text()).toBe(201);
  const result: GraphViewResponse = await response.json();
  expect(result.record).not.toBeNull();
  return { body, result, record: result.record! };
}

async function open(page: Page) {
  await page.goto(graphPath);
  await page.getByRole("button", { name: "保存当前视图", exact: true }).click();
  await expect(dialog(page).locator("ul").or(dialog(page).getByText("还没有保存的图谱视图。", { exact: true }))).toBeVisible();
  await expect(dialog(page).getByRole("button", { name: "保存为新视图", exact: true })).toBeEnabled();
}

async function switchAccount(page: Page) {
  const response = await page.request.post(`${api}/auth/login/`, {
    headers: await headers(page), data: { email: "administrator-v305@example.test", password },
  });
  expect(response.status(), await response.text()).toBe(200);
  const user = (await response.json()).user;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  return String(user.id);
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use only the disposable acceptance environment.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("reader-v305@example.test");
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
});

test("a saved_view link reads the owner's exact configuration and revalidates the public center", async ({ page }) => {
  const saved = await create(page, `Graph restore ${randomUUID()}`);
  const loaded = page.waitForResponse(response => response.url() === `${collection}${saved.record.id}/` && response.status() === 200);
  await page.goto(`/theories/graph?saved_view=${saved.record.id}`);
  const response = await loaded;
  expect(response.request().headers()["x-reader-owner"]).toBe(saved.result.owner_id);
  expect(response.headers()["cache-control"]).toContain("no-store");
  expect((await response.json()).record.data).toEqual(saved.body.data);
  await expect(page).toHaveURL(new RegExp(`center=${center}`));
  await expect(page).toHaveURL(/depth=2/);
  await expect(page).toHaveURL(/zoom=1.25/);
  await expect(page).toHaveURL(/offset_x=34/);
  await expect(page.getByRole("tab", { name: "关系列表", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("main")).toContainText("当前显示 2 层邻居");
});

test("a lost committed POST keeps its nonce through same-owner verification and guarded navigation", async ({ page }) => {
  await open(page);
  const title = `Uncertain graph ${randomUUID()}`;
  let posts = 0, nonce = "", saved: GraphViewResponse | undefined;
  await page.route(collection, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts += 1; nonce = route.request().postDataJSON().request_id;
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    saved = await response.json();
    await route.abort("failed");
  });
  await dialog(page).getByLabel("视图名称", { exact: true }).fill(title);
  await dialog(page).getByRole("button", { name: "保存为新视图", exact: true }).click();
  await expect(dialog(page).getByRole("alert")).toContainText("服务器可能已保存");
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(dialog(page).getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  await dialog(page).getByRole("button", { name: "关闭保存视图", exact: true }).click();
  await expect(page.getByText("原操作尚未核对，本页仍保留查回入口；请核对后再离开。", { exact: true })).toBeVisible();
  page.once("dialog", prompt => prompt.dismiss());
  await page.getByRole("link", { name: "目录视图", exact: true }).click();
  await expect(page).toHaveURL(/\/theories\/graph\?/);
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(title);
  await page.getByRole("button", { name: "核对未确认的保存", exact: true }).click();
  const lookup = page.waitForResponse(response => response.url().includes(`/graph-views/by-request/?request_id=${nonce}`));
  await dialog(page).getByRole("button", { name: "核对原操作", exact: true }).click();
  expect((await (await lookup).json()).record.id).toBe(saved!.record!.id);
  await expect(dialog(page).getByRole("status")).toContainText("视图已保存到当前账户");
  expect(posts).toBe(1);
  await expect(dialog(page).locator("li").filter({ hasText: title })).toHaveCount(1);
});

test("an absent receipt retries the original nonce and body after a request never reached the server", async ({ page }) => {
  await open(page);
  const payloads: Array<{ request_id: string; data: GraphViewData }> = [];
  await page.route(collection, async route => {
    if (route.request().method() !== "POST") return route.continue();
    payloads.push(route.request().postDataJSON());
    if (payloads.length === 1) return route.abort("failed");
    return route.continue();
  });
  await dialog(page).getByLabel("视图名称", { exact: true }).fill(`Unsent graph ${randomUUID()}`);
  await dialog(page).getByRole("button", { name: "保存为新视图", exact: true }).click();
  await expect(dialog(page).getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  const lookup = page.waitForResponse(response => response.url().includes(`/graph-views/by-request/?request_id=${payloads[0].request_id}`));
  await dialog(page).getByRole("button", { name: "核对原操作", exact: true }).click();
  expect((await lookup).status()).toBe(404);
  await expect(dialog(page).getByRole("status")).toContainText("视图已保存到当前账户");
  expect(payloads).toHaveLength(2);
  expect(payloads[1]).toEqual(payloads[0]);
});

test("successful writes remain uncertain when post-response owner verification fails", async ({ page }) => {
  await open(page);
  let failVerification = false, posts = 0;
  await page.route(`${api}/auth/me/`, async route => {
    if (failVerification) { failVerification = false; return route.abort("failed"); }
    return route.continue();
  });
  await page.route(collection, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    failVerification = true;
    await route.fulfill({ response });
  });
  await dialog(page).getByLabel("视图名称", { exact: true }).fill(`Owner verification ${randomUUID()}`);
  await dialog(page).getByRole("button", { name: "保存为新视图", exact: true }).click();
  await expect(dialog(page).getByRole("alert")).toContainText("服务器可能已保存");
  await dialog(page).getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(dialog(page).getByRole("status")).toContainText("视图已保存到当前账户");
  expect(posts).toBe(1);
});

test("a lost delete returns a tombstone and an old creation nonce cannot recreate it", async ({ page }) => {
  const title = `Deleted graph ${randomUUID()}`, saved = await create(page, title);
  await open(page);
  let deletes = 0;
  await page.route(`${collection}${saved.record.id}/**`, async route => {
    if (route.request().method() !== "DELETE") return route.continue();
    deletes += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    expect(await response.json()).toMatchObject({ record: null, receipt: { deleted: true, applied_revision: 2 } });
    await route.abort("failed");
  });
  const row = dialog(page).locator("li").filter({ hasText: title });
  await row.getByRole("button", { name: "删除", exact: true }).click();
  await row.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog(page).getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  await dialog(page).getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(dialog(page).getByRole("status")).toContainText("原视图已删除，不会通过重试恢复");
  await expect(row).toHaveCount(0);
  expect(deletes).toBe(1);
  const replay = await page.request.post(collection, { headers: await headers(page), data: saved.body });
  expect(replay.status()).toBe(201);
  expect(await replay.json()).toMatchObject({ record: null, receipt: { request_id: saved.body.request_id, deleted: true } });
  expect((await page.request.get(`${collection}${saved.record.id}/`, { headers: await headers(page) })).status()).toBe(404);
});

test("an expired protected write is not replayed through refresh", async ({ page }) => {
  await open(page);
  const anonymous = await request.newContext();
  let posts = 0, refreshes = 0, nonce = "";
  page.on("request", outgoing => { if (outgoing.url() === `${api}/auth/token/refresh/`) refreshes += 1; });
  await page.route(collection, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts += 1; nonce = route.request().postDataJSON().request_id;
    // Let the actual API reject a request whose cookie has expired after the
    // successful owner preflight, without manufacturing an error body.
    const response = await anonymous.post(collection, { headers: { "X-Reader-Owner": route.request().headers()["x-reader-owner"] }, data: route.request().postDataJSON() });
    expect(response.status()).toBe(401);
    await route.fulfill({ response });
  });
  try {
    await dialog(page).getByLabel("视图名称", { exact: true }).fill(`Expired graph ${randomUUID()}`);
    await dialog(page).getByRole("button", { name: "保存为新视图", exact: true }).click();
    await expect(dialog(page).getByRole("alert")).toBeVisible();
    await expect(dialog(page).getByRole("button", { name: "保存为新视图", exact: true })).toBeEnabled();
    await expect(dialog(page).getByRole("button", { name: "核对原操作", exact: true })).toHaveCount(0);
    expect(posts).toBe(1); expect(refreshes).toBe(0);
    expect((await page.request.get(`${collection}by-request/?request_id=${nonce}`, { headers: await headers(page) })).status()).toBe(404);
  } finally { await anonymous.dispose(); }
});

test("switching the actual cookie owner discards a late private response and cannot restore another owner's saved link", async ({ page }) => {
  await open(page);
  const title = `Owner A private graph ${randomUUID()}`;
  let saved: GraphViewResponse | undefined, posts = 0;
  let committed!: () => void, release!: () => void;
  const committedResponse = new Promise<void>(resolve => { committed = resolve; });
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route(collection, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    saved = await response.json(); committed();
    await delayed;
    // The client intentionally aborts this request when the session changes.
    await route.fulfill({ response }).catch(() => undefined);
  });
  await dialog(page).getByLabel("视图名称", { exact: true }).fill(title);
  await dialog(page).getByRole("button", { name: "保存为新视图", exact: true }).click();
  await committedResponse;
  try {
    const nextOwner = await switchAccount(page);
    expect(nextOwner).not.toBe(saved!.owner_id);
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "保存当前视图", exact: true })).toBeEnabled();
  } finally { release(); }
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "核对未确认的保存", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  const ownHeaders = await headers(page);
  expect((await page.request.get(`${collection}by-request/?request_id=${saved!.receipt!.request_id}`, { headers: ownHeaders })).status()).toBe(404);
  expect((await page.request.get(`${collection}${saved!.record!.id}/`, { headers: ownHeaders })).status()).toBe(404);
  await page.goto(`/theories/graph?saved_view=${saved!.record!.id}`);
  await expect(dialog(page).getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "当前中心节点", exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`saved_view=${saved!.record!.id}`));
});
