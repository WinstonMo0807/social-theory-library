import {chromium} from '../node_modules/playwright/index.mjs';
import {mkdir,readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));const out=path.resolve(here,'../../output/playwright/architecture-showcase-v6/4k');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1920,height:1080},acceptDownloads:true});
await page.goto('http://127.0.0.1:5198',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);await page.getByRole('button',{name:'暂停自动切换'}).click();
for(let scene=0;scene<5;scene++){
 await page.locator('.scene-nav nav button').nth(scene).click();if(scene===0)await page.getByRole('button',{name:'返回全局',exact:true}).click();else if(scene===2)await page.getByRole('combobox',{name:'选择操作步骤'}).selectOption('9');else await page.locator('.stage-nav button').last().click();await page.waitForTimeout(700);
 await page.locator('.masthead').getByRole('button',{name:'导出',exact:true}).click();const download=page.waitForEvent('download');await page.getByRole('button',{name:/^导出 PNG/}).click();const file=await download;const destination=path.join(out,`${scene+1}-${file.suggestedFilename()}`);await file.saveAs(destination);
 const bytes=await readFile(destination);assert.equal(bytes.readUInt32BE(16),3840);assert.equal(bytes.readUInt32BE(20),2160);console.log('Exported',path.basename(destination),'3840 × 2160');
 if(scene===0){await page.locator('.masthead').getByRole('button',{name:'导出',exact:true}).click();const dl=page.waitForEvent('download');await page.getByRole('button',{name:/^导出 SVG/}).click();const svg=await dl;await svg.saveAs(path.join(out,svg.suggestedFilename()));console.log('Exported standalone SVG');}
}
for(const [journey,stage,label] of [[0,0,'discovery-question'],[0,8,'discovery-summary'],[0,13,'discovery-selection'],[0,19,'discovery-export'],[1,6,'publishing-outline'],[2,4,'research-materials']]){
 await page.goto(`http://127.0.0.1:5198/?scene=2&journey=${journey}&stage=${stage}`,{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'暂停自动切换'}).click();await page.getByRole('combobox',{name:'选择操作步骤'}).selectOption(String(stage));await page.waitForTimeout(600);await page.locator('.masthead').getByRole('button',{name:'导出',exact:true}).click();const download=page.waitForEvent('download');await page.getByRole('button',{name:/^导出 PNG/}).click();const file=await download;const destination=path.join(out,`journey-${label}-3840.png`);await file.saveAs(destination);const bytes=await readFile(destination);assert.equal(bytes.readUInt32BE(16),3840);assert.equal(bytes.readUInt32BE(20),2160);console.log('Exported',label,'3840 × 2160');
}
for(const [scene,stage,label] of [[0,2,'overview-discovery'],[0,11,'overview-research'],[1,2,'website-reading-card']]){
 await page.goto(`http://127.0.0.1:5198/?scene=${scene}&stage=${stage}`,{waitUntil:'networkidle'});await page.getByRole('button',{name:'暂停自动切换'}).click();await page.waitForTimeout(650);
 await page.locator('.masthead').getByRole('button',{name:'导出',exact:true}).click();const ready=page.waitForEvent('download');await page.getByRole('button',{name:/^导出 PNG/}).click();const file=await ready;await file.saveAs(path.join(out,`${label}-3840.png`));console.log('Exported',label);
}
await browser.close();
