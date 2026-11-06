export function download(blob:Blob,name:string){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function dataURL(blob:Blob):Promise<string>{return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result));r.onerror=reject;r.readAsDataURL(blob);});}
let fontCache:Promise<string>|undefined;
async function embeddedFonts(){
 // Cache the repository's already licensed local font subsets. No external upload.
 fontCache??=(async()=>{const css=await (await fetch('/fonts.css')).text();const urls=[...new Set([...css.matchAll(/url\(([^)]+)\)/g)].map(m=>m[1].replace(/["']/g,'')))];const results=new Map<string,string>();
  // Bound parallel file reads to keep export responsive on slower machines.
  for(let i=0;i<urls.length;i+=8)await Promise.all(urls.slice(i,i+8).map(async url=>{const response=await fetch(url);if(!response.ok)throw new Error('无法读取本地字体。请刷新页面后重试。');results.set(url,await dataURL(await response.blob()));}));
  return css.replace(/url\(([^)]+)\)/g,(_,url)=>`url("${results.get(url.replace(/["']/g,''))}")`);})();return fontCache;
}
export async function exportFrame(element:HTMLElement,name:string,kind:'svg'|'png'){
 await document.fonts.ready;
 const clone=element.cloneNode(true) as HTMLElement;clone.style.transform='none';clone.style.position='relative';clone.style.left='0';clone.style.top='0';
 clone.querySelectorAll('.no-export').forEach(e=>e.remove());clone.classList.remove('playing');clone.classList.add('paused','reduced');
 const symbol=await (await fetch('/brand/stl-symbol-20261027.svg')).text();const parsed=new DOMParser().parseFromString(symbol,'image/svg+xml');
 for(const use of clone.querySelectorAll('use')){use.replaceWith(parsed.documentElement.querySelector('#mark')!.cloneNode(true));}
 for(const img of clone.querySelectorAll('img')){if(img.hidden){img.remove();continue;}try{img.src=await dataURL(await (await fetch(img.src)).blob());}catch{img.remove();}}
 const css=await (await fetch('/app.css')).text();const fonts=await embeddedFonts();
 const markup=new XMLSerializer().serializeToString(clone);
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 1600 900"><foreignObject width="1600" height="900"><div xmlns="http://www.w3.org/1999/xhtml"><style>${(fonts+css).replaceAll('&','&amp;').replaceAll('<','&lt;')}</style>${markup}</div></foreignObject></svg>`;
 const blob=new Blob([svg],{type:'image/svg+xml;charset=utf-8'});
 if(kind==='svg'){download(blob,`${name}.svg`);return;}
 // An opaque blob URL containing foreignObject taints Chromium canvases.
 // A self-contained data URL keeps this entirely local and origin-clean.
 const img=new Image();const url=await dataURL(blob);
 await new Promise<void>((resolve,reject)=>{img.onload=()=>resolve();img.onerror=()=>reject(new Error('无法转换图片。请改用 SVG 导出。'));img.src=url;});const canvas=document.createElement('canvas');canvas.width=3840;canvas.height=2160;const ctx=canvas.getContext('2d')!;ctx.fillStyle='#f7f4ee';ctx.fillRect(0,0,3840,2160);ctx.drawImage(img,0,0);const png=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(v=>v?resolve(v):reject(new Error('无法生成 PNG。请重试或改用 SVG 导出。')),'image/png'));download(png,`${name}.png`);
}
export async function recordPresentation(onFinish:()=>void){
 if(!navigator.mediaDevices?.getDisplayMedia||!window.MediaRecorder)throw new Error('当前浏览器无法录制标签页。请使用支持录屏的浏览器。');
 const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});
 const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));
 if(!mime){stream.getTracks().forEach(t=>t.stop());throw new Error('当前浏览器无法生成 WebM 视频。请更换浏览器后重试。');}
 const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:8000000});const chunks:Blob[]=[];
 recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
 recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());if(chunks.length)download(new Blob(chunks,{type:mime}),'STL-architecture.webm');onFinish();};
 stream.getVideoTracks()[0].addEventListener('ended',()=>{if(recorder.state!=='inactive')recorder.stop()});
 recorder.start(1000);return {stop(){if(recorder.state!=='inactive')recorder.stop()}};
}
