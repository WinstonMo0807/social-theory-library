"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { EntityPicker } from "../forms/workflow-fields";
import type { TimelineRelation } from "@/components/theory-system-admin";
import type { components } from "@/lib/api/generated/schema";
import styles from "./timeline-editor.module.css";

type EditionPeople = components["schemas"]["TimelineEditionParticipants"];
const roles = [["", "未标注角色"], ["subject", "事件主体"], ["author", "作者"], ["translator", "译者"], ["editor", "编者"], ["participant", "参与者"], ["other", "其他角色"]] as const;

function EditionResponsibility({ owner, editionId }: { owner: string; editionId: string }) {
  const [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<EditionPeople>(path,
    { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const result = usePersistentWorkspace<EditionPeople>(`/catalog/admin/theory-timeline/editions/${editionId}/participants/?page=${page}`, owner, undefined, load);
  return <section className={styles.editionPeople} aria-label="所选版本的责任者"><h3>所选版本的责任者</h3>
    {result.error ? <p role="alert">{result.error}<button type="button" onClick={result.reload}>重新读取</button></p> : !result.data ? <p role="status">正在读取版本资料…</p> : result.data.edition_id !== editionId ? <p role="alert">版本身份不一致，请重新选择。</p> : <>
      <p>{result.data.work_title}{result.data.version_label ? ` · ${result.data.version_label}` : ""}</p>
      <ul className={styles.participantChips}>{result.data.results.map(person => <li key={person.key}><span>{person.role_label}</span><strong>{person.name}</strong></li>)}{result.data.publisher ? <li><span>出版方</span><strong>{result.data.publisher}</strong></li> : null}</ul>
      {!result.data.count && !result.data.publisher ? <p>尚无已确认的整版责任资料。</p> : null}
      {result.data.pending_count ? <p>还有 {result.data.pending_count} 条责任记录待核对，未列入上述已确认角色。</p> : null}
      {result.data.total_pages > 1 ? <nav className={styles.controls} aria-label="版本责任者分页"><button type="button" disabled={result.data.page <= 1} onClick={() => setPage(result.data!.page - 1)}>上一页</button><span>{result.data.page} / {result.data.total_pages}</span><button type="button" disabled={result.data.page >= result.data.total_pages} onClick={() => setPage(result.data!.page + 1)}>下一页</button></nav> : null}
      <Link href={`/admin/library/works/${result.data.work_id}?edition=${editionId}`} target="_blank" rel="noopener noreferrer">核对原版本书目</Link>
      <p>此处读取原书目中的已确认整版责任，不会将章节作者标成整本书作者。公开时间线使用正式发布的版本资料。</p>
    </>}
  </section>;
}

export function TimelineParticipants({ owner, editionId, value, onChange }: {
  owner: string; editionId: string; value: TimelineRelation[]; onChange: (value: TimelineRelation[]) => void;
}) {
  const selected = [...new Map(value.filter(row => row.scholar).map(row => [row.scholar!, { id: row.scholar, name: row.scholar_name || `已关联学者 ${row.scholar!.slice(0, 8)}` }])).values()];
  return <section className={styles.participants}>
    {editionId ? <EditionResponsibility key={`${owner}:${editionId}`} owner={owner} editionId={editionId} /> : null}
    <EntityPicker owner={owner} label="补充事件参与学者，可多选" endpoint="/catalog/admin/scholars/" values={selected}
      onChange={choices => {
        const ids = new Set(choices.flatMap(row => row.id ? [row.id] : []));
        if (value.some(row => row.scholar && !ids.has(row.scholar) && row.description) && !window.confirm("移除所选人物在此事件中的关系及说明？学者档案不会删除。")) return;
        const retained = value.filter(row => row.scholar && ids.has(row.scholar));
        const added: TimelineRelation[] = choices.flatMap(row => row.id && !retained.some(old => old.scholar === row.id) ? [{ scholar: row.id, scholar_name: row.name,
          participant_role: "participant", relation_type: "subject", node: null, discipline: null, work: null, evidence: null, description: "", sort_order: retained.length }] : []);
        onChange([...retained, ...added]);
      }} />
    <p>事件主体仍由上方主学者字段指定。这里补充有出处支持的参与关系，不会修改原版本的作者、译者或编者。</p>
    {value.map((row, index) => <article className={styles.participantRow} key={row.id || `${row.scholar}:${row.relation_type}:${index}`}>
      <header><strong>{row.scholar_name || `已关联学者 ${row.scholar?.slice(0, 8)}`}</strong><button type="button" onClick={() => {
        if (!row.description || window.confirm("移除此事件中的人物关系及说明？学者档案不会删除。")) onChange(value.filter((_, position) => position !== index));
      }}>移除关联</button></header>
      <label>事件中的角色<select value={row.participant_role || ""} onChange={event => onChange(value.map((item, position) => position === index ? { ...item, participant_role: event.target.value } : item))}>
        {roles.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label><label>关系说明<input value={row.description} maxLength={400} onChange={event => onChange(value.map((item, position) => position === index ? { ...item, description: event.target.value } : item))} /></label>
    </article>)}
  </section>;
}
