import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { SourceCommand, SourceFollowsPage } from "../lib/api/source-follows.client";
import type { TopicSaveCommand, TopicSaveState } from "../lib/api/topic-saves.client";

// Definitions only: seed_topics in the disposable environment. Faults drop real responses.
const api = "http://127.0.0.1:8105/api", href = "/topics/stl4-topic-technology";
const topic = "4da2f1d4-622b-5647-8a5c-ce40ff6fd9ed", password = "E2E-Local-Only-305-passphrase";
const follows = `${api}/reading/source-follows/`, saves = `${api}/reading/saved-topics/`;

async function headers(page: Page) {
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.status()).toBe(200);
  const owner = String((await response.json()).id), csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken");
  expect(csrf).toBeTruthy();
  return { "X-Reader-Owner": owner, "X-CSRFToken": csrf!.value };
}

async function followState(page: Page) {
  const response = await page.request.get(`${follows}?topic_id=${topic}`, { headers: await headers(page) });
  expect(response.status()).toBe(200);
  return await response.json() as SourceFollowsPage;
}

async function saveState(page: Page) {
  const response = await page.request.get(`${saves}state/?topic=${topic}`, { headers: await headers(page) });
  expect(response.status()).toBe(200);
  return await response.json() as TopicSaveState;
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Private actions require disposable fixtures.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("reader-v305@example.test");
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
  for (const row of (await followState(page)).results) {
    expect((await page.request.delete(`${follows}${row.id}/`, { headers: await headers(page), data: { request_id: randomUUID(), expected_revision: row.revision } })).status()).toBe(200);
  }
  const saved = await saveState(page);
  if (saved.saved) expect((await page.request.post(`${saves}command/`, { headers: await headers(page), data: { topic, saved: false, expected_version: saved.version, request_id: randomUUID() } })).status()).toBe(200);
});

async function loseFollowResponse(page: Page) {
  await page.goto(href);
  await expect(page.getByRole("button", { name: "关注主题", exact: true })).toBeEnabled();
  const commands: SourceCommand[] = [];
  await page.route(follows, async route => {
    if (route.request().method() !== "POST") return route.continue();
    commands.push(route.request().postDataJSON());
    expect((await route.fetch()).status()).toBe(200);
    await route.abort("failed");
  });
  await page.getByRole("button", { name: "关注主题", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  return commands;
}

test("topic follow keeps its UUID and nonce across same-owner verification without creating a collection", async ({ page }) => {
  const commands = await loseFollowResponse(page);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator('a[href="/topics"]').first().click();
  await expect(page).toHaveURL(new RegExp(`${href}$`));
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(commands[0].request_id);
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(page.getByRole("button", { name: "已关注 · 取消关注", exact: true })).toBeEnabled();
  expect(commands).toHaveLength(1);
  expect((await followState(page)).results[0].topic_id).toBe(topic);
  expect((await saveState(page)).saved).toBe(false);
});

test("deleted unknown follow returns its tombstone and does not recreate the topic subscription", async ({ page }) => {
  const commands = await loseFollowResponse(page), row = (await followState(page)).results[0];
  expect((await page.request.delete(`${follows}${row.id}/`, { headers: await headers(page), data: { expected_revision: row.revision, request_id: randomUUID() } })).status()).toBe(200);
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(page.getByRole("button", { name: "关注主题", exact: true })).toBeEnabled();
  expect(commands).toHaveLength(1);
  expect((await followState(page)).count).toBe(0);
});

test("changing accounts discards topic follow recovery and rejects the prior owner's receipt", async ({ page }) => {
  const commands = await loseFollowResponse(page), previous = await headers(page);
  expect((await page.request.post(`${api}/auth/login/`, { headers: previous, data: { email: "administrator-v305@example.test", password } })).status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toHaveCount(0);
  const current = await headers(page);
  expect((await page.request.get(`${follows}by-request/?request_id=${commands[0].request_id}`, { headers: current })).status()).toBe(404);
  expect((await page.request.get(`${follows}by-request/?request_id=${commands[0].request_id}`, { headers: { ...current, "X-Reader-Owner": previous["X-Reader-Owner"] } })).status()).toBe(403);
  expect(commands).toHaveLength(1);
});

test("old collection removal keeps the original version through a failed post-write owner check and account remount", async ({ page }) => {
  expect((await page.request.post(`${saves}command/`, { headers: await headers(page), data: { topic, saved: true, expected_version: "0", request_id: randomUUID() } })).status()).toBe(200);
  const original = await saveState(page), writes: TopicSaveCommand[] = [];
  await page.goto("/account");
  await page.getByRole("button", { name: "收藏", exact: true }).click();
  await expect(page.getByRole("button", { name: "已收藏 · 取消收藏", exact: true })).toBeEnabled();
  let failVerification = false;
  await page.route(`${api}/auth/me/`, async route => {
    if (failVerification) { failVerification = false; return route.abort("failed"); }
    return route.continue();
  });
  await page.route(`${saves}command/`, async route => {
    writes.push(route.request().postDataJSON());
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    failVerification = true;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "已收藏 · 取消收藏", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原收藏操作", exact: true })).toBeEnabled();
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原收藏操作", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "核对原收藏操作", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原收藏操作", exact: true })).toHaveCount(0);
  expect(writes).toHaveLength(1);
  expect(writes[0].expected_version).toBe(original.version);
  expect((await saveState(page)).saved).toBe(false);
  expect((await followState(page)).count).toBe(0);
});
