/** Reader -> real private note -> center editor -> citation -> original source. */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=createRequire(path.join(root,'web/package.json'))('playwright');
const dir=path.join(root,'output/public-visual-20261110/runtime');
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1536,height:1024},storageState:path.join(dir,'fixture-session.json')});
await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
const page=await context.newPage();page.setDefaultTimeout(30000);
const result={fixtureOnly:true,asset:'30600000-0000-4000-8000-000000000313'};
try{
 await page.goto('http://127.0.0.1:18110/login?next=%2Faccount',{waitUntil:'networkidle'});
 await page.getByLabel('邮箱或用户名',{exact:true}).fill('owner-v305@example.test');
 await page.locator('input[name=password]').fill('E2E-Local-Only-305-passphrase');
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/account');
 await context.storageState({path:path.join(dir,'fixture-session.json')});
 await page.goto(`http://127.0.0.1:18110/reader/${result.asset}?page=1`,{waitUntil:'networkidle'});
 await page.locator('.pdf-canvas-stage canvas').first().waitFor();
 const text=page.locator('.pdf-page-shell[data-page-number="1"] .pdf-native-text-layer span').first();await text.waitFor();
 await text.evaluate(e=>{const r=document.createRange();r.selectNodeContents(e);const s=getSelection();s.removeAllRanges();s.addRange(r);});
 await page.locator('.reader-document').dispatchEvent('mouseup');
 await page.getByRole('toolbar',{name:'所选文字操作'}).getByRole('button',{name:'记笔记',exact:true}).click();
 const editor=page.locator('.reader-note-editor'),original='隔离排版笔记核对 '+Date.now();
 await editor.getByRole('textbox',{name:'笔记内容',exact:true}).fill(original);
 const saved=page.waitForResponse(r=>r.url().endsWith('/reading/annotations/')&&r.request().method()==='POST');
 await editor.getByRole('button',{name:'保存笔记',exact:true}).click();assert.equal((await saved).status(),201);result.createdThroughReader=true;
 await page.goto('http://127.0.0.1:18110/account/notes',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:new RegExp(original)}).click();
 const detail=page.getByRole('complementary',{name:'记录与来源详情',exact:true});await detail.getByRole('button',{name:'编辑',exact:true}).click();
 await detail.getByRole('textbox',{name:/^我的笔记/}).fill(original+' 已在读者中心编辑');
 await detail.getByRole('button',{name:'保存',exact:true}).click();await detail.getByRole('textbox',{name:/^我的笔记/}).waitFor({state:'hidden'});
 await page.reload({waitUntil:'networkidle'});await page.getByRole('button',{name:new RegExp(original+' 已在读者中心编辑')}).click();result.editedAndPersisted=true;
 await page.screenshot({path:path.join(dir,'note-center-filled-1536.png'),animations:'disabled'});
 const citation=page.waitForResponse(r=>r.url().includes('/citation')&&r.request().method()==='POST');
 await detail.getByRole('button',{name:'导出为引用',exact:true}).click();const response=await citation;
 if(response.status()===200){await page.getByRole('dialog').last().waitFor();result.citationVerified=true;await page.keyboard.press('Escape');}
 else{
   const body=await response.json();result.citationFailure={status:response.status(),details:body.details};
   // Disable only this candidate's styles and retry the same existing action.
   await page.evaluate(()=>{
     for(const link of document.querySelectorAll('link[rel="stylesheet"]'))if(link.href.includes('/styles/features/center-layout.css')&&link.sheet)link.sheet.disabled=true;
     const markers=['/* Center layout candidate boundary. */','/* Layout-only public candidate;','/* Current public candidate:'];
     for(const style of document.querySelectorAll('style[data-vite-dev-id]')){
       const cut=markers.map(m=>style.textContent.indexOf(m)).filter(i=>i>=0).sort((a,b)=>a-b)[0];
       if(cut!==undefined)style.textContent=style.textContent.slice(0,cut);
     }
   });
   const baseline=page.waitForResponse(r=>r.url().includes('/citation')&&r.request().method()==='POST');
   await detail.getByRole('button',{name:'导出为引用',exact:true}).click();const baselineResponse=await baseline;
   const baselineBody=await baselineResponse.json();assert.equal(baselineResponse.status(),response.status());assert.deepEqual(baselineBody.details,body.details);
   result.citationFailure.reproducesWithoutCandidateStyles=true;
   await page.screenshot({path:path.join(dir,'note-citation-existing-error.png'),animations:'disabled'});
 }
 const href=await detail.getByRole('link',{name:'回到原文 →',exact:true}).getAttribute('href');assert(href.includes(result.asset));
 await detail.getByRole('link',{name:'回到原文 →',exact:true}).click();await page.waitForURL(u=>u.pathname.includes('/reader/'));await page.locator('.pdf-canvas-stage canvas').first().waitFor();result.sourceReturn=true;
 await page.screenshot({path:path.join(dir,'note-source-reader.png'),animations:'disabled'});
 result.status=result.citationFailure?'partial_existing_failure':'pass';if(result.citationFailure)process.exitCode=1;
}catch(e){result.status='fail';result.error=e.message.slice(0,900);process.exitCode=1;}
finally{await fs.writeFile(path.join(dir,'note-source.json'),JSON.stringify(result,null,2));await context.close();await browser.close();}
console.log(JSON.stringify(result));
