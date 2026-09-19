"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionButton } from "@/components/action-feedback";
import { PageHeader } from "@/components/admin-ui";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { ApiRequestError, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useApiResource } from "@/lib/api/use-api-resource";
import {
  asRecord, canConfirmPersonMerge, isPersonId, mergePerson, personApi, personPage, rollbackPerson,
  rollbackState, textValue, type MergeHistory, type MergeInput, type PersonDuplicates, type PersonMerge,
  type PersonPreview, type PersonSearch, type PersonSummary, type PersonBusinessImpact,
} from "@/lib/api/person-resolution";
import styles from "./person-resolution.module.css";

const statusLabels: Record<string, string> = { verified: "已核验", draft: "草稿", needs_review: "待核验", merged: "已合并", archived: "已归档", rejected: "未采用" };
const fieldLabels: Record<string, string> = {
  id: "记录编号", person_id: "人物编号", scholar_id: "学者档案编号", preferred_name: "规范名称", original_name: "原文名称",
  birth_year: "出生年", death_year: "逝世年", authority_status: "核验状态", biography: "人物介绍", aliases: "原始别名",
  external_ids: "外部标识符", short_description: "档案简介", slug: "页面名称", name: "名称", title: "标题", term: "词条",
  role: "署名职责", approved: "已确认", is_verified: "已核验", language: "语言", variant_type: "名称类型", source_kind: "来源类型",
  source: "原始来源", source_ref: "来源依据", editorial_status: "编辑状态", review_status: "审核状态", status: "状态",
  work_id: "作品编号", edition_id: "版本编号", node_id: "知识节点编号", topic_id: "主题编号", discipline_id: "学科编号",
  subdiscipline_id: "子学科编号", theory_school_id: "旧理论编号", proposition: "观点", description: "说明", start_year: "开始年",
  end_year: "结束年", event_type: "事件类型", timeline: "学术经历", affiliations: "机构", key_concerns: "主要关切",
  revision: "修订号", catalog_revision_id: "书目修订编号", public_slug: "公开页面名称", publication_mode: "发布方式",
  displayable: "允许展示", public_active: "公开检索有效", admin_resolvable: "后台可解析", trust_level: "信任级别", term_type: "词条类型",
};

function useActiveView() {
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  return active;
}

function Failure({ message, retry, label = "重新读取" }: { message: string; retry: () => void; label?: string }) {
  return <div className={styles.notice} role="alert"><p>{message}</p><ActionButton className="button secondary" onClick={retry}>{label}</ActionButton></div>;
}

function PersonLabel({ person }: { person: PersonSummary }) {
  return <><strong>{person.preferred_name}</strong><span>{[person.original_name, person.birth_year === null ? "出生年未填写" : `${person.birth_year}年出生`, statusLabels[person.authority_status] || person.authority_status].filter(Boolean).join(" · ")}</span></>;
}

function PersonPicker({ sourceId = "", credential }: { sourceId?: string; credential: string }) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error, loading, retry } = useApiResource<PersonSearch>(personApi.search(submitted), credential);
  const label = sourceId ? "查找其他保留人物" : "查找馆内人物";
  function search(event: FormEvent) { event.preventDefault(); if (submitted === query.trim()) retry(); else setSubmitted(query.trim()); }
  return <section className={`admin-panel ${styles.panel}`} aria-label={label}>
    <h2>{label}</h2>
    <form className={styles.search} onSubmit={search}><label>{label}<input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={200} placeholder="输入名称或已核验译名" /></label><button className="button secondary" type="submit">查找</button></form>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在读取人物…</p> : data ? <>
      <ul className={styles.people}>{data.results.filter((row) => row.id !== sourceId).map((row) => <li key={row.id}><Link prefetch={false} href={sourceId ? personPage(sourceId, row.id) : personPage(row.id)}><PersonLabel person={row} /><b>{sourceId ? "设为保留人物" : "检查重复记录"}</b></Link></li>)}</ul>
      {!data.results.some((row) => row.id !== sourceId) ? <p>未找到符合条件的其他人物，请换一个名称查找。</p> : null}
      {data.has_more ? <p>这里只显示前20项，请补充名称缩小范围。</p> : null}
    </> : null}
  </section>;
}

function Details({ value }: { value: unknown }) {
  return <dl className={styles.fields}>{Object.entries(asRecord(value)).map(([field, item]) => <div key={field}><dt>{fieldLabels[field] || field}</dt><dd>{textValue(item)}</dd></div>)}</dl>;
}

function History({ sourceId, credential }: { sourceId: string; credential: string }) {
  const { data, error, loading, retry } = useApiResource<MergeHistory[]>(personApi.history(sourceId), credential);
  return <section className={`admin-panel ${styles.panel}`} aria-label="最近合并记录"><div className={styles.heading}><h2>最近合并记录</h2><ActionButton className="button secondary" onClick={retry}>刷新操作记录</ActionButton></div>
    <p>网络中断或重新打开页面后，可在这里核对已保存的操作。最多显示最近20次。</p>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在读取操作记录…</p> : data?.length ? <ul className={styles.rows}>{data.map((row) => <li key={row.id}><Link prefetch={false} href={personPage(sourceId, "", row.id)}>{row.rolled_back_at ? "已撤回的合并" : "已执行的合并"} · {new Date(row.created_at).toLocaleString("zh-CN")}</Link><small>{row.id}</small></li>)}</ul> : <p>暂无已保存的合并记录。仅此列表为空不能证明仍在传输的请求未执行。</p>}
  </section>;
}

function SourceWorkspace({ sourceId, targetId, allowed, credential }: { sourceId: string; targetId: string; allowed: boolean; credential: string }) {
  const { data, error, loading, retry } = useApiResource<PersonDuplicates>(personApi.duplicates(sourceId), credential);
  return <>
    <Link prefetch={false} href={personPage()}>重新选择来源人物</Link>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在检查疑似重复…</p> : data ? <>
      <section className={`admin-panel ${styles.panel}`} aria-label="来源人物"><h2>来源人物</h2><div className={styles.identity}><PersonLabel person={data.source} /></div><p>确认合并后，来源记录仍保留，其无冲突引用归入保留人物。</p></section>
      {!allowed ? <p className={styles.notice}>当前账户可以查重。影响预览、合并与撤回仅向书库所有者开放。</p> : null}
      <section className={`admin-panel ${styles.panel}`} aria-label="疑似重复人物"><h2>疑似重复人物</h2><p>名称或标识符相同只是核对线索，不能直接认定为同一个人。</p>
        {data.results.length ? <ul className={styles.people}>{data.results.map((row) => <li key={row.person.id}><div className={styles.identity}><PersonLabel person={row.person} />
          {row.matches.map((match, i) => <span key={i}>{asRecord(match).kind === "name" ? "名称匹配" : "标识符匹配"} {textValue(asRecord(match).values)}</span>)}
          {row.identity_conflicts.length ? <span>有 {row.identity_conflicts.length} 项身份差异，需要核对</span> : null}
          {allowed ? <Link prefetch={false} className="button secondary" href={personPage(sourceId, row.person.id)}>保留此人物并查看影响</Link> : null}</div></li>)}</ul> : <p>未找到名称或标识符匹配的其他人物。这不代表馆内没有重复记录。</p>}
        {data.has_more ? <p>候选超过20项，请用下方查找核对具体人物。</p> : null}
      </section>
      {allowed ? <><details open={!targetId}><summary>{targetId ? "更换保留人物" : "没有合适候选？查找其他人物"}</summary><PersonPicker sourceId={sourceId} credential={credential} /></details>{targetId ? <PreviewLoader key={`${sourceId}:${targetId}`} sourceId={sourceId} targetId={targetId} credential={credential} /> : null}</> : null}
    </> : null}
    {allowed ? <History sourceId={sourceId} credential={credential} /> : null}
  </>;
}

function PreviewFacts({ preview }: { preview: PersonPreview }) {
  const source = asRecord(preview.source), target = asRecord(preview.target);
  return <>
    <div className={styles.comparison}>{[["来源人物", source, preview.source_profile], ["保留人物", target, preview.target_profile]].map(([label, person, profile]) => <section key={String(label)} aria-label={`核对${label}`}><h3>{String(label)}</h3><strong>{textValue(asRecord(person).preferred_name)}</strong><p>{textValue(asRecord(person).original_name)} · {textValue(asRecord(person).birth_year)}—{textValue(asRecord(person).death_year)}</p><p>{textValue(asRecord(person).biography)}</p><details><summary>名称、身份与技术明细</summary><Details value={Object.fromEntries(["id", "original_name", "birth_year", "death_year", "authority_status", "aliases", "external_ids", "biography"].map((field) => [field, asRecord(person)[field]]))} /></details>{profile ? <details><summary>查看学者档案</summary><Details value={profile} /></details> : <p>没有独立学者档案</p>}</section>)}</div>
    <p>涉及 {preview.affected_works.length} 部作品、{preview.affected_edition_count} 个版本和 {preview.publication_revision_count} 条历史公开修订。历史修订不会被覆盖。</p>
    {preview.business_impact ? <BusinessImpact impact={preview.business_impact} /> : null}
    <details><summary>查看作品与版本</summary><ul className={styles.rows}>{preview.affected_works.map((value, i) => <li key={i}><strong>{textValue(asRecord(value).title)}</strong><small>{textValue(asRecord(value).id)}</small></li>)}</ul>{preview.affected_editions.map((value, i) => <details key={i}><summary>版本 {textValue(asRecord(value).id)}</summary><Details value={value} /></details>)}</details>
    <details><summary>查看历史公开修订</summary>{preview.publication_revisions.map((value, i) => <Details key={i} value={value} />)}</details>
    <section aria-label="关联影响"><h3>关联影响</h3><p>下方为双方现有引用。学者档案的下游引用保持原编号，只随同一份档案保留。</p>
      {preview.references.map((value, i) => { const row = asRecord(value); return <details key={i} className={styles.reference}><summary>{textValue(row.label)} · 来源 {textValue(row.source_count)} 项 · 保留人物 {textValue(row.target_count)} 项{Array.isArray(row.collisions) && row.collisions.length ? " · 存在重复关系" : ""}{row.truncated ? " · 未完整显示" : ""}</summary>
        <div className={styles.comparison}>{["source_rows", "target_rows"].map((key) => <section key={key}><h4>{key === "source_rows" ? "来源人物" : "保留人物"}</h4>{Array.isArray(row[key]) && row[key].length ? row[key].map((item: unknown, index: number) => <Details key={index} value={item} />) : <p>无相关记录</p>}</section>)}</div>
      </details>; })}
    </section>
    <details><summary>活动检索词条 · 来源 {preview.lexicon_entries.source} 项 · 保留人物 {preview.lexicon_entries.target} 项</summary>
      {!preview.lexicon_entries.available ? <p role="alert">{preview.lexicon_entries.error || "检索词典状态待核实"}</p> : <div className={styles.comparison}>{[preview.lexicon_entries.source_rows, preview.lexicon_entries.target_rows].map((rows, i) => <section key={i}><h4>{i === 0 ? "来源人物" : "保留人物"}</h4>{rows.length ? rows.map((row) => <Details key={row.id} value={row} />) : <p>当前没有活动词条</p>}</section>)}</div>}
    </details>
    {preview.identity_conflicts.length ? <section><h3>身份差异</h3>{preview.identity_conflicts.map((value, i) => <Details key={i} value={value} />)}</section> : null}
    <ul>{(preview.execution_guidance || []).map((line) => <li key={line}>{line}</li>)}</ul>
  </>;
}

function BusinessImpact({ impact }: { impact: PersonBusinessImpact }) {
  return <section aria-label="作品职责与公开位置"><h3>作品、职责与公开位置</h3><p>只归并人物身份；下列作者、译者及编者职责保持不变。相似名称不等于同一人物。</p><ul className={styles.rows}>{impact.editions.map((row) => <li key={row.edition_id}><strong>{row.title}</strong><span>{row.edition_label}</span><p>{row.roles.map((role) => `${role.name}：${role.role_label}${role.approved ? "（已确认）" : "（待确认）"}`).join("；") || "此版本通过其他规范关系受到影响"}</p><p>{row.publication.detail}</p><div className={styles.actions}><Link prefetch={false} href={row.editor_url}>核对当前版本与署名</Link><Link prefetch={false} href={row.publication_url}>查看发布更新</Link>{row.publication.public_url ? <Link prefetch={false} href={row.publication.public_url} target="_blank">核验公开位置</Link> : null}</div></li>)}</ul>{!impact.editions.length ? <p>没有需要更新的作品版本；人物和学者关系仍按影响预览处理。</p> : null}
    {impact.events.length ? <details open><summary>公开更新的实际处理结果</summary>{impact.events.map((event) => <article key={event.id}><strong>{event.title} · {event.status_label}</strong><p>{event.deliveries.map((row) => `${row.label}：${row.status}（来源修订${row.source_revision}）`).join("；")}</p>{event.error_code ? <p>异常 {event.error_code}，请从原发布记录检查并恢复。</p> : null}<Link prefetch={false} href={event.inspect_url}>查看关联处理</Link><small> 事件 {event.id}</small></article>)}</details> : null}</section>;
}

function PreviewLoader({ sourceId, targetId, credential }: { sourceId: string; targetId: string; credential: string }) {
  const resource = useApiResource<PersonPreview>(personApi.preview(sourceId, targetId), credential);
  return <section className={`admin-panel ${styles.panel}`} aria-label="合并影响预览"><h2>合并影响预览</h2>
    {resource.error ? <Failure message={resource.error} retry={resource.retry} label="重新预览" /> : resource.loading ? <p role="status">正在核对双方资料与关联…</p> : resource.data ? <MergeReview key={resource.data.fingerprint} preview={resource.data} sourceId={sourceId} targetId={targetId} credential={credential} refresh={resource.retry} /> : null}
  </section>;
}

function MergeReview({ preview, sourceId, targetId, credential, refresh }: { preview: PersonPreview; sourceId: string; targetId: string; credential: string; refresh: () => void }) {
  const router = useRouter();
  const active = useActiveView();
  const sending = useRef(false);
  const attempt = useRef<MergeInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [failure, setFailure] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const eligible = canConfirmPersonMerge(preview, sourceId, targetId);
  async function submit() {
    if (sending.current || !eligible || (!confirm && !attempt.current)) return;
    const input = attempt.current ?? { target_person: targetId, fingerprint: preview.fingerprint, confirmed: true, idempotency_key: createRequestKey() };
    attempt.current = input;
    sending.current = true;
    setBusy(true); setFailure("");
    try {
      const result = await mergePerson(sourceId, input, credential);
      if (!active.current) return;
      router.replace(personPage(sourceId, "", result.id));
    } catch (reason) {
      if (!active.current) return;
      // An HTTP error after a committed write or a lost response is not proof
      // of failure. Reuse the exact body/key until the outcome is known.
      const knownRejection = reason instanceof ApiRequestError && [400, 401, 403, 404, 409].includes(reason.status);
      setUncertain(!knownRejection);
      setFailure(reason instanceof Error ? reason.message : "未收到完整操作结果。");
      setConfirm(false);
    } finally { sending.current = false; if (active.current) setBusy(false); }
  }
  return <>
    <PreviewFacts preview={preview} />
    {preview.review_issues.length ? <div className={styles.notice} role="alert"><h3>需要先处理</h3><ul>{preview.review_issues.map((issue, i) => <li key={i}>{textValue(asRecord(issue).detail)}</li>)}</ul></div> : null}
    {!preview.complete_reference_listing ? <p role="alert">当前影响范围不完整，不能执行合并。</p> : null}
    {failure ? <div className={styles.notice} role="alert"><p>{failure}</p>{uncertain ? <><p>操作结果尚未确认。可刷新下方操作记录，或用原请求重试。不要把网络中断当作合并失败。</p><ActionButton className="button" state={busy ? "pending" : "idle"} onClick={() => void submit()}>重试同一次合并</ActionButton></> : <ActionButton className="button secondary" onClick={refresh}>重新预览并核对</ActionButton>}</div> : null}
    <div className={styles.actions}><ActionButton className="button secondary" disabled={busy || uncertain} onClick={refresh}>重新读取影响</ActionButton><ActionButton className="button" disabled={!eligible || busy || Boolean(failure)} onClick={() => setConfirm(true)}>核对完成，准备合并</ActionButton></div>
    <p>保留人物的基础资料不自动改写。原文件、来源记录、历史公开内容和读者私人笔记保留。合并后检索及公开书目仍需等待处理完成。</p>
    <ConfirmDialog open={confirm} title="确认合并人物" description={`将「${textValue(asRecord(preview.source).preferred_name)}」的无冲突引用归入「${textValue(asRecord(preview.target).preferred_name)}」。请确认这是同一人物，且保留方向正确。`} confirmLabel={busy ? "正在合并…" : "确认是同一人物并合并"} pending={busy} details={["目标人物基础资料保持原值，来源资料不删除。", "若后续有人修改相关资料，撤回可能被阻止。"]} onCancel={() => setConfirm(false)} onConfirm={submit} />
  </>;
}

function RecordWorkspace({ recordId, credential }: { recordId: string; credential: string }) {
  const resource = useApiResource<PersonMerge>(personApi.record(recordId), credential);
  return <section className={`admin-panel ${styles.panel}`} aria-label="人物合并操作记录"><h2>人物合并操作记录</h2>
    {resource.error ? <Failure message={resource.error} retry={resource.retry} label="重新读取操作" /> : resource.loading ? <p role="status">正在核对操作与当前撤回条件…</p> : resource.data ? <RecordReview key={`${resource.data.id}:${resource.data.status}:${rollbackState(resource.data).fingerprint}`} record={resource.data} credential={credential} refresh={resource.retry} /> : null}
  </section>;
}

function RecordReview({ record, credential, refresh }: { record: PersonMerge; credential: string; refresh: () => void }) {
  const active = useActiveView();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false), [confirm, setConfirm] = useState(false), [failure, setFailure] = useState("");
  const reversal = rollbackState(record);
  async function rollback() {
    if (sending.current || !confirm || !reversal.canRollback) return;
    sending.current = true; setBusy(true); setFailure("");
    try { await rollbackPerson(record.id, { confirmed: true, fingerprint: reversal.fingerprint }, credential); if (active.current) refresh(); }
    catch (reason) { if (active.current) { setFailure(reason instanceof Error ? reason.message : "未收到撤回结果。"); setConfirm(false); } }
    finally { sending.current = false; if (active.current) setBusy(false); }
  }
  return <>
    <h3 aria-live="polite">{record.status === "rolled_back" ? "本次合并已撤回" : record.status === "applied" ? "人物合并已记录" : "操作状态待核实"}</h3>
    <p>{record.status === "rolled_back" ? "本次移动的引用已恢复。" : "来源记录保留，合并关系已保存。"}公开书目与检索更新需等待处理完成，这里不表示已经公开生效。</p>
    <p>{record.source_name || "来源人物"} → {record.target_name || "保留人物"}</p>
    {record.business_impact ? <BusinessImpact impact={record.business_impact} /> : null}
    <dl className={styles.fields}><div><dt>操作编号</dt><dd>{record.id}</dd></div><div><dt>来源人物</dt><dd><Link prefetch={false} href={personPage(record.source_person_id)}>{record.source_person_id}</Link></dd></div><div><dt>保留人物</dt><dd><Link prefetch={false} href={personPage(record.target_person_id)}>{record.target_person_id}</Link></dd></div><div><dt>执行时间</dt><dd>{new Date(record.created_at).toLocaleString("zh-CN")}</dd></div>{record.rolled_back_at ? <div><dt>撤回时间</dt><dd>{new Date(record.rolled_back_at).toLocaleString("zh-CN")}</dd></div> : null}</dl>
    <details><summary>引用移动及处理记录</summary><Details value={record.moved_counts} /><p>受影响版本 {record.affected_edition_ids.length} 个，合并处理记录 {record.event_ids.length} 条，撤回处理记录 {record.rollback_event_ids.length} 条。</p><Details value={{ edition_ids: record.affected_edition_ids, merge_event_ids: record.event_ids, rollback_event_ids: record.rollback_event_ids }} /></details>
    {record.status !== "rolled_back" ? <><h3>撤回本次合并</h3><p>只恢复本次移动的引用。如果人物或相关编辑内容已有后续修改，系统会拒绝覆盖。</p>{reversal.blockers.length ? <ul role="alert">{reversal.blockers.map((line) => <li key={line}>{line}</li>)}</ul> : null}
      {!reversal.canRollback && !reversal.blockers.length ? <p role="alert">当前撤回资格待核实，请重新读取操作。</p> : null}
      <ActionButton className="button secondary" disabled={busy || !reversal.canRollback || Boolean(failure)} onClick={() => setConfirm(true)}>准备撤回本次合并</ActionButton></> : null}
    {failure ? <div role="alert" className={styles.notice}><p>{failure}</p><p>请重新读取操作，核对撤回是否已经完成及当前条件，不要假定请求失败。</p></div> : null}
    <div className={styles.actions}><ActionButton className="button secondary" disabled={busy} onClick={refresh}>重新读取操作及撤回条件</ActionButton><Link prefetch={false} href={personPage(record.source_person_id)}>返回来源人物</Link></div>
    <ConfirmDialog open={confirm} title="确认撤回本次合并" description="恢复本次迁移的引用与来源人物状态。既有文件和读者私人笔记不受影响，公开内容仍需等待恢复处理。" confirmLabel={busy ? "正在撤回…" : "确认撤回本次合并"} pending={busy} onCancel={() => setConfirm(false)} onConfirm={rollback} />
  </>;
}

export function PersonResolutionWorkspace() {
  const user = useAdminSession();
  const params = useSearchParams();
  const sourceId = params.get("source") || "", targetId = params.get("target") || "", recordId = params.get("record") || "";
  const allowed = hasAdminCapability(user, "can_merge_authority");
  const credential = user ? getServerSessionCredential() : null;
  const valid = [sourceId, targetId, recordId].every((value) => !value || isPersonId(value)) && (!targetId || Boolean(sourceId));
  return <div className={`admin-page ${styles.workspace}`}><PageHeader title="人物查重与整理" description="核对重复作者及学者资料，确认影响范围后再合并。" actions={<Link prefetch={false} href="/admin/knowledge" className="button secondary">返回馆内知识</Link>} />
    {!credential ? <p role="status">等待验证管理会话…</p> : !valid ? <p role="alert">人物或操作编号无效，请从馆内人物列表重新选择。<Link prefetch={false} href={personPage()}>返回列表</Link></p> : <div key={`${user?.id}:${allowed}`} className={styles.content}>{recordId ? allowed ? <RecordWorkspace key={recordId} recordId={recordId} credential={credential} /> : <p role="alert">合并记录与撤回仅向书库所有者开放。</p> : sourceId ? <SourceWorkspace key={sourceId} sourceId={sourceId} targetId={targetId} allowed={allowed} credential={credential} /> : <PersonPicker credential={credential} />}</div>}
  </div>;
}
