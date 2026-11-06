import assert from 'node:assert/strict';
import {chromium} from '../node_modules/playwright/index.mjs';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(here,'../../output/playwright/architecture-showcase-v6');await mkdir(out,{recursive:true});
const journeys=JSON.parse(await readFile(path.join(here,'journeys.json'),'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const results=[],errors=[];
for(const [width,height] of [[1920,1080],[1440,900],[1280,720],[980,950],[1024,1366],[768,1024],[390,844],[320,568],[844,390]]){
 const page=await browser.newPage({viewport:{width,height},isMobile:width<640,hasTouch:width<1180});page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5198');await page.getByRole('button',{name:'暂停自动切换'}).click();await page.evaluate(()=>document.fonts.ready);
 for(let scene=0;scene<5;scene++){
  await page.locator('.scene-nav nav button').nth(scene).click();if(scene===0)await page.getByRole('button',{name:'返回全局',exact:true}).click();else if(scene!==2)await page.locator('.stage-nav button').last().click();
  await page.waitForTimeout(600);
  const dimensions=await page.evaluate(()=>{const root=document.querySelector('.presentation'),main=document.querySelector('.main-scene'),r=root.getBoundingClientRect(),m=main.getBoundingClientRect();return {root:[r.x,r.y,r.width,r.height],main:[m.width,m.height],rootOverflow:root.scrollWidth-root.clientWidth,mainOverflow:main.scrollWidth-main.clientWidth,layout:root.dataset.layout}});
  results.push({width,height,scene,...dimensions});
  if([1920,768,390,320,980].includes(width))await page.screenshot({path:path.join(out,`${width}x${height}-scene-${scene}.png`)});
 }
 if([1920,768,390,320].includes(width)){
  await page.locator('.scene-nav nav button').first().click();await page.getByRole('button',{name:'返回全局',exact:true}).click();await page.getByRole('button',{name:'查看发现与检索详情',exact:true}).click();await page.waitForTimeout(700);await page.screenshot({path:path.join(out,`${width}-details.png`)});
  await page.getByRole('button',{name:'返回全局',exact:true}).click();await page.locator('.scene-nav nav button').nth(2).click();
  for(let ji=0;ji<3;ji++){
   await page.getByRole('tab').nth(ji).click();
   for(let stage=0;stage<journeys[ji].steps.length;stage++){
    await page.getByRole('combobox',{name:'选择操作步骤'}).selectOption(String(stage));await page.waitForTimeout(650);
    const data=await page.evaluate(target=>{const el=document.querySelector(`[data-demo-target="${target}"]`),surface=document.querySelector('.demo-surface'),panel=document.querySelector('.demo-panel'),main=document.querySelector('.main-scene');if(!el)return{completedTargetRemoved:true};const overlay=surface.querySelector('.demo-overlay');if(overlay&&!overlay.contains(el))return{completedTargetReplacedByOverlay:true};const r=el.getBoundingClientRect(),s=surface.getBoundingClientRect();return{target:[r.x,r.y,r.width,r.height],surface:[s.x,s.y,s.width,s.height],clipped:r.left<s.left-2||r.right>s.right+2||(r.height>s.height-24?(r.top+r.height*.64<s.top-2||r.top+r.height*.64>s.bottom+2):(r.top<s.top-2||r.bottom>s.bottom+2)),mainOverflow:main.scrollWidth-main.clientWidth,panelOverflow:panel.scrollWidth-panel.clientWidth}},journeys[ji].steps[stage].target);
    results.push({width,height,journey:ji,stage,...data});
    if([390,768,1920].includes(width)&&((ji===0&&[9,13,19].includes(stage))||(ji===1&&stage===6)||(ji===2&&stage===5))){await page.locator('.demo-window').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,`${width}-journey-${ji}-${stage}.png`)});}
   }
  }
 }
 await page.close();
}
await browser.close();await writeFile(path.join(out,'responsive-verification.json'),JSON.stringify({results,errors},null,2));
console.log(JSON.stringify({cases:results.length,errors,issues:results.filter(r=>r.rootOverflow>2||r.mainOverflow>2||r.clipped||r.missing)},null,2));

assert.equal(errors.length,0);assert.ok(results.every(r=>!(r.rootOverflow>2||r.mainOverflow>2||r.clipped)));assert.ok(results.filter(r=>r.root).every(r=>r.root[2]===r.width&&r.root[3]===r.height));
