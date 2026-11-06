import {chromium,expect} from '../../web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {scenes} from './data/architecture.source.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const out=path.join(root,'output/playwright/architecture-report');await fs.mkdir(out,{recursive:true});
const origin='http://127.0.0.1:5274';
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080}});
const page=await context.newPage();
const issues=[],checks=[];
page.on('pageerror',error=>issues.push(error.message));
page.on('response',r=>{if(r.status()>=400)issues.push(`${r.status()} ${new URL(r.url()).pathname}`);});
try{
  for(const scene of scenes){
    await page.goto(`${origin}/?scene=${scene.id}&phase=${scene.phases.length-1}`,{waitUntil:'networkidle'});
    await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(650);
    await expect(page.locator('h1')).toContainText(scene.title.replaceAll('\n',''));
    const geometry=await page.evaluate(()=>{
      const stage=document.querySelector('.stage').getBoundingClientRect();
      const elements=[...document.querySelectorAll('.map-node,.sitemap-node,.status-item,.phase-story,.slide-footer')];
      return {overflow:document.documentElement.scrollWidth>innerWidth,clipped:elements.filter(e=>{const r=e.getBoundingClientRect();return r.right>stage.right+1||r.bottom>stage.bottom-8||r.left<stage.left-1||e.scrollHeight>e.clientHeight+2;}).map(e=>e.textContent)};
    });
    checks.push({scene:scene.id,geometry});
    assert.equal(geometry.overflow,false,scene.id+' viewport overflow');
    await page.screenshot({path:path.join(out,`${scene.id}-1920.png`)});
  }
  assert.deepEqual(checks.flatMap(c=>c.geometry.clipped.map(text=>({scene:c.scene,text}))),[],'clipped scene content');
  await page.goto(origin+'/?scene=overview&phase=2',{waitUntil:'networkidle'});await page.waitForTimeout(600);
  await page.getByRole('button',{name:'查看私人研究',exact:true}).click();
  await expect(page.locator('.focus-panel h2')).toHaveText('私人研究');
  await page.getByRole('button',{name:'查看持续研究',exact:true}).click();
  await expect(page.locator('.focus-panel h2')).toHaveText('持续研究');
  await page.getByRole('button',{name:'返回上一层'}).click();await expect(page.locator('.focus-panel h2')).toHaveText('私人研究');
  await page.screenshot({path:path.join(out,'node-focus-1920.png')});
  await page.keyboard.press('Escape');await expect(page.locator('.focus-panel')).toHaveCount(0);
  await page.getByRole('button',{name:'路由索引',exact:true}).click();
  await page.getByPlaceholder('搜索路径、分组或源码').fill('/welcome');
  await expect(page.locator('.route-list>div')).toHaveCount(2);
  await page.keyboard.press('Escape');await expect(page.locator('dialog')).not.toBeVisible();
  await page.getByRole('button',{name:'播放',exact:true}).click();
  await expect(page.locator('.stage')).toHaveAttribute('data-phase','0');
  await page.waitForTimeout(500);await page.getByRole('button',{name:'暂停',exact:true}).click();
  const pausedPhase=await page.locator('.stage').getAttribute('data-phase');
  const time=await page.evaluate(()=>document.querySelector('.stage').getAnimations({subtree:true}).map(a=>({state:a.playState,time:a.currentTime})));
  await page.waitForTimeout(3850);assert.equal(await page.locator('.stage').getAttribute('data-phase'),pausedPhase);
  assert.ok(time.every(a=>a.state==='paused'||a.state==='finished'));
  await page.getByRole('button',{name:'下一阶段',exact:true}).click();
  await expect(page.locator('.stage')).toHaveAttribute('data-phase','1');
  await page.getByRole('button',{name:'重播当前阶段',exact:true}).click();await page.waitForTimeout(1800);
  await expect(page.locator('.stage')).toHaveAttribute('data-phase','1');await expect(page.locator('.stage')).toHaveAttribute('data-playing','false');
  await page.keyboard.press('3');await expect(page.locator('.stage')).toHaveAttribute('data-scene','workflow');
  await page.keyboard.press('ArrowRight');await expect(page.locator('.stage')).toHaveAttribute('data-phase','1');
  await page.getByRole('button',{name:'全屏展示',exact:true}).click();assert.equal(await page.evaluate(()=>Boolean(document.fullscreenElement)),true);
  await page.screenshot({path:path.join(out,'fullscreen-1920.png')});await page.getByRole('button',{name:'退出全屏',exact:true}).click();
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[390,844]]){
    await page.setViewportSize({width,height});await page.goto(origin+'/?scene=sitemap&phase=2',{waitUntil:'networkidle'});await page.waitForTimeout(600);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(out,`sitemap-${width}.png`)});
  }
  await page.setViewportSize({width:1920,height:1080});await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto(origin+'/?scene=technology&phase=3',{waitUntil:'networkidle'});
  await expect(page.locator('.report-app')).toHaveClass(/reduced/);
  await page.getByRole('button',{name:'播放',exact:true}).click();
  assert.equal(await page.locator('.flow').first().evaluate(e=>getComputedStyle(e).display),'none');
  await page.getByRole('button',{name:'暂停',exact:true}).click();
  await page.getByRole('button',{name:'导出',exact:true}).click();
  const downloadPromise=page.waitForEvent('download',{timeout:60000});await page.getByRole('button',{name:/4K PNG/}).click();
  const download=await downloadPromise;await download.saveAs(path.join(out,'export-button-3840.png'));
  const png=await fs.readFile(path.join(out,'export-button-3840.png'));assert.equal(png.readUInt32BE(16),3840);assert.equal(png.readUInt32BE(20),2160);
  // Security checks target only this local presentation, not the STL business site.
  assert.equal((await context.request.get(origin+'/api/catalog/')).status(),404);
  assert.equal((await context.request.get(origin+'/.env')).status(),404);
  assert.equal((await context.request.post(origin+'/api/export',{headers:{Origin:'https://unrelated.invalid'},data:{}})).status(),403);
  assert.deepEqual(issues,[]);
  checks.push({controls:'node drilldown/back/Escape, route filter, pause freeze, replay-current, keyboard, fullscreen, reduced motion, PNG download',result:'passed'});
  await fs.writeFile(path.join(out,'verification.json'),JSON.stringify({checkedAt:new Date().toISOString(),browser:browser.version(),checks,issues,limits:'This validates the independent presentation only. No STL business workflow was executed.'},null,2));
  console.log('Presentation verification passed. Screenshots and verification.json written.');
}catch(error){await page.screenshot({path:path.join(out,'verification-failure.png')});await fs.writeFile(path.join(out,'verification-failure.json'),JSON.stringify({error:String(error),checks,issues},null,2));throw error;}
finally{await browser.close();}
