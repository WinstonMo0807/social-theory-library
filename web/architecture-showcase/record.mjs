import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));const out=path.resolve(here,'../../output/playwright/architecture-showcase-v2/video');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},recordVideo:{dir:out,size:{width:1920,height:1080}}});
const page=await context.newPage();
await page.goto('http://127.0.0.1:5196',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
for(const name of ['检索与引用','入库与发布','私人研究']){
 await page.getByRole('tab',{name,exact:true}).click();await page.getByRole('button',{name:'播放当前场景',exact:true}).click();await page.locator('h1').click();
 await page.waitForFunction(()=>document.querySelector('.presentation')?.classList.contains('paused'),{},{timeout:45000});await page.waitForTimeout(1200);console.log('Recorded complete workflow:',name);
}
await page.getByRole('button',{name:'查看调用与字段',exact:true}).click();await page.waitForTimeout(2800);await page.keyboard.press('Escape');
for(const scene of [0,1,3,4,5]){
 await page.locator('.scene-nav nav button').nth(scene).click();await page.locator('.stage-nav button').last().click();await page.locator('h1').click();await page.waitForTimeout(2400);
}
await page.waitForTimeout(1500);const video=page.video();await context.close();
const result=path.join(out,'STL-architecture-v2-1080p.webm');await video.saveAs(result);await video.delete();
const playback=await browser.newPage({viewport:{width:1920,height:1080}});await playback.goto(pathToFileURL(result).href);await playback.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
const info=await playback.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration}));assert.equal(info.width,1920);assert.equal(info.height,1080);assert.ok(info.duration>90&&Number.isFinite(info.duration));
await playback.locator('video').evaluate(v=>{v.pause();v.currentTime=24});await playback.waitForTimeout(400);await playback.screenshot({path:path.join(out,'playback-proof.png')});
await writeFile(path.join(out,'video-verification.json'),JSON.stringify(info,null,2));
await browser.close();console.log('Saved and decoded 1080p WebM walkthrough.',JSON.stringify(info));
