"use client";

import { Check, ChevronsUpDown, Lock, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export type SelectOption = { value: string; label: string };
export type EntityValue = { id: string | null; name: string; status?: string; [key: string]: unknown };

type CanonicalFieldProps = {
  name: string;
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: "text" | "number" | "date" | "url";
  options?: readonly SelectOption[];
  multiline?: boolean;
  rows?: number;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  help?: ReactNode;
  status?: string;
  candidateCount?: number;
  locked?: boolean;
  onToggleLock?: () => void;
  onInspect?: () => void;
  error?: string;
};

export function CandidateIndicator({ count, onClick }: { count: number; onClick?: () => void }) {
  if (!count) return null;
  return (
    <button className="workflow-candidate-indicator" type="button" onClick={onClick}>
      {count} 个候选
    </button>
  );
}

export function CanonicalField({
  name,
  label,
  value,
  onChange,
  type = "text",
  options,
  multiline = false,
  rows = 4,
  required = false,
  disabled = false,
  placeholder,
  help,
  status,
  candidateCount = 0,
  locked = false,
  onToggleLock,
  onInspect,
  error,
}: CanonicalFieldProps) {
  const inputId = useId();
  const helpId = useId();
  const errorId = useId();
  const describedBy = [help ? helpId : "", error ? errorId : ""].filter(Boolean).join(" ") || undefined;
  const common = {
    id: inputId,
    name,
    value,
    required,
    disabled,
    placeholder,
    "aria-invalid": Boolean(error),
    "aria-describedby": describedBy,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => onChange(event.target.value),
  };
  return (
    <div className={`workflow-field ${error ? "has-error" : ""}`} data-field={name}>
      <div className="workflow-field-label-row">
        <label htmlFor={inputId}>{label}{required ? <span aria-hidden="true"> *</span> : null}</label>
        <span>
          {status ? <small className={`workflow-field-status status-${status}`}>{status}</small> : null}
          <CandidateIndicator count={candidateCount} onClick={onInspect} />
          {onToggleLock ? (
            <button className={locked ? "is-locked" : ""} type="button" onClick={onToggleLock}>
              <Lock size={11} />{locked ? "已锁定" : "锁定"}
            </button>
          ) : null}
        </span>
      </div>
      {options ? (
        <select {...common}>{options.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select>
      ) : multiline ? (
        <textarea {...common} rows={rows} />
      ) : (
        <input {...common} type={type} />
      )}
      {help ? <small className="workflow-field-help" id={helpId}>{help}</small> : null}
      {error ? <small className="workflow-field-error" id={errorId} role="alert">{error}</small> : null}
    </div>
  );
}

export function MultilingualField({
  primary,
  original,
}: {
  primary: CanonicalFieldProps;
  original: CanonicalFieldProps;
}) {
  return <div className="workflow-multilingual-field"><CanonicalField {...primary} /><CanonicalField {...original} /></div>;
}

export function ConditionalFieldGroup({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return <fieldset className="workflow-conditional-group"><legend>{title}</legend>{description ? <p>{description}</p> : null}<div>{children}</div></fieldset>;
}

export function RepeatableField<T>({
  label,
  values,
  create,
  render,
  onChange,
  addLabel = "添加一项",
}: {
  label: string;
  values: T[];
  create: () => T;
  render: (value: T, index: number, update: (value: T) => void) => ReactNode;
  onChange: (values: T[]) => void;
  addLabel?: string;
}) {
  return (
    <section className="workflow-repeatable-field">
      <header><strong>{label}</strong><button type="button" onClick={() => onChange([...values, create()])}><Plus size={14} />{addLabel}</button></header>
      <div>{values.map((value, index) => (
        <article key={index}>
          {render(value, index, (next) => onChange(values.map((entry, entryIndex) => entryIndex === index ? next : entry)))}
          <button className="workflow-repeatable-remove" type="button" aria-label={`移除${label} ${index + 1}`} onClick={() => onChange(values.filter((_entry, entryIndex) => entryIndex !== index))}><Trash2 size={14} /></button>
        </article>
      ))}</div>
    </section>
  );
}

export function EntityPicker({
  label,
  endpoint,
  values,
  onChange,
  nameField = "name",
  placeholder = "搜索已有条目",
  allowUnresolved = false,
}: {
  label: string;
  endpoint: string;
  values: EntityValue[];
  onChange: (values: EntityValue[]) => void;
  nameField?: string;
  placeholder?: string;
  allowUnresolved?: boolean;
}) {
  const listboxId = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<EntityValue[]>([]);

  useEffect(() => {
    if (!open) return;
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const suffix = query.trim() ? `${endpoint.includes("?") ? "&" : "?"}search=${encodeURIComponent(query.trim())}` : "";
      void apiRequest<{ results?: Array<Record<string, unknown>> } | Array<Record<string, unknown>>>(`${endpoint}${suffix}`, {}, token)
        .then((payload) => {
          if (!active) return;
          const rows = Array.isArray(payload) ? payload : payload.results ?? [];
          setOptions(rows.flatMap((row) => {
            const name = String(row[nameField] ?? row.preferred_name ?? row.canonical_name_zh ?? row.title ?? "").trim();
            return name ? [{ id: String(row.id), name, status: String(row.status ?? row.editorial_status ?? "") }] : [];
          }));
        })
        .catch(() => { if (active) setOptions([]); })
        .finally(() => { if (active) setLoading(false); });
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [endpoint, nameField, open, query]);

  const select = (value: EntityValue) => {
    if (!values.some((entry) => entry.id === value.id || entry.name.toLocaleLowerCase() === value.name.toLocaleLowerCase())) {
      onChange([...values, value]);
    }
    setQuery("");
    setOpen(false);
  };
  return (
    <div className="workflow-entity-picker">
      <strong>{label}</strong>
      <div className="workflow-entity-values">{values.map((value, index) => (
        <button type="button" key={`${value.id ?? value.name}-${index}`} onClick={() => onChange(values.filter((_entry, entryIndex) => entryIndex !== index))}>
          {value.name}{value.id ? "" : " · 未解析"} ×
        </button>
      ))}</div>
      <div className="workflow-entity-combobox">
        <Search size={14} />
        <input value={query} placeholder={placeholder} role="combobox" aria-expanded={open} aria-controls={listboxId} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} />
        <button type="button" aria-label="显示候选" onClick={() => setOpen((value) => !value)}><ChevronsUpDown size={14} /></button>
        {open ? <div className="workflow-entity-options" id={listboxId} role="listbox">
          {loading ? <small>正在搜索……</small> : null}
          {!loading ? options.map((option) => <button type="button" role="option" aria-selected={false} key={option.id} onClick={() => select(option)}><span><strong>{option.name}</strong><small>{option.status || "已有条目"}</small></span><Check size={13} /></button>) : null}
          {!loading && allowUnresolved && query.trim() ? <button type="button" onClick={() => select({ id: null, name: query.trim(), status: "unresolved" })}><span><strong>保留“{query.trim()}”</strong><small>保持未解析，后续仍需确认</small></span><Plus size={13} /></button> : null}
          {!loading && !options.length && !allowUnresolved ? <small>没有匹配的正式条目。</small> : null}
        </div> : null}
      </div>
    </div>
  );
}

export function QualityIssue({
  message,
  tone = "warning",
  onActivate,
}: {
  message: string;
  tone?: "blocker" | "warning" | "info";
  onActivate?: () => void;
}) {
  return onActivate
    ? <button className={`workflow-quality-issue tone-${tone}`} type="button" onClick={onActivate}>{message}</button>
    : <p className={`workflow-quality-issue tone-${tone}`}>{message}</p>;
}

export function LifecycleControl({
  value,
  options,
  onChange,
  disabled = false,
}: {
  value: string;
  options: readonly SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return <label className="workflow-lifecycle-control"><span>状态</span><select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>;
}
