"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useState } from "react";
import { WorkflowEditor } from "./admin/workflow/workflow-editor";
import { IntakeConfirmation } from "./admin/workflow/intake-confirmation";
/** Existing section deep links retain the full editor; new intake starts with identity confirmation. */
export function IntakeWorkspace({itemId}:{itemId:string}){
  const [section,setSection]=useState<string|null>(null);
  useEffect(()=>{const read=()=>setSection(window.location.hash.slice(1));queueMicrotask(read);window.addEventListener("hashchange",read);return()=>window.removeEventListener("hashchange",read);},[]);
  if(section===null)return <LoadingState>正在读取收件工作区…</LoadingState>;
  return section?<WorkflowEditor mode="intake" itemId={itemId}/>:<IntakeConfirmation itemId={itemId}/>;
}
