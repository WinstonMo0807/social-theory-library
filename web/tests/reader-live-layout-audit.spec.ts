import {expect,test} from "@playwright/test";

test("read-only current production Reader geometry with a real public PDF",async({page,request},testInfo)=>{
  const listing=await request.get("/api/catalog/works/?format=json");
  expect(listing.ok()).toBeTruthy();
  const payload=await listing.json();
  const work=payload.results.find((row:{edition?:{readable_asset?:{id:string}}})=>row.edition?.readable_asset?.id);
  expect(work?.edition?.readable_asset?.id).toBeTruthy();
  const asset=work.edition.readable_asset;
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(`/reader/${asset.id}?page=1`,{waitUntil:"domcontentloaded"});
  await expect(page.locator(".reader")).toBeVisible();
  let pdfRendered = false;
  try { await page.locator(".pdf-canvas-stage canvas").first().waitFor({state:"visible",timeout:15_000}); pdfRendered=true; } catch { /* Record the blocked file separately while still capturing toolbar geometry. */ }
  const measurements=[];
  for(const width of [1440,1280,768,390,360]){
    await page.setViewportSize({width,height:1000});
    await page.evaluate(()=>document.fonts.ready);
    await expect(page.locator(".reader")).toHaveCSS("width",`${width}px`);
    const row=await page.evaluate(()=>{
      const box=(element:Element)=>{const r=element.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
      const toolbar=document.querySelector(".reader-toolbar")!;
      const controls=[...toolbar.querySelectorAll("button,input,a")].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;}).map(e=>{
        const r=box(e);const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
        return {label:e.getAttribute("aria-label")||e.getAttribute("title")||e.textContent?.trim(),...r,covered:!!top&&!e.contains(top),outside:r.x<0||r.right>innerWidth||r.y<0||r.bottom>innerHeight};
      });
      const overlaps=controls.flatMap((a,i)=>controls.slice(i+1).filter(b=>Math.min(a.right,b.right)-Math.max(a.x,b.x)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>2).map(b=>[a.label,b.label]));
      return {width:innerWidth,toolbar:box(toolbar),document:box(document.querySelector(".reader-document")!),pageControl:box(document.querySelector(".page-control")!),controls,overlaps,documentScrollWidth:document.documentElement.scrollWidth};
    });
    measurements.push(row);
    await page.screenshot({path:testInfo.outputPath(`production-before-${width}.png`)});
    const open=page.getByRole("button",{name:"打开目录侧栏",exact:true});
    if(await open.isVisible()){
      await open.click();await expect(page.getByRole("button",{name:"关闭目录侧栏",exact:true})).toBeVisible();
      await page.screenshot({path:testInfo.outputPath(`production-before-directory-${width}.png`)});
      await page.getByRole("button",{name:"关闭目录侧栏",exact:true}).click();
    }
  }
  await testInfo.attach("source-and-geometry",{body:JSON.stringify({kind:"production-read-only-before",origin:testInfo.project.use.baseURL,pdfRendered,title:work.title,assetId:asset.id,pages:asset.page_count,measurements},null,2),contentType:"application/json"});
  expect(pdfRendered,"Real PDF rendering is still a required gate; geometry collection does not make a failed Reader pass").toBe(true);
  // This is baseline collection, intentionally not a repair acceptance claim.
  // The resulting overlap/hit-test measurements are checked in the repair run.
});
