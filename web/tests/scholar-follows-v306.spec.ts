import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { SourceCommand, SourceCommandResult, SourceFollowsPage } from "../lib/api/source-follows.client";

// Authored only. Use seed_scholars in the disposable acceptance environment.
// Fault injection drops real API responses and never fabricates private records.
const api = "http://127.0.0.1:8105/api", follows = `${api}/reading/source-follows/`;
const profile = "61000000-0000-4000-8000-000000000001", href = "/scholars/e2e-scholar-public";
const password = "E2E-Local-Only-305-passphrase";

async function headers(page: Page) {
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.status()).toBe(200);
  const owner = String((await response.json()).id);
  const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken");
  expect(csrf).toBeTruthy();
  return { "X-Reader-Owner": owner, "X-CSRFToken": csrf!.value };
}

async function existing(page: Page) {
  const response = await page.request.get(`${follows}?scholar_profile_id=${profile}`, { headers: await headers(page) });
  expect(response.status()).toBe(200);
  return await response.json() as SourceFollowsPage;
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Private fixtures require the disposable environment.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("reader-v305@example.test");
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
  for (const row of (await existing(page)).results) {
    const removed = await page.request.delete(`${follows}${row.id}/`, { headers: await headers(page),
      data: { request_id: randomUUID(), expected_revision: row.revision } });
    expect(removed.status(), await removed.text()).toBe(200);
  }
  await page.goto(href);
  await expect(page.getByRole("button", { name: "关注学者", exact: true })).toBeEnabled();
});

async function loseCommittedResponse(page: Page) {
  const commands: SourceCommand[] = [];
  await page.route(follows, async route => {
    if (route.request().method() !== "POST") return route.continue();
    commands.push(route.request().postDataJSON());
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await page.getByRole("button", { name: "关注学者", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  return commands;
}

test("lost committed response survives same-owner verification and prevents accidental departure", async ({ page }) => {
  const commands = await loseCommittedResponse(page);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator('a[href="/scholars"]').first().click();
  await expect(page).toHaveURL(new RegExp(`${href}$`));
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(commands[0].request_id);
  const receipt = page.waitForResponse(response => response.url().includes(`/source-follows/by-request/?request_id=${commands[0].request_id}`));
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  const recovered: SourceCommandResult = await (await receipt).json();
  expect(recovered.record?.scholar_profile_id).toBe(profile);
  await expect(page.getByRole("button", { name: "已关注 · 取消关注", exact: true })).toBeEnabled();
  expect(commands).toHaveLength(1);
  expect((await existing(page)).count).toBe(1);
});

test("a failed owner verification after a successful write keeps the same receipt", async ({ page }) => {
  let failVerification = false, writes = 0;
  await page.route(`${api}/auth/me/`, async route => {
    if (failVerification) { failVerification = false; return route.abort("failed"); }
    return route.continue();
  });
  await page.route(follows, async route => {
    if (route.request().method() !== "POST") return route.continue();
    writes += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    failVerification = true;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "关注学者", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  await expect(page.getByRole("button", { name: "已关注 · 取消关注", exact: true })).toBeEnabled();
  expect(writes).toBe(1);
});

test("deletion during an unknown result returns a tombstone without recreating the follow", async ({ page }) => {
  const commands = await loseCommittedResponse(page);
  const row = (await existing(page)).results[0];
  const removed = await page.request.delete(`${follows}${row.id}/`, { headers: await headers(page),
    data: { request_id: randomUUID(), expected_revision: row.revision } });
  expect(removed.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toBeEnabled();
  const receipt = page.waitForResponse(response => response.url().includes(`/source-follows/by-request/?request_id=${commands[0].request_id}`));
  await page.getByRole("button", { name: "核对原操作", exact: true }).click();
  const recovered: SourceCommandResult = await (await receipt).json();
  expect(recovered.record).toBeNull(); expect(recovered.receipt.deleted).toBe(true);
  await expect(page.getByRole("button", { name: "关注学者", exact: true })).toBeEnabled();
  expect(commands).toHaveLength(1); expect((await existing(page)).count).toBe(0);
});

test("an actual account change cannot read or replay the former owner's request", async ({ page }) => {
  const commands = await loseCommittedResponse(page), previous = await headers(page);
  const login = await page.request.post(`${api}/auth/login/`, { headers: previous,
    data: { email: "administrator-v305@example.test", password } });
  expect(login.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对原操作", exact: true })).toHaveCount(0);
  const current = await headers(page);
  expect(current["X-Reader-Owner"]).not.toBe(previous["X-Reader-Owner"]);
  expect((await page.request.get(`${follows}by-request/?request_id=${commands[0].request_id}`, { headers: current })).status()).toBe(404);
  expect((await page.request.get(`${follows}by-request/?request_id=${commands[0].request_id}`, { headers: { ...current, "X-Reader-Owner": previous["X-Reader-Owner"] } })).status()).toBe(403);
  expect(commands).toHaveLength(1);
});
