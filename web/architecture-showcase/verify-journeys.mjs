import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url)),out=path.resolve(here,'../../output/playwright/architecture-showcase-v4');
const journeys=JSON.parse(await readFile(path.join(here,'journeys.json'),'utf8'));
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},acceptDownloads:true});
const errors=[],requests=[],checks=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5196')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))requests.push(r.url())});
const check=(name,value)=>{assert.ok(value,name);checks.push(name);console.log('PASS',name)};
const select=async si=>page.getByRole('combobox',{name:'选择操作步骤'}).selectOption(String(si));
const scrub=async value=>page.getByRole('slider',{name:'播放进度'}).fill(String(Math.round(value/50)*50));
try{
 await page.goto('http://127.0.0.1:5196/?scene=2',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);await page.getByRole('button',{name:'暂停自动切换',exact:true}).click();
 check('five scenes with requested labels',await page.locator('.scene-nav nav button').count()===5&&(await page.locator('.scene-nav').innerText()).includes('底层架构')&&(await page.locator('.scene-nav').innerText()).includes('品牌标识')&&!(await page.locator('.scene-nav').innerText()).includes('实现与证据'));
 for(let ji=0;ji<journeys.length;ji++){
  const j=journeys[ji];await page.getByRole('tab').nth(ji).click();let elapsed=0;
  for(let si=0;si<j.steps.length;si++){
   const step=j.steps[si];await select(si);
   const layout=await page.evaluate(()=>{
    const explanation=document.querySelector('.journey-explanation'),window=document.querySelector('.demo-window'),rail=document.querySelector('.transport'),tabs=document.querySelector('.journey-tabs'),intro=document.querySelector('.scene-intro>p');
    const overflow=[...document.querySelectorAll('.demo-overlay>section,.admin-demo>main,.research-demo,.entry-screen,.journey-explanation')].filter(el=>el.scrollHeight>el.clientHeight+2).map(el=>({className:el.className,scroll:el.scrollHeight,client:el.clientHeight}));
    return {overflow,fit:explanation.getBoundingClientRect().bottom<rail.getBoundingClientRect().top&&window.getBoundingClientRect().bottom<rail.getBoundingClientRect().top&&tabs.getBoundingClientRect().top>=intro.getBoundingClientRect().bottom+5};
   });
   check(`${j.id}/${step.id}: layout without clipping`,layout.fit&&layout.overflow.length===0);
   check(`${j.id}/${step.id}: correct feedback`,(await page.locator('.journey-feedback').innerText()).includes(step.feedback));
   await page.getByRole('button',{name:'查看步骤依据',exact:true}).click();check(`${j.id}/${step.id}: traced contract and sources`,await page.locator('.step-inspector .source-list li').count()===step.sources.length&&(await page.locator('.step-contract').innerText()).includes(step.contract));await page.keyboard.press('Escape');
   await page.screenshot({path:path.join(out,`${j.id}-${step.id}-1920.png`)});
   // Intermediate states matter: opened menus and asynchronous placeholders must fit too.
   for(const fraction of [.2,.46,.7]){await scrub(elapsed+step.duration*fraction);check(`${j.id}/${step.id}: frame ${fraction}`,await page.locator('.demo-surface').evaluate(el=>[...el.querySelectorAll('.demo-overlay>section')].every(n=>n.scrollHeight<=n.clientHeight+2)));}
   elapsed+=step.duration;
  }
 }
 await page.getByRole('tab').nth(0).click();await page.getByRole('button',{name:'恢复自动切换',exact:true}).click();await page.waitForTimeout(400);const early=await page.locator('.typed-question').innerText();await page.waitForTimeout(900);const later=await page.locator('.typed-question').innerText();check('playback types query',later.length>early.length);
 await page.getByRole('button',{name:'暂停自动切换',exact:true}).click();const paused=await page.getByRole('slider',{name:'播放进度'}).inputValue(),text=await page.locator('.typed-question').innerText(),pointer=await page.locator('.demo-pointer').getAttribute('style');await page.waitForTimeout(700);check('pause freezes query, pointer and timeline',await page.getByRole('slider',{name:'播放进度'}).inputValue()===paused&&await page.locator('.typed-question').innerText()===text&&await page.locator('.demo-pointer').getAttribute('style')===pointer);
 await page.getByRole('button',{name:'恢复自动切换',exact:true}).click();await page.waitForTimeout(350);check('resume continues position',Number(await page.getByRole('slider',{name:'播放进度'}).inputValue())>Number(paused));await page.getByRole('button',{name:'暂停自动切换',exact:true}).click();
 const start=si=>journeys[0].steps.slice(0,si).reduce((n,s)=>n+s.duration,0);
 await scrub(start(9)+1000);check('context click precedes popup',await page.locator('.context-modal').count()===0);await scrub(start(9)+1900);check('context has loading state',(await page.locator('.context-modal').innerText()).includes('正在读取'));await scrub(start(9)+4000);check('context returns adjacent paragraphs',(await page.locator('.context-modal').innerText()).includes('后段'));
 await scrub(start(7)+1000);check('sort menu opens',await page.locator('.sort-popover').count()===1);await scrub(start(7)+3000);check('sort changes result order',(await page.locator('.result-row').first().innerText()).includes('示例文献 B'));
 await select(17);check('copy shows result',(await page.locator('.citation-notice').innerText()).includes('引用已复制'));
 await page.getByRole('button',{name:'重新播放当前阶段',exact:true}).click();await page.getByRole('button',{name:'恢复自动切换',exact:true}).click();await page.waitForTimeout(180);check('replay starts same operation',await page.locator('.journey-scene').getAttribute('data-step')==='copy'&&Number(await page.getByRole('slider',{name:'播放进度'}).inputValue())<start(17)+1000);await page.getByRole('button',{name:'暂停自动切换',exact:true}).click();
 const total=journeys[0].steps.reduce((n,s)=>n+s.duration,0);await scrub(total-450);await page.getByRole('button',{name:'恢复自动切换',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.presentation')?.getAttribute('data-journey')==='1');check('finish advances to publishing',await page.locator('.journey-scene').getAttribute('data-step')==='file');await page.getByRole('button',{name:'暂停自动切换',exact:true}).click();
 await page.getByRole('tab').nth(0).focus();await page.keyboard.press('ArrowRight');check('tabs support keyboard',await page.getByRole('tab').nth(1).getAttribute('aria-selected')==='true');
 await select(6);await page.getByRole('button',{name:'全屏展示',exact:true}).click();check('native fullscreen',await page.evaluate(()=>!!document.fullscreenElement));await page.getByRole('button',{name:'查看步骤依据',exact:true}).click();check('fullscreen supports details',await page.locator('.step-dialog').isVisible());await page.keyboard.press('Escape');await page.screenshot({path:path.join(out,'journey-fullscreen.png')});await page.getByRole('button',{name:'退出全屏',exact:true}).click();
 await page.emulateMedia({reducedMotion:'reduce'});await select(5);check('reduced motion shows settled state',await page.getByRole('button',{name:'恢复自动切换',exact:true}).isEnabled()&&await page.locator('.demo-pointer').isHidden());await page.emulateMedia({reducedMotion:'no-preference'});
 for(const [width,height] of [[1366,768],[1440,900],[1280,720]]){await page.setViewportSize({width,height});await page.waitForTimeout(80);check(`fits ${width}x${height}`,await page.locator('.presentation').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}));await page.screenshot({path:path.join(out,`layout-${width}.png`)});}
 await page.setViewportSize({width:1920,height:1080});await page.locator('.scene-nav nav button').first().click();await page.locator('.stage-nav button').last().click();await page.getByRole('button',{name:'查看阅读与引用详情',exact:true}).click();await page.locator('.detail-usage button').first().click();check('node opens reader operation',await page.locator('.journey-scene').getAttribute('data-step')==='reader');
 check('no browser errors',errors.length===0);check('no business or external requests',requests.length===0);
 await writeFile(path.join(out,'journey-verification.json'),JSON.stringify({checks,errors,requests,scope:'Independent presentation and sample UI states only. No live business writes.'},null,2));
}finally{await browser.close()}
