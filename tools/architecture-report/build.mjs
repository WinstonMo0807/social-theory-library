import { build } from '../../web/node_modules/vite/dist/node/index.js';
import react from '../../web/node_modules/@vitejs/plugin-react/dist/index.js';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)), root=path.resolve(here,'../..');
const publicDir=path.join(here,'.cache/public');
for(const dir of ['brand','fonts/stl-type'])await fs.cp(path.join(root,'web/public',dir),path.join(publicDir,dir),{recursive:true});
const config={root:here,publicDir,configFile:false,plugins:[react()],resolve:{alias:{'@':path.join(root,'web'),react:path.join(root,'web/node_modules/react'), 'react-dom':path.join(root,'web/node_modules/react-dom'),'lucide-react':path.join(root,'web/node_modules/lucide-react')}},build:{outDir:path.join(here,'dist'),emptyOutDir:true,sourcemap:false}};
await build(config);
await fs.cp(path.join(here,'data'),path.join(here,'dist/data'),{recursive:true,filter:source=>!source.endsWith('.mjs')});
try{await fs.cp(path.join(root,'output/playwright/architecture-report/source'),path.join(here,'dist/screens'),{recursive:true});}catch(error){if(error.code!=='ENOENT')throw error;}
console.log('Built local-only report. No business routes or backend were changed.');
