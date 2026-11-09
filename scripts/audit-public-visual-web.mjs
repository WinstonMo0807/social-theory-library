// Static discovery only. Every row stays pending until its business and runtime review.
// Reuses the project's TypeScript AST approach from tools/architecture-report/audit.mjs.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const web = path.join(root, 'web');
const out = path.join(root, 'docs/stl4/public-visual-20261110');
const raw = path.join(root, 'output/public-visual-20261110/audit');
const ts = (await import(pathToFileURL(process.env.STL_TYPESCRIPT_PATH || path.join(web, 'node_modules/typescript/lib/typescript.js')).href)).default;
const rel = file => path.relative(root, file).replaceAll('\\', '/');
function walk(dir) {
  return fs.readdirSync(dir, {withFileTypes:true}).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : [path.join(dir,e.name)]);
}
const files = ['app','components','lib'].flatMap(d => walk(path.join(web,d))).filter(f=>/\.[cm]?[tj]sx?$/.test(f));
const program = ts.createProgram(files, {target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext,moduleResolution:ts.ModuleResolutionKind.Bundler,
  jsx:ts.JsxEmit.Preserve,allowJs:true,noEmit:true,baseUrl:web,paths:{'@/*':['./*']}});
const checker = program.getTypeChecker();
const cache = new Map();
const position = n => ({file:rel(n.getSourceFile().fileName),line:n.getSourceFile().getLineAndCharacterOfPosition(n.getStart()).line+1});
const isLocal = n => n?.getSourceFile() && /\/web\/(app|components|lib)\//.test('/'+rel(n.getSourceFile().fileName)) && !n.getSourceFile().isDeclarationFile;
const transports = new Set(['apiRequest','serverRequest','apiBlob','apiUpload','apiStreamRequest','fetch']);
// Verified thin wrappers. Owner-first wrappers pass their URL as argument 2.
const wrapperPathIndex = new Map([
  ['privateRequest',0],['parallelRequest',0],['booklistRequest',1],['notebookRequest',1],
  ['sharingRequest',1],['accountRequest',1],['authorityRequest',1],['replayRequest',1],
  ['useApiResource',0],['usePersistentWorkspace',0],
]);
function requestInfo(n) {
  if(!ts.isCallExpression(n)) return null;
  const called = n.expression.getText().split('.').at(-1);
  if(!transports.has(called)&&!wrapperPathIndex.has(called)) return null;
  const pathIndex=wrapperPathIndex.get(called)||0;
  const arg=n.arguments[pathIndex]; if(!arg)return null;
  const text=arg.getText();
  let requestPath=ts.isStringLiteralLike(arg)?arg.text:ts.isTemplateExpression(arg)?text.slice(1,-1):null;
  if(called==='fetch' && requestPath && !/api|catalog|reading|ingestion|auth|distribution/.test(requestPath))return null;
  const resourceHook=called==='useApiResource'||called==='usePersistentWorkspace';
  const opts=resourceHook?undefined:n.arguments[pathIndex+1];
  const method=opts&&ts.isObjectLiteralExpression(opts)?opts.properties.find(p=>p.name?.getText()==='method')?.initializer?.getText().replaceAll(/["']/g,''):null;
  return {...position(n),transport:called,path:requestPath,expression:requestPath?null:text,method:method||((called==='apiUpload')?'POST':'GET'),
    options:opts?.getText().slice(0,1600)||'',requires_review:!requestPath||resourceHook||Boolean(opts&&!ts.isObjectLiteralExpression(opts))};
}
function inspectNode(entry) {
  if(cache.has(entry))return cache.get(entry);
  const result={requests:[],controls:[],pathLiterals:[],dependencies:new Set(),components:new Set(),stateSignals:new Set(),parameters:new Set()};
  cache.set(entry,result);
  function visit(n) {
    if(ts.isExportDeclaration(n)&&n.moduleSpecifier&&ts.isStringLiteralLike(n.moduleSpecifier)) {
      const resolved=ts.resolveModuleName(n.moduleSpecifier.text,n.getSourceFile().fileName,program.getCompilerOptions(),ts.sys).resolvedModule;
      const source=resolved&&program.getSourceFile(resolved.resolvedFileName);
      if(source&&isLocal(source))result.dependencies.add(source);
      return;
    }
    if(ts.isTypeNode(n)||ts.isImportDeclaration(n))return;
    const req=requestInfo(n);if(req)result.requests.push(req);
    if((ts.isStringLiteralLike(n)||ts.isTemplateExpression(n))&&/^\/(?:api\/)?(?:catalog|reading|auth|ingestion|distribution)\//.test(ts.isStringLiteralLike(n)?n.text:n.head.text)) {
      result.pathLiterals.push({...position(n),path:ts.isStringLiteralLike(n)?n.text:n.getText().slice(1,-1),scope:'path expression; transport/method requires review'});
    }
    if(ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n)) {
      const tag=n.tagName.getText();
      if(/^[A-Z]/.test(tag))result.components.add(tag);
      if(['input','select','textarea','button','dialog','details','form'].includes(tag)) {
        const attributes={};
        for(const attr of n.attributes.properties)if(ts.isJsxAttribute(attr)&&['name','type','required','min','max','minLength','maxLength','pattern','aria-label','placeholder','role','disabled','onSubmit','onClick','onChange'].includes(attr.name.getText()))attributes[attr.name.getText()]=attr.initializer?.getText()||true;
        result.controls.push({...position(n),tag,attributes});
      }
    }
    if(ts.isCallExpression(n)) {
      const name=n.expression.getText();
      if(/searchParams|params|search\.get|query\.get/.test(name)&&n.arguments[0]&&ts.isStringLiteralLike(n.arguments[0]))result.parameters.add(n.arguments[0].text);
      if(name.length<160&&/sessionStorage|localStorage|beforeunload|confirmAction|requestAnimationFrame|setInterval|setTimeout|useUnsaved|useDraft|router\.(push|replace|back)|window\.location/.test(name))result.stateSignals.add(name);
    }
    if(ts.isIdentifier(n)) {
      let symbol=checker.getSymbolAtLocation(n);
      if(symbol?.flags&ts.SymbolFlags.Alias)symbol=checker.getAliasedSymbol(symbol);
      for(const decl of symbol?.declarations||[]) {
        if(!isLocal(decl)||decl===entry)continue;
        if(ts.isFunctionDeclaration(decl)||ts.isVariableDeclaration(decl)||ts.isClassDeclaration(decl)) {
          if(!transports.has(decl.name?.getText()))result.dependencies.add(decl);
        }
      }
    }
    ts.forEachChild(n,visit);
  }
  visit(entry);return result;
}
const routes=[];
for(const file of files.filter(f=>/[/\\]page\.tsx?$/.test(f)).sort()) {
  const source=program.getSourceFile(file);const route='/'+path.relative(path.join(web,'app'),path.dirname(file)).replaceAll('\\','/').split('/').filter(p=>p&&!p.startsWith('(')).join('/');
  const visited=new Set();const pending=[source];const requests=[],controls=[],pathLiterals=[],components=new Set(),signals=new Set(),parameters=new Set(),sources=new Set();
  while(pending.length) {
    const node=pending.pop();if(visited.has(node))continue;visited.add(node);
    sources.add(rel(node.getSourceFile().fileName));
    const info=inspectNode(node);requests.push(...info.requests);controls.push(...info.controls);pathLiterals.push(...info.pathLiterals);
    for(const c of info.components)components.add(c);for(const c of info.stateSignals)signals.add(c);for(const c of info.parameters)parameters.add(c);
    pending.push(...info.dependencies);
  }
  const unique = values => [...new Map(values.map(v=>[v.file+':'+v.line+':'+(v.path||v.tag||v.expression),v])).values()];
  const code=source.text;
  const redirects=[...code.matchAll(/redirect\(\s*["']([^"']+)["']/g)].map(m=>m[1]);
  const excluded=/^\/(policy|drawer-preview|interaction-preview|layout-preview)(\/|$)/.test(route)||route==='/admin/visual-review';
  const legacy=/KnowledgeLegacyRedirect/.test(code);
  routes.push({route,source:rel(file),classification:excluded?'historical_demo_or_review':legacy||redirects.length?'compatibility_redirect':'business_candidate',
    role:route.startsWith('/admin')?'staff capability (per action)':/^\/(account|reader|explore)(\/|$)/.test(route)?'authenticated owner / reader':'public (action-level gates pending)',
    sources:[...sources].sort(),components:[...components].sort(),requests:unique(requests),controls:unique(controls),pathLiterals:unique(pathLiterals),parameters:[...parameters].sort(),stateSignals:[...signals].sort(),redirects,
    reviewed:false,limitation:'Symbol references are discovery evidence; dynamic paths, inherited guards and rendered branches need explicit review.'});
}
const allRequests=[...new Map(routes.flatMap(r=>r.requests).map(r=>[r.file+':'+r.line+':'+(r.path||r.expression),r])).values()];
fs.mkdirSync(out,{recursive:true});
fs.mkdirSync(raw,{recursive:true});
fs.writeFileSync(path.join(raw,'WEB_SOURCE_MAP.json'),JSON.stringify({routes,requests:allRequests,sharedShellSources:['web/app/layout.tsx','web/components/site-header.tsx','web/components/admin-shell.tsx','web/components/reader-center.tsx'],limitations:'Shared shell and dynamic function values require separate review. No browser or request executed.'},null,2));
const csv = value => '"'+String(value??'').replaceAll('"','""')+'"';
const header=['id','route','classification','role','domain','parameters','components','api_candidates','source','key_states_operations','current_problem_goal','design_version','implementation','validation','uncovered_reason','business_review'];
const lines=routes.map((r,i)=>['PV'+String(i+1).padStart(3,'0'),r.route,r.classification,r.role,r.route.split('/')[1]||'welcome',r.parameters.join(';'),r.components.join(';'),[...new Set(r.requests.filter(x=>x.path).map(x=>x.method+' '+x.path))].join(';'),r.source,
  '', '按本轮全站视觉目标逐页核对；未认定具体缺陷','','','未验证',r.classification==='historical_demo_or_review'?'历史演示/视觉复核入口，待确认在公网的启用归类':'接口字段、权限、状态、交互与运行观察未逐项闭合','待业务核对']);
// Never overwrite manually maintained coverage during a later discovery refresh.
const coverage=path.join(out,'COVERAGE.csv');
if(!fs.existsSync(coverage))fs.writeFileSync(coverage,'\ufeff'+[header,...lines].map(r=>r.map(csv).join(',')).join('\r\n'));
console.log(JSON.stringify({routes:routes.length,classes:Object.fromEntries([...new Set(routes.map(r=>r.classification))].map(c=>[c,routes.filter(r=>r.classification===c).length])),requestCallSites:allRequests.length,dynamicRequests:allRequests.filter(r=>!r.path).length,scope:'static source discovery; no business completion claim'}));
