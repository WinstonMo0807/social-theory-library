"use client";
import { SourceText } from "@/components/source-text";


import { LoadingState } from "@/components/ui/loading-state";
import { MediaPlacement } from "@/components/media-placement";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronLeft, ChevronRight } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import type { PublicWorkDetail } from "@/lib/api/public-catalog";
import type { SearchPayload } from "@/lib/api/search.types";
import { changeResearchSelection, createResearchProject, readResearchRecord, type AuditCandidate, type AuditCapabilities, type AuditEntry, type AuditOccurrence, type ProjectData, type ResearchRecord, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref } from "@/lib/api/research-evidence";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace, useResearchRecord } from "@/lib/api/use-persistent-workspace";
import { isTaskRunning } from "@/lib/api/task-polling";
import { AuditBreadcrumb, AuditEvidenceNotice, AuditFrame, AuditGate, auditCategories, auditCategory, auditDecisions, auditFindingNames, auditLocation, auditRelationNames } from "./citation-audit-shared";
import { AuditMessages, AuditUnavailable, DecisionForm, useAuditWorkspace } from "./citation-audit-report";
import { CitationSourcePreview } from "./citation-source-preview";
import { CitationAuditVersions } from "./citation-audit-versions";
import { CitationPrivateMatches, CitationPrivateReferencePreview } from "./citation-private-sources";

export const identityNames: Record<string, string> = { pending: "尚未匹配", private_confirmed: "本人已确认私人来源", identifier_matched: "标识匹配，待核对上下文", user_confirmed: "本人已确认", needs_review: "候选版本待确认", not_matched_in_library: "未找到馆内候选", source_unavailable: "版本当前不可用", not_requested: "未选择书目匹配" };


export function CitationAuditIssue({ id, issueId }: { id: string; issueId: string }) {
  return <AuditGate next={`/account/citation-audits/${id}/issues/${issueId}`}>{(ownerId, retrySession) => <Issue key={`${id}:${issueId}`} id={id} issueId={issueId} ownerId={ownerId} retrySession={retrySession} />}</AuditGate>;
}

function Issue({ id, issueId, ownerId, retrySession }: { id: string; issueId: string; ownerId: string; retrySession: () => void }) {
  const router = useRouter();
  const workspace = useAuditWorkspace(id, ownerId);
  const capabilities = usePersistentWorkspace<AuditCapabilities>("/reading/citation-audits/capabilities/", ownerId);
  const [sourceKey, setSourceKey] = useState("");
  const [tab, setTab] = useState("manuscript");
  const [decisionRevision, setDecisionRevision] = useState<number | null>(null);
  const [matching, setMatching] = useState<{ entry: AuditEntry; candidate: AuditCandidate; revision: number } | null>(null);
  const [links, setLinks] = useState<{ ids: string[]; revision: number } | null>(null);
  const [locator, setLocator] = useState(false);
  const [pickingSource, setPickingSource] = useState(false);
  const [selectedSource, setSelectedSource] = useState<ResolvedEvidence | null>(null);
  const [sourceRevision, setSourceRevision] = useState<number | null>(null);
  const [transferBusy, setTransferBusy] = useState(false);
  const [transferError, setTransferError] = useState("");
  const transferRequest = useRef<{ fingerprint: string; requestId: string; projectId?: string } | null>(null);
  const transferInFlight = useRef(false);
  const alive = useRef(false);
  useEffect(() => { alive.current = true; const off = subscribeToSessionChanges(() => { alive.current = false; transferRequest.current = null; setSelectedSource(null); setMatching(null); setLinks(null); setDecisionRevision(null); setLocator(false); }); return () => { alive.current = false; off(); }; }, []);
  const record = workspace.data;
  if (!record) return <AuditUnavailable error={workspace.error} retry={retrySession} />;
  const row = record.data.occurrences?.find(item => item.id === issueId);
  if (!row) return <AuditFrame><AuditBreadcrumb id={id} issue /><div className="stl4-research-empty"><h1>当前报告中没有这处引文</h1><p>重新解析后位置可能发生变化，前次人工记录仍可从报告历史中查阅。</p><Link href={`/account/citation-audits/${id}`}>返回报告</Link></div></AuditFrame>;
  const entryRows = record.data.bibliography.filter(entry => row.entry_ids.includes(entry.id));
  const sources = row.findings.flatMap(finding => finding.references || []);
  if (row.support_analysis?.reference) sources.push(row.support_analysis.reference);
  const privateSources = row.findings.flatMap(finding => finding.private_references || []);
  const uniquePrivateSources = privateSources.filter((ref, index) => privateSources.findIndex(item => item.source_id === ref.source_id && item.unit_id === ref.unit_id && item.source_generation === ref.source_generation) === index);
  const uniqueSources = sources.filter((ref, index) => sources.findIndex(item => researchEvidenceKey(item) === researchEvidenceKey(ref)) === index);
  const reference = uniqueSources.find(ref => researchEvidenceKey(ref) === sourceKey) || uniqueSources.find(ref => ref.source_status === "available") || uniqueSources[0] || null;
  const running = isTaskRunning(record.status);
  const busy = workspace.busy || running || transferBusy;
  const index = record.data.occurrences.findIndex(item => item.id === issueId);
  async function transfer() {
    if (!record || !row || busy || transferInFlight.current || !alive.current) return;
    transferInFlight.current = true;
    setTransferBusy(true); setTransferError("");
    const available = uniqueSources.filter(ref => ref.source_status === "available");
    const body: Omit<Parameters<typeof createResearchProject>[0], "request_id"> = {
      title: `引文核验：${record.data.filename}`.slice(0, 200), question: (row.quote || row.context).slice(0, 4000),
      scope: available.length ? { kind: "passages", references: available.map(researchEvidenceReference), allow_neighbors: false } : { kind: "library" },
    };
    const fingerprint = JSON.stringify(body);
    if (transferRequest.current?.fingerprint !== fingerprint) transferRequest.current = { fingerprint, requestId: createRequestKey() };
    const operation = transferRequest.current;
    try {
      const project = await withPrivateOwner(ownerId, async () => {
        if (!alive.current) throw new DOMException("Session changed", "AbortError");
        if (!operation.projectId) {
          const created = await createResearchProject({ ...body, request_id: operation.requestId });
          if (!alive.current) throw new DOMException("Session changed", "AbortError");
          operation.projectId = created.id;
        }
        // A previous add may have succeeded before its response was lost. Read
        // the saved selection and revision before retrying this remaining step.
        const current = await readResearchRecord<ProjectData>("research-projects", operation.projectId);
        if (!alive.current) throw new DOMException("Session changed", "AbortError");
        const saved = new Set(current.data.selections.map(researchEvidenceKey));
        const missing = available.filter(ref => !saved.has(researchEvidenceKey(ref)));
        return missing.length ? changeResearchSelection(current.id, {
          expected_revision: current.revision, action: "add", references: missing.map(researchEvidenceReference),
        }) : current;
      });
      if (alive.current) router.push(`/account/research/${project.id}`);
    } catch (reason) { if (alive.current) setTransferError(reason instanceof Error ? reason.message : "研究资料未能保存，请重试。"); }
    finally { transferInFlight.current = false; if (alive.current) setTransferBusy(false); }
  }
  return <AuditFrame className="stl4-audit-detail-page stl4-audit-issue-page"><AuditBreadcrumb id={id} issue /><header className="stl4-audit-heading"><div><h1>引文问题详情与原文核验</h1></div><div className="stl4-audit-header-actions">{reference && researchReaderHref(reference) ? <Link className="stl4-audit-button is-primary" target="_blank" rel="noreferrer" href={researchReaderHref(reference)}>打开原文 PDF</Link> : null}<button onClick={() => setLocator(true)}>稿件中定位</button><button onClick={() => void workspace.download("original")} disabled={workspace.busy}>下载原稿</button></div></header><AuditMessages workspace={workspace} />{transferError ? <p role="alert">{transferError}</p> : null}
    <CitationAuditVersions key={record.id} record={record} ownerId={ownerId} disabled={workspace.busy || transferBusy} onRefresh={workspace.reload} retrySession={retrySession} />
    <div className="stl4-audit-issue-bar"><div><strong>{record.data.filename}</strong><small>稿件版本 {record.data.manuscript_revision || 1} · {auditLocation(row.location)}</small></div><nav aria-label="逐条核验">{index > 0 ? <Link aria-label="上一条引文" href={`/account/citation-audits/${id}/issues/${record.data.occurrences[index - 1].id}`}><ChevronLeft size={16} /></Link> : <span />}<span>{index + 1} / {record.data.occurrences.length}</span>{index + 1 < record.data.occurrences.length ? <Link aria-label="下一条引文" href={`/account/citation-audits/${id}/issues/${record.data.occurrences[index + 1].id}`}><ChevronRight size={16} /></Link> : <span />}</nav><span className="stl4-audit-state" data-state={auditCategory(row)}>{auditCategories[auditCategory(row)]}</span></div>
    <nav className="stl4-audit-mobile-tabs" aria-label="核验内容">{[["manuscript", "稿件"], ["candidates", "候选版本"], ["source", "原文"], ["decision", "判断"]].map(([key, label]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}</nav>
    <div className="stl4-audit-issue-grid" data-mobile-tab={tab}>
      <section className="stl4-audit-manuscript-pane"><h2>1. 稿件中的引文</h2><blockquote>{row.quote || row.raw || "未解析出直接引文，请核对下方稿件上下文。"}</blockquote><h3>稿件上下文</h3><p className="stl4-audit-original-text">{row.context}</p>{row.note_text ? <><h3>脚注内容</h3><p>{row.note_text}</p></> : null}<button onClick={() => setLocator(true)}>{auditLocation(row.location)}</button><h3>关联参考文献</h3>{entryRows.length ? entryRows.map(entry => <p key={entry.id}>{entry.raw}</p>) : <p>尚未对应参考文献。</p>}<button disabled={busy} onClick={() => setLinks({ ids: row.entry_ids, revision: record.revision })}>修正书目对应关系</button></section>
      <section className="stl4-audit-candidate-pane"><h2>2. 候选作品与准确版本</h2>{entryRows.map(entry => <section key={entry.id}><h3>{entry.raw}</h3><p>{entry.selected_source_status === "source_unavailable" ? "已选版本当前不可用，请重新核对" : identityNames[entry.identity_status] || "书目信息待核对"}</p>{entry.candidates.map(candidate => <CandidateCard key={candidate.edition_id} candidate={candidate} selected={entry.selected_edition_id === candidate.edition_id} disabled={busy} onChoose={() => setMatching({ entry, candidate, revision: record.revision })} />)}{!entry.candidates.length ? <p>没有可确认的候选版本。可从馆藏查找，或保留为待核实。</p> : null}<EditionSearch ownerId={ownerId} disabled={busy} onChoose={candidate => setMatching({ entry, candidate, revision: record.revision })} /><CitationPrivateMatches entry={entry} record={record} ownerId={ownerId} workspace={workspace} /></section>)}{!entryRows.length ? <p>先确认稿件引文对应的参考文献，再核对候选版本。</p> : null}</section>
      <section className="stl4-audit-source-pane"><h2>3. 原文与上下文</h2>{uniqueSources.length > 1 ? <label>原文位置<select data-stl-select value={reference ? researchEvidenceKey(reference) : ""} onChange={event => setSourceKey(event.target.value)}>{uniqueSources.map((ref, sourceIndex) => <option key={researchEvidenceKey(ref)} value={researchEvidenceKey(ref)}>{ref.title || `来源 ${sourceIndex + 1}`} · {ref.pdf_page ? `PDF ${ref.pdf_page}` : "位置待核对"}{ref.source_status !== "available" ? "（不可用）" : ""}</option>)}</select></label> : null}{reference || !uniquePrivateSources.length ? <CitationSourcePreview reference={reference} /> : null}{uniquePrivateSources.map(ref => <CitationPrivateReferencePreview key={`${ref.source_id}:${ref.source_generation}:${ref.unit_id}`} reference={ref} ownerId={ownerId} />)}{!reference && !uniquePrivateSources.length ? <p>尚无可展示的原文证据。确认版本后重新检查，或从本人研究选材中选择公开原文。</p> : null}<button disabled={busy} onClick={() => { setPickingSource(true); setSourceRevision(record.revision); setSelectedSource(null); }}>选择原文核对论断</button></section>
      <section className="stl4-audit-decision-pane"><h2>4. 分项结论</h2><dl className="stl4-audit-findings">{entryRows.map(entry => <div key={entry.id}><dt>书目核对</dt><dd>{entry.selected_source_status === "source_unavailable" ? "已选版本当前不可用" : identityNames[entry.identity_status] || "待核对"}</dd></div>)}{row.findings.map((finding, findingIndex) => <div key={findingIndex}><dt>{auditFindingNames[finding.kind] || "检查记录"}</dt><dd><strong>{finding.status === "text_match" ? "规范化文字匹配" : finding.status === "not_requested" ? "未选择此检查" : "待核对"}</strong><p>{finding.message}</p>{finding.page_status ? <small>页码：{finding.page_status === "matched" ? "已匹配" : finding.page_status === "not_specified" ? "稿件未指定印刷页码" : "待核对"}{finding.claimed_printed_label ? ` · 稿件标注 ${finding.claimed_printed_label}` : ""}</small> : null}</dd></div>)}</dl>{!row.findings.length ? <p>当前尚未形成检查结果。</p> : null}{row.support_analysis ? <section><h3>论断关系建议</h3>{row.support_analysis.suggestions?.map((suggestion, n) => <p key={n}><strong>{auditRelationNames[suggestion.relation || ""] || "待核对建议"}</strong> {suggestion.reason || ""}</p>)}{!row.support_analysis.suggestions?.length ? <p>尚无可用建议，不能据此判定支持或反证。</p> : null}<small>建议仍需本人回到原文判断。</small></section> : null}<h2>5. 人工确认与操作</h2><AuditEvidenceNotice row={row} />{row.decision ? <div className="stl4-audit-owner-note"><strong>{auditDecisions[row.decision.value]}</strong><p>{row.decision.note || "未填写补充说明。"}</p>{row.decision.corrected_text ? <blockquote>本人校正：{row.decision.corrected_text}</blockquote> : null}<time dateTime={row.decision.at}>{new Date(row.decision.at).toLocaleString("zh-CN")}</time></div> : <p>尚未保存人工决定。</p>}<button className="is-primary" disabled={busy} onClick={() => setDecisionRevision(record.revision)}>记录人工决定</button><section className="stl4-audit-inline-decision">{decisionRevision !== null ? <DecisionForm title="保存人工核验" titleId="audit-decision-title" initial={row.decision} busy={busy} stale={decisionRevision !== record.revision} error={workspace.actionError} onReload={() => setDecisionRevision(record.revision)} onCancel={() => setDecisionRevision(null)} onSave={async (decision, note, correctedText) => { if (decisionRevision && await workspace.command({ action: "decision", occurrence_id: row.id, decision, note, ...(correctedText !== undefined ? { corrected_text: correctedText } : {}) }, decisionRevision)) setDecisionRevision(null); }} /> : null}</section><button disabled={busy} onClick={() => void workspace.command({ action: "retry", occurrence_ids: [row.id] })}>仅重新检查这一条</button><button disabled={busy} onClick={() => void transfer()}>转入后续研究（补充来源）</button>{uniquePrivateSources.length ? <p className="stl4-audit-caption">转入研究时保存当前问题与可访问的馆藏选材，私人来源不会自动带入。</p> : null}{record.project_id ? <Link href={`/account/research/${record.project_id}`}>返回关联研究</Link> : null}<Link href={`/account/citation-audits/${id}`}>返回体检报告</Link></section>
    </div>
    <IssueHistory row={row} />

    <Dialog open={Boolean(matching)} className="stl4-audit-dialog" onRequestClose={() => { if (!workspace.busy) setMatching(null); }} aria-labelledby="audit-match-title">{matching ? <><h2 id="audit-match-title">确认准确版本</h2><p>稿件书目：{matching.entry.raw}</p><blockquote>{matching.candidate.citation || `${matching.candidate.title} ${matching.candidate.version_label || ""} ${matching.candidate.year || ""}`}</blockquote><p>确认会更新这一条参考文献的版本，并重新检查所有引用它的位置。原稿和原有人工判断保留。</p>{matching.revision !== record.revision ? <p role="alert">报告已更新，请关闭此窗口后重新核对候选版本。</p> : null}{workspace.actionError ? <p role="alert">{workspace.actionError}</p> : null}<footer><button onClick={() => setMatching(null)} disabled={workspace.busy}>取消</button><button className="is-primary" disabled={busy || matching.revision !== record.revision} onClick={async () => { if (await workspace.command({ action: "match", entry_id: matching.entry.id, edition_id: matching.candidate.edition_id }, matching.revision)) setMatching(null); }}>确认版本并重新检查</button></footer></> : null}</Dialog>
    <Dialog open={Boolean(links)} className="stl4-audit-dialog" onRequestClose={() => { if (!workspace.busy) setLinks(null); }} aria-labelledby="audit-link-title">{links ? <><h2 id="audit-link-title">修正参考文献对应关系</h2><p>只选择稿件中这一处引文实际引用的书目。</p><div className="stl4-audit-link-options">{record.data.bibliography.map(entry => <label key={entry.id}><input type="checkbox" disabled={busy} checked={links.ids.includes(entry.id)} onChange={event => setLinks({ ...links, ids: event.target.checked ? [...links.ids, entry.id] : links.ids.filter(key => key !== entry.id) })} />{entry.raw}</label>)}</div>{links.revision !== record.revision ? <p role="alert">报告已更新，请关闭后重新核对书目。</p> : null}{workspace.actionError ? <p role="alert">{workspace.actionError}</p> : null}<footer><button disabled={workspace.busy} onClick={() => setLinks(null)}>取消</button><button disabled={busy || links.revision !== record.revision} onClick={async () => { if (await workspace.command({ action: "link", occurrence_id: row.id, entry_ids: links.ids }, links.revision)) setLinks(null); }}>保存对应关系并重查</button></footer></> : null}</Dialog>
    <Dialog open={locator} className="stl4-audit-dialog" onRequestClose={() => setLocator(false)} aria-labelledby="audit-locator-title"><h2 id="audit-locator-title">稿件原句与位置</h2><p>{record.data.filename} · 稿件版本 {record.data.manuscript_revision || 1}</p><p>{auditLocation(row.location)}</p><blockquote>{row.context}</blockquote><p>{record.data.location_notice || "PDF 页码与稿件段落位置分别记录。"}</p>{record.data.filetype === "docx" ? <p>下载原稿后，可在 Word 中搜索这段文字定位。段落位置不等于 Word 排版页码。</p> : null}<footer><Link className="stl4-audit-button" href={`/account/citation-audits/${id}/parse?occurrence=${encodeURIComponent(row.id)}`}>在解析工作台定位</Link><button onClick={() => void workspace.download("original")} disabled={workspace.busy}>下载原稿</button><button onClick={() => setLocator(false)}>关闭</button></footer></Dialog>
    <Dialog open={pickingSource} className="stl4-audit-dialog" onRequestClose={() => { if (!workspace.busy) setPickingSource(false); }} aria-labelledby="audit-source-title"><h2 id="audit-source-title">选择原文核对论断</h2>{pickingSource ? <AuditSourcePicker ownerId={ownerId} disabled={busy} selected={selectedSource} onChange={setSelectedSource} /> : null}<p>本次论断与所选原文将发送给书库配置的 API 服务。</p><p>{capabilities.data?.analysis?.reason || "正在读取分析服务状态。"}</p>{sourceRevision !== record.revision ? <p role="alert">报告已有更新，请关闭后重新选取原文。</p> : null}{workspace.actionError || capabilities.error ? <p role="alert">{workspace.actionError || capabilities.error}</p> : null}<footer><button onClick={() => setPickingSource(false)} disabled={workspace.busy}>取消</button><button disabled={busy || !selectedSource || !capabilities.data?.analysis?.available || sourceRevision !== record.revision} onClick={async () => { if (selectedSource && sourceRevision && await workspace.command({ action: "analyze", occurrence_id: row.id, reference: researchEvidenceReference(selectedSource) }, sourceRevision)) setPickingSource(false); }}>请求分析此原文</button></footer></Dialog>
  </AuditFrame>;
}

export function CandidateCard({ candidate, selected, disabled, onChoose }: { candidate: AuditCandidate; selected?: boolean; disabled: boolean; onChoose: () => void }) {
  return <article className="stl4-audit-candidate" data-selected={selected || undefined}>{candidate.cover_url ? <MediaPlacement uses={candidate.cover_media?.display_uses} fallback={<BookOpen size={32} aria-hidden="true" />}><Image src={normalizePublicResourceUrl(candidate.cover_url)} alt="" width={48} height={68} unoptimized /></MediaPlacement> : <BookOpen size={32} aria-hidden="true" />}<div><h4>{candidate.title}</h4><p>{candidate.authors?.join("、")}</p><small>{[candidate.year, candidate.version_label].filter(Boolean).join(" · ") || "出版信息待核对"}</small>{candidate.review_fields?.length ? <p>需要核对：{candidate.review_fields.map(field => ({ authors: "作者", year: "年份", language: "语言", translator: "译者", publisher: "出版者" }[field] || "版本信息")).join("、")}</p> : null}{Boolean(candidate.source_status && candidate.source_status !== "available") ? <p>该候选当前不可访问。</p> : <button disabled={disabled} onClick={onChoose}>{selected ? "已选版本 · 重新确认" : "选择此版本"}</button>}</div></article>;
}

function EditionSearch({ ownerId, disabled, onChoose }: { ownerId: string; disabled: boolean; onChoose: (candidate: AuditCandidate) => void }) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [page, setPage] = useState(1);
  const [slug, setSlug] = useState("");
  const search = usePersistentWorkspace<SearchPayload>(submitted ? `/catalog/search/?context=global&scope=works&q=${encodeURIComponent(submitted)}&page=${page}&page_size=8` : "", ownerId);
  const detail = usePersistentWorkspace<PublicWorkDetail>(slug ? `/catalog/works/${encodeURIComponent(slug)}/` : "", ownerId);
  return <details data-disclosure="collection" className="stl4-audit-edition-search"><summary>从馆藏查找其他版本</summary><form onSubmit={event => { event.preventDefault(); setSubmitted(query.trim()); setPage(1); setSlug(""); }}><label>书名、作者或标识<input value={query} onChange={event => setQuery(event.target.value)} maxLength={300} /></label><button disabled={!query.trim() || disabled}>查找</button></form>{search.loading || detail.loading ? <LoadingState role="status">正在读取馆藏…</LoadingState> : null}{search.error || detail.error ? <p role="alert">{search.error || detail.error}<button onClick={() => { search.reload(); detail.reload(); }}>重试</button></p> : null}{search.data?.works.map(work => <button key={work.id} disabled={!work.edition?.public_slug || disabled} onClick={() => setSlug(work.edition?.public_slug || "")}>{work.title} · 查看版本</button>)}{search.data && !search.data.works.length ? <p>没有找到可访问的馆藏作品。</p> : null}{search.data ? <div><button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><button disabled={page >= search.data.pagination.total_pages} onClick={() => setPage(page + 1)}>下一页</button></div> : null}{detail.data?.editions.map(edition => <CandidateCard key={edition.id} candidate={{ edition_id: edition.id, work_id: detail.data!.id, title: detail.data!.title, version_label: edition.version_label || edition.edition_statement, year: edition.publication_year, cover_url: detail.data!.cover, source_status: "available" }} disabled={disabled} onChoose={() => onChoose({ edition_id: edition.id, work_id: detail.data!.id, title: detail.data!.title, version_label: edition.version_label || edition.edition_statement, year: edition.publication_year })} />)}</details>;
}

function AuditSourcePicker({ ownerId, disabled, selected, onChange }: { ownerId: string; disabled: boolean; selected: ResolvedEvidence | null; onChange: (value: ResolvedEvidence | null) => void }) {
  const [projectId, setProjectId] = useState("");
  const [page, setPage] = useState(1);
  const projects = usePersistentWorkspace<Paginated<ResearchRecord<ProjectData>>>(`/reading/research-projects/?page=${page}`, ownerId);
  const project = useResearchRecord<ProjectData>("research-projects", projectId || null, ownerId);
  return <section><label>本人研究中的选材<select data-stl-select disabled={disabled} value={projectId} onChange={event => { setProjectId(event.target.value); onChange(null); }}><option value="">选择研究</option>{projects.data?.results.map(row => <option key={row.id} value={row.id}>{row.data.title || row.data.question}</option>)}</select></label><div><button disabled={disabled || page <= 1} onClick={() => { setPage(page - 1); setProjectId(""); onChange(null); }}>上一页</button><button disabled={disabled || !projects.data?.next} onClick={() => { setPage(page + 1); setProjectId(""); onChange(null); }}>下一页</button></div>{projects.error || project.error ? <p role="alert">{projects.error || project.error}</p> : null}{project.data?.data.selections.map(ref => <label className="stl4-audit-source-choice" key={researchEvidenceKey(ref)}><input type="radio" name="audit-reference" disabled={disabled || ref.source_status !== "available"} checked={Boolean(selected && researchEvidenceKey(selected) === researchEvidenceKey(ref))} onChange={() => onChange(ref)} /><span>{ref.title || "原文选段"}<small><SourceText text={(ref.source_status === "available" ? ref.quote || ref.text : "来源不可用") || ""} compact /></small></span></label>)}{project.data && !project.data.data.selections.length ? <p>此研究尚未保存原文选材。</p> : null}<Link href="/explore/original" target="_blank" rel="noreferrer">检索原文并保存到研究</Link></section>;
}

function IssueHistory({ row }: { row: AuditOccurrence }) {
  return <details data-disclosure="collection" className="stl4-audit-diagnostics"><summary>核验与人工决定历史</summary>{row.history?.map((version, index) => <section key={index}><h3>检查记录 {index + 1}</h3><time dateTime={version.checked_at}>{new Date(version.checked_at).toLocaleString("zh-CN")}</time>{version.findings.map((finding, findingIndex) => <p key={findingIndex}>{finding.message}</p>)}</section>)}{row.decision_history?.map((decision, index) => <p key={index}>{auditDecisions[decision.value]} · {decision.note || "无附注"}{decision.corrected_text ? ` · 本人校正：${decision.corrected_text}` : ""} · {new Date(decision.at).toLocaleString("zh-CN")}</p>)}{!row.history?.length && !row.decision_history?.length ? <p>尚无前次核验记录。</p> : null}</details>;
}
