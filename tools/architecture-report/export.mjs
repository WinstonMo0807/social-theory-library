import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {chromium} from '../../web/node_modules/@playwright/test/index.mjs';
import {scenes} from './data/architecture.source.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));

export async function exportScene({origin='http://127.0.0.1:5274',scene='overview',phase,kind='png',outDir=path.join(here,'exports')}){
  const definition=scenes.find(s=>s.id===scene);
  if(!definition||!['png','video'].includes(kind))throw Error('Invalid scene or export kind.');
  phase=Number.isInteger(phase)?Math.min(definition.phases.length-1,Math.max(0,phase)):definition.phases.length-1;
  await fs.mkdir(outDir,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const filename=path.join(outDir,`${scene}-${kind==='png'?'3840.png':'demo.webm'}`);
  let context;
  try{
    context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:kind==='png'?2:1,reducedMotion:kind==='png'?'reduce':'no-preference',...(kind==='video'?{recordVideo:{dir:outDir,size:{width:1920,height:1080}}}:{})});
    const page=await context.newPage();
    await page.goto(`${origin}/?capture=1&motion=${kind==='video'?1:0}&scene=${scene}&phase=${kind==='video'?0:phase}`,{waitUntil:'networkidle'});
    await page.evaluate(()=>document.fonts.ready);
    await page.locator('.stage').waitFor();
    if(kind==='png')await page.screenshot({path:filename});
    else{
      await page.keyboard.press('Space');
      await page.waitForTimeout(definition.phases.length*3600+1600);
      const video=page.video();await context.close();context=null;await video.saveAs(filename);await video.delete();
    }
    return filename;
  }finally{await context?.close();await browser.close();}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const scene=process.argv[2]||'all',kind=process.argv[3]||'png';
  for(const item of scene==='all'?scenes:[scenes.find(s=>s.id===scene)]){
    if(!item)throw Error('Unknown scene');
    console.log(await exportScene({scene:item.id,kind,outDir:path.join(here,'../../output/playwright/architecture-report/exports')}));
  }
}
