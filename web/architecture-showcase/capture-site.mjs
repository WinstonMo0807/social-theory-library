// Anonymous, read-only observation. Never submit forms or initiate a search.
import { chromium } from '../node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(here,'../../output/playwright/architecture-showcase/site');
const base=process.argv[2];
if(!base) throw new Error('Provide the authorized preview origin as an argument. It is not saved in presentation data.');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page=await context.newPage(); const observations=[];
for(const [route,name] of [['/','home'],['/welcome','welcome'],['/theories','theories'],['/scholars','scholars'],['/topics','topics'],['/recommendations','curation'],['/explore','gate']]){
 try{
  const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:30000});
  await page.screenshot({path:path.join(out,name+'.png')});
  const destination=new URL(page.url());
  observations.push({route,status:response.status(),destination:destination.pathname,title:await page.title(),scope:'匿名 GET 与页面渲染；未提交业务操作',screenshot:'/site/'+name+'.png',observedAt:new Date().toISOString()});
  console.log(route,response.status(),destination.pathname);
 }catch(e){observations.push({route,status:'unverified',scope:'页面观察未完成',error:e.name});console.log(route,e.name);}
}
await writeFile(path.join(here,'runtime-evidence.json'),JSON.stringify(observations,null,2)+'\n');
await browser.close();
