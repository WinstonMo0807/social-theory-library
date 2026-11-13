// Deterministic derivatives of public editorial art; originals and API media stay unchanged.
import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import sharp from 'sharp';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const publicRoot=path.join(root,'public'),target=path.join(publicRoot,'assets/performance');
const manifestFile=path.join(root,'lib/performance-assets.json');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const preferences=(await Promise.all(['appearance-init.js','typography-init.js'].map(name=>readFile(path.join(publicRoot,name),'utf8')))).map(s=>s.replace(/\r\n/g,'\n')).join('\n;\n');
await mkdir(target,{recursive:true});
let manifest;
if(process.argv.includes('--update-manifest')){
  const directory='editorial/generated-20261030';
  const images={};
  for(const name of (await readdir(path.join(publicRoot,directory))).filter(n=>n.endsWith('.webp')).sort()){
    const bytes=await readFile(path.join(publicRoot,directory,name));const meta=await sharp(bytes).metadata();
    images['/'+directory+'/'+name]={sha256:digest(bytes),width:meta.width,height:meta.height,widths:[480,960].filter(w=>w<meta.width)};
  }
  manifest={preferencesSha256:digest(preferences),images};
  await writeFile(manifestFile,JSON.stringify(manifest,null,2)+'\n');
}else manifest=JSON.parse(await readFile(manifestFile,'utf8'));
if(digest(preferences)!==manifest.preferencesSha256)throw Error('Preference source changed: run prepare-performance-assets.mjs --update-manifest.');
await writeFile(path.join(target,`preferences-${manifest.preferencesSha256.slice(0,16)}.js`),preferences);
// Use the server's immutable /assets/ path with actual byte hashes. Keep the
// approved font faces, unicode ranges and originals byte-for-byte otherwise.
let fontCss=await readFile(path.join(root,'styles/tokens/type-fonts.css'),'utf8');
const fontSources=[...new Set(fontCss.match(/\/fonts\/stl-type\/(?:sans|serif)-[a-f0-9]{16}\.woff2/g)??[])];
if(!fontSources.length)throw Error('No font subsets found in the approved font stylesheet.');
for(const src of fontSources){
  const bytes=await readFile(path.join(publicRoot,src.slice(1)));
  const name=`font-${digest(bytes).slice(0,24)}.woff2`;
  await writeFile(path.join(target,name),bytes);
  fontCss=fontCss.replaceAll(src,`/assets/performance/${name}`);
}
await writeFile(path.join(root,'styles/tokens/type-fonts.generated.css'),fontCss);
let variants=0;
for(const [src,item]of Object.entries(manifest.images)){
  const bytes=await readFile(path.join(publicRoot,src.slice(1)));
  if(digest(bytes)!==item.sha256)throw Error(`Editorial asset changed: update the performance manifest for ${src}`);
  for(const width of item.widths){
    await sharp(bytes).resize({width,withoutEnlargement:true}).webp({quality:82,effort:5}).toFile(path.join(target,`editorial-${item.sha256.slice(0,16)}-${width}.webp`));variants++;
  }
}
console.log(`Prepared ${variants} responsive editorial images, ${fontSources.length} immutable font subsets and one preference bootstrap; originals retained.`);
