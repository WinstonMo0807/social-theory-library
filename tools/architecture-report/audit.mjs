import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import ts from '../../web/node_modules/typescript/lib/typescript.js';
import { nodes, relations, scenes, statusLabels } from './data/architecture.source.mjs';

export const here = path.dirname(fileURLToPath(import.meta.url));
export const root = path.resolve(here, '../..');
const posix = value => value.split(path.sep).join('/');
async function walk(dir) {
  return (await Promise.all((await fs.readdir(dir,{withFileTypes:true})).filter(e=>!['node_modules','.git','.next','dist'].includes(e.name)).map(async e=>e.isDirectory()?walk(path.join(dir,e.name)):[path.join(dir,e.name)]))).flat();
}
const read = file => fs.readFile(path.join(root,file),'utf8');
const sha = data => createHash('sha256').update(data).digest('hex');
const cache = new Map();
async function evidence(input) {
  let content=cache.get(input.file);
  if(content===undefined) { content=await read(input.file);cache.set(input.file,content); }
  const at=content.indexOf(input.anchor);
  if(at<0) throw Error(`Evidence anchor missing: ${input.file} :: ${input.anchor}`);
  return {...input,line:content.slice(0,at).split('\n').length,sha256:sha(content)};
}

const webFiles=(await Promise.all(['web/app','web/components','web/lib'].map(d=>walk(path.join(root,d))))).flat().filter(f=>/\.(tsx?|jsx?|mjs)$/.test(f));
const fileSet = new Set(webFiles);
const importEdges=[];
const rawLinks=[];
const routeFiles=webFiles.filter(f=>/[/\\]page\.tsx?$/.test(f));
const importsByFile=new Map();
for(const file of webFiles) {
  const code=await fs.readFile(file,'utf8');
  const ast=ts.createSourceFile(file,code,ts.ScriptTarget.Latest,true);
  const imports=[];
  const visit=node=>{
    if((ts.isImportDeclaration(node)||ts.isExportDeclaration(node))&&node.moduleSpecifier&&ts.isStringLiteral(node.moduleSpecifier)) imports.push({specifier:node.moduleSpecifier.text,line:ast.getLineAndCharacterOfPosition(node.getStart()).line+1});
    if(ts.isJsxAttribute(node)&&node.name.getText(ast)==='href'&&node.initializer&&ts.isStringLiteral(node.initializer)&&node.initializer.text.startsWith('/'))rawLinks.push({file:posix(path.relative(root,file)),href:node.initializer.text,line:ast.getLineAndCharacterOfPosition(node.getStart()).line+1});
    ts.forEachChild(node,visit);
  };visit(ast);
  for(const imp of imports) {
    const target=imp.specifier.startsWith('@/')?path.join(root,'web',imp.specifier.slice(2)):imp.specifier.startsWith('.')?path.resolve(path.dirname(file),imp.specifier):null;
    if(!target)continue;
    const resolved=[target,...['.ts','.tsx','.js','.jsx','/index.ts','/index.tsx'].map(e=>target+e)].find(p=>fileSet.has(path.normalize(p)));
    if(resolved)importEdges.push({from:posix(path.relative(root,file)),to:posix(path.relative(root,resolved)),line:imp.line});
  }
  importsByFile.set(file,imports);
}
const routes=[];
for(const file of routeFiles) {
  const source=posix(path.relative(root,file));
  const route='/'+posix(path.relative(path.join(root,'web/app'),path.dirname(file))).split('/').filter(p=>p&&!p.startsWith('(')).join('/');
  const code=await fs.readFile(file,'utf8');
  const redirects=[...code.matchAll(/redirect\(\s*["']([^"']+)["']/g)].map(m=>m[1]);
  const excluded=/^\/(policy|drawer-preview|interaction-preview|layout-preview)(\/|$)/.test(route);
  const preview=route.includes('/preview');
  routes.push({route,source,group:excluded?(route.startsWith('/policy')?'已暂停模块':'视觉参考入口'):route.startsWith('/admin')?(preview?'管理工作区 · 预览':'管理工作区'):route.startsWith('/account')?'私人研究':/^\/(reader|explore)/.test(route)?'登录阅读':'公共与账户入口',excluded,preview,redirects,imports:importEdges.filter(e=>e.from===source).map(e=>e.to),sha256:sha(code)});
}
routes.sort((a,b)=>a.route.localeCompare(b.route));
const apiDeclarations=[];
for(const file of ['api/config/urls.py','api/accounts/urls.py','api/catalog/urls.py','api/ingestion/urls.py','api/reading/urls.py','api/distribution/urls.py']) {
  const code=await read(file);
  for(const m of code.matchAll(/(?:path|router\.register)\(\s*["']([^"']*)["']/g))apiDeclarations.push({file,pattern:m[1],line:code.slice(0,m.index).split('\n').length});
}
await fs.mkdir(path.join(here,'data'),{recursive:true});
const probeIndex=process.argv.indexOf('--probe');
if(probeIndex>=0){
  const base=new URL(process.argv[probeIndex+1]);
  if(!['http:','https:'].includes(base.protocol)||base.username||base.password)throw Error('Use a plain preview origin.');
  const {chromium}=await import('../../web/node_modules/@playwright/test/index.mjs');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
  const page=await context.newPage();
  const shots=path.join(root,'output/playwright/architecture-report/source');await fs.mkdir(shots,{recursive:true});
  const checks=[];
  try{
    for(const [route,name] of [['/','home'],['/welcome','welcome'],['/theories','theories'],['/explore','gate']]){
      const response=await page.goto(new URL(route,base).href,{waitUntil:'networkidle',timeout:45000});
      await page.evaluate(()=>document.fonts.ready);
      const final=new URL(page.url());
      checks.push({route,status:response?.status(),finalPath:final.pathname,heading:await page.locator('h1').allTextContents()});
      if(name!=='gate')await page.screenshot({path:path.join(shots,name+'.png')});
    }
    for(const route of ['/api/health/','/api/ready/','/api/catalog/discovery-search/']){
      const response=await context.request.get(new URL(route,base).href);
      checks.push({route,status:response.status(),scope:'anonymous GET; no task created'});
    }
    await fs.writeFile(path.join(here,'data/runtime.json'),JSON.stringify({checkedAt:new Date().toISOString(),environment:'内网预览，独立匿名会话',checks,limits:'未验证登录业务、任务执行、OCR、Provider、全站视觉或生产。'},null,2));
  }finally{await browser.close();}
}
let runtime=null;try{runtime=JSON.parse(await fs.readFile(path.join(here,'data/runtime.json'),'utf8'));}catch{}
const enriched=[];
for(const node of nodes)enriched.push({...node,sources:await Promise.all(node.sources.map(evidence))});
const edges=[];
for(const relation of relations)edges.push({...relation,sources:await Promise.all(relation.sources.map(evidence))});
const ids=new Set(nodes.map(n=>n.id));
if(ids.size!==nodes.length)throw Error('Duplicate node IDs.');
for(const n of nodes)for(const id of n.children||[])if(!ids.has(id))throw Error('Missing child '+id);
for(const n of nodes)for(const route of n.routes||[])if(!routes.some(r=>r.route===route))throw Error('Missing route '+route);
for(const e of edges)if(!ids.has(e.from)||!ids.has(e.to))throw Error('Missing edge endpoint.');
for(const s of scenes)for(const p of s.phases)for(const id of p.ids)if(!ids.has(id))throw Error('Missing scene node '+id);
const data={meta:{title:'STL 4.0 架构展映',snapshotDate:'2026-11-06',generatedAt:new Date().toISOString(),head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),worktree:'包含未提交修改，证据文件逐项散列',method:'人工核对业务调用链；TypeScript AST 提取静态导入与字面量链接；文件系统提取路由。静态引用不等同运行覆盖。',routeCount:routes.length,inScopeRouteCount:routes.filter(r=>!r.excluded).length,sourceCount:webFiles.length,importCount:importEdges.length},statusLabels,nodes:enriched,relations:edges,scenes,runtime};
await fs.writeFile(path.join(here,'data/architecture.json'),JSON.stringify(data,null,2));
await fs.writeFile(path.join(here,'data/inventory.json'),JSON.stringify({routes,importEdges,literalLinks:rawLinks,apiDeclarations,limitations:'静态导入包含类型和可能未调用的模块；API 是声明清单，不是完整展开后的端点数量。'},null,2));
const quote=s=>'"'+String(s??'').replaceAll('"','""')+'"';
const csv=[['node_id','name','status','file','line','anchor','sha256'],...enriched.flatMap(n=>n.sources.map(s=>[n.id,n.name,statusLabels[n.status],s.file,s.line,s.anchor,s.sha256]))].map(r=>r.map(quote).join(',')).join('\r\n');
await fs.writeFile(path.join(here,'data/evidence-index.csv'),'\ufeff'+csv);
console.log(JSON.stringify({nodes:nodes.length,relations:edges.length,routes:routes.length,imports:importEdges.length,sourceFiles:webFiles.length,runtimeChecks:runtime?.checks?.length||0},null,2));
