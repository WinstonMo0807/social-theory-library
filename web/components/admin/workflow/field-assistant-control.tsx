"use client";

import { Check, ChevronDown, ChevronUp, LoaderCircle, Plus, Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { assistantCacheKey, invalidateAssistantCache, lookupFieldSuggestions } from "./field-assistant-cache";

type Evidence = { category?: string; summary?: string };
type Suggestion = {
  id: string;
  label: string;
  status_label: string;
  summary: string;
  evidence: Evidence[];
  conflicts: string[];
  action: { source_type: string; source_id: string; selected_value?: string };
};

type LookupResult = {
  field: { lookup_label: string; adopt_label: string; create_label: string };
  results: Suggestion[];
  more_results?: Suggestion[];
  has_more: boolean;
  more_count: number;
};

const FIELD_COPY = {
  author: { label: "作者", lookup: "智能查找", create: "学者" },
  translator: { label: "译者", lookup: "智能查找", create: "学者" },
  publisher: { label: "出版社", lookup: "重新查找", create: "出版社" },
  topic: { label: "主题", lookup: "获取分类建议", create: "主题" },
  theory: { label: "理论传统", lookup: "获取分类建议", create: "理论传统" },
  publication_year: { label: "本版本出版年份", lookup: "智能查找", create: "" },
  abstract: { label: "简介", lookup: "查找简介", create: "" },
} as const;

export type AssistantFieldName = keyof typeof FIELD_COPY;
type Duplicate = { id: string; label?: string; name?: string; entity_type?: string };

export function FieldAssistantControl({
  editionId,
  fieldName,
  query,
  token,
  disabled,
  onSaved,
  beforeAction,
  contextKey = "",
}: {
  editionId: string;
  fieldName: AssistantFieldName;
  query?: string;
  token: string | null;
  disabled?: boolean;
  onSaved: (message: string) => Promise<void> | void;
  beforeAction?: () => Promise<boolean>;
  contextKey?: string;
}) {
  const popoverId = useId();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [data, setData] = useState<LookupResult | null>(null);
  const [message, setMessage] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [showMore, setShowMore] = useState(false);
  const [duplicates, setDuplicates] = useState<Duplicate[] | null>(null);
  const [duplicateName, setDuplicateName] = useState("");
  const requestRef = useRef<AbortController | null>(null);
  const preparingRef = useRef(false);
  const copy = FIELD_COPY[fieldName];
  const lookupKey = assistantCacheKey(editionId, fieldName, query, contextKey);
  const lookupKeyRef = useRef(lookupKey);
  lookupKeyRef.current = lookupKey;
  const lookupContextRef = useRef({ editionId, fieldName, query, contextKey });
  lookupContextRef.current = { editionId, fieldName, query, contextKey };

  useEffect(() => {
    setData(null);
    if (preparingRef.current) return;
    requestRef.current?.abort();
    setLoading(false);
    setOpen(false);
    setDuplicates(null);
  }, [lookupKey]);

  useEffect(() => () => requestRef.current?.abort(), []);

  const prepare = async () => {
    if (beforeAction && !(await beforeAction())) throw new Error("草稿尚未保存成功，请先处理保存提示。");
  };

  const lookup = async () => {
    setOpen(true);
    setLoading(true);
    setMessage("");
    setShowMore(false);
    requestRef.current?.abort();
    let request: AbortController | null = null;
    try {
      preparingRef.current = true;
      try { await prepare(); } finally { preparingRef.current = false; }
      setOpen(true);
      request = new AbortController();
      requestRef.current = request;
      const requestKey = lookupKeyRef.current;
      const result = await lookupFieldSuggestions<LookupResult>({ ...lookupContextRef.current, token, signal: request.signal });
      if (request.signal.aborted || requestKey !== lookupKeyRef.current) return;
      setData(result);
    } catch (reason) {
      if (request?.signal.aborted) return;
      setOpen(true);
      setMessage(reason instanceof Error ? reason.message : "暂时无法查找建议，可以继续手工填写。");
    } finally {
      if (!request || requestRef.current === request) setLoading(false);
    }
  };

  const adopt = async (suggestion: Suggestion) => {
    setBusy(suggestion.id);
    setMessage("");
    try {
      await prepare();
      await apiRequest("/catalog/admin/field-assistant/adopt/", {
        method: "POST",
        body: JSON.stringify({
          edition_id: editionId,
          field_name: fieldName,
          source_type: suggestion.action.source_type,
          source_id: suggestion.action.source_id,
          selected_value: suggestion.action.selected_value ?? suggestion.label,
        }),
      }, token);
      invalidateAssistantCache(editionId);
      setOpen(false);
      await onSaved("已采用并保存到当前草稿。");
    } catch (reason) {
      setOpen(true);
      setMessage(reason instanceof Error ? reason.message : "未保存成功，请重试。");
    } finally {
      setBusy("");
    }
  };

  const reject = async (suggestion: Suggestion) => {
    setBusy(`reject-${suggestion.id}`);
    setMessage("");
    try {
      await apiRequest("/catalog/admin/field-assistant/reject/", {
        method: "POST",
        body: JSON.stringify({ edition_id: editionId, field_name: fieldName, source_type: suggestion.action.source_type, source_id: suggestion.action.source_id, reason: "管理员确认与当前字段不符" }),
      }, token);
      invalidateAssistantCache(editionId);
      setData((current) => current ? { ...current, results: current.results.filter((item) => item.id !== suggestion.id), more_results: current.more_results?.filter((item) => item.id !== suggestion.id) } : current);
      setMessage("已记录不采用，可帮助后续辨别同名对象。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "未能保存这次决定，请重试。");
    } finally {
      setBusy("");
    }
  };

  const create = async (allowPossibleDuplicate = false) => {
    if (!newLabel.trim()) return;
    setBusy("create");
    setMessage("");
    try {
      await prepare();
      if (!allowPossibleDuplicate || duplicateName !== newLabel.trim()) {
        const found = await apiRequest<{ matches: Duplicate[] }>("/catalog/admin/field-assistant/duplicates/", { method: "POST", body: JSON.stringify({ field_name: fieldName, label: newLabel.trim() }) }, token);
        setDuplicates(found.matches);
        setDuplicateName(newLabel.trim());
        if (found.matches.length) {
          setMessage("馆内有相近记录。请先查看建议中的已有对象，确认不同后才新建。");
          return;
        }
      }
      await apiRequest("/catalog/admin/field-assistant/create/", {
        method: "POST",
        body: JSON.stringify({ edition_id: editionId, field_name: fieldName, label: newLabel.trim(), allow_possible_duplicate: allowPossibleDuplicate && duplicateName === newLabel.trim() }),
      }, token);
      invalidateAssistantCache(editionId);
      setOpen(false);
      setNewLabel("");
      await onSaved("已新建馆内草稿对象并关联当前作品。");
    } catch (reason) {
      setOpen(true);
      setMessage(reason instanceof Error ? reason.message : "未保存成功，请重试。");
    } finally {
      setBusy("");
    }
  };

  const primaryResults = data?.results.slice(0, 3) ?? [];
  const moreResults = [
    ...(data?.results.slice(3) ?? []),
    ...(data?.more_results ?? []),
  ];
  const visibleResults = showMore ? [...primaryResults, ...moreResults] : primaryResults;
  const moreCount = moreResults.length || data?.more_count || 0;

  return <div className="field-assistant-control">
    <button type="button" className="field-assistant-trigger" disabled={disabled || !editionId || Boolean(busy) || loading} aria-expanded={open} aria-controls={popoverId} onClick={lookup}><Search size={13} />{data?.field.lookup_label || copy.lookup}</button>
    {open ? <section id={popoverId} className="field-assistant-popover" aria-label={`${copy.label}建议`} aria-busy={loading}>
      <header><strong>{copy.label}建议</strong><button type="button" aria-label={`关闭${copy.label}建议`} onClick={() => setOpen(false)}><X size={14} /></button></header>
      {loading ? <p><LoaderCircle className="spin" size={14} />正在查找馆内记录和已有依据</p> : null}
      {!loading && visibleResults.map((suggestion) => <article key={suggestion.id}>
        <div><strong>{suggestion.label}</strong><span>{suggestion.status_label}</span><p>{suggestion.summary}</p></div>
        {suggestion.conflicts.length ? <p className="field-assistant-conflict">{suggestion.conflicts.join("；")}</p> : null}
        <details><summary>查看依据</summary><ul>{suggestion.evidence.map((item, index) => <li key={`${suggestion.id}-${index}`}><b>{item.category}</b>{item.summary}</li>)}</ul></details>
        <button type="button" disabled={Boolean(busy) || disabled} onClick={() => adopt(suggestion)}>{busy === suggestion.id ? <LoaderCircle className="spin" size={13} /> : <Check size={13} />}{data?.field.adopt_label || `采用${copy.label}`}</button><button type="button" disabled={Boolean(busy) || disabled} onClick={() => reject(suggestion)}>{fieldName === "author" || fieldName === "translator" ? "不是此人" : "不采用"}</button>
      </article>)}
      {!loading && data && !data.results.length ? <p>暂时没有合适建议，可以继续手工填写。</p> : null}
      {!loading && moreCount ? <button type="button" className="field-assistant-more" aria-expanded={showMore} onClick={() => setShowMore((current) => !current)}>{showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showMore ? "收起更多结果" : `查看另外 ${moreCount} 项结果`}</button> : null}
      {copy.create ? <footer><input aria-label={`新${copy.create}名称`} value={newLabel} disabled={Boolean(busy) || disabled} onChange={(event) => { setNewLabel(event.target.value); setDuplicates(null); }} placeholder={`输入${copy.create}名称`} /><button type="button" disabled={!newLabel.trim() || Boolean(busy) || disabled} onClick={() => create()}>{busy === "create" ? <LoaderCircle className="spin" size={13} /> : <Plus size={13} />}{data?.field.create_label || `创建${copy.create}`}并关联</button>{duplicates?.length ? <div><p>可能已有记录</p><ul>{duplicates.map((item) => <li key={item.id}>{item.label || item.name || "馆内已有对象"}</li>)}</ul><button type="button" disabled={Boolean(busy) || disabled} onClick={() => create(true)}>确认是不同对象，新建并关联</button></div> : null}</footer> : null}
      {message ? <p role="alert" aria-live="polite" className="field-assistant-message">{message}</p> : null}
    </section> : null}
  </div>;
}
