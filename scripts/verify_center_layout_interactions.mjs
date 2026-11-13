/** Real UI operations against synthetic localhost objects. Never production. */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=createRequire(path.join(root,'web/package.json'))('playwright');
const dir=path.join(root,'output/public-visual-20261110/runtime');
const targets=JSON.parse(await fs.readFile(path.join(dir,'layout-targets.json'),'utf8'));
const runtime=JSON.parse(await fs.readFile(path.join(root,'output/public-visual-20261110/audit/FIXTURE_RUNTIME.json'),'utf8'));
assert.equal(runtime.api_url,'http://127.0.0.1:18111/api');
assert.match(runtime.fixture_directory,/stl-v305-e2e-/);
const origin='http://127.0.0.1:18110';
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1536,height:1024},storageState:path.join(dir,'fixture-session.json'),reducedMotion:'reduce'});
await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
const report=[];
const page=await context.newPage();page.setDefaultTimeout(15000);
async function run(name,fn){try{report.push({name,status:'pass',details:await fn()});}catch(e){report.push({name,status:'fail',error:e.message.slice(0,700)});}await fs.writeFile(path.join(dir,'interactions.json'),JSON.stringify(report,null,2));console.log(name,report.at(-1).status);}
async function visit(id){await page.goto(targets.find(r=>r.id===id).url,{waitUntil:'networkidle'});assert.notEqual(new URL(page.url()).pathname,'/login');}
async function unchanged(selector){
 return page.evaluate(selector=>{
  const markers=['/* Center layout candidate boundary. */','/* Layout-only public candidate;','/* Current public candidate:'];
  const wrapper=document.querySelector('[data-stl-page-layout="account"]');if(wrapper)wrapper.style.display='contents';
  const nodes=[...document.querySelectorAll(selector)].flatMap(e=>[e,...e.querySelectorAll('*')]).filter(e=>e instanceof HTMLElement&&e.checkVisibility());
  const props=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','padding','border','borderRadius','width','height','gap','animationName','animationDuration'];
  const read=()=>nodes.map(e=>props.map(p=>getComputedStyle(e)[p]));
  const after=read(),saved=[];
  const sheets=[...document.querySelectorAll('link[rel="stylesheet"]')].filter(l=>l.href.includes('/styles/features/center-layout.css')&&l.sheet).map(l=>l.sheet);
  for(const s of sheets)s.disabled=true;
  for(const s of document.querySelectorAll('style[data-vite-dev-id]')){let cut=markers.map(m=>s.textContent.indexOf(m)).filter(i=>i>=0).sort((a,b)=>a-b)[0];if(cut!==undefined){saved.push([s,s.textContent]);s.textContent=s.textContent.slice(0,cut);}}
  const before=read();for(const [s,t]of saved)s.textContent=t;for(const s of sheets)s.disabled=false;
  return {nodes:nodes.length,equal:JSON.stringify(before)===JSON.stringify(after)};
 },selector);
}
try{
 await run('booklist dialog, keyboard focus, save and refresh',async()=>{
  await visit('PV007');await page.getByRole('button',{name:'创建书单',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'书单操作'});await dialog.waitFor();
  const styles=await unchanged('dialog[open]');assert(styles.nodes>0&&styles.equal);
  assert(await dialog.evaluate(d=>d.contains(document.activeElement)));
  const title='隔离排版交互验证书单';await dialog.getByLabel('书单名称',{exact:true}).fill(title);
  await dialog.getByLabel('我的说明',{exact:true}).fill('合成测试对象，仅验证现有保存入口。');
  await dialog.getByRole('button',{name:'保存书单',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await page.waitForURL(/\/account\/collections\/[^/?]+$/);await page.reload({waitUntil:'networkidle'});await page.getByRole('heading',{name:title,exact:true}).waitFor();
  return {styles,persisted:true};
 });
 await run('save error keeps entered booklist fields',async()=>{
  await visit('PV007');await page.getByRole('button',{name:'创建书单',exact:true}).click();const dialog=page.getByRole('dialog',{name:'书单操作'});
  await dialog.getByLabel('书单名称',{exact:true}).fill('隔离错误恢复测试');
  const pattern='**/api/**';const reject=r=>r.request().method()==='POST'?r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'隔离测试：服务暂时不可用'})}):r.fallback();
  await page.route(pattern,reject);await dialog.getByRole('button',{name:'保存书单',exact:true}).click();
  await page.getByText(/隔离测试：服务暂时不可用/).first().waitFor();assert.equal(await dialog.getByLabel('书单名称',{exact:true}).inputValue(),'隔离错误恢复测试');
  await page.unroute(pattern,reject);return {inputPreserved:true,realErrorVisible:true,recoveryGuardPreserved:await dialog.getByRole('button',{name:'关闭',exact:true}).isDisabled()};
 });
 await run('catalog draft preview, diff dialog and real save',async()=>{
  await visit('PV033');const field=page.locator('input[name=title]'),original='V306同名身份演练';const title='隔离草稿预览一致性测试 '+Date.now();
  await field.fill(title);assert((await page.locator('.workflow-v306-preview').innerText()).includes(title));assert((await page.locator('.admin-content').innerText()).includes('未保存'));
  await page.getByRole('button',{name:'查看差异',exact:true}).first().click();await page.locator('dialog[open]').waitFor();const styles=await unchanged('dialog[open]');assert(styles.nodes>0&&styles.equal);
  await page.keyboard.press('Escape');await page.locator('dialog[open]').waitFor({state:'hidden'});assert.equal(await field.inputValue(),title);
  await page.getByRole('button',{name:'保存',exact:true}).first().click();await page.waitForFunction(()=>!document.querySelector('input[name=title]').disabled&&document.querySelector('.admin-content').innerText.includes('已保存草稿'));
  await page.reload({waitUntil:'networkidle'});assert.equal(await field.inputValue(),title);
  await field.fill(original);await page.getByRole('button',{name:'保存',exact:true}).first().click();await page.waitForFunction(()=>!document.querySelector('input[name=title]').disabled&&document.querySelector('.admin-content').innerText.includes('已保存草稿'));
  return {previewMatches:true,styles,savedAndRestored:true,published:false};
 });
 await run('catalog search, pagination and return URL',async()=>{
  await visit('PV044');const input=page.getByLabel('题名、责任者、ISBN或DOI',{exact:true});await input.fill('同名身份');await input.press('Enter');await page.waitForURL(/q=/);await page.waitForFunction(()=>document.querySelector('.work-library-row')?.innerText.includes('同名身份'));
  assert((await page.locator('.work-library-row').first().innerText()).includes('同名身份'));const before=page.url();
  await page.getByRole('link',{name:'编辑当前版本',exact:true}).first().click();await page.waitForURL(u=>u.pathname.includes('/cataloging/')||u.pathname.includes('/works/'));await page.waitForLoadState('networkidle');await page.goBack({waitUntil:'networkidle'});assert.equal(page.url(),before);
  await input.fill('');await input.press('Enter');await page.waitForURL(u=>!u.searchParams.has('q'));await page.waitForLoadState('networkidle');const next=page.getByRole('link',{name:'下一页',exact:true});await next.click();await page.waitForURL(u=>u.searchParams.get('page')==='2');return {filtered:true,returnUrl:true,pagination:'page 2'};
 });
 await run('existing welcome editor draft stays through preview tab',async()=>{
  await visit('PV103');const field=page.getByLabel('标题第一行',{exact:true});const original=await field.inputValue();const title='隔离草稿标题';await field.fill(title);
  await page.getByRole('button',{name:'页面预览',exact:true}).click();await page.frameLocator('iframe:visible').first().getByText(title,{exact:true}).first().waitFor();
  await page.getByRole('button',{name:'内容设置',exact:true}).click();assert.equal(await field.inputValue(),title);await field.fill(original);return {draftProjection:true,tabRetention:true,saved:false,published:false};
 });
 await run('public and login styles unaffected after center navigation',async()=>{
  await page.goto(origin+'/home',{waitUntil:'networkidle'});const home=await unchanged('body');assert(home.nodes>0&&home.equal);
  await page.goto(origin+'/login',{waitUntil:'networkidle'});const login=await unchanged('body');assert(login.nodes>0&&login.equal);return {home,login};
 });
}finally{await context.close();await browser.close();}
if(report.some(r=>r.status!=='pass'))process.exitCode=1;
