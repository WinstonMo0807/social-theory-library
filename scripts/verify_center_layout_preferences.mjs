/** Appearance and narrow-screen checks on a separate synthetic admin account. */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=createRequire(path.join(root,'web/package.json'))('playwright');
const dir=path.join(root,'output/public-visual-20261110/runtime/preferences');
await fs.mkdir(dir,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1536,height:1024},reducedMotion:'reduce'});
await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
const page=await context.newPage();const report=[];
try{
 await page.goto('http://127.0.0.1:18110/login?next=%2Faccount%3Fsection%3Dsettings',{waitUntil:'networkidle'});
 await page.getByLabel('邮箱或用户名',{exact:true}).fill('administrator-v305@example.test');
 await page.locator('input[name=password]').fill('E2E-Local-Only-305-passphrase');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/account?section=settings');await page.waitForLoadState('networkidle');
 await page.getByRole('group',{name:'字号',exact:true}).getByRole('button',{name:'大号',exact:true}).click();
 await page.getByRole('group',{name:'字体',exact:true}).getByRole('button',{name:'宋体',exact:true}).click();
 await page.getByRole('group',{name:'外观模式',exact:true}).getByRole('button',{name:'夜间',exact:true}).click();
 await page.waitForLoadState('networkidle');await page.reload({waitUntil:'networkidle'});
 assert.deepEqual(await page.evaluate(()=>[document.documentElement.dataset.textSize,document.documentElement.dataset.fontFamily,document.documentElement.dataset.theme]),['large','serif','dark']);
 for(const route of ['/account?section=settings','/account','/account/notes','/admin/library']){
  await page.goto('http://127.0.0.1:18110'+route,{waitUntil:'networkidle'});
  for(const width of [1536,768,390,320]){
   await page.setViewportSize({width,height:1024});await page.evaluate(()=>document.fonts.ready);
   const check=await page.evaluate(()=>{
    const wrapper=document.querySelector('[data-stl-page-layout="account"]');if(wrapper)wrapper.style.display='contents';
    const nodes=[...document.querySelectorAll('body *')].filter(e=>e instanceof HTMLElement&&e.checkVisibility());
    const read=()=>nodes.map(e=>{let s=getComputedStyle(e);return ['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color'].map(p=>s[p]).join('|');});
    const candidate=read(),candidateWidth=document.documentElement.scrollWidth,saved=[];
    const sheets=[...document.querySelectorAll('link[rel="stylesheet"]')].filter(l=>l.href.includes('/styles/features/center-layout.css')&&l.sheet).map(l=>l.sheet);for(const s of sheets)s.disabled=true;
    for(const s of document.querySelectorAll('style[data-vite-dev-id]')){const cut=['/* Center layout candidate boundary. */','/* Layout-only public candidate;','/* Current public candidate:'].map(m=>s.textContent.indexOf(m)).filter(i=>i>=0).sort((a,b)=>a-b)[0];if(cut!==undefined){saved.push([s,s.textContent]);s.textContent=s.textContent.slice(0,cut);}}
    const baseline=read(),baselineWidth=document.documentElement.scrollWidth;for(const[s,t]of saved)s.textContent=t;for(const s of sheets)s.disabled=false;
    return {sameTextStyles:JSON.stringify(candidate)===JSON.stringify(baseline),baselineWidth,candidateWidth,theme:document.documentElement.dataset.theme,size:document.documentElement.dataset.textSize,reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches};
   });
   report.push({route,width,...check});await page.screenshot({path:path.join(dir,route.replace(/[^a-zA-Z0-9]/g,'-')+'-'+width+'.png'),animations:'disabled'});
  }
 }
 await fs.writeFile(path.join(dir,'report.json'),JSON.stringify(report,null,2));
 assert(report.every(r=>r.sameTextStyles&&r.reducedMotion&&r.theme==='dark'&&r.size==='large'));
 console.log(JSON.stringify({checks:report.length,newOverflow:report.filter(r=>r.candidateWidth>Math.max(r.width,r.baselineWidth)+2)}));
}finally{await context.close();await browser.close();}
