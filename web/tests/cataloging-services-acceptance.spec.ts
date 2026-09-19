import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const api = "http://127.0.0.1:8106/api";
type Session = { id: string; work_id: string; edition_id: string; upload_item_id: string | null; source_type: string };

async function login(page: Page, role: 'editor' | 'reader' | 'owner') {
  await page.route("**/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  const ready = await page.request.get(`${api}/ready/`);
  expect(ready.status()).toBe(200);
  expect((await ready.json()).version).toBe("3.0.6");
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v306@example.test`);
  await page.locator('input[name="password"]').fill("Isolated-v306-Only-Test-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === 'reader' ? /\/account$/ : /\/admin$/);
}

test.beforeEach(async ({ page, baseURL }) => {
  expect(baseURL).toBe("http://127.0.0.1:3106");
  await login(page, 'editor');
});

async function section(page: Page, key: string) {
  const row = page.locator(`#workflow-section-${key}`);
  const heading = row.locator('.workflow-section-heading');
  if (await heading.getAttribute('aria-expanded') !== 'true') await heading.click();
  await expect(row.locator('.workflow-section-content')).toBeVisible();
  return row;
}

async function confirmSection(page: Page, key: string) {
  const row = await section(page, key);
  const saved = page.waitForResponse(response => response.url().endsWith("/edits/") && response.request().method() === "POST" && response.request().postDataJSON().confirm_sections.includes(key));
  await row.getByRole('button', { name: '确认本节内容', exact: true }).click();
  const result = await saved;
  expect(result.status(), await result.text()).toBe(200);
}

async function createManualReport(page: Page, title: string): Promise<Session> {
  await page.goto('/admin/cataloging/new');
  await page.getByLabel('作品题名', { exact: true }).fill(title);
  await page.getByRole('combobox', { name: '文献类型', exact: true }).selectOption('report');
  const created = page.waitForResponse(response => response.url().endsWith('/cataloging-sessions/') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '创建草稿并开始编目', exact: true }).click();
  const result = await created;
  expect(result.status(), await result.text()).toBe(201);
  const session: Session = await result.json();
  expect(session.source_type).toBe('manual');
  expect(session.upload_item_id).toBeNull();
  await expect(page.getByRole('heading', { name: title, exact: true, level: 1 })).toBeVisible();
  await completeReportForm(page, title);
  return session;
}

async function completeReportForm(page: Page, title: string) {
  const work = await section(page, 'work');
  await work.getByRole('textbox', { name: '作品题名', exact: true }).fill(title);
  await work.getByRole('combobox', { name: '文献类型', exact: true }).selectOption('report');
  await confirmSection(page, 'work');
  const bibliography = await section(page, 'bibliography');
  await bibliography.getByRole('textbox', { name: '报告机构', exact: true }).fill('隔离演练研究机构');
  await bibliography.getByRole('spinbutton', { name: '本版本出版年份', exact: true }).fill('2026');
  await confirmSection(page, 'bibliography');
  const contributors = await section(page, 'contributors');
  await contributors.getByRole('button', { name: '智能查找', exact: true }).first().click();
  await page.getByLabel('新学者名称', { exact: true }).fill(`报告作者 ${title}`);
  await page.getByRole('button', { name: '创建学者并关联', exact: true }).click();
  await expect(page.getByText('已新建馆内草稿对象并关联当前作品。', { exact: true })).toBeVisible();
  await confirmSection(page, 'contributors');
}

async function publishReport(page: Page, session: Session, title: string, info: TestInfo, verifyLayout = false) {
  const workspaceUrl = `${api}/catalog/admin/library/works/${session.work_id}/?edition=${session.edition_id}`;
  const previous = await (await page.request.get(workspaceUrl)).json();
  const previousRevision = previous.publication.active_revision_id;
  const publication = await section(page, 'publication');
  const preflightResponse = page.waitForResponse(response => response.url().endsWith(`/editions/${session.edition_id}/publication/prepare/`));
  await publication.getByRole('button', { name: '发布前检查', exact: true }).click();
  const preparedResponse = await preflightResponse;
  expect(preparedResponse.status()).toBe(200);
  const prepared = await preparedResponse.json();
  await info.attach('publication-preflight', { body: JSON.stringify(prepared, null, 2), contentType: 'application/json' });
  expect(prepared.blocking).toEqual([]);
  await expect(publication.getByText('检查已完成，可以发布。请核对下方内容变化，再点击发布。', { exact: true })).toBeVisible();
  // The diff belongs to the same section as the confirmation button, not
  // above all editor sections where navigation would scroll it out of view.
  await expect(publication.getByRole('region', { name: '发布内容差异' })).toBeVisible();
  const optional = publication.locator('.workflow-optional-checks');
  await expect(optional).not.toHaveAttribute('open', '');
  await optional.locator('summary').focus();
  await page.keyboard.press('Enter');
  for (const warning of prepared.warnings) await expect(optional.getByText(warning, { exact: true })).toBeVisible();
  await optional.locator('summary').click();
  if (verifyLayout) {
    for (const width of [360, 390, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      const checkArea = publication.locator('.workflow-preflight-groups');
      expect(await checkArea.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length)).toBe(1);
      const publishButton = publication.getByRole('button', { name: '发布作品', exact: true });
      // Resizing can leave an already-focused button outside the viewport;
      // focus() alone does not scroll that same element a second time.
      await publishButton.scrollIntoViewIfNeeded();
      await publishButton.focus();
      await expect.poll(() => publishButton.evaluate(element => {
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return box.x >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight
          && Boolean(top && (element.contains(top) || top.contains(element)));
      })).toBe(true);
      await expect(publishButton).toBeFocused();
      await publishButton.click({ trial: true });
      await page.screenshot({ path: info.outputPath(`publication-actions-${width}.png`) });
      const showAll = publication.getByRole('checkbox', { name: '显示未变化字段', exact: true });
      await showAll.scrollIntoViewIfNeeded();
      await showAll.focus();
      await page.screenshot({ path: info.outputPath(`publication-diff-${width}.png`) });
    }
  }
  await page.screenshot({ path: info.outputPath('before-explicit-publication.png') });
  const publicationResponse = page.waitForResponse(response => response.request().method() === 'POST' && (
    response.url().includes(`/library/works/${session.work_id}/publication/`)
    || Boolean(session.upload_item_id && response.url().endsWith(`/items/${session.upload_item_id}/publish/`))
  ));
  await publication.getByRole('button', { name: previousRevision ? '发布当前更新' : '发布作品', exact: true }).click();
  if (prepared.warnings?.length) await page.getByRole('dialog').getByRole('button', { name: '确认发布', exact: true }).click();
  const accepted = await publicationResponse;
  // The application may navigate as soon as the command succeeds. The final
  // reader result below is reread independently, not inferred from this 200.
  if (accepted.status() !== 200) throw new Error(`${accepted.status()} ${await accepted.text()}`);
  await info.attach('publication-command-accepted', { body: JSON.stringify({ status: accepted.status(), url: accepted.url() }), contentType: 'application/json' });
  let workspace: { context: { public_url: string; edition_id: string }; publication: { active_revision_id: string | null }; data: unknown } | undefined;
  await expect.poll(async () => {
    const result = await page.request.get(workspaceUrl);
    expect(result.status()).toBe(200);
    workspace = await result.json();
    return Boolean(workspace?.context.public_url && workspace.publication.active_revision_id && workspace.publication.active_revision_id !== previousRevision);
  }, { timeout: 150_000, intervals: [1000, 2000, 5000] }).toBe(true);
  expect(workspace?.context.edition_id).toBe(session.edition_id);
  const publicPath = workspace!.context.public_url;
  const publicResponse = await page.request.get(`${api}/catalog${publicPath}/`);
  expect(publicResponse.status(), await publicResponse.text()).toBe(200);
  const publicWork = await publicResponse.json();
  expect(publicWork.title).toBe(title);
  await info.attach('actual-public-work', { body: JSON.stringify(publicWork, null, 2), contentType: 'application/json' });
  await page.goto(publicPath);
  await expect(page.getByRole('heading', { name: title, exact: true }).first()).toBeVisible();
  await page.screenshot({ path: info.outputPath('actual-public-page.png'), fullPage: true });
  return publicWork;
}

async function syntheticPdf(label: string, replacement = false) {
  const original = await readFile(resolve('..', 'output', 'verification', 'v306', replacement ? 'services-replacement.pdf' : 'services-original.pdf'));
  // A PDF comment after the final EOF gives each synthetic upload its own hash,
  // without changing the original test pages or using real collection files.
  return { name: `${label}.pdf`, mimeType: 'application/pdf', buffer: Buffer.concat([original, Buffer.from(`\n% isolated acceptance ${label}\n`)]) };
}

test('A06 editor uploads a PDF, reviews it and publishes through the real worker without an upload-ID detour', async ({ page }, info) => {
  const title = `服务演练上传报告 ${Date.now()}`;
  await page.goto('/admin/uploads');
  await page.locator('section[aria-label="拖入 PDF 和配套元数据"] input[type=file]').setInputFiles(await syntheticPdf(title));
  const uploaded = page.waitForResponse(response => response.url().endsWith('/ingestion/uploads/r2/init/') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '开始上传', exact: true }).click();
  const response = await uploaded;
  expect(response.ok(), await response.text()).toBe(true);
  const receipt = await response.json();
  const itemId = receipt.upload_session_id;
  expect(itemId).toBeTruthy();
  await info.attach('storage-test-boundary', { body: 'Real multipart HTTP, TLS, S3 object bytes, import worker and NAS file processing; isolated MinIO substitutes for the external Cloudflare R2 provider. No production storage credentials or objects.', contentType: 'text/plain' });
  await expect(page.getByRole('heading', { name: '批次已接收', exact: true })).toBeVisible();
  // The actual result card must lead to this upload, not an arbitrary work.
  const continueLink = page.getByRole('link', { name: '继续馆藏工作', exact: true });
  await expect(continueLink).toHaveAttribute('href', `/admin/intake/${itemId}#bibliography`, { timeout: 150_000 });
  await continueLink.click();
  const workspace = await (await page.request.get(`${api}/catalog/admin/intake/${itemId}/`)).json();
  const session: Session = { id: workspace.context.session_id, work_id: workspace.context.work_id, edition_id: workspace.context.edition_id, upload_item_id: itemId, source_type: 'upload' };
  expect(session.work_id).toBeTruthy();
  expect(session.edition_id).toBeTruthy();
  await expect.poll(async () => {
    const current = await (await page.request.get(`${api}/catalog/admin/intake/${itemId}/`)).json();
    return current.data.file.validation;
  }, { timeout: 120_000, intervals: [1000, 2000, 5000] }).toBe('valid');
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  await completeReportForm(page, title);
  const reviewedWorkspace = await (await page.request.get(`${api}/catalog/admin/intake/${itemId}/`)).json();
  session.id = reviewedWorkspace.context.session_id;
  expect(session.id).toBeTruthy();
  await expect((await section(page, 'file')).getByRole('button', { name: '确认本节内容', exact: true })).toHaveCount(0);
  await info.attach('real-upload-processing', { body: JSON.stringify(await (await page.request.get(`${api}/ingestion/items/${itemId}/`)).json(), null, 2), contentType: 'application/json' });
  const published = await publishReport(page, session, title, info);
  const assetId = published.edition.readable_asset.id;
  expect(published.edition.id).toBe(session.edition_id);
  const range = await page.request.get(`${api}/distribution/assets/${assetId}/file/`, { headers: { Range: 'bytes=0-31' } });
  expect(range.status()).toBe(206);
  expect((await range.body()).subarray(0, 5).toString()).toBe('%PDF-');
  await page.goto(`/reader/${assetId}`);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
  await page.screenshot({ path: info.outputPath('real-upload-reader.png') });
  const returnTo = '/admin/review?source=upload&q=服务演练&page=2';
  const compatibilityContext = new URLSearchParams({ edition: session.edition_id, session: session.id, return_to: returnTo, q: title });
  for (const [route, target] of [['review', 'bibliography'], ['publication', 'publication']]) {
    await page.goto(`/admin/${route}/${itemId}?${compatibilityContext}`);
    await expect(page).toHaveURL(url => url.pathname === `/admin/intake/${itemId}`
      && url.searchParams.get('edition') === session.edition_id
      && url.searchParams.get('session') === session.id
      && url.searchParams.get('return_to') === returnTo
      && url.searchParams.get('q') === title && url.hash === `#${target}`);
    await expect(page.getByRole('heading', { name: title, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByRole('combobox', { name: '当前出版版本', exact: true })).toHaveValue(session.edition_id);
  }
});

test('A05 editor publishes a manual no-PDF report through real PG Redis Worker and public reads', async ({ page }, info) => {
  const title = `服务演练纯书目 ${Date.now()}`;
  const session = await createManualReport(page, title);
  const published = await publishReport(page, session, title, info, true);
  expect(published.edition.readable_asset).toBeNull();
  const saved = await (await page.request.get(`${api}/catalog/admin/cataloging-sessions/${session.id}/?workspace=0`)).json();
  expect(saved.session.source_type).toBe('manual');
  expect(saved.session.upload_item_id).toBeNull();
  await info.attach('manual-source-after-publication', { body: JSON.stringify(saved, null, 2), contentType: 'application/json' });
});

test('A09 A08 manual report gains a PDF on the same edition and replacement preserves private page identities', async ({ page, browser }, info) => {
  test.setTimeout(420_000);
  const title = `服务演练版本文件 ${Date.now()}`;
  const session = await createManualReport(page, title);
  const before = await publishReport(page, session, title, info);
  expect(before.edition.readable_asset).toBeNull();
  const maintenance = `/admin/library/works/${session.work_id}?edition=${session.edition_id}#file`;
  const workspaceUrl = `${api}/catalog/admin/library/works/${session.work_id}/?edition=${session.edition_id}`;
  await page.goto(maintenance);
  const files = await section(page, 'file');
  page.once('dialog', async dialog => { expect(dialog.message()).toContain(title); await dialog.accept(); });
  const supplementResponse = page.waitForResponse(response => response.url().endsWith(`/editions/${session.edition_id}/files/`) && response.request().method() === 'POST');
  await files.getByLabel('为当前版本补充 PDF', { exact: true }).setInputFiles(await syntheticPdf(title));
  const supplement = await supplementResponse;
  expect(supplement.status(), await supplement.text()).toBe(202);
  const receipt = await supplement.json();
  expect(receipt.work_id).toBe(session.work_id);
  expect(receipt.edition_id).toBe(session.edition_id);
  await expect.poll(async () => {
    const current = await (await page.request.get(workspaceUrl)).json();
    expect(current.context.edition_id).toBe(session.edition_id);
    return current.data.file.validation;
  }, { timeout: 150_000, intervals: [1000, 2000, 5000] }).toBe('valid');
  const latestContext = await (await page.request.get(workspaceUrl)).json();
  const stillBeforeResponse = await page.request.get(`${api}/catalog${latestContext.context.public_url}/`);
  expect(stillBeforeResponse.status(), await stillBeforeResponse.text()).toBe(200);
  const stillBefore = await stillBeforeResponse.json();
  expect(stillBefore.edition.readable_asset).toBeNull();
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  await expect((await section(page, 'file')).getByRole('button', { name: '确认本节内容', exact: true })).toHaveCount(0);
  const published = await publishReport(page, session, title, info);
  const oldAsset = published.edition.readable_asset.id;
  expect(published.edition.id).toBe(session.edition_id);
  const initialWorkspace = await (await page.request.get(workspaceUrl)).json();
  const oldOriginal = initialWorkspace.data.file.original_asset_id;
  const source = await (await page.request.get(`${api}/catalog/admin/cataloging-sessions/${session.id}/?workspace=0`)).json();
  expect(source.session.source_type).toBe('manual');
  expect(source.session.upload_item_id).toBeNull();

  const readerContext = await browser.newContext({ baseURL: 'http://127.0.0.1:3106' });
  const reader = await readerContext.newPage();
  try {
    await login(reader, 'reader');
    await reader.goto(`/reader/${oldAsset}?page=1`);
    await expect(reader.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
    const bookmarked = reader.waitForResponse(response => response.url().endsWith('/reading/bookmarks/') && response.request().method() === 'POST');
    await reader.getByRole('button', { name: '收藏当前页书签', exact: true }).click();
    const bookmarkResponse = await bookmarked;
    expect(bookmarkResponse.status()).toBe(201);
    const bookmark = await bookmarkResponse.json();
    const span = reader.locator('.pdf-page-shell').first().locator('.pdf-native-text-layer span').first();
    await expect(span).toBeVisible();
    await span.evaluate(element => { const range = document.createRange(); range.selectNodeContents(element); const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range); });
    await reader.locator('.reader-document').dispatchEvent('mouseup');
    await reader.getByRole('toolbar', { name: '所选文字操作' }).getByRole('button', { name: '笔记', exact: true }).click();
    const composer = reader.locator('.annotation-composer');
    const privateText = `只属于演练读者的笔记 ${title}`;
    await composer.getByRole('textbox', { name: '笔记内容' }).fill(privateText);
    const annotated = reader.waitForResponse(response => response.url().endsWith('/reading/annotations/') && response.request().method() === 'POST');
    await composer.getByRole('button', { name: '保存笔记', exact: true }).click();
    const noteResponse = await annotated;
    expect(noteResponse.status()).toBe(201);
    const note = await noteResponse.json();
    expect(note.page).toBe(bookmark.page);
    const progressSaved = reader.waitForResponse(response => response.url().endsWith('/reading/progress/') && response.request().method() === 'POST' && response.request().postDataJSON()?.current_page === 2);
    await reader.getByRole('textbox', { name: '页码', exact: true }).fill('2');
    await reader.getByRole('textbox', { name: '页码', exact: true }).press('Enter');
    const progressResponse = await progressSaved;
    expect(progressResponse.status()).toBe(201);
    const progress = await progressResponse.json();

    await page.goto(maintenance);
    const replacementFiles = await section(page, 'file');
    const oldRange = await reader.request.get(`${api}/distribution/assets/${oldAsset}/file/`, { headers: { Range: 'bytes=0-31' } });
    expect(oldRange.status()).toBe(206);
    page.once('dialog', async dialog => { expect(dialog.message()).toContain(title); await dialog.accept(); });
    const replacementResponse = page.waitForResponse(response => response.url().endsWith(`/editions/${session.edition_id}/files/`) && response.request().method() === 'POST');
    await replacementFiles.getByLabel('替换当前版本阅读文件', { exact: true }).setInputFiles(await syntheticPdf(`${title} replacement`, true));
    const replacement = await replacementResponse;
    expect(replacement.status(), await replacement.text()).toBe(202);
    const replacementReceipt = await replacement.json();
    expect(replacementReceipt.edition_id).toBe(session.edition_id);
    let newAsset = '';
    const processingTimeline: unknown[] = [];
    try {
    await expect.poll(async () => {
      const current = await (await page.request.get(workspaceUrl)).json();
      newAsset = current.data.file.current_reader_asset_id || '';
      processingTimeline.push({ at: new Date().toISOString(), task: current.data.file.status, validation: current.data.file.validation, reader: newAsset, publication: current.publication.public_state });
      if (newAsset === oldAsset) {
        const stable = await reader.request.get(`${api}/distribution/assets/${oldAsset}/file/`, { headers: { Range: 'bytes=0-31' } });
        if (stable.status() === 404) {
          // These are separate HTTP reads. The formal pointer may switch
          // between them; strict current-reader URLs then retire the old URL.
          // A 404 is acceptable only after a fresh read proves that switch.
          const switched = await (await page.request.get(workspaceUrl)).json();
          newAsset = switched.data.file.current_reader_asset_id || '';
          expect(newAsset).toBeTruthy();
          expect(newAsset).not.toBe(oldAsset);
          processingTimeline.push({ at: new Date().toISOString(), oldRange: 404, confirmedNewReader: newAsset });
        } else {
          expect(stable.status()).toBe(206);
          expect((await stable.body()).subarray(0, 5).toString()).toBe('%PDF-');
        }
      }
      return Boolean(newAsset && newAsset !== oldAsset);
    // The real single-worker service also runs minute-based recovery. Record
    // that wait and continuously prove old reading, never infer activation
    // from an accepted request or mark unfinished work as passed.
    }, { timeout: 240_000, intervals: [1000, 2000, 5000] }).toBe(true);
    } finally {
    await info.attach('file-processing-timeline', { body: JSON.stringify(processingTimeline, null, 2), contentType: 'application/json' });
    }
    await expect(replacementFiles.getByText(/阅读文件 · 读者正在使用/)).toBeVisible({ timeout: 20_000 });
    await expect(replacementFiles.getByRole('status')).toHaveCount(0, { timeout: 20_000 });
    const finalWorkspace = await (await page.request.get(workspaceUrl)).json();
    expect(finalWorkspace.data.file.file_history.some((row: { id: string }) => row.id === oldAsset)).toBe(true);
    expect(finalWorkspace.data.file.file_history.some((row: { id: string }) => row.id === oldOriginal)).toBe(true);
    const noteAfter = await reader.request.get(`${api}/reading/annotations/${note.id}/`);
    expect(noteAfter.status()).toBe(200);
    expect(await noteAfter.json()).toMatchObject({ id: note.id, asset: oldAsset, page: note.page, body_text: privateText });
    const bookmarkAfter = await reader.request.get(`${api}/reading/bookmarks/${bookmark.id}/`);
    expect(bookmarkAfter.status()).toBe(200);
    expect(await bookmarkAfter.json()).toMatchObject({ asset: oldAsset, page: bookmark.page });
    const progressAfter = await reader.request.get(`${api}/reading/progress/${progress.id}/`);
    expect(progressAfter.status()).toBe(200);
    expect(await progressAfter.json()).toMatchObject({ asset: oldAsset, current_page: 2 });
    expect((await page.request.get(`${api}/reading/annotations/${note.id}/`)).status()).toBe(404);
    const range = await reader.request.get(`${api}/distribution/assets/${newAsset}/file/`, { headers: { Range: 'bytes=0-31' } });
    expect(range.status()).toBe(206);
    expect((await range.body()).subarray(0, 5).toString()).toBe('%PDF-');
    const publicManifest = await (await page.request.get(`${api}/catalog/assets/${newAsset}/manifest/`)).json();
    expect(JSON.stringify(publicManifest)).not.toContain(privateText);
    await reader.goto(`/reader/${newAsset}?page=1`);
    await expect(reader.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
    await reader.screenshot({ path: info.outputPath('replacement-real-reader.png') });
    await info.attach('stable-file-and-private-identities', { body: JSON.stringify({ work: session.work_id, edition: session.edition_id, oldAsset, newAsset, oldOriginal, page: note.page, note: note.id, bookmark: bookmark.id, progress: progress.id, fileHistory: finalWorkspace.data.file.file_history }, null, 2), contentType: 'application/json' });
  } finally { await readerContext.close(); }
});

test('A30 owner creates a real database and original-file backup; editor cannot read its sensitive records', async ({ page, browser }, info) => {
  const denied = await page.request.get(`${api}/distribution/backups/`);
  expect(denied.status()).toBe(403);
  expect(await denied.text()).not.toContain('/acceptance/');
  const ownerContext = await browser.newContext({ baseURL: 'http://127.0.0.1:3106' });
  const owner = await ownerContext.newPage();
  try {
    await login(owner, 'owner');
    await owner.goto('/admin/settings#backups');
    const panel = owner.locator('.backup-settings');
    await expect(panel).toBeVisible();
    await panel.getByLabel('容器内备份目录', { exact: true }).fill('/acceptance/media/backups/v306-services');
    await panel.getByLabel('归档内再包含原始 PDF', { exact: true }).check();
    const submitted = owner.waitForResponse(response => response.url().endsWith('/distribution/backups/') && response.request().method() === 'POST');
    await panel.getByRole('button', { name: '立即创建备份', exact: true }).click();
    const response = await submitted;
    expect(response.status(), await response.text()).toBe(201);
    const receipt = await response.json();
    let completed: typeof receipt;
    await expect.poll(async () => {
      const result = await owner.request.get(`${api}/distribution/backups/`);
      expect(result.status()).toBe(200);
      const jobs = await result.json();
      completed = jobs.results.find((job: { id: string }) => job.id === receipt.id);
      if (completed?.status === 'failed') throw new Error(completed.error_message);
      return completed?.status;
    }, { timeout: 120_000, intervals: [1000, 2000, 5000] }).toBe('completed');
    expect(completed!.checksum).toMatch(/^[a-f0-9]{64}$/);
    expect(completed!.include_originals).toBe(true);
    expect(completed!.manifest.included_original_count).toBeGreaterThan(0);
    expect(completed!.archive_path).toMatch(/^\/acceptance\/media\/backups\/v306-services\//);
    await panel.getByRole('button', { name: '刷新', exact: true }).click();
    await expect(panel.getByText(completed!.archive_path, { exact: true })).toBeVisible();
    await owner.screenshot({ path: info.outputPath('real-backup-receipt.png'), fullPage: true });
    // This receipt proves creation only. A separate guarded management command
    // restores this exact archive into a new, empty disposable PostgreSQL DB.
    await info.attach('actual-backup-receipt', { body: JSON.stringify(completed!, null, 2), contentType: 'application/json' });
  } finally { await ownerContext.close(); }
});
