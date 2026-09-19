"use client";

import { Check, Pencil, Search, ShieldCheck, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionButton } from "@/components/action-feedback";
import {
  candidateEditableValue,
  candidateRejectionAction,
  candidateRejectionReasons,
  parseCandidateEditableValue,
  resolveCandidateActionDescriptors,
  type CandidateActionDescriptor,
  type CandidateActionSource,
} from "./candidate-action-contract";

function ActionIcon({ action }: { action: string }) {
  if (action === "reject") return <X size={12} />;
  if (action === "accept_with_edit") return <Pencil size={12} />;
  if (action === "inspect") return <Search size={12} />;
  if (action === "verify") return <ShieldCheck size={12} />;
  return <Check size={12} />;
}

export function CandidateDecisionBar({
  candidate,
  busyAction = "",
  disabled = false,
  className = "candidate-decision-bar",
  showInspect = true,
  actionFilter,
  onInspect,
  onAction,
}: {
  candidate: CandidateActionSource;
  busyAction?: string;
  disabled?: boolean;
  className?: string;
  showInspect?: boolean;
  actionFilter?: (descriptor: CandidateActionDescriptor) => boolean;
  onInspect?: () => void;
  onAction: (descriptor: CandidateActionDescriptor, editedValue?: unknown) => Promise<void> | void;
}) {
  const descriptors = useMemo(() => {
    const resolved = resolveCandidateActionDescriptors(candidate);
    const withInspect = showInspect && onInspect && !resolved.some((row) => row.action === "inspect")
      ? [...resolved, {
          action: "inspect",
          label: "查看依据",
          url: "",
          method: "GET",
          payload: {},
          tone: "secondary" as const,
          editable: false,
          valueField: "proposed_value",
          disabled: false,
          disabledReason: "",
          source: "legacy" as const,
        }]
      : resolved;
    return actionFilter ? withInspect.filter(actionFilter) : withInspect;
  }, [actionFilter, candidate, onInspect, showInspect]);
  const candidateIdentity = String(candidate.id ?? candidate.label ?? "candidate");
  const [editor, setEditor] = useState(() => ({
    candidateIdentity,
    action: "",
    text: candidateEditableValue(candidate),
  }));
  const editingAction = editor.candidateIdentity === candidateIdentity ? editor.action : "";
  const editedText = editor.candidateIdentity === candidateIdentity ? editor.text : candidateEditableValue(candidate);

  const editingDescriptor = descriptors.find((row) => row.action === editingAction);
  const original = candidate.proposed_value ?? candidate.value ?? candidate.label;
  const [rejection, setRejection] = useState({ candidateIdentity, action: "", reason: "unsupported_content", detail: "" });
  const rejecting = rejection.candidateIdentity === candidateIdentity ? descriptors.find((row) => row.action === rejection.action) : undefined;

  async function invoke(descriptor: CandidateActionDescriptor, editedValue?: unknown) {
    if (descriptor.action === "inspect") {
      onInspect?.();
      return;
    }
    await onAction(descriptor, editedValue);
  }

  return (
    <div className={className}>
      <div className="candidate-decision-actions">
        {descriptors.map((descriptor) => (
          <ActionButton
            className={descriptor.tone === "danger" ? "danger" : descriptor.tone === "secondary" ? "secondary" : ""}
            state={busyAction === descriptor.action ? "pending" : "idle"}
            pendingLabel={descriptor.action === "verify" ? "核实中" : "处理中"}
            disabled={disabled || Boolean(busyAction) || descriptor.disabled}
            title={descriptor.disabledReason || undefined}
            type="button"
            key={descriptor.action}
            onClick={() => descriptor.action === "reject"
              ? setRejection({ candidateIdentity, action: "reject", reason: "unsupported_content", detail: "" })
              : descriptor.editable
              ? setEditor((current) => ({
                  candidateIdentity,
                  action: current.candidateIdentity === candidateIdentity && current.action === descriptor.action ? "" : descriptor.action,
                  text: current.candidateIdentity === candidateIdentity ? current.text : candidateEditableValue(candidate),
                }))
              : void invoke(descriptor)}
          >
            <ActionIcon action={descriptor.action} />{descriptor.label}
          </ActionButton>
        ))}
      </div>
      {rejecting ? <section className="candidate-decision-editor" aria-label="不采用理由"><label><span>不采用理由</span><select value={rejection.reason} onChange={(event) => setRejection({ ...rejection, reason: event.target.value })}>{Object.entries(candidateRejectionReasons).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label><span>{rejection.reason === "other" ? "具体理由（必填）" : "补充说明（可选）"}</span><textarea rows={2} value={rejection.detail} onChange={(event) => setRejection({ ...rejection, detail: event.target.value })} /></label><footer><ActionButton className="danger" type="button" disabled={disabled || Boolean(busyAction) || (rejection.reason === "other" && !rejection.detail.trim())} onClick={() => void invoke(candidateRejectionAction(rejecting, rejection.reason, rejection.detail))}>确认不采用并记录理由</ActionButton><ActionButton className="secondary" type="button" disabled={Boolean(busyAction)} onClick={() => setRejection({ ...rejection, action: "" })}>取消</ActionButton></footer></section> : null}
      {editingDescriptor ? (
        <section className="candidate-decision-editor" aria-label={`${editingDescriptor.label}编辑器`}>
          <label><span>修改后的候选值</span><textarea rows={4} value={editedText} onChange={(event) => setEditor({ candidateIdentity, action: editingAction, text: event.target.value })} /></label>
          <footer>
            <ActionButton
              state={busyAction === editingDescriptor.action ? "pending" : "idle"}
              pendingLabel="正在采用"
              disabled={disabled || Boolean(busyAction) || !editedText.trim()}
              type="button"
              onClick={() => void invoke(editingDescriptor, parseCandidateEditableValue(editedText, original))}
            ><Check size={12} />确认修改并采用</ActionButton>
            <ActionButton className="secondary" disabled={disabled || Boolean(busyAction)} type="button" onClick={() => setEditor({ candidateIdentity, action: "", text: candidateEditableValue(candidate) })}>取消</ActionButton>
          </footer>
        </section>
      ) : null}
    </div>
  );
}
