// Vinext's startup static-file cache serves these variants directly, without request-time compression.
import {readdir,readFile,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {brotliCompressSync,gzipSync,constants} from 'node:zlib';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist/client');
const extensions=new Set(['.css','.js','.mjs','.svg','.json']);
let files=0,original=0,brotli=0,gzip=0;
async function compress(directory){
  for(const entry of await readdir(directory,{withFileTypes:true})){
    const file=path.join(directory,entry.name);
    if(entry.isDirectory()){if(entry.name!=='.vite')await compress(file);continue;}
    // Runtime config is rewritten by the container entrypoint; stale compressed copies would be unsafe.
    if(!extensions.has(path.extname(file))||entry.name==='runtime-config.js')continue;
    const source=await readFile(file);if(source.length<1024)continue;
    const br=brotliCompressSync(source,{params:{[constants.BROTLI_PARAM_QUALITY]:9}}),gz=gzipSync(source,{level:9});
    if(br.length>=source.length||gz.length>=source.length)continue;
    await writeFile(file+'.br',br);await writeFile(file+'.gz',gz);
    files++;original+=source.length;brotli+=br.length;gzip+=gz.length;
  }
}
await stat(root);await compress(root);
console.log(JSON.stringify({files,original,brotli,gzip}));
