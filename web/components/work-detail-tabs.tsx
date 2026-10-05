"use client";
import { useEffect, useId, useState, type ReactNode } from "react";

export function WorkDetailTabs({ panels }: { panels: { id: string; label: string; content: ReactNode }[] }) {
  const [active, setActive] = useState(panels[0].id);
  const scope = useId();
  useEffect(() => {
    const locate = () => { if (window.location.hash === "#citation") setActive("edition"); };
    const timer = window.setTimeout(locate, 0);
    window.addEventListener("hashchange", locate);
    return () => { window.clearTimeout(timer); window.removeEventListener("hashchange", locate); };
  }, []);
  return <><nav className="work-detail-tabs" role="tablist" aria-label="图书内容">{panels.map((panel,index)=><button key={panel.id} type="button" role="tab" id={`${scope}-${panel.id}-tab`} aria-controls={`${scope}-${panel.id}`} aria-selected={active===panel.id} tabIndex={active===panel.id ? 0 : -1} onClick={()=>setActive(panel.id)} onKeyDown={event=>{
    const next = event.key==="ArrowRight" ? (index+1)%panels.length : event.key==="ArrowLeft" ? (index+panels.length-1)%panels.length : event.key==="Home" ? 0 : event.key==="End" ? panels.length-1 : -1;
    if(next<0) return;
    event.preventDefault();setActive(panels[next].id);event.currentTarget.ownerDocument.getElementById(`${scope}-${panels[next].id}-tab`)?.focus();
  }}>{panel.label}</button>)}</nav>{panels.map(panel=><section className="work-detail-tab-panel" role="tabpanel" aria-labelledby={`${scope}-${panel.id}-tab`} id={`${scope}-${panel.id}`} key={panel.id} hidden={active!==panel.id}>{panel.content}</section>)}</>;
}
