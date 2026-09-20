"use client";
import { ArrowLeft, Check } from "lucide-react";
import type { WorkflowStep } from "./workflow-types";
import type { WorkflowStepKey } from "./workflow-state";
import { WORKFLOW_GROUPS } from "./file-presentation";

export function WorkflowStepRail({ steps, active, dirtyCount, returnHref, onStep, onExit }: {
  title: string; filename?: string; steps: WorkflowStep[]; active: WorkflowStepKey;
  unresolvedCount: number; dirtyCount: number; returnHref: string;
  onStep: (step: WorkflowStepKey) => void; onExit: (href: string) => void;
}) {
  const descriptions = ["当前文件、历史版本与 OCR", "基本资料、出版版本与封面", "作者译者、学科与知识关联", "核对草稿并明确发布"];
  return <div className="workflow-v307-rail">
    <button className="workflow-v307-return" type="button" onClick={() => onExit(returnHref)}><ArrowLeft size={15} />返回列表{dirtyCount ? <span> · {dirtyCount} 项未保存</span> : null}</button>
    <nav aria-label="馆藏工作分区">{WORKFLOW_GROUPS.map((group, index) => {
      const members = steps.filter(step => group.steps.some(key => key === step.key));
      const current = group.steps.some(key => key === active);
      const complete = members.length > 0 && members.every(step => ["complete", "skipped"].includes(step.status));
      return <button type="button" key={group.label} className={current ? "active" : ""} aria-current={current ? "step" : undefined} onClick={() => onStep((members[0]?.key || group.steps[0]) as WorkflowStepKey)}><b>{complete && !current ? <Check size={16} /> : index + 1}</b><span><strong>{group.label}</strong><small>{descriptions[index]}</small></span></button>;
    })}</nav>
  </div>;
}
