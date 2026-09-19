import {expect,test,type Page} from "@playwright/test";

const asset="30600000-0000-4000-8000-000000000313";
const api="http://127.0.0.1:8105/api";
test.beforeEach(async({page,baseURL})=>{
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  await page.route("**/runtime-config.js",route=>route.fulfill({contentType:"application/javascript",body:`window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`}));
});

async function visibleGeometry(page:Page,selector:string){
  return page.locator(selector).first().evaluate(element=>{
    const r=element.getBoundingClientRect();const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,hit:!!top&&(element===top||element.contains(top))};
  });
}

for(const width of [360,390,768,1280,1440]) test(`Reader real 1001-page PDF controls, sidebars and keyboard at ${width}`,async({page},info)=>{
  await page.setViewportSize({width,height:1000});
  const response=await page.goto(`/reader/${asset}?page=1`);
  expect(response?.status()).toBe(200);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible({timeout:40_000});
  await expect(page.getByRole("textbox",{name:"页码",exact:true})).toHaveValue("1");
  await expect(page.locator('.page-control')).toContainText("1001");
  const pageBox=await visibleGeometry(page,'.page-control');
  const nextBox=await visibleGeometry(page,'.page-control button:last-child');
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
  await page.screenshot({path:info.outputPath(`reader-after-${width}.png`)});
  if(width<=760){
    await page.getByRole('button',{name:'展开阅读工具',exact:true}).click();
    await expect(page.getByRole('textbox',{name:'文档内搜索',exact:true})).toBeVisible();
    await expect(page.getByRole('button',{name:'放大',exact:true})).toBeVisible();
    const search=await visibleGeometry(page,'.reader-tool-groups');
    expect(search.right).toBeLessThanOrEqual(width);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button',{name:'展开阅读工具',exact:true})).toBeFocused();
  }
  if(await page.getByRole('button',{name:'打开目录侧栏',exact:true}).count()) await page.getByRole('button',{name:'打开目录侧栏',exact:true}).click();
  await expect(page.locator('.reader-left')).toBeVisible();
  const sidebar=await visibleGeometry(page,'.reader-left');
  expect(sidebar.y).toBeGreaterThanOrEqual(toolbar.bottom-1);
  expect(sidebar.bottom).toBeLessThanOrEqual((await visibleGeometry(page,'.reader-bottom')).y+1);
  await page.locator('.reader-left').getByRole('button',{name:'关闭目录侧栏',exact:true}).click();
  const informationToggle=page.locator('.reader-bottom').getByRole('button',{name:'打开信息侧栏',exact:true});
  if(await informationToggle.count()) await informationToggle.click();
  await expect(page.locator('.reader-right')).toBeVisible();
  await expect(page.locator('.reader-right')).toContainText('引用此页');
  await page.locator('.reader-right').getByRole('button',{name:'关闭信息侧栏',exact:true}).click();
  await page.getByRole('button',{name:'添加批注',exact:true}).click();
  const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
  const gate=await visibleGeometry(page,'.login-gate > div');
  expect(gate.x).toBeGreaterThanOrEqual(0);expect(gate.right).toBeLessThanOrEqual(width);expect(gate.bottom).toBeLessThanOrEqual(1000);
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'添加批注',exact:true})).toBeFocused();
  await page.getByRole('textbox',{name:'页码',exact:true}).fill('1001');
  await page.getByRole('textbox',{name:'页码',exact:true}).press('Enter');
  await expect(page.getByRole('textbox',{name:'页码',exact:true})).toHaveValue('1001');
  await info.attach('geometry',{body:JSON.stringify({pageBox,nextBox,canvas,documentBox,toolbar,toolbarControls,sidebar},null,2),contentType:'application/json'});
});

test('Reader keeps the requested canvas after sidebar resizing and offscreen pages render', async ({ page }, info) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  await page.goto(`/reader/${asset}?page=1`);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
  const measurements: unknown[] = [];
  try {
    for (const width of [768, 390, 1280, 768]) {
      await page.setViewportSize({ width, height: 1000 });
      const close = page.locator('.reader-left').getByRole('button', { name: '关闭目录侧栏', exact: true });
      if (await close.isVisible()) await close.click();
      const input = page.getByRole('textbox', { name: '页码', exact: true });
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
              const rect = shell.getBoundingClientRect();
              return [{ number, top: rect.top - box.top, height: rect.height, offsetTop: shell.offsetTop }];
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

test('Reader real API Range, private bookmark and annotation keep identity and recover after reload',async({page},info)=>{
  await page.goto('/login');await page.getByLabel('邮箱').fill('reader-v305@example.test');await page.locator('input[name="password"]').fill('E2E-Local-Only-305-passphrase');await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page).toHaveURL(/\/account$/);
  await page.goto(`/reader/${asset}?page=1`);
  await expect(page.locator('.pdf-canvas-stage canvas').first()).toBeVisible();
  const response=await page.request.get(`${api}/distribution/assets/${asset}/file/`,{headers:{Range:'bytes=0-31'}});
  expect(response.status()).toBe(206);expect((await response.body()).subarray(0,5).toString()).toBe('%PDF-');
  const bookmarkSaved=page.waitForResponse(r=>r.url().includes('/reading/bookmarks/')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'收藏当前页书签',exact:true}).click();
  expect((await bookmarkSaved).status()).toBe(201);
  await page.reload();await expect(page.getByRole('button',{name:'取消当前页书签',exact:true})).toBeVisible();
  const text=page.locator('.pdf-page-shell').first().locator('.pdf-native-text-layer span').first();await expect(text).toBeVisible();
  await text.evaluate(element=>{const range=document.createRange();range.selectNodeContents(element);const selection=window.getSelection();selection?.removeAllRanges();selection?.addRange(range);});
  await page.locator('.reader-document').dispatchEvent('mouseup');
  await expect(page.getByRole('toolbar',{name:'所选文字操作'})).toBeVisible();
  await page.getByRole('toolbar',{name:'所选文字操作'}).getByRole('button',{name:'笔记',exact:true}).click();
  const composer=page.locator('.annotation-composer');await expect(composer).toBeVisible();
  await composer.getByRole('textbox',{name:'笔记内容'}).fill('V306 私人笔记与稳定页面身份');
  const saved=page.waitForResponse(r=>r.url().endsWith('/reading/annotations/')&&r.request().method()==='POST');
  await composer.getByRole('button',{name:'保存笔记',exact:true}).click();
  const noteResponse=await saved;expect(noteResponse.status()).toBe(201);const note=await noteResponse.json();expect(note.asset).toBe(asset);
  const noteId=note.id;const pageId=note.page;
  await page.reload();
  const loaded=await page.request.get(`${api}/reading/annotations/${noteId}/`);expect(loaded.status()).toBe(200);expect((await loaded.json()).page).toBe(pageId);
  const anonymous=await page.request.get(`${api}/catalog/assets/${asset}/manifest/`);expect(JSON.stringify(await anonymous.json())).not.toContain('V306 私人笔记');
  await info.attach('private-record-identity',{body:JSON.stringify({asset,pageId,noteId}),contentType:'application/json'});
});
