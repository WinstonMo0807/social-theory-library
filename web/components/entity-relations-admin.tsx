"use client";

import { Check, ExternalLink, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";

type Page<T> = { results: T[] };
type Named = { id: string; name: string; slug?: string; foreign_name?: string; discipline?: string };
type Relation = Record<string, unknown> & { id: string; review_status?: string; evidence_text?: string; relation_label?: string; role?: string; relation_type?: string; strength?: string };

function useRows<T>(path: string) {
  const [rows, setRows] = useState<T[]>([]);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const token = getStoredAccessToken();
    let active = true;
    if (!token) return;
    apiRequest<Page<T> | T[]>(path, {}, token).then((payload) => {
      if (!active) return;
      setRows(Array.isArray(payload) ? payload : payload.results);
    }).catch(() => { if (active) setRows([]); });
    return () => { active = false; };
  }, [path, revision]);
  return { rows, refresh };
}

const relationTitles: Record<string, string> = {
  "theory-disciplines": "所属学科",
  "theory-subdisciplines": "相关子学科",
  "theory-hierarchy": "上位理论传统",
  "theory-relations": "理论关系",
  "topic-disciplines": "相关学科",
  "topic-subdisciplines": "相关子学科",
  "topic-theories": "相关理论传统",
};

function RelationEditor({
  resource,
  ownerField,
  ownerId,
  targetField,
  candidates,
  existing,
  refresh,
  children,
}: {
  resource: string;
  ownerField: string;
  ownerId: string;
  targetField: string;
  candidates: Named[];
  existing: Relation[];
  refresh: () => void;
  children?: (draft: Record<string, string>, setDraft: (value: Record<string, string>) => void) => ReactNode;
}) {
  const [target, setTarget] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const used = new Set(existing.map((row) => String(row[targetField] ?? "")));

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!target) return;
    const token = getStoredAccessToken();
    if (!token) return;
    try {
      await apiRequest(`/catalog/admin/knowledge-relations/${resource}/`, {
        method: "POST",
        body: JSON.stringify({
          [ownerField]: ownerId,
          [targetField]: target,
          ...draft,
          review_status: "approved",
          source: draft.source || "管理员确认",
        }),
      }, token);
      setTarget("");
      setDraft({});
      setMessage("关系已经确认并同步前台。");
      refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  async function remove(id: string) {
    const token = getStoredAccessToken();
    if (!token || !window.confirm("删除这条已确认关系吗？相关前台模块会同步更新。")) return;
    await apiRequest(`/catalog/admin/knowledge-relations/${resource}/${id}/`, { method: "DELETE" }, token);
    refresh();
  }

  return (
    <section className="entity-relation-group">
      <header><h3>{relationTitles[resource]}</h3><small>管理员确认优先</small></header>
      <div className="entity-relation-existing">
        {existing.map((row) => {
          const candidate = candidates.find((item) => item.id === String(row[targetField] ?? ""));
          return <div key={row.id}><Check size={14} /><span><strong>{candidate?.name || "已关联对象"}</strong><small>{String(row.role || row.relation_label || row.relation_type || "已确认")}</small></span><button type="button" onClick={() => void remove(row.id)} aria-label="删除关系"><Trash2 size={14} /></button></div>;
        })}
        {!existing.length ? <p>暂无已确认关系。</p> : null}
      </div>
      <form onSubmit={add}>
        <select value={target} onChange={(event) => setTarget(event.target.value)} required><option value="">选择已有对象</option>{candidates.filter((item) => !used.has(item.id)).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select>
        {children?.(draft, setDraft)}
        <button type="submit"><Plus size={14} />确认关系</button>
      </form>
      {message ? <small className="form-message">{message}</small> : null}
    </section>
  );
}

export function EntityRelationsAdmin({
  kind,
  entityId,
  previewHref,
}: {
  kind: "theory" | "topic";
  entityId: string;
  previewHref?: string;
}) {
  const disciplines = useRows<Named>("/catalog/admin/disciplines/?page_size=100");
  const subdisciplines = useRows<Named>("/catalog/admin/subdisciplines/?page_size=200");
  const theories = useRows<Named>("/catalog/admin/theory-schools/?page_size=200");
  const resources = useMemo(() => kind === "theory" ? [
    { resource: "theory-disciplines", ownerField: "theory_school", targetField: "discipline" },
    { resource: "theory-subdisciplines", ownerField: "theory_school", targetField: "subdiscipline" },
    { resource: "theory-hierarchy", ownerField: "child", targetField: "parent" },
    { resource: "theory-relations", ownerField: "source_theory", targetField: "target_theory" },
  ] : [
    { resource: "topic-disciplines", ownerField: "topic", targetField: "discipline" },
    { resource: "topic-subdisciplines", ownerField: "topic", targetField: "subdiscipline" },
    { resource: "topic-theories", ownerField: "topic", targetField: "theory_school" },
  ], [kind]);
  const relationResources = resources.map((item) => ({
    ...item,
    // Hooks cannot be called dynamically. The child component below owns the fetch.
  }));

  return (
    <section className="admin-panel entity-relations-admin">
      <header>
        <div><p className="eyebrow">规范关系</p><h2>知识归位与前台去向</h2><span>这里管理实体关系。保存后，学科页、理论页、子学科页和主题页会从同一条关系记录自动生成。</span></div>
        {previewHref ? <Link className="admin-outline-button" href={previewHref} target="_blank">预览公开页面 <ExternalLink size={14} /></Link> : null}
      </header>
      <div className="entity-relations-grid">
        {relationResources.map((configuration) => (
          <RelationResource
            key={configuration.resource}
            {...configuration}
            ownerId={entityId}
            candidates={configuration.targetField === "discipline" ? disciplines.rows : configuration.targetField === "subdiscipline" ? subdisciplines.rows : theories.rows.filter((item) => item.id !== entityId)}
          />
        ))}
      </div>
    </section>
  );
}

function RelationResource({ resource, ownerField, ownerId, targetField, candidates }: { resource: string; ownerField: string; ownerId: string; targetField: string; candidates: Named[] }) {
  const relations = useRows<Relation>(`/catalog/admin/knowledge-relations/${resource}/?${ownerField}=${encodeURIComponent(ownerId)}`);
  return <RelationEditor resource={resource} ownerField={ownerField} ownerId={ownerId} targetField={targetField} candidates={candidates} existing={relations.rows} refresh={relations.refresh}>{(draft, setDraft) => {
    if (resource === "theory-disciplines") return <select value={draft.role || "related"} onChange={(event) => setDraft({ ...draft, role: event.target.value })}><option value="primary">主要学科</option><option value="related">相关学科</option></select>;
    if (resource === "theory-subdisciplines") return <select value={draft.role || "related"} onChange={(event) => setDraft({ ...draft, role: event.target.value })}><option value="core">核心理论</option><option value="related">相关理论</option><option value="applied">常用理论</option></select>;
    if (resource === "theory-relations") return <><select value={draft.relation_type || "adjacent"} onChange={(event) => setDraft({ ...draft, relation_type: event.target.value })}><option value="influence">影响</option><option value="continuation">继承</option><option value="split">分化</option><option value="critique">批评</option><option value="synthesis">综合</option><option value="adjacent">相邻</option></select><select value={draft.strength || "medium"} onChange={(event) => setDraft({ ...draft, strength: event.target.value })}><option value="high">强</option><option value="medium">中</option><option value="low">弱</option></select><input value={draft.evidence_text || ""} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} placeholder="依据或证据原文" /></>;
    if (resource === "theory-hierarchy") return <input value={draft.evidence_text || ""} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} placeholder="谱系依据" />;
    if (resource === "topic-disciplines") return <label className="relation-check"><input type="checkbox" checked={draft.is_primary === "true"} onChange={(event) => setDraft({ ...draft, is_primary: String(event.target.checked) })} />主要学科</label>;
    return <input value={draft.relation_label || ""} onChange={(event) => setDraft({ ...draft, relation_label: event.target.value })} placeholder="关系说明" />;
  }}</RelationEditor>;
}
