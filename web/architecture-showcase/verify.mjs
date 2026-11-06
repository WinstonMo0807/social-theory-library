import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir,writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));const out=path.resolve(here,'../../output/playwright/architecture-showcase-v3');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},acceptDownloads:true});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const external=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5196')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))external.push(r.url())});
const results=[];const check=(name,value)=>{assert.ok(value,name);results.push(name);console.log('PASS',name)};
try{
 await page.goto('http://127.0.0.1:5196/?scene=0&stage=3',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
 check('presentation renders',await page.locator('h1').innerText()==='书库的功能与协作关系');
 for(let scene=0;scene<5;scene++){
  await page.locator('.scene-nav nav button').nth(scene).click();
  if(scene===2)await page.getByRole('combobox',{name:'选择操作步骤'}).selectOption('19');else await page.locator('.stage-nav button').last().click();
  await page.waitForTimeout(650);
  await page.screenshot({path:path.join(out,`scene-${scene+1}-1920.png`)});
  check(`scene ${scene+1} text stays within stage`,await page.locator('.main-scene').evaluate(el=>el.scrollWidth<=el.clientWidth+2));
  check(`scene ${scene+1} note clears controls`,await page.locator('.speaker-note').evaluate(el=>el.getBoundingClientRect().bottom<document.querySelector('.transport').getBoundingClientRect().top));
 }
 await page.locator('.scene-nav nav button').nth(0).click();await page.locator('.stage-nav button').last().click();
 await page.getByRole('button',{name:'查看发现与检索详情',exact:true}).click();
 await page.waitForTimeout(650);check('node drilldown opens sources',await page.locator('.details .source-list li').count()>0);
 await page.screenshot({path:path.join(out,'node-detail-1920.png')});
 check('detail content stays inside panel',await page.locator('.detail-scroll').evaluate(el=>el.getBoundingClientRect().bottom<=el.closest('.details').getBoundingClientRect().bottom));
 await page.locator('.details .child-list').getByRole('button',{name:/观点检索/}).click();check('child drilldown works',(await page.locator('.details h2').innerText())==='观点检索');
 await page.keyboard.press('Escape');check('escape returns global',await page.locator('.details').count()===0);
 await page.getByRole('button',{name:'查看来源',exact:true}).click();await page.getByPlaceholder('搜索模块、路径或源码').fill('discovery.client');check('evidence search works',await page.locator('.evidence-results article').count()>0);
 await page.getByRole('button',{name:'关闭来源索引',exact:true}).click();
 await page.locator('.stage-nav button').first().click();
 await page.getByRole('button',{name:'播放当前场景',exact:true}).click();await page.waitForTimeout(700);await page.getByRole('button',{name:'暂停播放',exact:true}).click();
 const paused=await page.locator('.presentation').getAttribute('data-stage');await page.waitForTimeout(4500);check('pause preserves stage',await page.locator('.presentation').getAttribute('data-stage')===paused);
 await page.keyboard.press('ArrowRight');check('keyboard advances stage',await page.locator('.presentation').getAttribute('data-stage')==='1');
 await page.getByRole('button',{name:'重新播放当前阶段',exact:true}).click();check('replay preserves current stage',await page.locator('.presentation').getAttribute('data-stage')==='1');
 await page.getByRole('button',{name:'全屏展示',exact:true}).click();check('native fullscreen entered',await page.evaluate(()=>Boolean(document.fullscreenElement)));await page.screenshot({path:path.join(out,'fullscreen-1920.png')});await page.getByRole('button',{name:'退出全屏',exact:true}).click();
 for(const [width,height] of [[1440,900],[1366,768],[1280,720],[1920,1080]]){await page.setViewportSize({width,height});await page.waitForTimeout(150);check(`fits ${width}x${height}`,await page.locator('.presentation').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}));}
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>document.querySelector('.presentation')?.classList.contains('reduced'));check('reduced motion disables timed playback',await page.getByRole('button',{name:'播放当前场景',exact:true}).isDisabled());await page.keyboard.press('ArrowRight');check('reduced motion manual navigation works',await page.locator('.presentation').getAttribute('data-stage')==='2');await page.emulateMedia({reducedMotion:'no-preference'});
 await page.locator('.stage-nav button').last().click();await page.waitForTimeout(700);
 await page.locator('.masthead').getByRole('button',{name:'导出',exact:true}).click();const downloaded=page.waitForEvent('download',{timeout:30000});await page.getByRole('button',{name:/^导出 PNG/}).click();const file=await downloaded;await file.saveAs(path.join(out,'STL-overview-3840.png'));check('4K PNG export succeeds',!(await file.failure()));
 check('no browser JS errors',errors.length===0);check('no external requests or business API calls',external.length===0);
 await writeFile(path.join(out,'verification.json'),JSON.stringify({results,errors,external,scope:'Only the independent presentation; does not certify STL business workflows.'},null,2));
}finally{await browser.close();}
