"use client";

import { createContext, useContext, useEffect, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { useAdminSession } from "@/lib/admin-session";
import { subscribeToSessionChanges } from "@/lib/api";
import type { PlacementPickerDraft } from "./placement-catalog-picker";

type SelectionSession = {value:PlacementPickerDraft;setValue:Dispatch<SetStateAction<PlacementPickerDraft>>;open:boolean;setOpen:Dispatch<SetStateAction<boolean>>};
const SelectionContext=createContext<SelectionSession|null>(null);

/** Only the selected catalog references/prose travel between page editors, in memory. */
export function PlacementSelectionProvider({children}:{children:ReactNode}) {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return <SelectionState key={`${user?.id||"anonymous"}:${epoch}`}>{children}</SelectionState>;
}

function SelectionState({children}:{children:ReactNode}) {
  const [value,setValue]=useState<PlacementPickerDraft>({selected:[],group:0});
  const [open,setOpen]=useState(false);
  return <SelectionContext.Provider value={{value,setValue,open,setOpen}}>{children}</SelectionContext.Provider>;
}

export function usePlacementSelection() {
  const value=useContext(SelectionContext);
  if(!value)throw new Error("内容编排需要在受保护的页面编排工作区中打开。");
  return value;
}
