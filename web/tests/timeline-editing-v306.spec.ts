import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// Real disposable API only. Business responses are never replaced by fixtures.
const api = "http://127.0.0.1:8105/api";
const leftWork = "41300000-0000-4000-8000-000000000100";
const leftEdition = "41300000-0000-4000-8000-000000000101";
const scanEdition = "41300000-0000-4000-8000-000000000301";
const rightWork = "41300000-0000-4000-8000-000000000200";
const rightEdition = "41300000-0000-4000-8000-000000000201";
const rightAsset = "41300000-0000-4000-8000-000000000203";
const relatedScholar = "56000000-0000-4000-8000-000000000041";

async function login(page: Page, context: BrowserContext, baseURL: string | undefined) {
  expect(baseURL).toBe("http://127.0.0.1:3105");
  await context.route("**/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`,
  }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const csrf = (await context.cookies(api)).find(cookie => cookie.name === "csrftoken")!.value;
  return { "X-CSRFToken": csrf, Origin: baseURL!, Referer: `${baseURL}/admin` };
}

test("PDF57 admin preserves distinct event edition and citation edition through staged publication", async ({ page, context, baseURL }) => {
  const headers = await login(page, context, baseURL);
  const created = await page.request.post(`${api}/catalog/admin/theory-timeline/`, {
    headers, data: {
      title: `TL57版本分离 ${Date.now()}`, event_type: "publication",
      work: leftWork, subject_edition: leftEdition, start_year: 1900, date_precision: "year",
      source: "隔离PDF夹具；这只是版本身份验收，不是学术事件",
      evidence_asset: rightAsset, evidence_work_id: rightWork,
      evidence_edition_id: rightEdition, evidence_page: 2, review_status: "approved",
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const event = await created.json();
  const published = await page.request.post(`${api}${event.editorial_revision.publish_url}`, { headers, data: {} });
  expect(published.status(), await published.text()).toBe(200);
  const publicUrl = `${api}/catalog/theory-system/timeline/${event.id}/`;
  const original = await (await page.request.get(publicUrl)).json();
  expect(original.subject_edition.edition_id).toBe(leftEdition);
  expect(original.evidence_source.edition_id).toBe(rightEdition);

  await page.goto(`/admin/theories/timeline?event=${event.id}`);
  const form = page.locator(".timeline-event-editor");
  await expect(form.getByLabel("事件出版版本", { exact: true })).toHaveValue(leftEdition);
  await form.getByLabel("事件出版版本", { exact: true }).selectOption(scanEdition);
  await form.getByLabel("时间确定程度", { exact: true }).selectOption("range");
  await form.getByLabel("结束年", { exact: true }).fill("1910");
  const savedResponse = page.waitForResponse(response =>
    response.url() === `${api}/catalog/admin/theory-timeline/${event.id}/` && response.request().method() === "PATCH");
  await form.getByRole("button", { name: "保存事件", exact: true }).click();
  const saved = await savedResponse;
  expect(saved.status(), await saved.text()).toBe(202);
  const draft = await saved.json();
  expect(draft.subject_edition).toBe(scanEdition);
  expect(draft.evidence_asset).toBe(rightAsset);
  expect(draft.evidence_file.edition_id).toBe(rightEdition);
  expect(await (await page.request.get(publicUrl)).json()).toEqual(original);
  page.once("dialog", dialog => dialog.accept());
  await form.getByRole("button", { name: "确认发布已保存的修改", exact: true }).click();
  await expect(form).toContainText("事件修改已发布");
  const current = await (await page.request.get(publicUrl)).json();
  expect(current.subject_edition.edition_id).toBe(scanEdition);
  expect(current.date_precision).toBe("range");
  expect(current.end_year).toBe(1910);
  expect(current.evidence_source.edition_id).toBe(rightEdition);

  // Removing the event's work must not erase another work's citation.
  const workPicker = form.locator(".workflow-research-entity-picker").filter({
    has: page.getByText("关联馆藏", { exact: true }),
  });
  await workPicker.getByRole("button", { name: /^移除/ }).click();
  await expect(form.getByLabel("事件出版版本", { exact: true })).toHaveValue("");
  await expect(form.locator('input[name="evidence_page"]')).toHaveValue("2");
  const removedResponse = page.waitForResponse(response =>
    response.url() === `${api}/catalog/admin/theory-timeline/${event.id}/` && response.request().method() === "PATCH");
  await form.getByRole("button", { name: "保存事件", exact: true }).click();
  // A source alone cannot establish the event's subject. The rejected draft stays editable.
  expect((await removedResponse).status()).toBe(400);
  await expect(form.locator('input[name="evidence_page"]')).toHaveValue("2");
});

test("PDF57 related works and scholars stay relations after a title edit, without inferred subjects", async ({ page, context, baseURL }) => {
  const headers = await login(page, context, baseURL);
  const created = await page.request.post(`${api}/catalog/admin/theory-timeline/`, {
    headers, data: {
      title: `TL57关联与主体 ${Date.now()}`, event_type: "concept_proposed", start_year: 0,
      date_precision: "approximate", review_status: "suggested",
      relations: [
        { work: leftWork, relation_type: "context", description: "仅为关联文献" },
        { scholar: relatedScholar, relation_type: "context", description: "仅为关联学者" },
      ],
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const event = await created.json();
  await page.goto(`/admin/theories/timeline?event=${event.id}`);
  const form = page.locator(".timeline-event-editor");
  await expect(form.getByLabel("开始年", { exact: true })).toHaveValue("0");
  await expect(form.getByLabel("事件出版版本", { exact: true })).toHaveValue("");
  await form.getByLabel("事件标题", { exact: true }).fill(`${event.title} 编辑题名`);
  const savedResponse = page.waitForResponse(response =>
    response.url() === `${api}/catalog/admin/theory-timeline/${event.id}/` && response.request().method() === "PATCH");
  await form.getByRole("button", { name: "保存事件", exact: true }).click();
  const saved = await savedResponse;
  expect(saved.status(), await saved.text()).toBe(200);
  const result = await saved.json();
  expect(result.work).toBeNull();
  expect(result.scholar).toBeNull();
  expect(result.subject_edition).toBeNull();
  expect(result.start_year).toBe(0);
  expect(result.relations.map((row: { work: string | null; scholar: string | null; relation_type: string; description: string }) => ({
    work: row.work, scholar: row.scholar, relation_type: row.relation_type, description: row.description,
  }))).toEqual([
    { work: leftWork, scholar: null, relation_type: "context", description: "仅为关联文献" },
    { work: null, scholar: relatedScholar, relation_type: "context", description: "仅为关联学者" },
  ]);
});
