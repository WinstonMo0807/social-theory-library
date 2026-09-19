"use client";

import { AlertCircle, Check, Circle, CircleDot, LogOut } from "lucide-react";
import type { WorkflowStep } from "./workflow-types";
import type { WorkflowStepKey } from "./workflow-state";
import { WORKFLOW_GROUPS } from "./file-presentation";
import { useCallback, useState, useSyncExternalStore } from "react";
import { Drawer } from "@/components/ui/dialog";

function StepIcon({ status, active }: { status: string; active: boolean }) {
  if (status === "complete" || status === "skipped") return <Check size={14} />;
  if (status === "attention" || status === "blocked") return <AlertCircle size={14} />;
  if (active || status === "working") return <CircleDot size={14} />;
  return <Circle size={14} />;
}

const statusLabels: Record<string, string> = {
  pending: "待处理",
  available: "可处理",
  working: "处理中",
  attention: "需注意",
  blocked: "需要先处理",
  complete: "已完成",
  skipped: "无需处理",
};

export function WorkflowStepRail({
  title,
  filename,
  steps,
  active,
  unresolvedCount,
  dirtyCount,
  returnHref,
  onStep,
  onExit,
}: {
  title: string;
  filename?: string;
  steps: WorkflowStep[];
  active: WorkflowStepKey;
  unresolvedCount: number;
  dirtyCount: number;
  returnHref: string;
  onStep: (step: WorkflowStepKey) => void;
  onExit: (href: string) => void;
}) {
  const [open,setOpen]=useState(false);
  const subscribe=useCallback((notify:()=>void)=>{const media=window.matchMedia('(max-width: 820px)');media.addEventListener('change',notify);return()=>media.removeEventListener('change',notify);},[]);
  const mobile=useSyncExternalStore(subscribe,()=>window.matchMedia('(max-width: 820px)').matches,()=>false);
  const currentIndex = Math.max(0, steps.findIndex((step) => step.key === active));
  const selectStep = (step: WorkflowStepKey) => {
    setOpen(false);
    onStep(step);
  };
  const content=<>
    <header><small>当前文献</small><h2>{title || "未命名文献"}</h2>{filename ? <p>{filename}</p> : null}{mobile ? <button type="button" onClick={()=>setOpen(false)} aria-label="关闭编辑目录">关闭</button> : null}</header>
    <nav>{WORKFLOW_GROUPS.map((group) => <section key={group.label} className="workflow-v306-step-group"><h3>{group.label}</h3>{steps.filter((step) => group.steps.some((key) => key === step.key)).map((step) => <button className={step.key === active ? "active" : ""} type="button" key={step.key} onClick={() => selectStep(step.key)}><StepIcon status={step.status} active={step.key === active} /><span><strong>{step.label}</strong></span><b>{statusLabels[step.status] ?? step.status}</b></button>)}</section>)}</nav>
    <div className="workflow-step-totals"><span>待处理 {unresolvedCount}</span><span>未保存 {dirtyCount}</span></div>
    <footer><button type="button" onClick={() => onExit(returnHref)}><LogOut size={14} />返回列表</button></footer>
  </>;
  return (
    <>
      <div className="workflow-mobile-progress">
        <button type="button" aria-label="打开编辑目录" aria-expanded={open} onClick={() => setOpen(true)}>
          <span>{currentIndex + 1}/{steps.length}</span><strong>{steps[currentIndex]?.label || "馆藏工作"}</strong><small>{unresolvedCount} 项提醒 · {dirtyCount} 项未保存</small>
        </button>
      </div>
      {mobile ? <Drawer open={open} onRequestClose={()=>setOpen(false)} className="workflow-step-rail mobile-open" aria-label="编辑目录">{content}</Drawer> : <aside className="workflow-step-rail" aria-label="当前馆藏工作步骤">{content}</aside>}
    </>
  );
}
