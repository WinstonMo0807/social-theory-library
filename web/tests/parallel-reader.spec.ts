import { randomUUID } from "node:crypto";
import { expect, test, type Page, type Response } from "@playwright/test";
import type {
  ParallelCandidates, ParallelRecord, ParallelSegment, ParallelSegments, ParallelVersion, ParallelVersions,
} from "../lib/api/parallel-reader.client";
import type { EvidenceReference } from "../lib/api/research.client";

// Final acceptance only: the isolated runner must call seed_parallel_reader().
// Every business response comes from the real API and its extracted synthetic
// PDFs. Missing extraction/fixtures fail explicitly; no business response mocks.
const api = "http://127.0.0.1:8105/api";
const ids = {
  left: "41300000-0000-4000-8000-000000000103",
  right: "41300000-0000-4000-8000-000000000203",
  scan: "41300000-0000-4000-8000-000000000303",
};
type Sources = {
  left: ParallelVersion; right: ParallelVersion; scan: ParallelVersion;
  leftPage: ParallelSegments; rightPage: ParallelSegments;
  leftTail: ParallelSegments; rightTail: ParallelSegments;
};
const column = (page: Page, side: "left" | "right") => page.locator(`section[aria-label="${side === "left" ? "左" : "右"}侧正文"]`);
const segmentButton = (page: Page, side: "left" | "right", segment: ParallelSegment) =>
  column(page, side).locator(`button[data-segment="${segment.id}"]`);
const taskWrite = (response: Response) =>
  response.request().method() === "POST" && new URL(response.url()).pathname === "/api/reading/parallel-tasks/";
const compact = (segment: ParallelSegment): EvidenceReference => ({
  asset_id: segment.reference.asset_id, document_revision_id: segment.reference.document_revision_id,
  evidence_span_id: segment.reference.evidence_span_id, pdf_page: segment.reference.pdf_page,
  content_hash: segment.reference.content_hash,
  ...(segment.reference.selection_start === undefined ? {} : {
    selection_start: segment.reference.selection_start, selection_end: segment.reference.selection_end,
  }),
});

async function transport(page: Page) {
  // Runtime transport selection only. SSR must point to this same fixture API.
  await page.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL, "Use the disposable loopback acceptance configuration.").toBeTruthy();
  expect(new URL(baseURL!).origin).toBe("http://127.0.0.1:3105");
  await transport(page);
});

async function login(page: Page, role = "reader") {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "reader" ? /\/account$/ : /\/admin$/);
  const response = await page.request.get(`${api}/auth/me/`);
  expect(response.ok()).toBeTruthy();
  const me = await response.json() as { id: number };
  expect(me.id).toBeTruthy();
  return me.id;
}

async function readSegments(page: Page, version: ParallelVersion, physicalPage: number, offset = 0) {
  const query = new URLSearchParams({
    asset_id: version.asset_id!, document_revision_id: version.document_revision_id!,
    page: String(physicalPage), offset: String(offset),
  });
  const response = await page.request.get(`${api}/catalog/parallel/segments/?${query}`);
  expect(response.status(), `Real extracted segments are required for ${version.asset_id}, page ${physicalPage}.`).toBe(200);
  return await response.json() as ParallelSegments;
}

async function sources(page: Page): Promise<Sources> {
  const response = await page.request.get(`${api}/catalog/parallel/versions/?asset_id=${ids.left}`);
  expect(response.status(), "Missing parallel PDF fixture: call seed_parallel_reader() in the isolated E2E runner.").toBe(200);
  const versions = (await response.json() as ParallelVersions).versions;
  const byAsset = (asset: string) => {
    const version = versions.find(row => row.asset_id === asset);
    expect(version, `Required fixture asset ${asset} was not published by the real source chain.`).toBeDefined();
    return version!;
  };
  const left = byAsset(ids.left), right = byAsset(ids.right), scan = byAsset(ids.scan);
  expect([left.state, right.state, right.relation, scan.state]).toEqual(["available", "available", "translation", "metadata_only"]);
  expect(scan.document_revision_id).toBeNull();
  const [leftPage, rightPage, leftTail, rightTail] = await Promise.all([
    readSegments(page, left, 1), readSegments(page, right, 2),
    readSegments(page, left, 1, 20), readSegments(page, right, 2, 20),
  ]);
  expect([leftPage.segments.length, rightPage.segments.length, leftTail.segments.length, rightTail.segments.length],
    "Actual extraction must produce 25 original / 27 translated located paragraphs; do not replace missing paragraphs with mock data.")
    .toEqual([20, 20, 5, 7]);
  expect(leftPage.next_offset).toBe(20);
  expect(rightPage.next_offset).toBe(20);
  return { left, right, scan, leftPage, rightPage, leftTail, rightTail };
}

async function openPair(page: Page, fixture: Sources) {
  await page.goto(`/reader/${ids.left}?mode=parallel`);
  await expect(page.getByRole("heading", { name: "原文与译本并读", exact: true })).toBeVisible();
  await page.getByLabel("右侧版本", { exact: true }).selectOption(fixture.right.edition_id);
  if ((page.viewportSize()?.width || 1280) <= 760) {
    await page.getByRole("navigation", { name: "并读内容", exact: true }).getByRole("button", { name: "阅读方式", exact: true }).click();
  }
  await column(page, "right").getByLabel("右侧PDF页码", { exact: true }).fill("2");
  await column(page, "right").getByRole("button", { name: "前往", exact: true }).click();
  await expect(column(page, "left").locator("button[data-segment]")).toHaveCount(20);
  await expect(column(page, "right").locator("button[data-segment]")).toHaveCount(20);
}

async function manual(page: Page) {
  if ((page.viewportSize()?.width || 1280) <= 760) {
    await page.getByRole("navigation", { name: "并读内容", exact: true }).getByRole("button", { name: "对齐与笔记", exact: true }).click();
  }
  await page.getByRole("button", { name: "手动调整对齐", exact: true }).click();
  await expect(page.getByRole("heading", { name: "手动对齐与私人保存", exact: true })).toBeVisible();
}

async function saveManual(page: Page, note: string) {
  await page.getByLabel("添加笔记（可选）", { exact: true }).fill(note);
  const pending = page.waitForResponse(taskWrite);
  await page.locator(".parallel-manual-summary").getByRole("button", { name: "保存到我的对齐", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(201);
  const record = await response.json() as ParallelRecord;
  await expect(page.getByText("已保存到我的对齐，仅自己可见。", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`alignment=${record.id}`));
  return record;
}

test("visitors read the exact versions, page through real paragraphs and keep scan-only access truthful", async ({ page }) => {
  const fixture = await sources(page);
  await openPair(page, fixture);
  await expect(segmentButton(page, "left", fixture.leftPage.segments[0]).locator("span").last()).toHaveText(fixture.leftPage.segments[0].text);
  await expect(segmentButton(page, "right", fixture.rightPage.segments[2])).toContainText("PARALLEL RIGHT SEGMENT 01");
  await column(page, "left").getByRole("button", { name: "更多正文", exact: true }).click();
  await expect(column(page, "left").locator("button[data-segment]")).toHaveCount(5);
  await expect(segmentButton(page, "left", fixture.leftTail.segments[1])).toBeVisible();
  await column(page, "left").getByRole("button", { name: "上一组正文", exact: true }).click();
  await expect(column(page, "left").locator("button[data-segment]")).toHaveCount(20);
  await page.locator(".parallel-save-bar").getByRole("button", { name: "保存到我的对齐", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "登录后保存私人对齐" })).toBeVisible();
  await page.getByRole("button", { name: "关闭登录提示", exact: true }).click();
  await page.getByLabel("右侧版本", { exact: true }).selectOption(fixture.scan.edition_id);
  await expect(column(page, "right").getByText("此页尚无可用文字", { exact: true })).toBeVisible();
  await expect(column(page, "right").locator("button[data-segment]")).toHaveCount(0);
  await expect(column(page, "right").getByRole("link", { name: "在新标签页打开右侧PDF原文" }))
    .toHaveAttribute("href", `/reader/${ids.scan}?page=1`);
  await expect(page.getByRole("button", { name: "手动调整对齐", exact: true })).toBeDisabled();
});

test("manual confirmation saves differing pages and restores the exact segment beyond the first twenty", async ({ page, browser, baseURL }) => {
  const owner = await login(page), fixture = await sources(page);
  await openPair(page, fixture);
  await column(page, "left").getByRole("button", { name: "更多正文", exact: true }).click();
  await column(page, "right").getByRole("button", { name: "更多正文", exact: true }).click();
  const left = fixture.leftTail.segments[1], right = fixture.rightTail.segments[3];
  await segmentButton(page, "left", left).click();
  await segmentButton(page, "right", right).click();
  await manual(page);
  const record = await saveManual(page, "Synthetic private alignment note; never public.");
  expect(record.data.alignments[0]).toMatchObject({
    status: "confirmed", left: { asset_id: ids.left, pdf_page: 1, evidence_span_id: left.reference.evidence_span_id },
    right: { asset_id: ids.right, pdf_page: 2, evidence_span_id: right.reference.evidence_span_id },
  });
  expect(record.data.positions).toMatchObject({ left_page: 1, right_page: 2, left_segment_id: left.id, right_segment_id: right.id });
  await page.reload();
  await expect(segmentButton(page, "left", left)).toHaveAttribute("aria-pressed", "true");
  await expect(segmentButton(page, "right", right)).toHaveAttribute("aria-pressed", "true");
  await expect(column(page, "left").getByRole("button", { name: "上一组正文", exact: true })).toBeEnabled();
  await column(page, "left").getByRole("button", { name: "上一组正文", exact: true }).click();
  await expect(column(page, "left").locator("button[data-segment]")).toHaveCount(20);
  await column(page, "left").getByRole("button", { name: "更多正文", exact: true }).click();
  await expect(column(page, "left").locator("button[data-segment]")).toHaveCount(5);

  const own = await page.request.get(`${api}/reading/parallel-tasks/${record.id}/`, { headers: { "X-Reader-Owner": String(owner) } });
  expect(own.status()).toBe(200);
  const outsider = await browser.newContext({ baseURL });
  try {
    const other = await outsider.newPage();
    await transport(other);
    const anonymous = await other.request.get(`${api}/reading/parallel-tasks/${record.id}/`, { headers: { "X-Reader-Owner": String(owner) } });
    expect([401, 403]).toContain(anonymous.status());
    const otherOwner = await login(other, "administrator");
    expect(otherOwner).not.toBe(owner);
    const foreign = await other.request.get(`${api}/reading/parallel-tasks/${record.id}/`, { headers: { "X-Reader-Owner": String(otherOwner) } });
    expect(foreign.status()).toBe(404);
    const forgedOwner = await other.request.get(`${api}/reading/parallel-tasks/${record.id}/`, { headers: { "X-Reader-Owner": String(owner) } });
    expect(forgedOwner.status()).toBe(403);
  } finally {
    await outsider.close();
  }
});

test("restoring a real saved subspan retains its exact quote instead of selecting the page-window first row", async ({ page, baseURL }) => {
  const owner = await login(page), fixture = await sources(page);
  const left = fixture.leftTail.segments[2], right = fixture.rightTail.segments[4];
  const sliced = { ...compact(right), selection_start: 8, selection_end: 64 };
  expect(right.reference.evidence_span_id, "The fixture must contain extractor-created evidence spans.").toBeTruthy();
  const focus = `${right.reference.evidence_span_id}:range:8:64`;
  const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken")?.value;
  expect(csrf, "The real fixture login must establish CSRF protection.").toBeTruthy();
  const response = await page.request.post(`${api}/reading/parallel-tasks/`, {
    headers: { "X-Reader-Owner": String(owner), "X-CSRFToken": csrf!, Origin: baseURL!, Referer: `${baseURL}/reader/${ids.left}?mode=parallel` },
    data: {
      request_id: randomUUID(), data: {
        left_asset_id: ids.left, right_asset_id: ids.right,
        left_document_revision_id: fixture.left.document_revision_id, right_document_revision_id: fixture.right.document_revision_id,
        positions: { left_page: 1, right_page: 2, left_segment_id: left.id, right_segment_id: focus },
        sync_scroll: false, alignments: [{ id: randomUUID(), left: compact(left), right: sliced, status: "confirmed", note: "Synthetic exact subspan" }], terms: [],
      },
    },
  });
  expect(response.status()).toBe(201);
  const record = await response.json() as ParallelRecord;
  expect(record.data.alignments[0].right?.quote).toBe(right.text.slice(8, 64));
  await page.goto(`/reader/${ids.left}?mode=parallel&alignment=${record.id}`);
  await expect(segmentButton(page, "right", right)).toHaveAttribute("aria-pressed", "true");
  await expect(segmentButton(page, "right", fixture.rightTail.segments[0])).toHaveAttribute("aria-pressed", "false");
  await page.locator(".parallel-alignment-list").getByRole("button", { name: "调整", exact: true }).click();
  const saved = page.waitForResponse(value => value.request().method() === "PATCH" && new URL(value.url()).pathname === `/api/reading/parallel-tasks/${record.id}/`);
  await page.locator(".parallel-manual-summary").getByRole("button", { name: "保存到我的对齐", exact: true }).click();
  const updated = await saved;
  expect(updated.status()).toBe(200);
  const result = await updated.json() as ParallelRecord;
  expect(result.data.alignments[0].right).toMatchObject({ selection_start: 8, selection_end: 64, quote: right.text.slice(8, 64) });
});

test("an accepted save with a dropped response is recovered by nonce without a duplicate task", async ({ page }) => {
  await login(page);
  const fixture = await sources(page);
  await openPair(page, fixture);
  await manual(page);
  const accepted: ParallelRecord[] = [];
  await page.route(`${api}/reading/parallel-tasks/`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    // Execute the real write, then lose only its transport response.
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    accepted.push(await response.json() as ParallelRecord);
    await route.abort("failed");
  });
  await page.getByLabel("添加笔记（可选）", { exact: true }).fill("Synthetic accepted write with lost response");
  await page.locator(".parallel-manual-summary").getByRole("button", { name: "保存到我的对齐", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原保存结果", exact: true })).toBeVisible();
  await expect(page.locator(".parallel-save-bar").getByRole("button", { name: "保存到我的对齐", exact: true })).toBeDisabled();
  expect(accepted).toHaveLength(1);
  const recovery = page.waitForResponse(response => new URL(response.url()).pathname === "/api/reading/parallel-tasks/by-request/");
  await page.getByRole("button", { name: "核对原保存结果", exact: true }).click();
  const response = await recovery;
  expect(response.status()).toBe(200);
  expect((await response.json() as ParallelRecord).id).toBe(accepted[0].id);
  await expect(page.getByText("已保存到我的对齐，仅自己可见。", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`alignment=${accepted[0].id}`));
  expect(accepted).toHaveLength(1);
});

test("a restored task can swap and then change versions without keeping its initial recovery lock", async ({ page }) => {
  await login(page);
  const fixture = await sources(page);
  await openPair(page, fixture);
  await manual(page);
  const original = await saveManual(page, "Synthetic original task before version changes");
  await page.goto(`/reader/${ids.left}?mode=parallel&alignment=${original.id}`);
  await expect(page.getByRole("button", { name: "交换左右版本", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "交换左右版本", exact: true }).click();
  await expect(page.getByLabel("左侧版本", { exact: true })).toHaveValue(fixture.right.edition_id);
  await expect(page.getByLabel("右侧版本", { exact: true })).toHaveValue(fixture.left.edition_id);
  const saveButton = page.locator(".parallel-save-bar").getByRole("button", { name: "保存到我的对齐", exact: true });
  await expect(saveButton).toBeEnabled();
  const saving = page.waitForResponse(taskWrite);
  await saveButton.click();
  const response = await saving;
  expect(response.status()).toBe(201);
  const reversed = await response.json() as ParallelRecord;
  expect(reversed.id).not.toBe(original.id);
  expect(reversed.data).toMatchObject({ left_asset_id: ids.right, right_asset_id: ids.left });
  await expect(page.getByText("已保存到我的对齐，仅自己可见。", { exact: true })).toBeVisible();
  await page.getByLabel("右侧版本", { exact: true }).selectOption(fixture.scan.edition_id);
  await expect(page.getByLabel("右侧版本", { exact: true })).toBeEnabled();
  await expect(column(page, "right").getByText("此页尚无可用文字", { exact: true })).toBeVisible();
  await page.getByLabel("右侧版本", { exact: true }).selectOption(fixture.left.edition_id);
  await expect(page.getByRole("button", { name: "手动调整对齐", exact: true })).toBeEnabled();
  await expect(saveButton).toBeEnabled();
  await expect(page.getByText("正在恢复私人对齐和两侧原文位置…", { exact: true })).toHaveCount(0);
});

test("a recovered create receipt with a later real revision offers the existing task instead of creating a duplicate", async ({ page, baseURL }) => {
  const owner = await login(page), fixture = await sources(page);
  await openPair(page, fixture);
  await manual(page);
  const accepted: ParallelRecord[] = [];
  const bodies: Array<{ request_id: string; data: ParallelRecord["data"] }> = [];
  await page.route(`${api}/reading/parallel-tasks/`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON() as typeof bodies[number]);
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    accepted.push(await response.json() as ParallelRecord);
    await route.abort("failed");
  });
  await page.getByLabel("添加笔记（可选）", { exact: true }).fill("Synthetic original request waiting for a receipt");
  await page.locator(".parallel-manual-summary").getByRole("button", { name: "保存到我的对齐", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对原保存结果", exact: true })).toBeVisible();
  expect(accepted).toHaveLength(1);
  const original = accepted[0], changedNote = `Synthetic second-session change ${randomUUID()}`;
  const csrf = (await page.context().cookies(api)).find(cookie => cookie.name === "csrftoken")?.value;
  expect(csrf).toBeTruthy();
  // A second real command changes the already-created task before the first
  // browser learns its id. This tests durable receipts against actual revisioning.
  const amended = await page.request.patch(`${api}/reading/parallel-tasks/${original.id}/`, {
    headers: { "X-Reader-Owner": String(owner), "X-CSRFToken": csrf!, Origin: baseURL!, Referer: `${baseURL}/reader/${ids.left}?mode=parallel` },
    data: {
      request_id: randomUUID(), expected_revision: original.revision,
      data: { ...bodies[0].data, alignments: bodies[0].data.alignments.map(row => ({ ...row, note: changedNote })) },
    },
  });
  expect(amended.status()).toBe(200);
  const latest = await amended.json() as ParallelRecord;
  expect(latest.revision).toBe(original.revision + 1);
  const recovery = page.waitForResponse(response => new URL(response.url()).pathname === "/api/reading/parallel-tasks/by-request/");
  await page.getByRole("button", { name: "核对原保存结果", exact: true }).click();
  const receipt = await recovery;
  expect(receipt.status()).toBe(200);
  expect(await receipt.json()).toMatchObject({
    id: original.id, applied_revision: original.revision, revision: latest.revision,
  });
  const readLatest = page.getByRole("button", { name: "读取最新任务", exact: true });
  await expect(readLatest).toBeVisible();
  await expect(page.locator(".parallel-save-bar").getByRole("button", { name: "保存到我的对齐", exact: true })).toBeDisabled();
  expect(accepted).toHaveLength(1);
  page.once("dialog", dialog => dialog.accept());
  await readLatest.click();
  await expect(page).toHaveURL(new RegExp(`alignment=${original.id}`));
  await expect(page.locator(".parallel-save-bar")).toContainText(`修订 ${latest.revision}`);
  await page.locator(".parallel-alignment-list").getByRole("button", { name: "调整", exact: true }).click();
  await expect(page.getByLabel("添加笔记（可选）", { exact: true })).toHaveValue(changedNote);
  expect(accepted).toHaveLength(1);
});

test("mobile tabs retain both selected positions; candidates never save automatically and no-correspondence is explicit", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const fixture = await sources(page);
  await openPair(page, fixture);
  const left = fixture.leftPage.segments[1], right = fixture.rightPage.segments[3];
  await segmentButton(page, "left", left).click();
  await segmentButton(page, "right", right).click();
  await manual(page);
  const tabs = page.getByRole("navigation", { name: "对齐内容", exact: true });
  await expect(column(page, "left")).toBeVisible();
  await tabs.getByRole("button", { name: "候选", exact: true }).click();
  await expect(column(page, "left")).toBeHidden();
  await expect(page.locator(".parallel-candidates")).toBeVisible();
  const saves: string[] = [];
  page.on("request", request => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/reading/parallel-tasks/") saves.push(request.postData() || "");
  });
  const candidateResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/catalog/parallel/candidates/");
  await page.getByRole("button", { name: "查找候选", exact: true }).click();
  const candidateResult = await candidateResponse;
  expect(candidateResult.status()).toBe(200);
  const result = await candidateResult.json() as ParallelCandidates;
  expect(["ready", "partial", "empty", "unavailable"]).toContain(result.state);
  expect(result.candidates.length).toBeLessThanOrEqual(6);
  expect(result.candidates.every(candidate => candidate.status === "pending" && candidate.reference.asset_id === ids.right)).toBe(true);
  // The disposable runner has no search index/model requirement. A genuine
  // unavailable result must stay visible; this does not claim retrieval quality.
  if (result.notice) await expect(page.locator(".parallel-candidates")).toContainText(result.notice);
  expect(saves).toHaveLength(0);
  await page.locator(".parallel-candidate-cards").getByRole("button", { name: /无对应段/ }).click();
  await tabs.getByRole("button", { name: "笔记", exact: true }).click();
  await expect(page.locator(".parallel-candidates")).toBeHidden();
  await page.getByLabel("添加笔记（可选）", { exact: true }).fill("Synthetic explicit no-correspondence decision");
  await tabs.getByRole("button", { name: "对照", exact: true }).click();
  await expect(segmentButton(page, "left", left)).toHaveAttribute("aria-pressed", "true");
  await expect(segmentButton(page, "right", right)).toHaveAttribute("aria-pressed", "true");
  const record = await saveManual(page, "Synthetic explicit no-correspondence decision");
  expect(record.data.alignments[0]).toMatchObject({
    status: "no_match", right: null, left: { evidence_span_id: left.reference.evidence_span_id },
  });
  await page.getByRole("navigation", { name: "并读内容", exact: true }).getByRole("button", { name: "对齐与笔记", exact: true }).click();
  await expect(page.locator(".parallel-alignment-list")).toContainText("无对应段");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("a public contribution declares its scope, omits private notes and stays absent until separate review and publication", async ({ page, browser, baseURL }) => {
  await login(page);
  const fixture = await sources(page);
  await openPair(page, fixture);
  await manual(page);
  const privateNote = `Private fixture note ${randomUUID()}`;
  const record = await saveManual(page, privateNote);
  await page.getByRole("button", { name: "提交公共校准", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "提交为公共校准" });
  await expect(dialog.getByLabel("仅书目级，不显示具体段落", { exact: true })).toBeChecked();
  await dialog.getByLabel("显示所选段落，需说明依据", { exact: true }).check();
  await dialog.getByLabel("选择已保存的对齐", { exact: true }).selectOption(record.data.alignments[0].id);
  const basis = `Synthetic independently submitted basis ${randomUUID()}`;
  await dialog.getByLabel("校准依据", { exact: true }).fill(basis);
  const submission = page.waitForResponse(response => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/reading/parallel-calibrations/");
  await dialog.getByRole("button", { name: "确认提交审核", exact: true }).click();
  const response = await submission;
  expect(response.status()).toBe(201);
  const contribution = await response.json() as { id: string; status: string; scope: string; data: { basis: string } };
  expect(contribution).toMatchObject({ status: "submitted", scope: "passages", data: { basis } });
  expect(JSON.stringify(contribution)).not.toContain(privateNote);
  await expect(dialog).toBeHidden();
  const visitor = await browser.newContext({ baseURL });
  try {
    const publicDetail = await visitor.request.get(`${api}/reading/parallel-calibrations/public/${contribution.id}/`);
    expect(publicDetail.status()).toBe(404);
    const publicList = await visitor.request.get(`${api}/reading/parallel-calibrations/public/?left_asset=${ids.left}`);
    expect(publicList.status()).toBe(200);
    expect(await publicList.text()).not.toContain(basis);
    expect(await publicList.text()).not.toContain(privateNote);
  } finally {
    await visitor.close();
  }
});
