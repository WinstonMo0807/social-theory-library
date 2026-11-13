"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "@/lib/request-key";
import { confirmAction } from "@/lib/ui-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AssertionFields, assertionPredicateLabels, type AssertionFieldsValue } from "./assertion-fields";
import { ArrowLeft, Check, PanelRightOpen } from "lucide-react";
import { KnowledgePageContent, KnowledgeAssertionContent, EntityAliases, type KnowledgeAssertion, type KnowledgeBlock, type KnowledgePageData } from "@/components/public/knowledge-page-content";
import { EvidencePanel, KnowledgeNavigation } from "./knowledge-workbench";
import { IntelligencePageEditor } from "./intelligence-page-editor";
import { EntityProfileFields } from "./entity-profile-editor";
import { EntityProfileContent } from "../public/entity-profile-content";
import { type IdentityProfile } from "@/lib/knowledge-profiles";
import styles from "./intelligence-workspace.module.css";

type Evidence = { stance: string; anchor_id?: string; segments?: { page_number: number; start: number; end: number; exact: string }[] };
type EvidenceLocator = { asset_id: string; anchor_id: string; document_revision_id: string; reader_url: string; segments: NonNullable<Evidence["segments"]> };
type Candidate = { id: string; label: string; kind: string; definition: string; context: string; profile?: IdentityProfile; aliases: { text: string }[]; identifiers: { namespace: string; value: string }[]; related_works?: { work_id: string; edition_id?: string; title: string; source_type: string; role_label: string; text?: string; citation?: string; assertion_id?: string }[] };
type Payload = AssertionFieldsValue & { language?: string; script?: string; entity_id?: string | { change_item: string }; profile?: IdentityProfile; title?: string; scope?: string; label?: string; kind?: string; definition?: string; context?: string; existing_id?: string; candidates?: Candidate[]; comparisons?: { candidate_id: string; judgment: string; reason: string }[];
  source_citation?: string; text?: string; predicate?: string; expression?: string; unresolved_names?: string[]; participants?: { role: string; work_id?: string; edition_id?: string; entity_id?: string | { change_item: string } }[];
  evidence?: Evidence[]; reason?: string; operation?: string; human_protected?: boolean; human_edited?: boolean; block_id?: string; block?: Omit<Partial<KnowledgeBlock>, "references"> & { references?: { type: string; id: string | { change_item: string } }[] }; page_id?: string };
type Item = { identity?: Candidate | null; evidence_context?: EvidenceLocator[]; current_status?: string; id: string; kind: string; payload: Payload; dependencies: string[]; decision: string; decision_note: string;
  application: { id?: string; page_id?: string }; conflict: { reason?: string }; current?: { block: { text?: string } | null; hash: string | null } };
type Changes = { origin: string; work_id: string; asset_id: string; pages: number; title: string; document_revision_id: string; edition_id: string; id: string; version: number; status: string; items: Item[] };
type ReviewContext = { title: string; edition_id: string; document_revision_id: string; work_id: string; asset_id: string; pages: number; changeset: Changes };
type Index = { drafts: { id: string; title: string; origin: string }[] };
const kinds: Record<string, string> = { entity: "实体身份", alias: "异名", assertion: "学术陈述", wiki_patch: "知识页修改" };
const decisions: Record<string, string> = { pending: "待审核", accepted: "已确认", rejected: "已拒绝", deferred: "暂缓" };
const call = <T,>(path: string, body?: unknown, signal?: AbortSignal) => apiRequest<T>(path, { cache: "no-store", signal, ...(body === undefined ? {} : { method: "POST", body: JSON.stringify(body) }) }, getServerSessionCredential());

export function KnowledgeReviewWorkspace() {
  const query = useSearchParams();
  const [index, setIndex] = useState<Index | null>(null);
  const [run, setRun] = useState<ReviewContext | null>(null);
  const [selectedChangeset, setSelectedChangeset] = useState(query.get("changeset") || "");
  const requestedChangeset = query.get("changeset") || "";
  useEffect(() => { setSelectedChangeset(requestedChangeset); }, [requestedChangeset]);
  const workFilter = query.get("work_id") || "";
  const [category, setCategory] = useState("all"), [selected, setSelected] = useState(""), [draft, setDraft] = useState<Payload | null>(null);
  const [note, setNote] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState(0), [checked, setChecked] = useState<string[]>([]);
  const [wikiEvidence, setWikiEvidence] = useState<EvidenceLocator[]>([]);
  const [evidenceOpen, setEvidenceOpen] = useState(false), [preview, setPreview] = useState<{ id?: string; title: string; scope?: string; references?: KnowledgePageData["references"]; identity?: KnowledgePageData["identity"]; blocks: { id: string; text?: string }[]; assertions?: KnowledgeAssertion[]; anchors?: KnowledgePageData["anchors"]; publication_scope?: KnowledgePageData["publication_scope"]; revision_id: string | null; status?: string } | null>(null);
  const applyRequest = useRef<{ signature: string; request_id: string } | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort(); }, []);
  const refresh = useCallback(async () => {
    const result = await call<Index>("/knowledge/reviews/", undefined, lifetime.current?.signal); setIndex(result);
    if (selectedChangeset) {
      const changeset = await call<Changes>(`/intelligence/changesets/${selectedChangeset}/`, undefined, lifetime.current?.signal);
      setRun({ title: changeset.title, edition_id: changeset.edition_id, document_revision_id: changeset.document_revision_id,
        work_id: changeset.work_id, asset_id: changeset.asset_id, pages: changeset.pages, changeset });
    } else setRun(null);
  }, [selectedChangeset]);
  useEffect(() => { setError(""); void refresh().catch(e => { if (!lifetime.current?.signal.aborted) setError(e.message); }); }, [refresh]);
  const changes = run?.changeset, items = changes?.items || [];
  const item = items.find(i => i.id === selected);
  const dirty = !!draft || !!item && note !== item.decision_note;
  useUnsavedForm(dirty, false);
  const source = run?.asset_id ? { asset_id: run.asset_id, revision_id: run.document_revision_id, pages: run.pages || 0, title: run.title, work_id: run.work_id || "" } : undefined;
  const value = draft || item?.payload;
  const matchedIdentity = value?.candidates?.find(c => c.id === value.existing_id);
  const evidence = value?.evidence?.flatMap(e => e.segments || []) || [];
  const anchoredEvidence = item?.evidence_context || [];
  const evidenceSources = evidence.length ? [{ anchor_id: "", asset_id: source?.asset_id || "", document_revision_id: run?.document_revision_id || "",
    reader_url: source ? `/reader/${source.asset_id}?revision=${run?.document_revision_id}&preview=1` : "", segments: evidence }] : anchoredEvidence.length ? anchoredEvidence : wikiEvidence;
  useEffect(() => {
    setWikiEvidence([]);
    if (item?.kind !== "wiki_patch") return;
    const controller = new AbortController();
    const references = value?.block?.references || [];
    void Promise.all(references.map(async ref => {
      if (typeof ref.id !== "string") {
        const dependency = items.find(v => v.id === (ref.id as { change_item: string }).change_item);
        const segments = dependency?.payload.evidence?.flatMap(v => v.segments || []) || [];
        return segments.length && run && source ? [{ anchor_id: "", asset_id: source.asset_id, document_revision_id: run.document_revision_id,
          reader_url: `/reader/${source.asset_id}?page=${segments[0].page_number}${run.document_revision_id ? `&revision=${run.document_revision_id}` : ""}&preview=1`, segments }] : [];
      }
      if (ref.type === "anchor") return [await call<EvidenceLocator>(`/knowledge/anchors/${ref.id}/?preview=1`, undefined, controller.signal)];
      if (ref.type === "assertion") {
        const assertion = await call<{ evidence: { locator: EvidenceLocator }[] }>(`/knowledge/assertions/${ref.id}/?preview=1`, undefined, controller.signal);
        return assertion.evidence.map(e => e.locator).filter(Boolean);
      }
      return [];
    })).then(rows => { if (!controller.signal.aborted) setWikiEvidence(rows.flat()); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [item?.id, value?.block?.references, source?.asset_id]);
  function choose(id: string) { setSelectedEvidence(0); setSelected(id); setDraft(null); setNote(items.find(i => i.id === id)?.decision_note || ""); setPreview(null); }
  async function action(fn: () => Promise<void>) {
    if (busy) return; setBusy(true); setError(""); setNotice("");
    try { await fn(); } catch (e) { if (!lifetime.current?.signal.aborted) setError(e instanceof Error ? e.message : "请求失败，请重试。"); } finally { setBusy(false); }
  }
  async function decide(decision: string) {
    if (!item || !changes) return;
    await action(async () => { const next = await call<Changes>(`/intelligence/changesets/${changes.id}/review/`, { expected_version: changes.version, decisions: [{ id: item.id, decision, note, ...(draft ? { payload: draft } : {}) }] });
      setRun(old => old ? { ...old, changeset: next } : old); setDraft(null); setNotice("审核决定已保存。"); });
  }
  async function decideSelected(decision: string) {
    if (!changes || !checked.length) return;
    await action(async () => {
      const next = await call<Changes>(`/intelligence/changesets/${changes.id}/review/`, { expected_version: changes.version, decisions: checked.filter(id => items.some(i => i.id === id && !i.application.id)).map(id => ({ id, decision, note: "" })) });
      setRun(old => old ? { ...old, changeset: next } : old); setChecked([]); setNotice("所选审核决定已保存。");
    });
  }
  async function apply() {
    if (!changes) return;
    const selected_ids = items.filter(i => i.decision === "accepted" && !i.application.id).map(i => i.id);
    const signature = JSON.stringify([changes.id, changes.version, selected_ids]);
    if (applyRequest.current?.signature !== signature) applyRequest.current = { signature, request_id: createRequestKey() };
    await action(async () => { const result = await call<{ saved: Record<string, unknown>; blocked: Record<string, unknown> }>(`/intelligence/changesets/${changes.id}/apply/`, { expected_version: changes.version, selected_ids, request_id: applyRequest.current!.request_id });
      await refresh(); setNotice(`已保存 ${Object.keys(result.saved).length} 项草稿，${Object.keys(result.blocked).length} 项需要处理依赖或冲突。`); });
  }
  async function previewPage(pageId: string) {
    await action(async () => { setPreview(await call(`/knowledge/pages/${pageId}/?preview=1`)); });
  }
  const available = items.filter(i => category === "all" || i.kind === category);
  return <section className={styles.workspace}>
    <header className={styles.header}><div className={styles.brand}><img src="/brand/stl-symbol-20261027.svg" alt="" width={40} height={48} /><div><h1>审核与发布</h1><p>知识编纂</p></div></div>
      <div className={styles.actions}><Link href="/admin/knowledge">返回知识编纂</Link><button onClick={() => void action(refresh)} disabled={busy || dirty}>刷新状态</button>
        {run && <button className={styles.primary} disabled={busy || dirty || !items.some(i => i.decision === "accepted" && !i.application.id)} onClick={() => void apply()}>保存已审核草稿</button>}</div></header>
    <KnowledgeNavigation active="review" workId={source?.work_id || workFilter} revisionId={run?.document_revision_id || ""} />
    {error && <div role="alert" className={styles.error}>{error}</div>}{notice && <p role="status" className={styles.notice}>{notice}</p>}
    {!index ? !error && <LoadingState>正在读取审核草稿…</LoadingState> : <>
      {!run ? <section><h2>提交的草稿</h2>{index.drafts.length ? <ul className={styles.runs}>{index.drafts.map(d => <li key={d.id}><button onClick={() => { setSelectedChangeset(d.id); choose(""); }}><strong>{d.title}</strong><span>{d.origin === "human" ? "人工编纂" : d.origin === "wiki_agent" ? "原文代理编纂" : d.origin === "wiki_compilation" ? "文献持续编纂" : d.origin.startsWith("internal_demo_") ? "流程验证草稿" : "外部代理草稿"}</span></button></li>)}</ul> : <p>暂无待审核草稿。可从知识编纂页面提交修改。</p>}</section> : <>
        <div className={styles.runbar}><button disabled={dirty || busy} onClick={() => { setRun(null); setSelectedChangeset(""); choose(""); }}><ArrowLeft size={15} />全部草稿</button><div><h2>{run.title}</h2><p>{changes?.origin === "human" ? "人工编纂" : "提交的编纂草稿"} · 审核与发布</p></div></div>
        <div className={styles.columns}>
          <nav className={styles.outline} aria-label="审核内容"><h3>审核内容</h3>{[["all", "全部建议"], ...Object.entries(kinds)].map(([key, label]) => <button key={key} aria-current={category === key ? "true" : undefined} disabled={dirty || busy} onClick={() => { setCategory(key); choose(""); }}>{label}<span>{items.filter(i => (key === "all" || i.kind === key) && i.decision === "pending").length}</span></button>)}
            <details><summary>来源版本</summary><p>版本 {run.edition_id || "未绑定出版版本"}</p><p>正文修订 {run.document_revision_id || "由各项证据分别记录"}</p></details>
          </nav>
          <section className={styles.review} aria-label="建议审核">
            {preview ? <article><h3>{preview.title}</h3>{preview.scope && <p>{preview.scope}</p>}<KnowledgePageContent page={{ identity: preview.identity, references: preview.references, blocks: preview.blocks, assertions: preview.assertions || [], anchors: preview.anchors }} /><button onClick={() => setPreview(null)}>返回审核</button><p>{preview.status === "published" ? "此知识页已在当前实例发布。" : "此处展示已保存的知识页草稿；发布会同时公开本页引用的已审核陈述。"}</p>{!!preview.publication_scope?.entities.length && <p>一并发布的新身份：{preview.publication_scope.entities.map(v => v.label).join("、")}</p>}{preview.publication_scope?.withdrawals?.map(v => <p key={v.id}>将撤回：{v.text} · {v.reason}</p>)}{preview.id && preview.revision_id && preview.status !== "published" && <button disabled={busy} onClick={() => void action(async () => { if (!await confirmAction(`发布此知识页及其已审核陈述？${preview.publication_scope?.withdrawals?.length ? `同时撤回 ${preview.publication_scope.withdrawals.length} 条陈述。` : ""}${preview.publication_scope?.aliases?.length ? `同时发布异名：${preview.publication_scope.aliases.map(v => v.text).join("、")}。` : ""}${preview.publication_scope?.profiles?.length ? `同时更新已审核的类型资料：${preview.publication_scope.profiles.map(v => v.label).join("、")}。` : ""}${preview.publication_scope?.entities.length ? `同时发布已审核的新身份：${preview.publication_scope.entities.map(v => v.label).join("、")}。` : ""}`, { title: "发布知识", confirmLabel: "发布" })) return; await call(`/knowledge/pages/${preview.id}/`, { revision_id: preview.revision_id }); setNotice("知识页已在当前实例发布。"); setPreview(null); })}>发布此页</button>}</article> : item && value ? <article>
              <div className={styles.itemhead}><button className={styles.textButton} disabled={dirty || busy} onClick={() => choose("")}><ArrowLeft size={15} />返回建议</button><span className={styles.status}>{item.current_status === "published" ? "已发布" : item.application.id ? "已保存草稿" : decisions[item.decision]}</span><button className={styles.evidenceButton} onClick={() => setEvidenceOpen(!evidenceOpen)}><PanelRightOpen size={15} />查看原文</button></div>
              <h3 className={styles.reviewTitle}>{kinds[item.kind]}</h3>
              {evidenceSources.length > 1 && <div className={styles.actions} aria-label="证据来源">{evidenceSources.map((v, i) => <button key={i} aria-pressed={selectedEvidence === i} onClick={() => { setSelectedEvidence(i); setEvidenceOpen(true); }}>依据 {i + 1} · PDF {v.segments.map(p => p.page_number).join("、")}</button>)}</div>}
              {item.conflict.reason && <p role="alert" className={styles.error}>{item.conflict.reason}</p>}
              {item.kind === "entity" && value.operation === "profile_patch" ? <><h4>{value.label}</h4><EntityProfileFields kind={value.kind || ""} value={value.profile || {}} disabled={busy || !!item.application.id} onChange={profile => setDraft({ ...value, profile })} /><section className={styles.identityPreview} aria-label="类型资料展示预览"><h4>发布后的类型资料</h4><EntityProfileContent kind={value.kind || ""} profile={value.profile || {}} /></section><p>资料随知识页发布生效，原有身份与历史修订保留。</p></> : item.kind === "entity" ? <><label>名称<input value={value.label || ""} disabled={!!item.application.id} onChange={e => setDraft({ ...value, label: e.target.value })} /></label><p>类型 {value.kind} · {value.context}</p><label>定义或人物资料<textarea value={value.definition || ""} disabled={!!item.application.id} onChange={e => setDraft({ ...value, definition: e.target.value })} /></label>
                <EntityProfileFields kind={value.kind || ""} value={value.profile || {}} disabled={busy || !!item.application.id || !!value.existing_id} onChange={profile => setDraft({ ...value, profile })} /><section className={styles.identityPreview} aria-label="实体资料预览"><h4>身份资料预览</h4><strong>{matchedIdentity?.label || value.label || "名称待填写"}</strong><p>{matchedIdentity ? matchedIdentity.definition || matchedIdentity.context || "尚无定义资料" : value.definition || "定义或人物资料待填写"}</p><EntityProfileContent kind={value.kind || ""} profile={matchedIdentity?.profile || value.profile || {}} /><span>{value.existing_id ? "将关联已有身份，当前填写不会覆盖它的资料。" : "将保存为独立实体草稿，供知识页面关联。"}</span></section>
                <label>身份决定<select value={value.existing_id || ""} disabled={!!item.application.id} onChange={e => setDraft({ ...value, existing_id: e.target.value })}><option value="">保留为独立身份，建立实体草稿</option>{value.candidates?.map(c => <option key={c.id} value={c.id}>关联 {c.label} · {c.kind}</option>)}</select></label>
                {value.candidates?.map(c => <div key={c.id} className={styles.candidate}><strong>{c.label}</strong><p>{c.kind} · {c.definition || c.context || "尚无定义资料"}</p><EntityProfileContent kind={c.kind} profile={c.profile || {}} /><p>{c.aliases?.map(a => a.text).join("、")}</p><p>{c.identifiers?.map(i => `${i.namespace}: ${i.value}`).join(" · ")}</p>{!!c.related_works?.length && <section className={styles.candidateWorks}><h4>关联作品</h4><ul>{c.related_works.map((work, index) => <li key={`${work.work_id}-${index}`}><div><Link href={`/admin/library/works/${work.work_id}${work.edition_id ? `?edition=${work.edition_id}` : ""}`}>{work.title}</Link><span>{work.source_type === "contribution" ? `书目责任 · ${work.role_label}` : `陈述来源 · ${assertionPredicateLabels[work.role_label] || work.role_label || "学术论述"}`}</span></div>{work.text && <p>{work.text}</p>}{work.citation && <small>{work.citation}</small>}</li>)}</ul><small>每类最多展示 12 条已有记录；作品关联用于核对身份。</small></section>}<p>匹配依据：名称或已确认异名相符，作品关联供核对，身份仍须审核。</p>{value.comparisons?.filter(v => v.candidate_id === c.id).map(v => <p key={v.candidate_id}>{({ same_suggested: "建议同一", different: "不同身份", uncertain: "尚不确定" })[v.judgment] || v.judgment}：{v.reason}</p>)}</div>)}</> : item.kind === "assertion" && value.operation === "withdraw" ? <><h3>撤回陈述</h3><blockquote>{value.text}</blockquote><label>撤回原因<textarea value={value.reason || ""} disabled={!!item.application.id} onChange={e => setDraft({ ...value, reason: e.target.value })} /></label><p>保存后公开内容保持原样，发布时才撤回。历史记录与原文证据保留。</p></> : item.kind === "assertion" ? <><AssertionFields value={value} disabled={!!item.application.id} options={items.filter(v => v.kind === "entity").map(v => ({ id: v.id, label: v.payload.label || "待命名", kind: v.payload.kind, definition: v.payload.definition, pending: true }))} onChange={next => setDraft({ ...value, ...next })} />
                {value.source_citation !== undefined && <label>文献出处<textarea value={value.source_citation} disabled={busy || !!item.application.id} onChange={e => setDraft({ ...value, source_citation: e.target.value })} /></label>}
                <section className={styles.assertionPreview} aria-label="陈述展示预览"><h4>选用到知识页后的陈述样式</h4><KnowledgeAssertionContent assertion={{ id: item.id, text: value.text || "", conditions: value.conditions, sources: [{ work__title: run.title, attribution__label: typeof value.attribution_id === "object" && value.attribution_id ? items.find(v => v.id === (value.attribution_id as { change_item: string }).change_item)?.payload.label || null : value.attribution_id || null, expression: value.expression || "", citation: value.source_citation }], evidence: (value.evidence || []).map((e, i) => ({ anchor_id: e.anchor_id || `${item.id}-${i}`, stance: e.stance, ...(e.anchor_id && anchoredEvidence.find(a => a.anchor_id === e.anchor_id) ? { locator: anchoredEvidence.find(a => a.anchor_id === e.anchor_id)! } : {}), ...(source && e.segments?.length ? { locator: { reader_url: `/reader/${source.asset_id}?page=${e.segments[0].page_number}${run.document_revision_id ? `&revision=${run.document_revision_id}` : ""}&preview=1`, segments: e.segments } } : {}) })) }} /></section>
                {value.evidence?.map((e, i) => <div key={i}><label>证据作用<select value={e.stance} disabled={!!item.application.id} onChange={event => setDraft({ ...value, evidence: value.evidence?.map((row, index) => index === i ? { ...row, stance: event.target.value } : row) })}>{Object.entries({ supports: "支持", opposes: "反对", qualifies: "限定", context: "仅提供语境" }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>{(e.segments || anchoredEvidence.find(a => a.anchor_id === e.anchor_id)?.segments || []).map((s, j) => <blockquote key={j}>{s.exact}<cite>PDF 第 {s.page_number} 页</cite></blockquote>)}</div>)}</> : item.kind === "alias" ? <><h3>异名与归属身份</h3><p>{item.identity?.label || (typeof value.entity_id === "object" ? items.find(v => v.id === (value.entity_id as { change_item: string }).change_item)?.payload.label : "归属身份待核对")}</p>{([{ key: "text", label: "异名", max: 600 }, { key: "language", label: "语言（选填）", max: 32 }, { key: "script", label: "书写方式（选填）", max: 32 }] as const).map(field => <label key={field.key}>{field.label}<input value={value[field.key] || ""} maxLength={field.max} disabled={busy || !!item.application.id} onChange={e => setDraft({ ...value, [field.key]: e.target.value })} /></label>)}<section className={styles.identityPreview} aria-label="异名展示预览"><h4>{item.identity?.label || "关联身份"}</h4><EntityAliases aliases={value.text ? [{ text: value.text, language: value.language, script: value.script }] : []} /></section><p>保存为已审核草稿，知识页发布后用于公开展示与身份检索。</p></> : item.kind === "wiki_patch" ? <IntelligencePageEditor key={item.id} anchors={wikiEvidence.filter(v => v.anchor_id).map(v => ({ anchor_id: v.anchor_id, locator: v }))} patch={{ ...value, block: { ...value.block, references: value.block?.references?.filter((r): r is { type: string; id: string } => typeof r.id === "string") }, page_id: item.application.page_id || value.page_id }} title={run.title}
                profilePatch={items.find(v => v.kind === "entity" && v.payload.operation === "profile_patch" && v.payload.page_id === value.page_id && v.decision !== "rejected")?.payload.profile} version={changes?.version || 0} applied={!!item.application.id}
                onMetadata={fields => setDraft({ ...value, ...fields, human_edited: true })} onHumanReview={confirmed => setDraft({ ...value, human_edited: confirmed })} onBlock={block => setDraft({ ...value, human_edited: true, block: { ...value.block, ...block, references: value.block?.references } })} /> : <p>{value.label}</p>}
              {!!item.dependencies.length && <p>依赖 {item.dependencies.length} 项身份或证据建议，保存时一并检查。</p>}
              {(item.application.page_id || value.page_id) && <p><Link href={`/admin/knowledge?page=${item.application.page_id || value.page_id}${run.document_revision_id ? `&revision=${run.document_revision_id}` : ""}`}>进入知识页编纂 →</Link></p>}
              {item.application.page_id && <button onClick={() => void previewPage(item.application.page_id!)}>预览已保存知识页</button>}
              {!item.application.id && <div className={styles.decide}><label>审核备注（选填）<input value={note} onChange={e => setNote(e.target.value)} /></label><div className={styles.actions}><button className={styles.primary} disabled={busy} onClick={() => void decide("accepted")}><Check size={15} />确认此项</button><button disabled={busy} onClick={() => void decide("deferred")}>暂缓</button><button disabled={busy} onClick={() => void decide("rejected")}>拒绝</button>{dirty && <button className={styles.textButton} disabled={busy} onClick={() => { setDraft(null); setNote(item.decision_note || ""); }}>撤销未保存编辑</button>}</div></div>}
            </article> : <div><h3>{category === "all" ? "审核内容" : kinds[category]}</h3>{available.length ? <><div className={styles.actions}><button onClick={() => setChecked(available.filter(i => !i.application.id && i.decision === "pending").map(i => i.id))}>选择待审核项</button><button disabled={busy || !checked.length} onClick={() => void decideSelected("accepted")}>确认所选 {checked.length || ""}</button><button disabled={busy || !checked.length} onClick={() => void decideSelected("deferred")}>暂缓所选</button></div><ul className={styles.items}>{available.map(i => <li key={i.id}>{!i.application.id && <input aria-label={`选择${kinds[i.kind]}：${i.payload.title || i.payload.label || i.payload.text || i.payload.block?.text || kinds[i.kind]}`} type="checkbox" checked={checked.includes(i.id)} onChange={e => setChecked(old => e.target.checked ? [...old, i.id] : old.filter(id => id !== i.id))} />}<button onClick={() => choose(i.id)}><span>{kinds[i.kind]} · {i.current_status === "published" ? "已发布" : i.application.id ? "已保存草稿" : decisions[i.decision]}</span><strong>{i.payload.title || i.payload.label || i.payload.text || i.payload.block?.text || kinds[i.kind]}</strong>{i.conflict.reason && <span className={styles.error}>需要处理冲突</span>}</button></li>)}</ul></> : <p>此分类尚无建议。</p>}</div>}
          </section>
          <EvidencePanel source={source} locator={evidenceSources[selectedEvidence] || evidenceSources[0] || null} open={evidenceOpen} onClose={() => setEvidenceOpen(false)} />
        </div></>}
    </>}
  </section>;
}
