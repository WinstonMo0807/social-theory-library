import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { PathFollowResponse, PublicReadingPath } from "../lib/api/reading-paths.types";
import type { PlanData, ResearchRecord } from "../lib/api/research.client";

// Run only at unified acceptance with seed_reading_paths in the disposable
// cataloging environment. Faults lose real responses, never fabricate records.
const api = "http://127.0.0.1:8105/api";
const follows = `${api}/reading/path-follows/`;
const plans = `${api}/reading/reading-plans/`;
const publicPath = `${api}/theory-system/reading-paths/e2e-reading-path/`;
const chapterOne = "58000000-0000-4000-8000-000000000021";
const chapterTwo = "58000000-0000-4000-8000-000000000022";
const password = "E2E-Local-Only-305-passphrase";

async function headers(page: Page) {
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.status()).toBe(200);
  const owner = String((await response.json()).id);
  const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken");
  expect(csrf).toBeTruthy();
  return { "X-Reader-Owner": owner, "X-CSRFToken": csrf!.value };
}

async function createCopy(page: Page) {
  const publicResponse = await page.request.get(publicPath);
  expect(publicResponse.status()).toBe(200);
  const path: PublicReadingPath = await publicResponse.json();
  const ownerHeaders = await headers(page);
  const response = await page.request.post(follows, { headers: ownerHeaders, data: {
    request_id: randomUUID(), path_id: path.id, expected_source_revision: path.revision.token, bookmarked: false,
  } });
  expect(response.status(), await response.text()).toBe(201);
  const followed: PathFollowResponse = await response.json();
  expect(followed.record).not.toBeNull();
  const copied = await page.request.post(`${follows}${followed.record!.id}/copy-plan/`, {
    headers: ownerHeaders, data: { request_id: randomUUID(), expected_revision: followed.record!.revision, title: `Private path ${randomUUID()}` },
  });
  expect(copied.status(), await copied.text()).toBe(201);
  const result: PathFollowResponse = await copied.json();
  expect(result.record?.type).toBe("personal_plan");
  return result.record!;
}

async function readPlan(page: Page, id: string) {
  const response = await page.request.get(`${plans}${id}/`, { headers: await headers(page) });
  expect(response.status(), await response.text()).toBe(200);
  return await response.json() as ResearchRecord<PlanData>;
}

async function editSecondChapter(page: Page, id: string) {
  await page.goto(`/account/plans/${id}`);
  await expect(page.getByText("来自公共阅读路径的私人副本。", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /更多操作$/ }).nth(1).click();
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "保存材料设置", exact: true }) });
  await expect(dialog).toBeVisible();
  return dialog;
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

test("a copy keeps two chapters from one work and saves minutes by the exact item id", async ({ page }) => {
  const copy = await createCopy(page), before = await readPlan(page, copy.id);
  const first = before.data.items.find(item => item.id === chapterOne)!;
  const second = before.data.items.find(item => item.id === chapterTwo)!;
  expect(first.work_id).toBe(second.work_id);
  const dialog = await editSecondChapter(page, copy.id);
  await dialog.getByLabel("本人估计时长（分钟）", { exact: true }).fill("17");
  const saved = page.waitForResponse(response => response.url() === `${plans}${copy.id}/` && response.request().method() === "PATCH");
  await dialog.getByRole("button", { name: "保存材料设置", exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toMatchObject({ item_id: chapterTwo, item_minutes: 17, expected_revision: copy.revision });
  expect(response.request().postDataJSON()).not.toHaveProperty("item_estimates");
  expect(response.request().headers()["x-reader-owner"]).toBe((await headers(page))["X-Reader-Owner"]);
  await expect(dialog).toHaveCount(0);
  const after = await readPlan(page, copy.id);
  expect(after.data.items.map(item => item.id)).toEqual(before.data.items.map(item => item.id));
  expect(after.data.items.find(item => item.id === chapterOne)?.estimated_minutes).toBeNull();
  expect(after.data.items.find(item => item.id === chapterTwo)?.estimated_minutes).toBe(17);
  await page.getByRole("link", { name: "返回来源路径并核对版本", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`copy=${copy.id}`));
  await expect(page.getByText("当前私人计划副本", { exact: true })).toBeVisible();
});

test("a committed save with a lost response keeps the nonce through same-owner verification", async ({ page }) => {
  const copy = await createCopy(page), dialog = await editSecondChapter(page, copy.id);
  const note = `Owner-only note ${randomUUID()}`;
  let patches = 0, nonce = "";
  await page.route(`${plans}${copy.id}/`, async route => {
    if (route.request().method() !== "PATCH") return route.continue();
    patches += 1; nonce = route.request().postDataJSON().request_id;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await dialog.getByLabel("相关问题与阅读笔记", { exact: true }).fill(note);
  await dialog.getByRole("button", { name: "保存材料设置", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toBeEnabled();
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toBeEnabled();
  page.once("dialog", prompt => prompt.dismiss());
  await page.getByRole("link", { name: "阅读计划", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/account/plans/${copy.id}$`));
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(note);
  const lookup = page.waitForResponse(response => response.url().includes(`/path-follows/by-request/?request_id=${nonce}`));
  await page.getByRole("button", { name: "核对上次保存结果", exact: true }).click();
  expect((await (await lookup).json()).record.id).toBe(copy.id);
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toHaveCount(0);
  expect(patches).toBe(1);
  expect((await readPlan(page, copy.id)).data.items.find(item => item.id === chapterTwo)?.note).toBe(note);
});

test("a successful save remains recoverable if post-response owner verification fails", async ({ page }) => {
  const copy = await createCopy(page), dialog = await editSecondChapter(page, copy.id);
  let failVerification = false, patches = 0;
  await page.route(`${api}/auth/me/`, async route => {
    if (failVerification) { failVerification = false; return route.abort("failed"); }
    return route.continue();
  });
  await page.route(`${plans}${copy.id}/`, async route => {
    if (route.request().method() !== "PATCH") return route.continue();
    patches += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    failVerification = true;
    await route.fulfill({ response });
  });
  await dialog.getByLabel("本人估计时长（分钟）", { exact: true }).fill("23");
  await dialog.getByRole("button", { name: "保存材料设置", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "核对上次保存结果", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toHaveCount(0);
  expect(patches).toBe(1);
  expect((await readPlan(page, copy.id)).data.items.find(item => item.id === chapterTwo)?.estimated_minutes).toBe(23);
});

test("an actual owner change drops the old command and another owner cannot open the copy or receipt", async ({ page }) => {
  const copy = await createCopy(page), dialog = await editSecondChapter(page, copy.id);
  const note = `Only first owner ${randomUUID()}`;
  let nonce = "";
  await page.route(`${plans}${copy.id}/`, async route => {
    if (route.request().method() !== "PATCH") return route.continue();
    nonce = route.request().postDataJSON().request_id;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await dialog.getByLabel("相关问题与阅读笔记", { exact: true }).fill(note);
  await dialog.getByRole("button", { name: "保存材料设置", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toBeEnabled();
  const previousOwner = (await headers(page))["X-Reader-Owner"];
  const login = await page.request.post(`${api}/auth/login/`, { headers: await headers(page), data: { email: "administrator-v305@example.test", password } });
  expect(login.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("button", { name: "核对上次保存结果", exact: true })).toHaveCount(0);
  await expect(page.getByText(note, { exact: true })).toHaveCount(0);
  const currentHeaders = await headers(page);
  expect(currentHeaders["X-Reader-Owner"]).not.toBe(previousOwner);
  expect((await page.request.get(`${follows}${copy.id}/`, { headers: currentHeaders })).status()).toBe(404);
  expect((await page.request.get(`${follows}by-request/?request_id=${nonce}`, { headers: currentHeaders })).status()).toBe(404);
  await page.goto(`/theories/reading-paths/e2e-reading-path?copy=${copy.id}`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("当前私人计划副本", { exact: true })).toHaveCount(0);
});
