"use client";

import { Check, ChevronDown, ChevronUp, LoaderCircle, Plus, Search, X } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { useContextState } from "@/lib/use-context-state";
import { useActionGuard } from "@/lib/use-action-guard";
import { assistantCacheKey, invalidateAssistantCache, lookupFieldSuggestions } from "./field-assistant-cache";
import { CandidateDecisionBar } from "../research/candidate-decision-bar";
import { Dialog } from "@/components/ui/dialog";

type Evidence = { category?: string; summary?: string };
type Suggestion = {
  id: string;
  label: string;
  status_label: string;
  summary: string;
  evidence: Evidence[];
  conflicts: string[];
  entity?: { id: string; type: string } | null;
  action: { source_type: string; source_id: string; selected_value?: string };
};

type LookupResult = {
  refresh?: { state: string; message: string };
  field: { lookup_label: string; adopt_label: string; create_label: string; locked?: boolean; lock_reason?: string };
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

export const ASSISTED_WORK_FIELDS = {
  title: "作品题名", subtitle: "副题名", original_title: "原题名", uniform_title: "规范题名",
  language: "作品语言", original_language: "原作语言", first_publication_date: "首次出版日期", abstract: "简介",
} as const;
export const ASSISTED_BIBLIOGRAPHY_FIELDS = {
  version_label: "版本说明", publication_date: "出版日期", publication_year: "年份", publisher: "出版社",
  publication_place: "出版地", isbn10: "ISBN-10", isbn13: "ISBN-13", doi: "DOI", series: "丛书",
  extent: "页数与装帧说明", responsibility_statement: "贡献说明原文", journal_title: "期刊", volume: "卷", issue: "期",
  page_range: "页码范围", degree_institution: "学位授予单位", degree_type: "学位类型", report_institution: "报告机构",
} as const;
export const FILL_FIELD_LABELS = { ...ASSISTED_WORK_FIELDS, ...ASSISTED_BIBLIOGRAPHY_FIELDS, author: "作者", translator: "译者" } as const;
export type AssistantFieldName = keyof typeof FILL_FIELD_LABELS | keyof typeof FIELD_COPY;
export type AssistedFieldFill = { field_name: keyof typeof FILL_FIELD_LABELS; source_type: string; source_id: string; selected_value: string; selected_entity_id?: string };
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
  onFill,
  formContext,
  onInspect,
  onCreateDraft,
}: {
  editionId: string;
  fieldName: AssistantFieldName;
  query?: string;
  token: string | null;
  disabled?: boolean;
  onSaved: (message: string) => Promise<void> | void;
  beforeAction?: () => Promise<boolean>;
  contextKey?: string;
  onFill?: (selection: AssistedFieldFill) => void;
  formContext?: Record<string, unknown>;
  onInspect?: () => void;
  onCreateDraft?: (entity: { id: string; name: string; type: string; edit_url?: string }) => void;
}) {
  const popoverId = useId();
  const lookupKey = assistantCacheKey(editionId, fieldName, query, contextKey);
  const [open, setOpen] = useContextState(`${editionId}:${fieldName}`, false);
  const [lookupAttempt, setLookupAttempt] = useState(0);
  const [loading, setLoading] = useContextState(lookupKey, false);
  const [busy, setBusy] = useState("");
  const { startAction, finishAction } = useActionGuard();
  const [data, setData] = useContextState<LookupResult | null>(lookupKey, null);
  const [message, setMessage] = useContextState(lookupKey, "");
  const [newLabel, setNewLabel] = useState("");
  const [showMore, setShowMore] = useState(false);
  const [createdEditUrl, setCreatedEditUrl] = useState("");
  const [duplicates, setDuplicates] = useContextState<Duplicate[] | null>(lookupKey, null);
  const [duplicateName, setDuplicateName] = useState("");
  const [identityReview, setIdentityReview] = useContextState(lookupKey, "");
  const newLabelRef = useRef<HTMLInputElement | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const externalLookup = useRef("");
  const copy = fieldName in FIELD_COPY ? FIELD_COPY[fieldName as keyof typeof FIELD_COPY]
    : { label: FILL_FIELD_LABELS[fieldName as keyof typeof FILL_FIELD_LABELS], lookup: "查看填写建议", create: "" };
  const lookupKeyRef = useRef(lookupKey);
  const lookupContextRef = useRef({ editionId, fieldName, query, contextKey, formContext, setData, setOpen, setLoading, setMessage });
  useLayoutEffect(() => {
    lookupKeyRef.current = lookupKey;
    lookupContextRef.current = { editionId, fieldName, query, contextKey, formContext, setData, setOpen, setLoading, setMessage };
  }, [editionId, fieldName, query, contextKey, formContext, lookupKey, setData, setOpen, setLoading, setMessage]);

  useEffect(() => () => requestRef.current?.abort(), []);

  const prepare = async () => {
    if (beforeAction && !(await beforeAction())) throw new Error("草稿尚未保存成功，请先处理保存提示。");
  };

  const lookup = () => {
    externalLookup.current = "";
    setOpen(true);
    setShowMore(false);
    setLookupAttempt((value) => value + 1);
  };

  useEffect(() => {
    if (!open || !editionId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController | null = null;
    const requestKey = lookupKey;
    const external = externalLookup.current === requestKey;
    externalLookup.current = "";
    lookupContextRef.current.setLoading(true);
    async function read(refresh: boolean) {
      request = new AbortController();
      requestRef.current = request;
      const timeout = setTimeout(() => request?.abort(), 15_000);
      const current = lookupContextRef.current;
      try {
        const result = await lookupFieldSuggestions<LookupResult>({ ...current, token, signal: request.signal, refresh, poll: !refresh });
        if (disposed || requestKey !== lookupKeyRef.current) return;
        current.setData(result);
        current.setMessage(result.refresh?.message || "已按当前填写更新建议，尚未保存任何字段。");
        if (result.refresh?.state === "preparing") timer = setTimeout(() => void read(false), 2_000);
      } catch (reason) {
        if (disposed || requestKey !== lookupKeyRef.current) return;
        current.setMessage(`${reason instanceof Error ? reason.message : "建议暂时读取失败"}。保留你的填写，正在重新读取已有任务结果，不会重复启动外部查找。`);
        timer = setTimeout(() => void read(false), 5_000);
      } finally {
        clearTimeout(timeout);
        if (!disposed && requestKey === lookupKeyRef.current) current.setLoading(false);
      }
    }
    // Editing upstream inputs refreshes local/saved results only. An explicit
    // click is required to start another external or paid research run.
    timer = setTimeout(() => void read(external), external ? 0 : 350);
    return () => { disposed = true; clearTimeout(timer); request?.abort(); };
  }, [editionId, lookupKey, lookupAttempt, open, token]);

  const adopt = async (suggestion: Suggestion) => {
    if (!onFill && onCreateDraft && suggestion.entity?.id) {
      if (suggestion.conflicts.length && identityReview !== suggestion.id) {
        setIdentityReview(suggestion.id);
        setMessage("这项关联存在冲突。请核对依据与具体对象，再决定是否填入当前表单。");
        return;
      }
      onCreateDraft({ id: suggestion.entity.id, name: suggestion.label, type: suggestion.entity.type });
      setMessage("已填入当前关联，尚未保存；原表单输入保持不变。");
      return;
    }
    if (onFill && fieldName in FILL_FIELD_LABELS) {
      if ((fieldName === "author" || fieldName === "translator") && !suggestion.entity?.id) {
        setNewLabel(suggestion.label);
        setDuplicates(null);
        setMessage("已将建议姓名填入下方新建框，尚未保存。请先核对馆内相近人物；确认没有对应人物后再新建，不会自动合并同名人物。");
        newLabelRef.current?.focus();
        return;
      }
      if (suggestion.conflicts.length && identityReview !== suggestion.id) {
        setIdentityReview(suggestion.id);
        setMessage("这项建议存在冲突。请查看依据并确认具体人物或出版社；不确定时不要填入。");
        return;
      }
      onFill({ field_name: fieldName as AssistedFieldFill["field_name"], source_type: suggestion.action.source_type,
        source_id: suggestion.action.source_id, selected_value: suggestion.action.selected_value ?? suggestion.label,
        ...(suggestion.entity?.id ? { selected_entity_id: suggestion.entity.id } : {}) });
      setOpen(false);
      return;
    }
    if (!startAction(suggestion.id)) return;
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
      finishAction(suggestion.id);
    }
  };

  const reject = async (suggestion: Suggestion, reason: string) => {
    const actionKey = `reject-${suggestion.id}`;
    if (!startAction(actionKey)) return;
    setBusy(`reject-${suggestion.id}`);
    setMessage("");
    try {
      await apiRequest("/catalog/admin/field-assistant/reject/", {
        method: "POST",
        body: JSON.stringify({ edition_id: editionId, field_name: fieldName, source_type: suggestion.action.source_type, source_id: suggestion.action.source_id, reason }),
      }, token);
      invalidateAssistantCache(editionId);
      setData((current) => current ? { ...current, results: current.results.filter((item) => item.id !== suggestion.id), more_results: current.more_results?.filter((item) => item.id !== suggestion.id) } : current);
      setMessage(`已记录不采用：${reason}。原有资料未改变。`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "未能保存这次决定，请重试。");
    } finally {
      setBusy("");
      finishAction(actionKey);
    }
  };

  const create = async (allowPossibleDuplicate = false) => {
    if (!newLabel.trim() || !startAction("create")) return;
    setBusy("create");
    setMessage("");
    try {
      if (!onCreateDraft) await prepare();
      if (!allowPossibleDuplicate || duplicateName !== newLabel.trim()) {
        const found = await apiRequest<{ matches: Duplicate[] }>("/catalog/admin/field-assistant/duplicates/", { method: "POST", body: JSON.stringify({ field_name: fieldName, label: newLabel.trim() }) }, token);
        setDuplicates(found.matches);
        setDuplicateName(newLabel.trim());
        if (found.matches.length) {
          setMessage("馆内有相近记录。请先查看建议中的已有对象，确认不同后才新建。");
          return;
        }
      }
      const created = await apiRequest<{ entity: { id: string; name: string; type: string; edit_url?: string }; edit_url?: string }>("/catalog/admin/field-assistant/create/", {
        method: "POST",
        body: JSON.stringify({ edition_id: editionId, field_name: fieldName, label: newLabel.trim(), defer_link: Boolean(onCreateDraft), allow_possible_duplicate: allowPossibleDuplicate && duplicateName === newLabel.trim() }),
      }, token);
      invalidateAssistantCache(editionId);
      if (onCreateDraft) {
        onCreateDraft(created.entity);
        setCreatedEditUrl(created.edit_url || created.entity.edit_url || "");
        setMessage("已建立最小草稿并填入本页关联。当前表单未自动保存；可在新标签页补充完整内容。");
      } else setOpen(false);
      setNewLabel("");
      if (!onCreateDraft) await onSaved("已新建馆内草稿对象并关联当前作品。");
    } catch (reason) {
      setOpen(true);
      setMessage(reason instanceof Error ? reason.message : "未保存成功，请重试。");
    } finally {
      setBusy("");
      finishAction("create");
    }
  };

  const primaryResults = data?.results.slice(0, 3) ?? [];
  const moreResults = [
    ...(data?.results.slice(3) ?? []),
    ...(data?.more_results ?? []),
  ];
  const visibleResults = showMore ? [...primaryResults, ...moreResults] : primaryResults;
  const moreCount = moreResults.length || data?.more_count || 0;
  const currentValue = fieldName === "author" ? formContext?.authors : fieldName === "translator" ? formContext?.translators : formContext?.[fieldName] ?? query;
  const currentLabel = Array.isArray(currentValue) ? currentValue.filter((value) => typeof value === "string").join("、") : typeof currentValue === "string" || typeof currentValue === "number" ? String(currentValue) : "";

  return <div className="field-assistant-control">
    <button type="button" className="field-assistant-trigger" disabled={disabled || !editionId || Boolean(busy)} aria-haspopup="dialog" aria-expanded={open} aria-controls={popoverId} onClick={() => setOpen(true)}><Search size={13} />查看填写建议</button>
    {open ? <Dialog open id={popoverId} className="field-assistant-dialog field-assistant-popover" aria-label={`${copy.label}建议`} aria-busy={loading} onRequestClose={() => { if (!busy) setOpen(false); }} onKeyDown={(event) => {
      // Enter in the new-name input must not submit the surrounding work form.
      if (event.key === "Enter" && event.target instanceof HTMLInputElement) event.preventDefault();
    }}>
      <header><strong>{copy.label}建议</strong><button type="button" disabled={Boolean(busy)} aria-label={`关闭${copy.label}建议`} onClick={() => setOpen(false)}><X size={14} /></button></header>
      <p>{onFill ? "按本页填写核对建议。只有你选择填入的字段会改变；填写后仍需保存书目。" : "按本页填写核对建议。采用关联建议前请核对对象，现有公开内容保持不变。"}</p>
      <button type="button" className="button secondary" disabled={disabled || loading || Boolean(busy)} onClick={lookup}>刷新馆内{copy.label}候选</button>
      <small>这里仅查看馆内记录与已有候选。外部书目查询请使用整条书目中的免费来源按钮。</small>
      <p className="field-assistant-current">当前填写：{currentLabel || "尚未填写，可核对后填入建议。"}</p>
      {data?.field.locked ? <p role="status">此字段有人工锁：{data.field.lock_reason || "须由管理员核对后手工修改"}。建议可查看，不能直接填入。</p> : null}
      {loading ? <p><LoaderCircle className="spin" size={14} />正在查找馆内记录和已有依据</p> : null}
      {!loading && visibleResults.map((suggestion) => <article key={suggestion.id}>
        <div><strong>{suggestion.label}</strong><span>{suggestion.status_label}</span><p>{suggestion.summary}</p></div>
        {suggestion.conflicts.length ? <p className="field-assistant-conflict">{suggestion.conflicts.join("；")}</p> : null}
        <details><summary>查看依据</summary><ul>{suggestion.evidence.map((item, index) => <li key={`${suggestion.id}-${index}`}><b>{item.category}</b>{item.summary}</li>)}</ul>{suggestion.entity?.id ? <small>馆内记录编号：{suggestion.entity.id}。仅关联当前书目，不合并人物或修改学者主页。</small> : null}</details>
        <button type="button" disabled={Boolean(busy) || disabled || data?.field.locked} onClick={() => adopt(suggestion)}>{busy === suggestion.id ? <LoaderCircle className="spin" size={13} /> : <Check size={13} />}{onFill ? identityReview === suggestion.id ? `已核对，填入${copy.label}` : (fieldName === "author" || fieldName === "translator") && !suggestion.entity?.id ? "填写新人物名称" : `填入${copy.label}` : data?.field.adopt_label || `采用${copy.label}`}</button>
        <CandidateDecisionBar candidate={{ id: suggestion.id, actions: [{ action: "reject", label: "不采用" }] }} showInspect={false} disabled={Boolean(busy) || disabled} busyAction={busy === `reject-${suggestion.id}` ? "reject" : ""} onAction={(action) => reject(suggestion, String(action.payload.reason))} />
      </article>)}
      {!loading && data && !data.results.length && !message ? <p>当前没有可显示的已有建议，可以继续手工填写。</p> : null}
      {!loading && moreCount ? <button type="button" className="field-assistant-more" aria-expanded={showMore} onClick={() => setShowMore((current) => !current)}>{showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showMore ? "收起更多结果" : `查看另外 ${moreCount} 项结果`}</button> : null}
      {copy.create ? <footer><input ref={newLabelRef} aria-label={`新${copy.create}名称`} value={newLabel} disabled={Boolean(busy) || disabled} onChange={(event) => { setNewLabel(event.target.value); setDuplicates(null); }} placeholder={`输入${copy.create}名称`} /><button type="button" disabled={!newLabel.trim() || Boolean(busy) || disabled} onClick={() => create()}>{busy === "create" ? <LoaderCircle className="spin" size={13} /> : <Plus size={13} />}{data?.field.create_label || `创建${copy.create}`}并关联</button>{onFill ? <p>新建只保存最小身份草稿；当前书目的关联仍需点击页面保存，完整资料可稍后补充。</p> : null}{duplicates?.length ? <div><p>可能已有记录</p><ul>{duplicates.map((item) => <li key={item.id}>{item.label || item.name || "馆内已有对象"}</li>)}</ul><button type="button" disabled={Boolean(busy) || disabled} onClick={() => create(true)}>确认是不同对象，新建并关联</button></div> : null}</footer> : null}
      {message ? <p role="alert" aria-live="polite" className="field-assistant-message">{message}</p> : null}
      {createdEditUrl && /^\/admin\//.test(createdEditUrl) ? <a className="button secondary" href={createdEditUrl} target="_blank" rel="noreferrer">在新标签页完善此草稿 ↗</a> : null}
      {onFill ? <p>填入后可以继续修改，点击页面顶部“保存书目修改”才会保存。不会自动发布。</p> : null}
      {onInspect ? <button type="button" disabled={Boolean(busy)} onClick={() => { setOpen(false); onInspect(); }}>查看全部候选、原文与处理记录</button> : null}
    </Dialog> : null}
  </div>;
}
