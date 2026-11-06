import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(here,'../../output/playwright/architecture-showcase-v2');
const journeys=JSON.parse(await readFile(path.join(here,'journeys.json'),'utf8'));
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},acceptDownloads:true});
const errors=[],requests=[],checks=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5196')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))requests.push(r.url())});
const check=(name,value)=>{assert.ok(value,name);checks.push(name);console.log('PASS',name)};
try{
 await page.goto('http://127.0.0.1:5196/',{waitUntil:'networkidle'});
 await page.evaluate(()=>document.fonts.ready);
 check('default opens usage demonstration',await page.locator('.journey-scene').count()===1);
 for(let ji=0;ji<journeys.length;ji++){
  const j=journeys[ji];await page.getByRole('tab',{name:j.name,exact:true}).click();
  for(let si=0;si<j.steps.length;si++){
   const step=j.steps[si];await page.locator('.stage-nav button').nth(si).click();
   check(`${j.id}/${step.id}: complete layout and readable controls`,await page.evaluate(()=>{
    const panel=document.querySelector('.journey-explanation'),stage=document.querySelector('.demo-surface'),rail=document.querySelector('.playback-rail'),note=document.querySelector('.speaker-note');
    const p=panel.getBoundingClientRect(),n=note.getBoundingClientRect();
    const children=[...stage.querySelector('.demo-panel').children];
    return panel.scrollHeight<=panel.clientHeight+1&&children.every(el=>el.scrollHeight<=stage.clientHeight+1)&&p.bottom<n.top&&n.bottom<rail.getBoundingClientRect().top;
   }));
   await page.getByRole('button',{name:'查看实现详情',exact:true}).click();
   check(`${j.id}/${step.id}: source and contract available`,(await page.locator('.step-inspector .source-list li').count())===step.sources.length&&(await page.locator('.step-contract').innerText()).includes(step.contract));
   await page.keyboard.press('Escape');
   await page.locator('h1').click();
   if(si===0||si===2||si===j.steps.length-1)await page.screenshot({path:path.join(out,`${j.id}-${step.id}-1920.png`)});
  }
 }
 await page.getByRole('tab',{name:'检索与引用',exact:true}).click();
 await page.getByRole('button',{name:'播放当前场景',exact:true}).click();
 await page.waitForTimeout(600);const early=await page.locator('.demo-question').innerText();
 await page.waitForTimeout(1200);const later=await page.locator('.demo-question').innerText();
 check('playback changes actual input content',later.length>early.length);
 await page.getByRole('button',{name:'暂停播放',exact:true}).click();
 const position=await page.getByRole('slider',{name:'播放进度'}).inputValue();
 await page.waitForTimeout(1000);
 check('pause freezes content and timeline',await page.getByRole('slider',{name:'播放进度'}).inputValue()===position&&await page.locator('.demo-question').innerText()===later);
 await page.getByRole('button',{name:'播放当前场景',exact:true}).click();await page.waitForTimeout(450);
 check('resume continues existing position',Number(await page.getByRole('slider',{name:'播放进度'}).inputValue())>Number(position));
 await page.getByRole('button',{name:'暂停播放',exact:true}).click();
 const scrub=async value=>page.getByRole('slider',{name:'播放进度'}).fill(String(value));
 await scrub(15000);check('scrub selects evidence at precise time',await page.locator('.journey-scene').getAttribute('data-step')==='evidence');
 await page.getByRole('button',{name:'重新播放当前阶段',exact:true}).click();await page.waitForTimeout(200);
 check('replay restarts the same step',await page.locator('.journey-scene').getAttribute('data-step')==='evidence'&&Number(await page.getByRole('slider',{name:'播放进度'}).inputValue())<13500);
 await page.getByRole('button',{name:'暂停播放',exact:true}).click();
 await scrub(32300);await page.getByRole('button',{name:'播放当前场景',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.presentation')?.classList.contains('paused'));
 check('final step stops without scene jump',await page.locator('.journey-scene').getAttribute('data-step')==='citation'&&await page.locator('.presentation').getAttribute('data-scene')==='workflow');
 await page.getByRole('tab',{name:'检索与引用',exact:true}).focus();await page.keyboard.press('ArrowRight');
 check('tab keyboard selects next journey',await page.getByRole('tab',{name:'入库与发布',exact:true}).getAttribute('aria-selected')==='true');
 await page.getByRole('button',{name:'全屏展示',exact:true}).click();
 check('journey fullscreen enters',await page.evaluate(()=>!!document.fullscreenElement));
 await page.getByRole('button',{name:'查看实现详情',exact:true}).click();check('contract dialog available in fullscreen',await page.locator('.step-dialog').isVisible());await page.keyboard.press('Escape');
 await page.screenshot({path:path.join(out,'journey-fullscreen.png')});await page.getByRole('button',{name:'退出全屏',exact:true}).click();
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(50);await page.locator('.stage-nav button').nth(2).click();
 check('reduced motion shows complete frame',await page.getByRole('button',{name:'播放当前场景',exact:true}).isDisabled()&&await page.locator('.journey-scene').getAttribute('data-step')==='outline');
 await page.emulateMedia({reducedMotion:'no-preference'});
 for(const [width,height] of [[1366,768],[1440,900],[1280,720]]){await page.setViewportSize({width,height});await page.waitForTimeout(80);check(`journey fits ${width}x${height}`,await page.locator('.presentation').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}));}
 await page.setViewportSize({width:1920,height:1080});
 await page.locator('.scene-nav nav button').first().click();await page.locator('.stage-nav button').last().click();await page.getByRole('button',{name:'查看阅读与引用详情',exact:true}).click();
 await page.locator('.detail-usage button').first().click();check('architecture node opens matching usage step',await page.locator('.journey-scene').getAttribute('data-step')==='reader');
 check('no browser errors',errors.length===0);check('no external or business requests',requests.length===0);
 const backup=await browser.newPage({viewport:{width:1920,height:1080}});await backup.goto('http://127.0.0.1:5197/?scene=0&stage=3',{waitUntil:'networkidle'});
 check('STC backup runs independently with original behavior',await backup.locator('h1').innerText()==='书库的功能与协作关系'&&await backup.locator('.journey-scene').count()===0);
 await backup.screenshot({path:path.join(out,'v1-STC-backup.png')});await backup.close();
 await writeFile(path.join(out,'journey-verification.json'),JSON.stringify({checks,errors,requests,scope:'Independent presentation only; no real business operations.'},null,2));
}finally{await browser.close()}
