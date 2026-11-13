"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { apiEndpoint } from "@/lib/runtime-api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./media-workspace.module.css";

export type MediaTransform = {x:number;y:number;width:number;height:number;rotation:number};
export const wholeImage:MediaTransform={x:0,y:0,width:1,height:1,rotation:0};
export async function ownedImage(owner:string,path:string,signal:AbortSignal){
  // All callers supply a local protected media endpoint, never an external source URL.
  const parsed=new URL(path,window.location.origin),local=parsed.pathname.replace(/^\/api\//,"/");
  if(!local.startsWith("/catalog/admin/"))throw Error("图片不是受保护的馆藏素材。");
  const url=apiEndpoint(`${local}${parsed.search}`);
  return withPrivateOwner(owner,async()=>{const response=await fetch(url,{credentials:"include",cache:"no-store",signal,headers:{"X-Editor-Owner":owner}});if(!response.ok)throw Error(`图片暂时无法读取（${response.status}），请重新加载。`);return response.blob();},signal);
}

export function PrivateMediaImage({owner,path,alt}:{owner:string;path:string;alt:string}){
  const [result,setResult]=useState<{key:string;src:string;error:string}|null>(null);
  const key=`${owner}:${path}`;
  useEffect(()=>{if(!path)return;const abort=new AbortController();let src="";
    void ownedImage(owner,path,AbortSignal.any([abort.signal,AbortSignal.timeout(30000)])).then(blob=>{src=URL.createObjectURL(blob);if(!abort.signal.aborted)setResult({key,src,error:""});else URL.revokeObjectURL(src);}).catch(reason=>{if(!abort.signal.aborted)setResult({key,src:"",error:reason instanceof Error?reason.message:"图片读取失败。"});});
    return()=>{abort.abort();if(src)URL.revokeObjectURL(src);};
  },[owner,path,key]);
  const current=result?.key===key?result:null;
  return !path?<span className={styles.empty}>尚无图片</span>:current?.error?<span role="status" title={current.error}>图片暂不可用</span>:current?.src?<img src={current.src} alt={alt} loading="lazy"/>:<span role="status">正在读取图片…</span>;
}

export function MediaCrop({owner,mediaId,value,onChange,onReady,disabled,labels=["书页大封面","列表封面","移动端封面"]}:{labels?:string[];owner:string;mediaId:string;value:MediaTransform;onChange:(value:MediaTransform)=>void;onReady:(ready:boolean)=>void;disabled:boolean}){
  const [image,setImage]=useState<HTMLImageElement|null>(null),[error,setError]=useState(""),[attempt,setAttempt]=useState(0),[ratio,setRatioValue]=useState("free");
  const source=useRef<HTMLCanvasElement>(null),outputs=useRef<(HTMLCanvasElement|null)[]>([]),stage=useRef<HTMLDivElement>(null);
  const drag=useRef<{x:number;y:number;rect:MediaTransform;corner:string}|null>(null);
  useEffect(()=>{const abort=new AbortController();let url="";onReady(false);setError("");
    void ownedImage(owner,`/catalog/admin/media/${mediaId}/source/`,AbortSignal.any([abort.signal,AbortSignal.timeout(120000)])).then(async blob=>{
      url=URL.createObjectURL(blob);const next=new Image();next.src=url;await next.decode();if(!abort.signal.aborted){setImage(next);setError("");onReady(true);}
    }).catch(reason=>{if(!abort.signal.aborted){setError(reason instanceof Error&&reason.name==="TimeoutError"?"原图读取超时，已上传的图片仍保留。请重新加载。":reason instanceof Error?reason.message:"原图无法读取。");onReady(false);}});
    return()=>{abort.abort();if(url)URL.revokeObjectURL(url);};
  },[owner,mediaId,attempt,onReady]);
  const rotated=value.rotation%180!==0,width=image?(rotated?image.naturalHeight:image.naturalWidth):1,height=image?(rotated?image.naturalWidth:image.naturalHeight):1;
  useEffect(()=>{if(!image||!source.current)return;const canvas=source.current;const scale=Math.min(1,900/width,900/height);canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));const ctx=canvas.getContext("2d");if(!ctx)return;
    ctx.clearRect(0,0,canvas.width,canvas.height);ctx.save();ctx.translate(canvas.width/2,canvas.height/2);ctx.rotate(value.rotation*Math.PI/180);ctx.drawImage(image,-image.naturalWidth*scale/2,-image.naturalHeight*scale/2,image.naturalWidth*scale,image.naturalHeight*scale);ctx.restore();
    for(const preview of outputs.current){if(!preview)continue;const cropWidth=value.width*canvas.width,cropHeight=value.height*canvas.height;preview.width=Math.max(1,Math.round(240*Math.min(1,cropWidth/cropHeight)));preview.height=Math.max(1,Math.round(240*Math.min(1,cropHeight/cropWidth)));preview.getContext("2d")?.drawImage(canvas,value.x*canvas.width,value.y*canvas.height,cropWidth,cropHeight,0,0,preview.width,preview.height);}
  },[image,value,width,height]);
  function setRatio(next:string){setRatioValue(next);const target=next==="original"?width/height:next==="3:4"?3/4:next==="1:1"?1:next==="16:9"?16/9:null;if(!target){return;}let w=1,h=width/(height*target);if(h>1){h=1;w=height*target/width;}onChange({...value,x:(1-w)/2,y:(1-h)/2,width:w,height:h});}
  function begin(event:PointerEvent<HTMLDivElement>){if(disabled||!image)return;const target=event.target as HTMLElement;drag.current={x:event.clientX,y:event.clientY,rect:value,corner:target.dataset.corner||"move"};event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault();}
  function move(event:PointerEvent<HTMLDivElement>){const active=drag.current,bounds=stage.current?.getBoundingClientRect();if(!active||!bounds)return;const dx=(event.clientX-active.x)/bounds.width,dy=(event.clientY-active.y)/bounds.height,r=active.rect;
    if(active.corner==="move")onChange({...r,x:Math.max(0,Math.min(1-r.width,r.x+dx)),y:Math.max(0,Math.min(1-r.height,r.y+dy))});
    else{const west=active.corner.includes("w"),north=active.corner.includes("n");let left=west?Math.max(0,Math.min(r.x+r.width-.02,r.x+dx)):r.x,top=north?Math.max(0,Math.min(r.y+r.height-.02,r.y+dy)):r.y;const right=west?r.x+r.width:Math.max(r.x+.02,Math.min(1,r.x+r.width+dx)),bottom=north?r.y+r.height:Math.max(r.y+.02,Math.min(1,r.y+r.height+dy));left=Math.max(0,left);top=Math.max(0,top);setRatioStateFree();onChange({...r,x:left,y:top,width:right-left,height:bottom-top});}
  }
  function setRatioStateFree(){setRatioValue("free");}
  function zoom(factor:number){const fit=Math.min(1/value.width,1/value.height,Math.max(.02/Math.min(value.width,value.height),factor));const w=value.width*fit,h=value.height*fit;onChange({...value,x:Math.max(0,Math.min(1-w,value.x+(value.width-w)/2)),y:Math.max(0,Math.min(1-h,value.y+(value.height-h)/2)),width:w,height:h});}
  return <section className={styles.crop}><h2>裁切与适配预览</h2>{error?<p role="alert">{error}<button type="button" disabled={disabled} onClick={()=>setAttempt(n=>n+1)}>重新加载</button></p>:null}
    {!image&&!error?<LoadingState role="status">正在读取原图…</LoadingState>:null}
    <div className={styles.cropColumns}><div className={styles.stageFrame}><div className={styles.stage} ref={stage} style={{aspectRatio:`${width}/${height}`}}>
      <canvas ref={source} role="img" aria-label="原图与裁切范围"/>
      {image?<div className={styles.selection} style={{left:`${value.x*100}%`,top:`${value.y*100}%`,width:`${value.width*100}%`,height:`${value.height*100}%`}} onPointerDown={begin} onPointerMove={move} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}} aria-hidden="true">{["nw","ne","sw","se"].map(corner=><span key={corner} data-corner={corner}/>)}</div>:null}
    </div></div><div className={styles.samples}>{labels.map((label,i)=><figure key={label}><canvas ref={node=>{outputs.current[i]=node;}} role="img" aria-label={`${label}裁切预览`}/><figcaption>{label}</figcaption></figure>)}</div></div>
    <fieldset disabled={disabled||!image}><legend>裁切比例</legend><div className={styles.controls}>{[["original","原图"],["3:4","3:4"],["1:1","1:1"],["free","自由"]].map(([key,label])=><button type="button" key={key} aria-pressed={ratio===key} onClick={()=>setRatio(key)}>{label}</button>)}</div>
      <div className={styles.controls}><button type="button" onClick={()=>zoom(1.1)} aria-label="缩小图片，扩大裁切范围">−</button><label>选区大小<input type="range" min={10} max={100} value={Math.round(Math.max(value.width,value.height)*100)} onChange={event=>zoom(Number(event.target.value)/100/Math.max(value.width,value.height))}/></label><button type="button" onClick={()=>zoom(.9)} aria-label="放大图片，缩小裁切范围">＋</button></div>
      <div className={styles.controls}><button type="button" onClick={()=>{setRatio("free");onChange({...wholeImage,rotation:(value.rotation+270)%360});}}>↶ 向左旋转</button><button type="button" onClick={()=>{setRatio("free");onChange({...wholeImage,rotation:(value.rotation+90)%360});}}>↷ 向右旋转</button><button type="button" onClick={()=>{setRatio("original");onChange({...wholeImage});}}>重置</button></div>
      <details data-disclosure="collection"><summary>精确调整裁切范围</summary><button type="button" aria-pressed={ratio==="16:9"} onClick={()=>setRatio("16:9")}>横幅比例 16:9</button><p>可拖动选区或四角；也可用下列数值调整。单位为图片百分比。</p><div className={styles.coordinates}>{(["x","y","width","height"] as const).map((key,i)=><label key={key}>{["左侧","顶部","宽度","高度"][i]}<input type="number" min={key==="x"||key==="y"?0:1} max={100} step={.1} value={Number((value[key]*100).toFixed(1))} onChange={event=>{const n=Number(event.target.value)/100;if(!Number.isFinite(n))return;const next={...value,[key]:n};if(next.x>=0&&next.y>=0&&next.width>0&&next.height>0&&next.x+next.width<=1&&next.y+next.height<=1){setRatio("free");onChange(next);}}}/></label>)}</div></details>
    </fieldset>{image?<p className={styles.note}>原图 {image.naturalWidth} × {image.naturalHeight} · 裁切 {Math.round(width*value.width)} × {Math.round(height*value.height)}。原图保留，保存后生成新的图片版本。</p>:null}
  </section>;
}
