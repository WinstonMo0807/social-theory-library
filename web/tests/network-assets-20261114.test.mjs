import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createHash} from 'node:crypto';
import {matchHeaders} from '../node_modules/vinext/dist/config/config-matchers.js';
import ts from 'typescript';

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8');
const manifest=JSON.parse(read('../lib/performance-assets.json'));
const combined=read(`../public/assets/performance/preferences-${manifest.preferencesSha256.slice(0,16)}.js`);
function boot(scripts,options={}){
 const local=new Map(Object.entries(options.local??{})),session=new Map(Object.entries(options.session??{})),dataset={},listeners=[];
 const storage=map=>({getItem:key=>{if(options.blocked)throw Error('storage disabled');return map.get(key)??null;},setItem:(key,value)=>{if(options.blocked)throw Error('storage disabled');map.set(key,value);}});
 const scope={document:{documentElement:{dataset}},localStorage:storage(local),sessionStorage:storage(session),URLSearchParams,matchMedia:()=>({matches:!!options.darkSystem}),window:{location:{hash:options.hash??''},addEventListener:(type,fn)=>listeners.push({type,fn})}};
 for(const script of scripts)runInNewContext(script,scope);
 return {dataset,session:[...session],listeners: listeners.map(item=>item.type)};
}
test('the single blocking preference asset preserves both previous scripts, including denied storage and URL trials',()=>{
 const before=[read('../public/appearance-init.js'),read('../public/typography-init.js')];
 for(const options of [{},{blocked:true},{local:{library_theme:'dark',library_text_size:'large',library_font_family:'serif'}},{local:{library_theme:'system'},darkSystem:true},{hash:'#typography=B&font=song'},{session:{'stl-typeset-20261029':'B','stl-font-trial':'wenkai'}},{local:{library_theme:'invalid'},hash:'#font=invalid'}])assert.deepEqual(boot([combined],options),boot(before,options));
 assert.equal(createHash('sha256').update(combined).digest('hex'),manifest.preferencesSha256);
 const inlineModule=ts.transpileModule(read('../lib/preferences-bootstrap.generated.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const inline={};new Function('exports',inlineModule)(inline);
 assert.equal(inline.preferencesBootstrapCode,combined);
});

test('immutable font copies preserve the approved font faces and runtime configuration remains fresh',()=>{
 let css=read('../styles/tokens/type-fonts.css');
 const sources=[...new Set(css.match(/\/fonts\/stl-type\/(?:sans|serif)-[a-f0-9]{16}\.woff2/g)??[])];
 assert.ok(sources.length>0);
 for(const src of sources){
  const original=readFileSync(new URL('../public'+src,import.meta.url));
  const target=`/assets/performance/font-${createHash('sha256').update(original).digest('hex').slice(0,24)}.woff2`;
  assert.deepEqual(readFileSync(new URL('../public'+target,import.meta.url)),original);
  css=css.replaceAll(src,target);
 }
 assert.equal(read('../styles/tokens/type-fonts.generated.css'),css);
 const code=ts.transpileModule(read('../next.config.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const exported={};new Function('exports',code)(exported);
 return exported.default.headers().then(rules=>{
  for(const path of ['/fonts/stl-type/wenkai-regular.woff2','/fonts/stl-type/SOURCES.json','/api/reading/progress/','/api/distribution/assets/private/'])assert.deepEqual(matchHeaders(path,rules),[]);
  assert.deepEqual(matchHeaders('/runtime-config.js',rules),[{key:'Cache-Control',value:'no-store'}]);
 });
});
