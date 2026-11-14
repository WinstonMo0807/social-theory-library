import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import test from 'node:test';
import postcss from 'postcss';
import {styleSemanticSnapshot} from '../scripts/style-source.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const read=p=>readFileSync(path.join(root,p),'utf8');
const obsolete=s=>/^\s*(?:html[^ ]*\s+)?(?:\[data-theme=[^\]]+\]\s+)?(?:\.site-header)?\[data-ui-scope="(?:editorial-v2|explore-frozen)"\]/.test(s);

test('the removed style scopes cannot be emitted by application components',()=>{
 function scan(dir){for(const e of readdirSync(path.join(root,dir),{withFileTypes:true})){
  const name=path.join(dir,e.name);
  if(e.isDirectory())scan(name);
  else if(/\.(tsx?|jsx?)$/.test(name))assert.doesNotMatch(read(name),/data-ui-scope\s*=\s*["'](?:editorial-v2|explore-frozen)["']/);
 }}
 scan('app');scan('components');
 const old=postcss.parse(read('app/editorial-v2.css'));
 old.walkRules(rule=>{if(rule.parent.type==='atrule'&&rule.parent.name.endsWith('keyframes'))return;assert.ok(rule.selectors.every(obsolete),rule.selector);});
});

test('route-owned administrative rules retain all declarations, conditions and ordering',()=>{
 const before=postcss.parse(read('app/editorial-workspaces.css'));
 before.walkRules(rule=>{if(rule.selectors.every(obsolete))rule.remove();});
 before.walkAtRules(rule=>{if(rule.nodes&&!rule.nodes.length)rule.remove();});
 assert.deepEqual(styleSemanticSnapshot(read('styles/features/admin/editorial-workspaces-current.css')),styleSemanticSnapshot(before.toString()));
 const global=read('app/layout.tsx');
 assert.doesNotMatch(global,/import ["']\.\/editorial-(?:v2|workspaces)\.css/);
 assert.match(read('app/admin/route-styles.css'),/editorial-workspaces-current\.css/);
});
