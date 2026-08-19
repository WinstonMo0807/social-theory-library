"use client";

import { AlertCircle, Check, Circle, CircleDot, LogOut } from "lucide-react";
import type { WorkflowStep } from "./workflow-types";
import type { WorkflowStepKey } from "./workflow-state";

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
  blocked: "被阻止",
  complete: "已完成",
  skipped: "已跳过",
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
  const currentIndex = Math.max(0, steps.findIndex((step) => step.key === active));
  const selectStep = (step: WorkflowStepKey) => {
    document.querySelector<HTMLElement>(".workflow-step-rail")?.classList.remove("mobile-open");
    onStep(step);
  };
  return (
    <>
      <div className="workflow-mobile-progress">
        <button type="button" onClick={() => document.querySelector<HTMLElement>(".workflow-step-rail")?.classList.toggle("mobile-open")}>
          <span>{currentIndex + 1}/{steps.length}</span><strong>{steps[currentIndex]?.label || "馆藏工作"}</strong><small>{unresolvedCount} 项异常 · {dirtyCount} 项未保存</small>
        </button>
      </div>
      <aside className="workflow-step-rail" aria-label="当前馆藏工作步骤">
        <header><small>当前馆藏</small><h2>{title || "未命名馆藏"}</h2>{filename ? <p>{filename}</p> : null}</header>
        <nav>{steps.map((step) => <button className={step.key === active ? "active" : ""} type="button" key={step.key} onClick={() => selectStep(step.key)}><StepIcon status={step.status} active={step.key === active} /><span><strong>{step.label}</strong>{step.summary && typeof step.summary === "string" ? <small>{step.summary}</small> : null}</span><b>{statusLabels[step.status] ?? step.status}</b></button>)}</nav>
        <div className="workflow-step-totals"><span>异常 {unresolvedCount}</span><span>未保存 {dirtyCount}</span></div>
        <footer><button type="button" onClick={() => onExit(returnHref)}><LogOut size={14} />退出当前工作</button><button type="button" onClick={() => onExit(returnHref)}>返回队列</button></footer>
      </aside>
    </>
  );
}
