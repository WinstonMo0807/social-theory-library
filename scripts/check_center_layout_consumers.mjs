/** Measures the actual consumers of layout rules on the disposable fixture. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=createRequire(path.join(root,'web/package.json'))('playwright');
const dir=path.join(root,'output/public-visual-20261110/runtime');
const targets=JSON.parse(await fs.readFile(path.join(dir,'layout-targets.json'),'utf8'));
if(targets.some(t=>!t.url.startsWith('http://127.0.0.1:18110/')))throw Error('Isolated fixture only');
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1536,height:1024},storageState:path.join(dir,'fixture-session.json')});
await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
const result=[];
try{
 const page=await context.newPage();
 for(const target of targets){
  const row={id:target.id,route:target.route};
  try{
   await page.goto(target.url,{waitUntil:'networkidle',timeout:60000});
   if(new URL(page.url()).pathname==='/login')throw Error('Fixture session expired');
   row.changes=await page.evaluate(()=>{
    const wrapper=document.querySelector('[data-stl-page-layout="account"]');if(wrapper)wrapper.style.display='contents';
    const markers=['/* Center layout candidate boundary. */','/* Layout-only public candidate;','/* Current public candidate:'];
    const nodes=[...document.querySelectorAll('.admin-content *,[data-stl-page-layout="account"] *')].filter(e=>e instanceof HTMLElement&&e.checkVisibility());
    const props=['padding','margin','gap','borderRadius','boxShadow','gridTemplateColumns','minWidth','maxWidth'];
    const read=()=>nodes.map(e=>{const s=getComputedStyle(e);return props.map(p=>s[p]);});
    const after=read();const styles=[];
    const sheets=[...document.querySelectorAll('link[rel="stylesheet"]')].filter(l=>l.href.includes('/styles/features/center-layout.css')&&l.sheet).map(l=>l.sheet);
    for(const s of sheets)s.disabled=true;
    for(const s of document.querySelectorAll('style[data-vite-dev-id]')){
     const text=s.textContent;let cut=markers.map(m=>text.indexOf(m)).filter(i=>i>=0).sort((a,b)=>a-b)[0];
     if(s.dataset.viteDevId.includes('center-layout.css')){styles.push([s,text]);s.textContent='[data-stl-page-layout="account"]{display:contents}';}
     else if(cut!==undefined){styles.push([s,text]);s.textContent=text.slice(0,cut);}
    }
    const before=read();for(const [s,text]of styles)s.textContent=text;
    for(const s of sheets)s.disabled=false;
    const changed=nodes.flatMap((e,i)=>JSON.stringify(after[i])===JSON.stringify(before[i])?[]:[{tag:e.tagName,cls:e.className,properties:props.filter((p,j)=>after[i][j]!==before[i][j])}]);
    return {count:changed.length,sample:changed.slice(0,8)};
   });
  }catch(e){row.error=e.message.slice(0,200);}
  result.push(row);await fs.writeFile(path.join(dir,'consumers.json'),JSON.stringify(result,null,2));
  if(result.length%10===0)console.log(`${result.length}/${targets.length}`);
 }
}finally{await context.close();await browser.close();}
console.log(JSON.stringify({count:result.length,zero:result.filter(r=>r.changes?.count===0).map(r=>r.id),errors:result.filter(r=>r.error)}));
