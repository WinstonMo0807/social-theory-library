import { build } from '../node_modules/esbuild/lib/main.js';
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const web = path.dirname(root);
await mkdir(path.join(root, 'dist'), { recursive: true });
await mkdir(path.join(root, 'dist/brand'), { recursive: true });
await build({ entryPoints: [path.join(root,'app.tsx')], outfile: path.join(root,'dist/app.js'), bundle: true, format:'esm', platform:'browser', jsx:'automatic', target:'es2022', minify:true, alias:{'@':web}, define:{'process.env.NODE_ENV':'"production"'} });
await cp(path.join(root,'index.html'),path.join(root,'dist/index.html'));
await cp(path.join(root,'architecture.json'),path.join(root,'dist/architecture.json'));
await cp(path.join(root,'evidence-index.csv'),path.join(root,'dist/evidence-index.csv'));
await cp(path.join(web,'public/brand/stl-symbol-20261027.svg'),path.join(root,'dist/brand/stl-symbol-20261027.svg'),{recursive:true});
await cp(path.join(web,'public/fonts/stl-type'),path.join(root,'dist/fonts/stl-type'),{recursive:true});
await cp(path.join(web,'styles/tokens/type-fonts.css'),path.join(root,'dist/fonts.css'));
try { await cp(path.resolve(web,'../output/playwright/architecture-showcase/site'),path.join(root,'dist/site'),{recursive:true}); } catch(e) { if(e.code!=='ENOENT') throw e; }
console.log('Built isolated presentation. No business routes or API requests.');
