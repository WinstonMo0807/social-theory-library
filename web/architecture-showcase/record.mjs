import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, rename } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));const out=path.resolve(here,'../../output/playwright/architecture-showcase/video');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},recordVideo:{dir:out,size:{width:1920,height:1080}}});
const page=await context.newPage();
await page.goto('http://127.0.0.1:5196',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
for(let scene=0;scene<6;scene++){
 await page.locator('.scene-nav nav button').nth(scene).click();
 const stages=await page.locator('.stage-nav button').count();
 for(let stage=0;stage<stages;stage++){await page.locator('.stage-nav button').nth(stage).click();await page.waitForTimeout(1900);}
 if(scene===0){await page.getByRole('button',{name:'查看发现与检索详情',exact:true}).click();await page.waitForTimeout(2300);await page.keyboard.press('Escape');}
 await page.waitForTimeout(600);
}
await page.waitForTimeout(1500);const video=page.video();await context.close();
const result=path.join(out,'STL-architecture-1080p.webm');await video.saveAs(result);
const playback=await browser.newPage({viewport:{width:1920,height:1080}});await playback.goto(pathToFileURL(result).href);await playback.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
const info=await playback.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration}));assert.equal(info.width,1920);assert.equal(info.height,1080);assert.ok(info.duration>30&&Number.isFinite(info.duration));
await playback.locator('video').evaluate(v=>{v.pause();v.currentTime=24});await playback.waitForTimeout(400);await playback.screenshot({path:path.join(out,'playback-proof.png')});
await browser.close();console.log('Saved and decoded 1080p WebM walkthrough.',JSON.stringify(info));
