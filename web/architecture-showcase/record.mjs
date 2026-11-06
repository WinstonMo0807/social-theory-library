import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));const out=path.resolve(here,'../../output/playwright/architecture-showcase-v6/video');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},recordVideo:{dir:out,size:{width:1920,height:1080}}});
const page=await context.newPage();
await page.goto('http://127.0.0.1:5198',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
// Capture one untouched loop: no synthetic clicks that would extend dwell time.
const deadline=Date.now()+360000;let sawBrand=false,last='';const visited=[];
while(Date.now()<deadline){
 const current=await page.locator('.presentation').evaluate(el=>`${el.dataset.scene}/${el.dataset.journey}/${el.dataset.stage}`);
 if(current!==last){visited.push(current);console.log('Recording',current);last=current;}
 if(current.startsWith('design/'))sawBrand=true;
 if(sawBrand&&current==='overview/0/0')break;
 await page.waitForTimeout(500);
}
assert.ok(sawBrand&&last==='overview/0/0','Presentation did not complete one automatic loop');
await page.waitForTimeout(1000);const video=page.video();await context.close();
const result=path.join(out,'STL-architecture-v6-1080p.webm');await video.saveAs(result);await video.delete();
const playback=await browser.newPage({viewport:{width:1920,height:1080}});await playback.goto(pathToFileURL(result).href);await playback.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
const info=await playback.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration}));assert.equal(info.width,1920);assert.equal(info.height,1080);assert.ok(info.duration>280&&Number.isFinite(info.duration));
await playback.locator('video').evaluate(v=>{v.pause();v.currentTime=24});await playback.waitForTimeout(400);await playback.screenshot({path:path.join(out,'playback-proof.png')});
await writeFile(path.join(out,'video-verification.json'),JSON.stringify({...info,visited},null,2));
await browser.close();console.log('Saved and decoded 1080p WebM walkthrough.',JSON.stringify(info));
