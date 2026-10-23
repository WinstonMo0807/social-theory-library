"use client";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useCatalogCommand } from "./use-intake-command";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { invalidateAssistantCache } from "./field-assistant-cache";

type Action="adopt"|"reject"|"create";
type Command={action:Action;field_name:string;expected_version:string;payload:Record<string,unknown>};
type Result={owner_id:string;request_id:string;edition_id:string;state:"applied"|"cancelled";action:string;field_name:string;next_url:string;result:Record<string,unknown>};
type Context={send:(action:Action,field:string,payload:Record<string,unknown>)=>Promise<Record<string,unknown>>;blocked:boolean;notice:ReactNode};
const Commands=createContext<Context|null>(null);
export function useAssistantCommands(){return useContext(Commands);}
export function AssistantCommandNotice(){return useContext(Commands)?.notice||null;}

export function AssistantCommandsProvider({owner,editionId,version,onGuard,onRecovered,children}:{owner:string;editionId:string;version:string;onGuard:(value:boolean)=>void;onRecovered:()=>Promise<unknown>;children:ReactNode}){
  const expected=useRef<{action:Action;field:string}|null>(null);
  const request=useCatalogCommand<Command,Result>(owner,`/catalog/admin/editions/${editionId}/field-decisions/`,`stl-assistant-command:${owner}:${editionId}`,result=>result.edition_id===editionId&&(result.state==="cancelled"||!expected.current||result.action===expected.current.action&&result.field_name===expected.current.field));
  const [stopping,setStopping]=useState(false),[message,setMessage]=useState("");
  const blocked=!request.ready||request.busy||Boolean(request.recovery);
  useEffect(()=>{onGuard(blocked);},[blocked,onGuard]);
  useUnsavedForm(Boolean(request.recovery),false);
  async function recovered(cancel=false,retry=false){
    const value=retry?await request.send():await request.lookup(cancel);
    if(!value)return;
    expected.current=null;
    setStopping(false);invalidateAssistantCache(editionId);
    const entity=value.result.entity as {name?:string;edit_url?:string}|undefined;
    setMessage(value.state==="cancelled"?"尚未执行的原决定已停止。":value.action==="create"?`原请求已创建${entity?.name||"馆内对象"}。可重新查找并选择该对象；不会自动填入已改变的表单。`:"已查回原决定，原操作没有重复执行。请重新读取建议核对当前状态。");
    await onRecovered();
  }
  const notice=<>{request.error?<p role="alert">{request.error}</p>:null}{message?<p role="status">{message}</p>:null}{request.recovery?<div className="field-assistant-message"><p>材料助手有一项尚待核对的决定，请先查回结果。</p><button type="button" disabled={request.busy} onClick={()=>void recovered()}>查回原决定</button>{request.canRetry?<button type="button" disabled={request.busy} onClick={()=>void recovered(false,true)}>重试原决定</button>:null}<button type="button" disabled={request.busy} onClick={()=>setStopping(true)}>停止尚未执行的请求</button></div>:null}</>;
  async function send(action:Action,field_name:string,payload:Record<string,unknown>){
    if(blocked)throw Error("请先核对材料助手的原请求。");
    expected.current={action,field:field_name};
    setMessage("");const value=await request.send({action,field_name,expected_version:version,payload});
    if(!value)throw Error("尚未确认这次决定，请查看原请求状态。");
    if(value.state!=="applied"||value.action!==action||value.field_name!==field_name)throw Error("返回的决定与当前字段不一致，请重新读取当前记录。");
    expected.current=null;
    return value.result;
  }
  return <Commands value={{send,blocked,notice}}>{children}<div>{notice}</div><ConfirmDialog open={stopping} title="核对并停止材料助手的原决定？" description="已有结果返回原回执，未执行请求会被停止；不会撤销已经建立的人物或已有字段决定。" confirmLabel="核对并停止" pending={request.busy} onCancel={()=>setStopping(false)} onConfirm={()=>recovered(true)}/></Commands>;
}
