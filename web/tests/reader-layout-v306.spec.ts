import {expect,test,type Page,type Locator} from "@playwright/test";

const asset="30600000-0000-4000-8000-000000000313";
const api="http://127.0.0.1:8105/api";
test.beforeEach(async({page,baseURL})=>{
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  await page.route("**/runtime-config.js",route=>route.fulfill({contentType:"application/javascript",body:`window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`}));
});

async function visibleGeometry(page:Page,selector:string|Locator){
  return (typeof selector === "string" ? page.locator(selector).first() : selector).evaluate(element=>{
    const r=element.getBoundingClientRect();const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,hit:!!top&&(element===top||element.contains(top))};
  });
}

function readerPanel(page: Page, side: "left" | "right", width: number) {
  return width <= (side === "left" ? 760 : 1050)
    ? page.getByRole("dialog", { name: side === "left" ? "目录与查找" : "原文、笔记与引用", exact: true })
    : page.locator(`.reader-${side}`);
}

async function expectModalKeyboard(page: Page, dialog: Locator) {
  const controls = dialog.locator('button:enabled:visible,input:enabled:visible,select:enabled:visible,textarea:enabled:visible,a[href]:visible');
  await controls.first().focus();
  await page.keyboard.press('Shift+Tab');
  await expect(controls.last()).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(controls.first()).toBeFocused();
  await page.locator('.reader-page-controls input').evaluate(element => (element as HTMLElement).focus());
  expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
}

async function selectPageText(page: Page) {
  await expect(page.locator('.reader-page-label')).toContainText('书页');
  const text = page.locator('.pdf-page-shell[data-page-number="1"] .pdf-native-text-layer span').first();
  await expect(text).toBeVisible();
  await text.evaluate(element => {
    const range = document.createRange(); range.selectNodeContents(element);
    const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range);
  });
  await page.locator('.reader-document').dispatchEvent('mouseup');
  const toolbar = page.getByRole('toolbar', { name: '所选文字操作' });
  await expect(toolbar).toBeVisible();
  return toolbar;
}

for(const width of [360,390,768,1280,1440]) test(`Reader real 1001-page PDF controls, sidebars and keyboard at ${width}`,async({page},info)=>{
  await page.setViewportSize({width,height:1000});
  const response=await page.goto(`/reader/${asset}?page=1`);
  expect(response?.status()).toBe(200);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible({timeout:40_000});
  await expect(page.getByRole("textbox",{name:"PDF 页码",exact:true})).toHaveValue("1");
  await expect(page.locator('.reader-page-controls')).toContainText("1001");
  const pageBox=await visibleGeometry(page,'.reader-page-controls');
  const nextBox=await visibleGeometry(page,'.reader-page-controls button:last-child');
  expect(nextBox.right).toBeLessThanOrEqual(pageBox.right+1);
  expect(nextBox.hit).toBe(true);
  const canvas=await visibleGeometry(page,'.pdf-canvas-stage');
  const documentBox=await visibleGeometry(page,'.reader-document');
  expect(canvas.x).toBeGreaterThanOrEqual(documentBox.x);
  expect(canvas.right).toBeLessThanOrEqual(documentBox.right+1);
  expect(canvas.width).toBeGreaterThan(280);
  const toolbar=await visibleGeometry(page,'.reader-toolbar');
  expect(documentBox.y).toBeGreaterThanOrEqual(toolbar.bottom-1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const toolbarControls=await page.locator('.reader-toolbar').locator('button,input,a').evaluateAll(elements=>elements.filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height;}).map(e=>{const r=e.getBoundingClientRect();return {name:e.getAttribute('aria-label')||e.textContent,x:r.x,right:r.right,y:r.y,bottom:r.bottom};}));
  for(const control of toolbarControls){expect(control.x,control.name||"").toBeGreaterThanOrEqual(0);expect(control.right,control.name||"").toBeLessThanOrEqual(width+1);expect(control.bottom).toBeLessThanOrEqual(toolbar.bottom+1);}
  await page.screenshot({path:info.outputPath(`reader-atlas-${width}.png`)});

  const moreOpener = page.getByRole('button', { name: '更多阅读工具', exact: true });
  await moreOpener.click();
  const more = page.getByRole('dialog', { name: '阅读工具', exact: true });
  await expect(more).toBeVisible();
  await expect(more.getByRole('button', { name: '书内搜索', exact: true })).toBeVisible();
  await expect(more.getByRole('link', { name: /下载.*PDF/ }).first()).toHaveAttribute('href', /.+/);
  await expect(more.locator('.reader-more-zoom button').last()).toBeVisible();
  const toolsBox = await visibleGeometry(page, more);
  expect(toolsBox.x).toBeGreaterThanOrEqual(0); expect(toolsBox.right).toBeLessThanOrEqual(width);
  expect(toolsBox.y).toBeGreaterThanOrEqual(0); expect(toolsBox.bottom).toBeLessThanOrEqual(1000);
  await expectModalKeyboard(page, more);
  await page.keyboard.press('Escape'); await expect(more).toBeHidden(); await expect(moreOpener).toBeFocused();

  const directoryOpener = page.locator('.reader-bottom').getByRole('button', { name: '目录', exact: true });
  if(await directoryOpener.getAttribute('aria-pressed') !== 'true') await directoryOpener.click();
  const left = readerPanel(page, 'left', width);
  await expect(left).toBeVisible();
  const sidebar=await visibleGeometry(page,left);
  expect(sidebar.x).toBeGreaterThanOrEqual(0); expect(sidebar.right).toBeLessThanOrEqual(width);
  if(width <= 760) {
    expect(sidebar.y).toBeGreaterThanOrEqual(0); expect(sidebar.bottom).toBeLessThanOrEqual(1000);
    await expectModalKeyboard(page, left);
  } else {
    expect(Math.abs(sidebar.y - toolbar.y)).toBeLessThan(2);
    expect(sidebar.bottom).toBeLessThanOrEqual((await visibleGeometry(page,'.reader-bottom')).y+1);
  }
  await left.getByRole('button', { name: '搜索', exact: true }).click();
  await expect(left.getByRole('textbox', { name: '文档内搜索', exact: true })).toBeVisible();
  await left.getByRole('button', { name: '目录', exact: true }).click();
  await expect(left.getByRole('textbox', { name: '搜索目录', exact: true })).toBeVisible();
  if(width <= 760) {
    await page.keyboard.press('Escape'); await expect(left).toBeHidden(); await expect(directoryOpener).toBeFocused();
  } else {
    await page.getByRole('button', { name: '收起目录', exact: true }).click(); await expect(left).toBeHidden();
  }

  const citationOpener = page.locator('.reader-bottom').getByRole('button', { name: '引用', exact: true });
  await citationOpener.click();
  const right = readerPanel(page, 'right', width);
  await expect(right).toBeVisible();
  await expect(right.getByRole('heading', { name: '引用信息', exact: true })).toBeVisible();
  await expect(right.getByRole('combobox', { name: '引用格式', exact: true })).toBeVisible();
  const information = await visibleGeometry(page, right);
  expect(information.x).toBeGreaterThanOrEqual(0); expect(information.right).toBeLessThanOrEqual(width);
  expect(information.y).toBeGreaterThanOrEqual(0); expect(information.bottom).toBeLessThanOrEqual(1000);
  if(width <= 1050) await expectModalKeyboard(page, right);
  await right.getByRole('button', { name: '关闭信息侧栏', exact: true }).click();
  await expect(right).toBeHidden();
  if(width <= 1050) await expect(citationOpener).toBeFocused();

  const selection = await selectPageText(page);
  const noteOpener = selection.getByRole('button', { name: '记笔记', exact: true });
  // The selection toolbar preserves the PDF selection on mousedown; focus it
  // explicitly so keyboard opening and the gate's return-focus are both checked.
  await noteOpener.focus(); await noteOpener.press('Enter');
  const dialog=page.getByRole('dialog', { name: '登录后使用笔记', exact: true });await expect(dialog).toBeVisible();
  const gate=await visibleGeometry(page,'.login-gate > div');
  expect(gate.x).toBeGreaterThanOrEqual(0);expect(gate.right).toBeLessThanOrEqual(width);expect(gate.bottom).toBeLessThanOrEqual(1000);
  await expect(dialog).toContainText('在线阅读、下载、全文搜索、复制和引用对访客开放');
  await expectModalKeyboard(page, dialog);
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(noteOpener).toBeFocused();
  await selection.getByRole('button', { name: '关闭选文菜单', exact: true }).click();
  await page.getByRole('textbox',{name:'PDF 页码',exact:true}).fill('1001');
  await page.getByRole('textbox',{name:'PDF 页码',exact:true}).press('Enter');
  await expect(page.getByRole('textbox',{name:'PDF 页码',exact:true})).toHaveValue('1001');
  await info.attach('geometry',{body:JSON.stringify({pageBox,nextBox,canvas,documentBox,toolbar,toolbarControls,toolsBox,sidebar,information},null,2),contentType:'application/json'});
});

test('Reader keeps the requested canvas after sidebar resizing and offscreen pages render', async ({ page }, info) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  await page.goto(`/reader/${asset}?page=1`);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
  const measurements: unknown[] = [];
  try {
    for (const width of [768, 390, 1280, 768]) {
      await page.setViewportSize({ width, height: 1000 });
      const directory = page.locator('.reader-bottom').getByRole('button', { name: '目录', exact: true });
      if (await directory.getAttribute('aria-pressed') === 'true') await directory.click();
      const input = page.getByRole('textbox', { name: 'PDF 页码', exact: true });
      for (const target of [997, 1001]) {
        await input.fill(String(target));
        await input.press('Enter');
        const stage = page.locator(`.pdf-page-shell[data-page-number="${target}"] .pdf-canvas-stage`);
        await expect(stage.locator('canvas')).toBeVisible();
        await expect(stage).toHaveAttribute('aria-busy', 'false');
        const geometry = await page.locator('.reader-document').evaluate((element, targetPage) => {
          const root = element as HTMLElement;
          const box = root.getBoundingClientRect();
          return { scrollTop: root.scrollTop, scrollHeight: root.scrollHeight, height: root.clientHeight, page: targetPage,
            nearby: [targetPage - 1, targetPage, targetPage + 1].flatMap(number => {
              const shell = root.querySelector<HTMLElement>(`.pdf-page-shell[data-page-number="${number}"]`);
              if (!shell) return [];
              const stage = shell.querySelector<HTMLElement>('.pdf-canvas-stage');
              if (!stage) return [];
              const rect = stage.getBoundingClientRect();
              return [{ number, top: rect.top - box.top, height: rect.height, offsetTop: rect.top - box.top + root.scrollTop }];
            }) };
        }, target);
        measurements.push({ width, ...geometry });
        await expect(input).toHaveValue(String(target));
        await expect(page).toHaveURL(new RegExp(`page=${target}(?:&|$)`));
        const targetGeometry = geometry.nearby.find(row => row.number === target)!;
        // The requested page must be at the reading position, not merely the
        // next page partially visible below a stale page-number label.
        // A short last page cannot scroll past the document's lower boundary.
        const expectedScroll = Math.min(Math.max(targetGeometry.offsetTop - 22, 0), geometry.scrollHeight - geometry.height);
        expect(Math.abs(targetGeometry.top - (targetGeometry.offsetTop - expectedScroll)), JSON.stringify(geometry)).toBeLessThan(2);
      }
    }
  } finally {
    await info.attach('reader-jump-geometry', { body: JSON.stringify(measurements, null, 2), contentType: 'application/json' });
  }
});

test('Reader real API Range, private bookmark and annotation keep identity and recover after reload',async({page,browser},info)=>{
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/login');await page.getByLabel('邮箱').fill('reader-v305@example.test');await page.locator('input[name="password"]').fill('E2E-Local-Only-305-passphrase');await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page).toHaveURL(/\/account$/);
  await page.goto(`/reader/${asset}?page=1`);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
  const response=await page.request.get(`${api}/distribution/assets/${asset}/file/`,{headers:{Range:'bytes=0-31'}});
  expect(response.status()).toBe(206);expect((await response.body()).subarray(0,5).toString()).toBe('%PDF-');
  await expect(page.locator('.reader-related-notes').getByRole('heading', { name: /^我的笔记（\d+）$/ })).toBeVisible();
  const bookmarkSaved=page.waitForResponse(r=>r.url().includes('/reading/bookmarks/')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'更多阅读工具',exact:true}).click();
  await page.getByRole('dialog',{name:'阅读工具',exact:true}).getByRole('button',{name:'保存本页书签',exact:true}).click();
  expect((await bookmarkSaved).status()).toBe(201);
  await page.reload();
  await page.getByRole('button',{name:'更多阅读工具',exact:true}).click();
  const more = page.getByRole('dialog',{name:'阅读工具',exact:true});
  await expect(more.getByRole('button',{name:'移除本页书签',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  const selection = await selectPageText(page);
  await selection.getByRole('button',{name:'记笔记',exact:true}).click();
  const composer=page.locator('.reader-note-editor');await expect(composer).toBeVisible();
  await composer.getByRole('textbox',{name:'笔记内容'}).fill('V306 私人笔记与稳定页面身份');
  await composer.getByRole('textbox',{name:'笔记标签'}).fill('PDF39真实标签');
  await composer.getByRole('button',{name:'添加标签',exact:true}).click();
  const saved=page.waitForResponse(r=>r.url().endsWith('/reading/annotations/')&&r.request().method()==='POST');
  await composer.getByRole('button',{name:'保存笔记',exact:true}).click();
  const noteResponse=await saved;expect(noteResponse.status()).toBe(201);const note=await noteResponse.json();expect(note.asset).toBe(asset);expect(note.tags).toEqual(['PDF39真实标签']);
  expect(noteResponse.request().postDataJSON().request_id).toBe(note.id);
  const noteId=note.id;const pageId=note.page;
  await page.reload();
  const loaded=await page.request.get(`${api}/reading/annotations/${noteId}/`);expect(loaded.status()).toBe(200);
  const persisted = await loaded.json();expect(persisted.page).toBe(pageId);expect(persisted.tags).toEqual(['PDF39真实标签']);
  await page.locator('.reader-bottom').getByRole('button',{name:'笔记',exact:true}).click();
  await expect(page.locator('.reader-right').getByRole('button',{name:/V306 私人笔记与稳定页面身份/})).toContainText('PDF39真实标签');
  // A separate context has no authenticated cookies; this is an actual public
  // request, unlike reusing the signed-in page.request context.
  const publicContext = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  try {
    const publicManifest = await publicContext.request.get(`${api}/catalog/assets/${asset}/manifest/`);
    expect(publicManifest.status()).toBe(200);
    const manifest = await publicManifest.json();
    expect(manifest.asset_id).toBe(asset);
    expect(manifest.work.edition.id).toBe(manifest.edition_id);
    expect(manifest.work.edition.readable_asset.id).toBe(asset);
    expect(manifest.page_count).toBe(1001);
    expect(JSON.stringify(manifest)).not.toContain('V306 私人笔记');
    expect(JSON.stringify(manifest)).not.toContain('PDF39真实标签');
    const denied = await publicContext.request.get(`${api}/reading/annotations/${noteId}/`);
    expect([401, 403]).toContain(denied.status());
  } finally { await publicContext.close(); }

  await info.attach('private-record-identity',{body:JSON.stringify({asset,pageId,noteId}),contentType:'application/json'});
});
