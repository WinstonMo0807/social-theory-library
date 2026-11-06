import { build } from '../node_modules/esbuild/lib/main.js';
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const web = path.dirname(root);
const isPublic=process.argv.includes('--public');
const dest=path.join(root,isPublic?'dist-public':'dist');
// Allow-list public content before bundling: hiding controls alone is insufficient.
const original=JSON.parse(await readFile(path.join(root,'architecture.json'),'utf8'));
const publicLabels={'design-controls':'按钮、输入框与对话框','design-shells':'公共页头、管理框架与阅读框架'};
const publicData={nodes:original.nodes.map(n=>({id:n.id,title:n.title,type:n.type,subtitle:publicLabels[n.id]??n.subtitle,status:n.status,note:n.note,boundary:n.boundary,children:n.children,routes:[],sources:[]})),edges:original.edges,statuses:original.statuses,sources:{},routes:[],commit:''};
const plugins=isPublic?[{name:'public-content',setup(b){b.onLoad({filter:/(architecture|journeys|module-facts)\.json$/},async({path:filename})=>{
 let value=JSON.parse(await readFile(filename,'utf8'));
 if(filename.endsWith('architecture.json'))value=publicData;
 else if(filename.endsWith('journeys.json'))value=value.map(j=>({...j,steps:j.steps.map(({id,label,visual,duration,node,action,system,input,output,handoff,boundary,exception,chapter,feedback,target})=>({id,label,visual,duration,node,action,system,input,output,handoff,boundary,exception,chapter,feedback,target,route:'',contract:'',records:[],sources:[]}))}));
 else value=Object.fromEntries(Object.entries(value).map(([id,f])=>[id,{responsibility:f.responsibility,boundary:f.boundary,records:[],sources:[]}]));
 return {contents:JSON.stringify(value),loader:'json'};
 });}}]:[];
await mkdir(path.join(dest,'brand'),{recursive:true});
await build({entryPoints:[path.join(root,'app.tsx')],outfile:path.join(dest,'app.js'),bundle:true,format:'esm',platform:'browser',jsx:'automatic',target:'es2022',minify:true,alias:{'@':web},define:{'process.env.NODE_ENV':'"production"','__PUBLIC_DEMO__':String(isPublic)},plugins});
if(isPublic){
 const bundle=await readFile(path.join(dest,'app.js'),'utf8');
 if(/(?:\/admin\/|(?:web|api|docs)\/[\w/\[\].-]+|192\.168\.\d+\.|\b\w[\w-]*\.(?:tsx|py|md)\b)/.test(bundle))throw new Error('Public bundle contains an internal path. Review the content before publishing.');
}
await cp(path.join(root,'index.html'),path.join(dest,'index.html'));
await writeFile(path.join(dest,'architecture.json'),JSON.stringify(isPublic?publicData:original));
if(!isPublic)await cp(path.join(root,'evidence-index.csv'),path.join(dest,'evidence-index.csv'));
await cp(path.join(web,'public/brand/stl-symbol-20261027.svg'),path.join(dest,'brand/stl-symbol-20261027.svg'));
await cp(path.join(web,'public/fonts/stl-type'),path.join(dest,'fonts/stl-type'),{recursive:true});
await cp(path.join(web,'styles/tokens/type-fonts.css'),path.join(dest,'fonts.css'));
try{await cp(path.resolve(web,'../output/playwright/architecture-showcase/site/home.png'),path.join(dest,'home.png'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log(`Built ${isPublic?'public':'internal'} presentation. No business API requests.`);
