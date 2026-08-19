"use client";

import { ExternalLink, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export type AuthorityAlias = {
  name: string;
  language?: string;
  type?: string;
};

export type AuthoritySuggestion = {
  id?: string;
  label: string;
  original_name?: string;
  aliases: AuthorityAlias[];
  description?: string;
  birth_year?: number | null;
  death_year?: number | null;
  external_ids?: Record<string, string>;
  source?: string;
  source_url?: string;
  source_record_id?: string;
  match_reasons?: string[];
  conflicts?: string[];
};

type RawAuthoritySuggestion = Record<string, unknown>;

type AuthoritySuggestionResponse = {
  results?: RawAuthoritySuggestion[];
  warnings?: Array<string | { code?: string; detail?: string }>;
  ai_filter?: { status?: string };
  request_id?: string;
};

function text(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function optionalYear(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && /^-?\d{1,4}$/.test(value.trim())) return Number(value);
  return null;
}

function normalizeAliases(value: unknown): AuthorityAlias[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry) => {
    if (typeof entry === "string") {
      const name = entry.trim();
      return name ? [{ name }] : [];
    }
    if (!entry || typeof entry !== "object") return [];
    const row = entry as Record<string, unknown>;
    const name = text(row.name) || text(row.alias) || text(row.label);
    return name ? [{ name, language: text(row.language), type: text(row.type) || text(row.alias_type) }] : [];
  });
}

function normalizeSuggestion(value: RawAuthoritySuggestion): AuthoritySuggestion | null {
  const label = text(value.label) || text(value.preferred_name) || text(value.canonical_name_zh) || text(value.name);
  if (!label) return null;
  return {
    id: text(value.id),
    label,
    original_name: text(value.original_name) || text(value.canonical_name_en) || text(value.foreign_name),
    aliases: normalizeAliases(value.aliases),
    description: text(value.description),
    birth_year: optionalYear(value.birth_year),
    death_year: optionalYear(value.death_year),
    external_ids: value.external_ids && typeof value.external_ids === "object"
      ? Object.fromEntries(Object.entries(value.external_ids as Record<string, unknown>).flatMap(([key, entry]) => {
        const normalized = text(entry);
        return normalized ? [[key, normalized]] : [];
      }))
      : {},
    source: text(value.source) || text(value.provider),
    source_url: text(value.source_url),
    source_record_id: text(value.source_record_id),
    match_reasons: Array.isArray(value.match_reasons) ? value.match_reasons.map(text).filter(Boolean) : [],
    conflicts: Array.isArray(value.conflicts) ? value.conflicts.map(text).filter(Boolean) : [],
  };
}

export function mergeUniqueStrings(current: string[], additions: string[]) {
  const seen = new Set(current.map((item) => item.trim().toLocaleLowerCase()).filter(Boolean));
  return [...current, ...additions.flatMap((item) => {
    const normalized = item.trim();
    const key = normalized.toLocaleLowerCase();
    if (!normalized || seen.has(key)) return [];
    seen.add(key);
    return [normalized];
  })];
}

type StringListEditorProps = {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  description?: string;
  itemLabel?: string;
  placeholder?: string;
  addLabel?: string;
  required?: boolean;
};

export function StringListEditor({
  label,
  value,
  onChange,
  description,
  itemLabel = "内容",
  placeholder,
  addLabel = "添加一项",
  required = false,
}: StringListEditorProps) {
  const rows = value.length ? value : [""];
  return (
    <fieldset className="structured-editor string-list-editor">
      <legend>{label}</legend>
      {description ? <p className="structured-editor-description">{description}</p> : null}
      <div className="structured-editor-rows">
        {rows.map((item, index) => (
          <div className="structured-editor-row string-row" key={index}>
            <label>
              <span>{itemLabel} {index + 1}</span>
              <input
                autoComplete="off"
                required={required && index === 0}
                value={item}
                placeholder={placeholder}
                onChange={(event) => {
                  const next = [...rows];
                  next[index] = event.target.value;
                  onChange(next);
                }}
              />
            </label>
            <button
              className="structured-editor-remove"
              type="button"
              aria-label={`移除${itemLabel} ${index + 1}`}
              title={`移除${itemLabel} ${index + 1}`}
              disabled={rows.length === 1 && !item}
              onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      <button className="structured-editor-add" type="button" onClick={() => onChange([...rows, ""])}>
        <Plus size={15} />{addLabel}
      </button>
    </fieldset>
  );
}

export type StructuredRow = Record<string, string>;

export type StructuredColumn = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "number";
  multiline?: boolean;
  options?: Array<{ value: string; label: string }>;
};

type StructuredRowsEditorProps = {
  label: string;
  value: StructuredRow[];
  columns: StructuredColumn[];
  createRow: () => StructuredRow;
  onChange: (value: StructuredRow[]) => void;
  description?: string;
  addLabel?: string;
  rowLabel?: string;
};

export function StructuredRowsEditor({
  label,
  value,
  columns,
  createRow,
  onChange,
  description,
  addLabel = "添加记录",
  rowLabel = "记录",
}: StructuredRowsEditorProps) {
  const rows = value.length ? value : [createRow()];
  return (
    <fieldset className="structured-editor structured-rows-editor">
      <legend>{label}</legend>
      {description ? <p className="structured-editor-description">{description}</p> : null}
      <div className="structured-editor-rows">
        {rows.map((row, index) => (
          <article className="structured-editor-card" key={index}>
            <header>
              <strong>{rowLabel} {index + 1}</strong>
              <button
                className="structured-editor-remove"
                type="button"
                aria-label={`移除${rowLabel} ${index + 1}`}
                title={`移除${rowLabel} ${index + 1}`}
                onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
              >
                <Trash2 size={15} />
              </button>
            </header>
            <div className="structured-editor-grid">
              {columns.map((column) => {
                const fieldId = `${label}-${index}-${column.key}`.replace(/\s+/g, "-");
                return (
                  <label key={column.key} htmlFor={fieldId} className={column.multiline ? "span-all" : undefined}>
                    <span>{column.label}</span>
                    {column.options ? (
                      <select id={fieldId} value={row[column.key] ?? ""} onChange={(event) => {
                        const next = [...rows];
                        next[index] = { ...row, [column.key]: event.target.value };
                        onChange(next);
                      }}>
                        {column.options.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                      </select>
                    ) : column.multiline ? (
                      <textarea id={fieldId} rows={2} value={row[column.key] ?? ""} placeholder={column.placeholder} onChange={(event) => {
                        const next = [...rows];
                        next[index] = { ...row, [column.key]: event.target.value };
                        onChange(next);
                      }} />
                    ) : (
                      <input id={fieldId} autoComplete="off" type={column.type ?? "text"} value={row[column.key] ?? ""} placeholder={column.placeholder} onChange={(event) => {
                        const next = [...rows];
                        next[index] = { ...row, [column.key]: event.target.value };
                        onChange(next);
                      }} />
                    )}
                  </label>
                );
              })}
            </div>
          </article>
        ))}
      </div>
      <button className="structured-editor-add" type="button" onClick={() => onChange([...rows, createRow()])}>
        <Plus size={15} />{addLabel}
      </button>
    </fieldset>
  );
}

type AuthoritySuggestionsProps = {
  entityType: "person" | "concept" | "discipline" | "subdiscipline" | "theory_tradition" | "topic";
  query: string;
};

export function AuthoritySuggestions({ entityType, query }: AuthoritySuggestionsProps) {
  const normalizedQuery = useMemo(() => query.normalize("NFKC").trim(), [query]);
  const [request, setRequest] = useState<{ query: string; nonce: number } | null>(null);
  const [results, setResults] = useState<AuthoritySuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setLoading(true);
      setMessage("");
      const token = getServerSessionCredential();
      apiRequest<AuthoritySuggestionResponse>(
        `/catalog/admin/authority-suggestions/?entity_type=${encodeURIComponent(entityType)}&q=${encodeURIComponent(request.query)}`,
        { signal: controller.signal },
        token,
      )
        .then((payload) => {
          if (!active) return;
          const normalized = (payload.results ?? [])
            .map(normalizeSuggestion)
            .filter((item): item is AuthoritySuggestion => item !== null)
            .slice(0, 3);
          const warning = (payload.warnings ?? []).map((item) => typeof item === "string" ? item : text(item.detail) || text(item.code)).filter(Boolean)[0] ?? "";
          setResults(normalized);
          setMessage(warning ? `来源提示：${warning}${payload.request_id ? `（请求编号 ${payload.request_id.slice(0, 12)}）` : ""}` : (normalized.length ? "" : "没有找到可核对的权威候选。可继续人工填写。"));
        })
        .catch((reason) => {
          if (!active || controller.signal.aborted) return;
          setResults([]);
          setMessage(reason instanceof Error ? `来源服务暂时不可用：${reason.message}` : "来源服务暂时不可用，请稍后重试。");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [entityType, request]);

  const minimumLength = /[\u3400-\u9fff]/.test(normalizedQuery) ? 2 : 3;
  if (normalizedQuery.length < minimumLength) return null;
  const currentRequest = request?.query === normalizedQuery;
  return (
    <section className="authority-suggestions" aria-label="联网权威候选">
      <header>
        <div><strong>联网身份候选</strong><span>只用于确认“查的是谁”。当前检索词为 {normalizedQuery}；字段写入必须进入候选审核。</span></div>
        <button type="button" disabled={loading} onClick={() => setRequest({ query: normalizedQuery, nonce: (request?.nonce ?? 0) + 1 })}>查找权威对象</button>
      </header>
      <div aria-live="polite" aria-atomic="true">
        {loading && currentRequest ? <p className="authority-suggestion-status"><LoaderCircle className="spin" size={15} />正在核对来源……</p> : null}
        {!loading && currentRequest && message ? <p className="authority-suggestion-status">{message}</p> : null}
      </div>
      {!loading && currentRequest && results.length ? <div className="authority-suggestion-list">
        {results.map((result, index) => (
          <article key={result.id || `${result.label}-${index}`}>
            <div>
              <strong>{result.label}</strong>
              {result.original_name ? <span>{result.original_name}</span> : null}
              <small>
                {[result.birth_year ? `${result.birth_year}${result.death_year ? `—${result.death_year}` : "—"}` : "", result.source]
                  .filter(Boolean)
                  .join(" · ") || "来源记录待管理员核对"}
              </small>
              {result.description ? <p>{result.description}</p> : null}
              {result.match_reasons?.length ? <p className="authority-match-reason">匹配依据 {result.match_reasons.slice(0, 2).join("；")}</p> : null}
            </div>
            {result.source_url ? <a href={result.source_url} target="_blank" rel="noreferrer">查看来源<ExternalLink size={13} /></a> : <span>来源记录已保留</span>}
          </article>
        ))}
      </div> : null}
    </section>
  );
}
