import { expect, test, type Page } from "@playwright/test";
import type { ReaderOcrCommand, ReaderOcrStatus } from "../lib/api/reader-ocr.client";

// Synthetic OCR transport contracts over the existing real, isolated Reader PDF.
// These cases do not claim a live OCR worker, published result, or visual acceptance.
const api = "http://127.0.0.1:8105/api", asset = "30600000-0000-4000-8000-000000000313";
const jobId = "44000000-0000-4000-8000-000000000001", otherId = "44000000-0000-4000-8000-000000000002";
const stamp = "2026-10-20T00:00:00+00:00", path = `/api/distribution/assets/${asset}/ocr-status/`;
const dialogFor = (page: Page) => page.getByRole("dialog", { name: "文字识别与处理状态", exact: true });

test.beforeEach(async ({ page, baseURL }) => {
  expect(new URL(baseURL!).origin, "Only the disposable fixture environment is allowed.").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
});

async function setup(page: Page, role: "anonymous" | "manager" | "reviewer" = "manager", mutate?: (data: ReaderOcrStatus) => void) {
  const manifestResponse = await page.request.get(`${api}/catalog/assets/${asset}/manifest/`);
  expect(manifestResponse.status(), "Run seed_reader_v306() in the isolated runner; do not substitute a fake PDF.").toBe(200);
  const manifest = await manifestResponse.json() as { asset_id: string; edition_id: string; document_revision_id: string | null };
  const accessResponse = await page.request.get(`${api}/distribution/assets/${asset}/access/`);
  expect(accessResponse.status()).toBe(200);
  const access = await accessResponse.json() as { sha256: string };
  const fixture = {
    owner: role === "anonymous" ? null : 777,
    canManage: role === "manager", canView: role !== "anonymous",
    fail: 0, lookupFail: 0, readFail: 0, applyOnFailure: true, refreshes: 0, accesses: 0, documentNavigations: 0,
    commands: [] as ReaderOcrCommand[], ownerHeaders: [] as (string | undefined)[], lookups: [] as string[],
    receipts: new Map<string, NonNullable<ReaderOcrStatus["receipt"]>>(),
    data: {
      asset_id: asset, edition_id: manifest.edition_id, document_revision_id: manifest.document_revision_id,
      source_sha256: access.sha256, owner_id: role === "anonymous" ? null : 777,
      file_page_count: 1001, ocr_status: "running", checked_at: stamp,
      job: { id: jobId, job_version: stamp, status: "running", phase: "recognizing", phase_label: "正在识别文字",
        completed_pages: 12, total_pages: 310, percent: 3.87, phase_elapsed_seconds: 45,
        updated_at: stamp, pause_requested: false, stale: false },
      can_pause: role === "manager", can_resume: false, denied_reason: "", management_url: role === "anonymous" ? null : `/admin/library/assets/${asset}/ocr`,
      processed_content: role === "anonymous"
        ? { state: "awaiting_publication", url: null, label: "已处理内容等待公开", notice: "合成状态：已处理文字尚未公开。" }
        : { state: "admin_preview", url: `/admin/library/assets/${asset}/ocr`, label: "在新标签页核对已处理内容", notice: "合成状态：仅管理预览可用。" },
      receipt: null,
    } as ReaderOcrStatus,
  };
  mutate?.(fixture.data);
  await page.addInitScript(loggedIn => {
    if (loggedIn) localStorage.setItem("library_session_active", "1");
    else localStorage.removeItem("library_session_active");
  }, role !== "anonymous");
  page.on("request", request => {
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) fixture.documentNavigations += 1;
    if (new URL(request.url()).pathname === `/api/distribution/assets/${asset}/access/`) fixture.accesses += 1;
  });
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url());
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body),
      headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3105", "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "Content-Type, X-Reader-Owner, X-CSRFToken", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" } });
    if (request.method() === "OPTIONS" && (url.pathname === path || url.pathname.startsWith("/api/auth/")
      || /^\/api\/reading\/(annotations|bookmarks|progress|history)\/$/.test(url.pathname))) return respond({});
    if (url.pathname === "/api/auth/me/") return fixture.owner === null
      ? respond({ detail: "合成匿名会话" }, 401)
      : respond({ id: fixture.owner, role: "admin", display_name: "OCR synthetic reviewer",
        capabilities: [...(fixture.canView ? ["access_back_office"] : []), ...(fixture.canManage ? ["can_retry_jobs"] : [])], reading_preferences: {} });
    if (url.pathname === "/api/auth/token/refresh/") { fixture.refreshes += 1; return respond({ detail: "合成会话不可刷新" }, 401); }
    // No private fixture records are needed or written by these OCR UI cases.
    if (/^\/api\/reading\/(annotations|bookmarks|progress|history)\/$/.test(url.pathname))
      return respond(request.method() === "GET" ? { count: 0, next: null, previous: null, results: [] } : {});
    if (url.pathname !== path) return route.continue();
    if (request.method() === "POST") {
      const command = request.postDataJSON() as ReaderOcrCommand;
      fixture.commands.push(command); fixture.ownerHeaders.push(request.headers()["x-reader-owner"]);
      if (fixture.fail && fixture.fail < 500 && ![408, 429].includes(fixture.fail)) return respond({ detail: "合成操作已明确拒绝" }, fixture.fail);
      if (!fixture.fail || fixture.applyOnFailure) {
        fixture.receipts.set(command.request_id, { request_id: command.request_id, action: command.action, job_id: command.job_id, applied: true });
        fixture.data.job = { ...fixture.data.job!, status: "paused", job_version: "2026-10-20T00:01:00+00:00" };
        fixture.data.can_pause = false; fixture.data.can_resume = true;
      }
      if (fixture.fail) return respond({ detail: "合成命令响应无法确认" }, fixture.fail);
      return respond({ ...fixture.data, receipt: fixture.receipts.get(command.request_id) });
    }
    const nonce = url.searchParams.get("request_id");
    if (nonce) {
      fixture.lookups.push(nonce); fixture.ownerHeaders.push(request.headers()["x-reader-owner"]);
      if (fixture.lookupFail) return respond({ detail: "合成回执读取权限失效" }, fixture.lookupFail);
      return respond({ ...fixture.data, receipt: fixture.receipts.get(nonce) || null });
    }
    if (fixture.readFail) return respond({ detail: "合成状态暂不可读" }, fixture.readFail);
    return respond({ ...fixture.data, receipt: null });
  });
  await page.goto(`/reader/${asset}?page=2`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".pdf-canvas-stage canvas").first()).toBeVisible({ timeout: 40_000 });
  await page.getByRole("button", { name: "更多阅读工具", exact: true }).click();
  await page.getByRole("dialog", { name: "阅读工具", exact: true }).getByRole("button", { name: "文字识别与处理状态", exact: true }).click();
  const dialog = dialogFor(page);
  await expect(dialog.getByRole("region", { name: "文字识别进度" })).toBeVisible();
  await expect(dialog.getByText(/状态核对于/)).toBeVisible();
  return fixture;
}

test("task progress distinguishes its target pages from the source and reports actual stage time", async ({ page }) => {
  await setup(page);
  const dialog = dialogFor(page);
  await expect(dialog.getByRole("progressbar")).toHaveAttribute("value", "3.87");
  await expect(dialog).toContainText("本次任务已保存 12 / 310 页");
  await expect(dialog).toContainText("整份文件共 1001 页");
  await expect(dialog).toContainText("本阶段已用时（含等待） 00:45");
  await expect(dialog.getByRole("link", { name: "在新标签页核对已处理内容" })).toHaveAttribute("target", "_blank");
});

test("missing metrics and anonymous access do not invent progress or management controls", async ({ page }) => {
  await setup(page, "anonymous", data => {
    data.job = { ...data.job!, completed_pages: null, total_pages: null, percent: null, phase_elapsed_seconds: null };
  });
  const dialog = dialogFor(page);
  await expect(dialog.getByRole("progressbar")).toHaveCount(0);
  await expect(dialog).toContainText("尚无可报告的处理百分比");
  await expect(dialog).toContainText("本次任务尚无可报告的已处理页数");
  await expect(dialog).toContainText("本阶段已用时（含等待） 暂未记录");
  await expect(dialog.getByRole("button", { name: /暂停处理|继续处理/ })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: /处理内容|处理详情/ })).toHaveCount(0);
});

test("backoffice read permission exposes processed preview without granting task controls", async ({ page }) => {
  await setup(page, "reviewer");
  const dialog = dialogFor(page);
  await expect(dialog.getByRole("link", { name: "在新标签页核对已处理内容" })).toHaveAttribute("href", `/admin/library/assets/${asset}/ocr`);
  await expect(dialog.getByRole("link", { name: "查看文字处理详情" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /暂停处理|继续处理/ })).toHaveCount(0);
});

for (const status of [503, 408, 429]) test(`accepted but unknown ${status} looks up the exact receipt without replaying`, async ({ page }) => {
  const fixture = await setup(page); fixture.fail = status;
  const dialog = dialogFor(page), originalSource = { sha: fixture.data.source_sha256, revision: fixture.data.document_revision_id };
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeDisabled();
  await page.keyboard.press("Escape"); await expect(dialog).toBeVisible();
  fixture.fail = 0;
  await dialog.getByRole("button", { name: "查回原处理结果" }).click();
  await expect(dialog).toContainText("暂停请求已确认");
  expect(fixture.commands).toHaveLength(1);
  expect(fixture.lookups).toEqual([fixture.commands[0].request_id]);
  expect(fixture.commands[0]).toMatchObject({ action: "pause", job_id: jobId, job_version: stamp,
    source_sha256: originalSource.sha, document_revision_id: originalSource.revision });
  expect(fixture.ownerHeaders).toEqual(["777", "777"]);
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
});

test("an unconfirmed command retries its exact body only after an empty receipt and unchanged task", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 503; fixture.applyOnFailure = false;
  const dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  fixture.fail = 0;
  await dialog.getByRole("button", { name: "查回原处理结果" }).click();
  await expect(dialog).toContainText("暂停请求已确认");
  expect(fixture.lookups).toEqual([fixture.commands[0].request_id]);
  expect(fixture.commands).toHaveLength(2);
  expect(fixture.commands[1]).toEqual(fixture.commands[0]);
});

test("a changed task cannot receive an old unknown command and releases the close lock", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 503; fixture.applyOnFailure = false;
  const dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  fixture.data.job = { ...fixture.data.job!, id: otherId };
  await dialog.getByRole("button", { name: "查回原处理结果" }).click();
  await expect(dialog).toContainText("未重新发送旧命令");
  expect(fixture.commands).toHaveLength(1);
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "暂停处理", exact: true })).toBeDisabled();
});

test("a new published revision stays visible but cannot be controlled through the old source", async ({ page }) => {
  const fixture = await setup(page);
  const dialog = dialogFor(page);
  fixture.data.document_revision_id = otherId;
  fixture.data.job = { ...fixture.data.job!, status: "succeeded", completed_pages: 310, percent: 100 };
  fixture.data.processed_content = { state: "published", url: `/reader/${asset}?page=1&revision=${otherId}`,
    label: "在新标签页查看已公开内容", notice: "合成新修订已经公开。" };
  await dialog.getByRole("button", { name: "刷新文字识别状态" }).click();
  await expect(dialog).toContainText("当前正式原文修订已有变化");
  await expect(dialog).toContainText("本次识别已完成");
  await expect(dialog.getByRole("link", { name: "在新标签页查看已公开内容" })).toHaveAttribute("href", `/reader/${asset}?page=1&revision=${otherId}`);
  await expect(dialog.getByRole("button", { name: "暂停处理", exact: true })).toBeDisabled();
  expect(fixture.commands).toHaveLength(0);
});

test("receipt permission loss clears management content and permits an explicit abandonment without new commands", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 503;
  const dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  fixture.lookupFail = 403;
  await dialog.getByRole("button", { name: "查回原处理结果" }).click();
  await expect(dialog).toContainText("合成回执读取权限失效");
  await expect(dialog.getByRole("link", { name: /处理内容|处理详情/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeDisabled();
  await dialog.getByRole("button", { name: "放弃本页核对", exact: true }).click();
  const confirmation = dialog.getByRole("group", { name: "确认放弃本页核对" });
  await expect(confirmation).toContainText("原命令可能已执行");
  await confirmation.getByRole("button", { name: "确认放弃核对", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
  expect(fixture.commands).toHaveLength(1);
});

test("an explicit unauthorized POST is not replayed after session refresh", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 401;
  const baseline = fixture.refreshes, dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog).toContainText("合成操作已明确拒绝");
  await expect(dialog.getByRole("link", { name: /处理内容|处理详情/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
  expect(fixture.commands).toHaveLength(1); expect(fixture.refreshes).toBe(baseline);
});

test("status failure and retry preserve the existing PDF and current reading page", async ({ page }) => {
  const fixture = await setup(page), dialog = dialogFor(page);
  const baseline = { accesses: fixture.accesses, navigations: fixture.documentNavigations };
  await page.locator(".pdf-canvas-stage canvas").first().evaluate(element => element.setAttribute("data-ocr-preserved-canvas", "yes"));
  fixture.readFail = 503;
  await dialog.getByRole("button", { name: "刷新文字识别状态" }).click();
  await expect(dialog).toContainText("合成状态暂不可读");
  fixture.readFail = 0;
  await dialog.getByRole("button", { name: "重新读取状态", exact: true }).click();
  await expect(dialog.getByText("合成状态暂不可读", { exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "关闭文字处理状态" }).click();
  await expect(page.getByRole("textbox", { name: "PDF 页码", exact: true })).toHaveValue("2");
  await expect(page.locator('canvas[data-ocr-preserved-canvas="yes"]')).toHaveCount(1);
  expect(fixture.documentNavigations).toBe(baseline.navigations);
  expect(fixture.accesses).toBe(baseline.accesses);
});

test("a withdrawn source hides processing data and leaves a separate current-version lookup", async ({ page }) => {
  const fixture = await setup(page), dialog = dialogFor(page);
  fixture.readFail = 404;
  await dialog.getByRole("button", { name: "刷新文字识别状态" }).click();
  await expect(dialog).toContainText("合成状态暂不可读");
  await expect(dialog.getByRole("progressbar")).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "在新标签页核对已处理内容" })).toHaveCount(0);
  const currentVersion = dialog.getByRole("link", { name: "在文献详情核对当前版本", exact: true });
  await expect(currentVersion).toHaveAttribute("href", /^\/works\/[^/]+$/);
  await expect(currentVersion).toHaveAttribute("target", "_blank");
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
  expect(fixture.commands).toHaveLength(0);
});

test("account changes remove retained recovery and management content", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 503;
  const dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  fixture.owner = null;
  await page.evaluate(() => {
    localStorage.removeItem("library_session_active");
    window.dispatchEvent(new Event("social-theory-library:session-change"));
  });
  await expect(dialog).toBeHidden();
  expect(fixture.commands).toHaveLength(1);
  expect(fixture.lookups).toHaveLength(0);
});

test("same-owner capability loss preserves an unknown command until explicit abandonment", async ({ page }) => {
  const fixture = await setup(page); fixture.fail = 503;
  const dialog = dialogFor(page);
  await dialog.getByRole("button", { name: "暂停处理", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeVisible();
  fixture.canManage = false; fixture.canView = false;
  fixture.data.can_pause = false; fixture.data.can_resume = false; fixture.data.management_url = null;
  fixture.data.processed_content = { state: "awaiting_publication", url: null, label: "等待公开", notice: "" };
  await page.clock.install();
  await page.clock.fastForward(31_000); // Cross the existing session validation throttle.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(dialog).toContainText("当前账户已无任务操作权限");
  await expect(dialog.getByRole("button", { name: "查回原处理结果" })).toBeDisabled();
  await expect(dialog.getByRole("link", { name: /处理内容|处理详情/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeDisabled();
  await dialog.getByRole("button", { name: "放弃本页核对", exact: true }).click();
  await dialog.getByRole("button", { name: "确认放弃核对", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "关闭文字处理状态" })).toBeEnabled();
  expect(fixture.commands).toHaveLength(1);
  expect(fixture.lookups).toHaveLength(0);
});
