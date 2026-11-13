"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { profileFields, type IdentityProfile } from "@/lib/knowledge-profiles";
import { EntityProfileContent } from "../public/entity-profile-content";
import { EntityAliases } from "../public/knowledge-page-content";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { knowledgeCall } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";

export function EntityProfileFields({ kind, value, disabled, onChange }: { kind: string; value: IdentityProfile; disabled?: boolean; onChange: (profile: IdentityProfile) => void }) {
  return <div className={s.profileFields}>{(profileFields[kind] || []).filter(field => !field.date || value[field.key] || ["month", "day"].includes(String(value.date_precision))).map(field => <label key={field.key} className={field.multiline ? s.profileWide : undefined}>{field.label}{field.options ?
    <select value={String(value[field.key] || "")} disabled={disabled} onChange={e => onChange({ ...value, [field.key]: field.date ? e.target.value || null : e.target.value })}><option value="" disabled>请选择</option>{Object.entries(field.options).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select> :
    field.multiline ? <textarea rows={3} maxLength={field.max || 600} value={value[field.key] ?? ""} disabled={disabled} onChange={e => onChange({ ...value, [field.key]: e.target.value })} /> :
    <input type={field.number ? "number" : field.date ? "date" : "text"} min={field.number ? -32768 : undefined} max={field.number ? 32767 : undefined} maxLength={field.max || 600} value={value[field.key] ?? ""} disabled={disabled} onChange={e => onChange({ ...value, [field.key]: field.number ? (e.target.value === "" ? null : Number(e.target.value)) : field.date ? e.target.value || null : e.target.value })} />}</label>)}</div>;
}

type ProfileData = { label: string; kind: string; profile: IdentityProfile; profile_hash: string; profile_editable: boolean; editor_url?: string };
export function EntityProfileEditor({ entityId }: { entityId: string }) {
  const [data, setData] = useState<ProfileData | null>(null), [profile, setProfile] = useState<IdentityProfile>({});
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [saved, setSaved] = useState(""), [attempt, setAttempt] = useState(0);
  const request = useRef<{ signature: string; id: string } | null>(null);
  const dirty = !!data && JSON.stringify(profile) !== JSON.stringify(data.profile);
  useUnsavedForm(!saved && dirty, false);
  useEffect(() => { const c = new AbortController(); setData(null); setError("");
    void knowledgeCall<ProfileData>(`/knowledge/entities/${entityId}/profile/`, undefined, c.signal).then(value => { setData(value); setProfile(value.profile || {}); }).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort(); }, [entityId, attempt]);
  async function submit() {
    if (!data) return; setBusy(true); setError("");
    const body = { profile, base_hash: data.profile_hash }, signature = JSON.stringify(body);
    if (request.current?.signature !== signature) request.current = { signature, id: createRequestKey() };
    try { const result = await knowledgeCall<{ id: string }>(`/knowledge/entities/${entityId}/profile/`, { ...body, request_id: request.current.id }); setSaved(result.id); }
    catch (e) { setError(e instanceof Error ? e.message : "资料未能提交，请重试。"); } finally { setBusy(false); }
  }
  if (error && !data) return <p className={s.error} role="alert">{error} <button onClick={() => setAttempt(v => v + 1)}>重试</button></p>;
  if (!data) return null;
  return <><EntityAliasEditor key={entityId} entityId={entityId} label={data.label} baseHash={data.profile_hash} />{data.profile_editable && <details data-disclosure="collection"><summary>编辑类型资料</summary><div className={s.editor}>
    {data.editor_url && <p><Link href={data.editor_url}>核对事件关联的学者、出版版本与出处</Link></p>}
    <EntityProfileFields kind={data.kind} value={profile} disabled={busy} onChange={value => { setProfile(value); setSaved(""); }} />
    <section className={s.preview} aria-label="类型资料展示预览"><h2>{data.label}</h2><EntityProfileContent kind={data.kind} profile={profile} /></section>
    <button className={s.primary} disabled={busy || !dirty} onClick={() => void submit()}>提交资料并审核</button>
    {error && <p className={s.error} role="alert">{error}</p>}{saved && <p role="status">审核稿已保存。<Link href={`/admin/knowledge/review?changeset=${saved}`}>打开审核工作台</Link></p>}
  </div></details>}</>;
}

function EntityAliasEditor({ entityId, label, baseHash }: { entityId: string; label: string; baseHash: string }) {
  const [value, setValue] = useState({ text: "", language: "", script: "" }), [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState("");
  const request = useRef<{ signature: string; id: string } | null>(null);
  useUnsavedForm(!saved && !!Object.values(value).some(Boolean), false);
  async function submit() {
    setBusy(true); setError("");
    const body = { ...value, base_hash: baseHash }, signature = JSON.stringify(body);
    if (request.current?.signature !== signature) request.current = { signature, id: createRequestKey() };
    try { const result = await knowledgeCall<{ id: string }>(`/knowledge/entities/${entityId}/aliases/`, { ...body, request_id: request.current.id }); setSaved(result.id); }
    catch (e) { setError(e instanceof Error ? e.message : "异名未能提交，请重试。"); } finally { setBusy(false); }
  }
  return <details data-disclosure="collection"><summary>新增异名</summary><div className={s.editor}>
    <div className={s.aliasCompose}><div className={s.profileFields}>{([{ key: "text", label: "异名", max: 600 }, { key: "language", label: "语言（选填）", max: 32 }, { key: "script", label: "书写方式（选填）", max: 32 }] as const).map(field => <label key={field.key} className={field.key === "text" ? s.profileWide : undefined}>{field.label}<input maxLength={field.max} disabled={busy || !!saved} value={value[field.key]} onChange={e => setValue({ ...value, [field.key]: e.target.value })} /></label>)}</div>
    <section className={s.aliasPreview} aria-label="异名展示预览"><small>知识页中的展示</small><h2>{label}</h2><EntityAliases aliases={value.text.trim() ? [value] : []} /></section></div>
    <button className={s.primary} disabled={busy || !value.text.trim() || !!saved} onClick={() => void submit()}>提交异名并审核</button>
    {error && <p className={s.error} role="alert">{error}</p>}{saved && <p role="status">审核稿已保存。<Link href={`/admin/knowledge/review?changeset=${saved}`}>打开审核工作台</Link></p>}
  </div></details>;
}
