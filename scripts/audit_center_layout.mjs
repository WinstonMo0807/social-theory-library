/** Read-only browser layout audit against the disposable fixture, never production. */
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(root, "web/package.json"));
const { chromium } = require("playwright");
const dir = path.join(root, "output/public-visual-20261110/runtime");
const targets = JSON.parse(await fs.readFile(path.join(dir, "layout-targets.json"), "utf8"));
const phase = process.argv[2] || "round1";
const only = process.argv[3]?.split(",");
const selected = only ? targets.filter(r => only.includes(r.id)) : targets;
if (!selected.length || targets.some(r => !r.url.startsWith("http://127.0.0.1:18110/"))) throw Error("Only isolated fixture pages may be audited");
await fs.mkdir(path.join(dir, phase), { recursive: true });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 1536, height: 1024 }, storageState: path.join(dir, "fixture-session.json") });
await context.route("**/*", route => {
  const u = new URL(route.request().url());
  return ["127.0.0.1", "localhost"].includes(u.hostname) || ["data:", "blob:"].includes(u.protocol) ? route.continue() : route.abort("blockedbyclient");
});
const report = [];
const narrow = new Set(["PV002","PV005","PV006","PV008","PV010","PV012","PV018","PV020","PV024","PV027","PV033","PV042","PV044","PV048","PV056","PV066","PV078","PV090","PV100","PV101"]);

async function snapshot(page) {
  return page.evaluate(() => {
    const protectedSelector = 'nav,aside,dialog,[role="dialog"],[role="menu"],[data-menu-panel],.stl-loading,.site-header,.site-footer';
    const textProps = ["fontFamily","fontSize","fontWeight","fontStyle","lineHeight","letterSpacing","color"];
    const protectedProps = [...textProps,"padding","borderRadius","borderWidth","backgroundColor","display","position","gap","animationName","animationDuration"];
    // PDF's own text layer and rendering notice change when its viewport resizes.
    // Compare UI type and content; original PDF rendering is checked separately.
    const nodes = [...document.querySelectorAll("body *")].filter(e => e instanceof HTMLElement && e.checkVisibility() && !e.closest('.pdf-canvas-stage'));
    return {
      layout: nodes.map(e=>{const s=getComputedStyle(e);return ['padding','margin','gap','gridTemplateColumns','borderRadius','boxShadow','minWidth','maxWidth'].map(p=>s[p]).join('|');}),
      type: nodes.map(e => { const s=getComputedStyle(e); return textProps.map(p=>s[p]).join("|"); }),
      // Typed OM keeps authored auto margins as auto, rather than comparing
      // their resolved free-space pixels when the surrounding body changes size.
      protected: nodes.filter(e=>e.matches(protectedSelector)||e.closest(protectedSelector)).map(e=>{const s=getComputedStyle(e);return {tag:e.tagName,cls:e.className,style:protectedProps.map(p=>s[p]).join("|"),margins:["top","right","bottom","left"].map(side=>{const v=e.computedStyleMap().get(`margin-${side}`);return v?.unit==='px'&&Math.abs(v.value)<1e-8?'0px':String(v);}).join("|")};}),
      content: nodes.flatMap(e=>[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent.trim()).filter(Boolean)).join('\n'),
      width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
      overflow:nodes.filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+2||r.left< -2)&&!e.closest('nav,dialog,[role="dialog"],.reader,.pdf-canvas-stage')&&!e.parentElement?.closest('[style*="overflow"]');}).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,50)})),
    };
  });
}

async function toggleCandidate(page, enabled) {
  await page.evaluate(enabled => {
    const wrapper=document.querySelector('[data-stl-page-layout="account"]');
    if(wrapper) wrapper.style.display='contents';
    for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
      if (link.href.includes('/styles/features/center-layout.css') && link.sheet) link.sheet.disabled = !enabled;
    }
    const markers = ["/* Center layout candidate boundary. */", "/* Layout-only public candidate;", "/* Current public candidate:"];
    for (const style of document.querySelectorAll("style[data-vite-dev-id]")) {
      const id=style.getAttribute("data-vite-dev-id");
      if (enabled) { if(style.dataset.layoutOriginal) {style.textContent=style.dataset.layoutOriginal;delete style.dataset.layoutOriginal;} continue; }
      const content=style.textContent;
      if(id.includes("center-layout.css")) {style.dataset.layoutOriginal=content;style.textContent='[data-stl-page-layout="account"]{display:contents}';continue;}
      const cut=markers.map(m=>content.indexOf(m)).filter(i=>i>=0).sort((a,b)=>a-b)[0];
      if(cut!==undefined){style.dataset.layoutOriginal=content;style.textContent=content.slice(0,cut);}
    }
  },enabled);
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
}

try {
  for (const target of selected) {
    const page = await context.newPage();
    const failures=[];
    page.on("response",r=>{if(r.status()>=400 && r.url().includes("/api/")) failures.push({status:r.status(),path:new URL(r.url()).pathname});});
    page.on("pageerror",e=>failures.push({pageError:e.message.slice(0,240)}));
    const row={...target,views:[]};
    try {
      await page.goto(target.url,{waitUntil:"networkidle",timeout:60000});
      await page.evaluate(()=>document.fonts.ready);
      row.finalUrl=page.url();row.headings=await page.locator("h1").allTextContents();
      if (new URL(row.finalUrl).pathname === '/login') throw Error('Fixture session expired; login page is not a completed consumer audit');
      if(row.headings.some(h=>/没有找到这个页面|出了点问题/.test(h)))throw Error('Unavailable route or error boundary; not an accepted consumer capture');
      await toggleCandidate(page,false); const before=await snapshot(page);
      await toggleCandidate(page,true); const after=await snapshot(page);
      row.preservation={sameVisibleText:before.content===after.content,sameTextStyles:JSON.stringify(before.type)===JSON.stringify(after.type),sameProtectedStyles:JSON.stringify(before.protected)===JSON.stringify(after.protected)};
      row.layoutChangedNodes=after.layout.filter((value,i)=>value!==before.layout[i]).length;
      if(!row.preservation.sameProtectedStyles) row.protectedDiff=after.protected.filter((r,i)=>JSON.stringify(r)!==JSON.stringify(before.protected[i])).slice(0,8);
      for(const width of [1536,390,...(narrow.has(target.id)?[320,768]:[])]) {
        await page.setViewportSize({width,height:1024});
        await page.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
        await toggleCandidate(page,false);const base=await snapshot(page);
        await toggleCandidate(page,true);const s=await snapshot(page);
        row.views.push({width,baselineScrollWidth:base.scrollWidth,scrollWidth:s.scrollWidth,overflow:s.overflow});
        await page.screenshot({path:path.join(dir,phase,`${target.id}-${width}.png`),animations:"disabled"});
      }
      row.failures=failures;
    } catch(e) { row.error=e.message.slice(0,400);row.failures=failures; }
    report.push(row);await page.close();
    await fs.writeFile(path.join(dir,`${phase}.json`),JSON.stringify(report,null,2));
    if(report.length%5===0||report.length===selected.length)console.log(`${phase}: ${report.length}/${selected.length}; current ${target.id}`);
  }
} finally {await context.close();await browser.close();}
console.log(JSON.stringify({pages:report.length,errors:report.filter(r=>r.error).map(r=>r.id),preservationIssues:report.filter(r=>r.preservation&&Object.values(r.preservation).some(v=>!v)).map(r=>r.id),overflowPages:report.filter(r=>r.views.some(v=>v.scrollWidth>v.width+2)).map(r=>r.id)}));
