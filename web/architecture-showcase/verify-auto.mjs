import {chromium} from '../node_modules/playwright/index.mjs';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(here,'../../output/playwright/architecture-showcase-v6');await mkdir(out,{recursive:true});
const journeys=JSON.parse(await readFile(path.join(here,'journeys.json'),'utf8'));
const tour=JSON.parse(await readFile(path.join(here,'overview-tour.json'),'utf8'));
const checks=[],errors=[],requests=[];const check=(name,value)=>{assert.ok(value,name);checks.push(name);console.log('PASS',name)};
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080}});
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5198')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))requests.push(r.url())});
const state=()=>page.locator('.presentation').evaluate(e=>({...e.dataset,playing:e.classList.contains('playing')}));
try{
 await page.clock.install({time:new Date('2026-11-07T12:00:00Z')});
 await page.goto('http://127.0.0.1:5198');await page.evaluate(()=>document.fonts.ready);
 await page.clock.pauseAt(new Date('2026-11-07T12:00:02Z'));
 check('starts automatically at overview',(await state()).playing&&(await state()).scene==='overview');
 check('no play-flow button',await page.getByText('播放流程',{exact:true}).count()===0);
 await page.locator('.scene-nav nav button').first().click();await page.clock.runFor(3100);
 const before=await state();await page.locator('h1').click();const clicked=await state();
 check('click resets dwell without rewinding animation',+clicked.dwell>.99&&Math.abs(+clicked.progress- +before.progress)<.02);
 await page.clock.runFor(1600);check('click extends current step',(await state()).stage==='0');
 await page.locator('h1').hover();const hoverBefore=await state();await page.mouse.move(15,15);check('hover does not reset dwell',+(await state()).dwell<=+hoverBefore.dwell+.01);
 await page.clock.runFor(1700);check('continues after refreshed dwell',(await state()).stage==='1');
 check('bottom timeline and dwell strip removed',await page.getByRole('slider').count()===0&&await page.locator('.playback-rail,.auto-dwell').count()===0);
 await page.locator('.scene-nav nav button').first().click();await page.clock.fastForward(tour.opening+40);await page.clock.runFor(40);
 for(let i=0;i<tour.modules.length;i++){
  const module=tour.modules[i];check(`tour directly focuses ${module.id}`,(await state()).tourPhase==='focus'&&await page.locator(`[data-node="${module.id}"].selected`).count()===1);
  check(`tour has no simulated mouse for ${module.id}`,await page.locator('.overview-pointer,.demo-pointer').count()===0);
  check(`tour moves card before details for ${module.id}`,await page.locator('.details').count()===0&&!(await page.locator('.graph-camera').getAttribute('style')).includes('translate(0px, 0px)'));
  await page.clock.fastForward(tour.focus+50);await page.clock.runFor(40);
  check(`tour opens ${module.id}`,(await state()).tourNode===module.id&&(await page.locator('.details h2').innerText())===module.label);
  check(`tour exposes children of ${module.id}`,await page.locator('.details .child-list button').count()>0);
  check(`tour panel fits ${module.id}`,await page.locator('.detail-scroll').evaluate(e=>e.scrollHeight<=e.clientHeight+2));
  if(i===0){const position=(await state()).progress;await page.locator('.details h2').click();check('click within automatic detail preserves animation',(await state()).progress===position&&(await state()).dwell==='1.000');await page.clock.runFor(7000);check('automatic detail keeps reading time',await page.locator('.details').count()===1);await page.locator('.details h2').click();await page.clock.runFor(2000);check('automatic detail click extends reading',await page.locator('.details').count()===1);await page.screenshot({path:path.join(out,'overview-auto-detail-1920.png')});}
  await page.clock.fastForward(tour.detail+50);await page.clock.runFor(40);
  check(`tour returns after ${module.id}`,(await state()).tourPhase==='return'&&await page.locator('.details').count()===0);
  check(`camera restores after ${module.id}`,(await page.locator('.graph-camera').getAttribute('style')).includes('translate(0px, 0px)'));
  await page.clock.fastForward(tour.return+50);await page.clock.runFor(40);
 }
 check('six modules finish at full overview',(await state()).tourPhase==='overview'&&(await state()).stage==='19');
 await page.clock.fastForward(tour.closing+50);await page.clock.runFor(40);
 check('overview reaches website pages',(await state()).scene==='sitemap');
 check('website pages renamed',(await page.locator('.scene-nav').innerText()).includes('网站页面')&&!(await page.locator('.scene-nav').innerText()).includes('页面地图'));
 check('four complete cards',await page.locator('.map-group').evaluateAll(nodes=>nodes.length===4&&nodes.every(e=>{const c=getComputedStyle(e);return ['Top','Right','Bottom','Left'].every(s=>parseFloat(c['border'+s+'Width'])>=1)})));
 for(let i=0;i<4;i++){
  await page.clock.fastForward(4250);await page.clock.runFor(40);
  check(`website card ${i+1} highlights alone`,await page.locator('.map-group.current-card').count()===1&&await page.locator('.map-group').nth(i).getAttribute('aria-current')==='step');
  check(`website card ${i+1} stays inside canvas`,await page.locator('.map-group').evaluateAll(a=>a.every(e=>e.scrollHeight<=e.clientHeight+1&&e.getBoundingClientRect().bottom<document.querySelector('.speaker-note').getBoundingClientRect().top)));
  if(i===1)await page.screenshot({path:path.join(out,'website-cards-1920.png')});
 }
 await page.clock.fastForward(4250);await page.clock.runFor(40);check('website returns to all cards',await page.locator('.map-group.all-visible').count()===4);
 await page.clock.fastForward(4250);await page.clock.runFor(40);check('website pages continue to use demonstration',(await state()).scene==='workflow');

 const visited=[];
 for(let ji=0;ji<journeys.length;ji++)for(let si=0;si<journeys[ji].steps.length;si++){
  const value=await state();check(`automatic order ${journeys[ji].id}/${journeys[ji].steps[si].id}`,value.scene==='workflow'&&+value.journey===ji&&+value.stage===si);
  visited.push([ji,si]);await page.clock.runFor(40);await page.clock.fastForward(journeys[ji].steps[si].duration+80);await page.clock.runFor(40);
 }
 check('all workflows reach underlying architecture',(await state()).scene==='technology');
 for(let si=0;si<4;si++){await page.clock.fastForward(4250);await page.clock.runFor(40)}
 check('architecture reaches brand',(await state()).scene==='design');
 for(let si=0;si<3;si++){await page.clock.fastForward(4250);await page.clock.runFor(40)}
 check('last scene loops to overview',(await state()).scene==='overview'&&(await state()).stage==='0');
 await page.locator('.scene-nav nav button').nth(2).click();
 check('use demonstration still has simulated mouse',await page.locator('.demo-pointer').count()===1);
 await page.getByRole('button',{name:'暂停自动切换'}).click();const paused=await state();await page.clock.fastForward(12000);check('accessible pause holds progress',(await state()).stage===paused.stage&&(await state()).progress===paused.progress);
 await page.getByRole('button',{name:'恢复自动切换'}).click();await page.clock.runFor(500);check('resume continues',+(await state()).progress>+paused.progress);
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>document.querySelector('.presentation').classList.contains('reduced'));await page.clock.runFor(40);check('reduced motion removes pointer',await page.locator('.demo-pointer').isHidden());await page.clock.fastForward(5000);await page.clock.runFor(40);check('reduced motion still advances',(await state()).stage!=='0');
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.locator('.scene-nav nav button').first().click();await page.getByRole('button',{name:'返回全局',exact:true}).click();await page.getByRole('button',{name:'查看发现与检索详情',exact:true}).click();await page.clock.runFor(7000);check('detail gets reading time',await page.locator('.details').count()===1);await page.locator('.details h2').click();await page.clock.runFor(2000);check('click extends detail',await page.locator('.details').count()===1);await page.clock.runFor(6100);check('detail closes and resumes automatically',await page.locator('.details').count()===0&&(await state()).scene==='overview'&&(await state()).stage==='1');
 await page.clock.fastForward(tour.focus+50);await page.clock.runFor(40);await page.getByRole('button',{name:'返回全局',exact:true}).click();check('return control preserves remaining tour',(await state()).tourPhase==='return');await page.clock.fastForward(tour.return+50);await page.clock.runFor(40);check('tour continues to next module after return',(await state()).stage==='4');
 check('public removes evidence controls',await page.getByRole('button',{name:'查看来源',exact:true}).count()===0);
 const json=await (await page.request.get('http://127.0.0.1:5198/architecture.json')).json();check('public data has no sources or routes',Object.keys(json.sources).length===0&&json.routes.length===0&&json.nodes.every(n=>!n.sources.length&&!n.routes.length));
 check('public evidence CSV unavailable',(await page.request.get('http://127.0.0.1:5198/evidence-index.csv')).status()===404);
 const bundle=await (await page.request.get('http://127.0.0.1:5198/app.js')).text();check('public bundle contains no internal paths',!/(?:SiteHeader|AdminShell|ReaderShell|\/admin\/|(?:web|api|docs)\/[\w/\[\].-]+|192\.168\.\d+\.|\b\w[\w-]*\.(?:tsx|py|md)\b)/.test(bundle));
 check('no browser errors',!errors.length);check('no external or business requests',!requests.length);
 await page.clock.resume();await page.getByRole('button',{name:'暂停自动切换'}).click();await page.screenshot({path:path.join(out,'public-auto-1920.png')});
 await writeFile(path.join(out,'auto-verification.json'),JSON.stringify({checks,visited,errors,requests},null,2));
}finally{await browser.close()}
