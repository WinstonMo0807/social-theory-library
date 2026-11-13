"use client";

import { createPortal } from "react-dom";
import type { AuditData, AuditEntry, AuditFinding, AuditOccurrence, PrivateCitationReference, ResearchRecord, ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchReaderHref } from "@/lib/api/research-evidence";
import { AuditEvidenceNotice, auditCategories, auditCategory, auditDecisions, auditFindingNames, auditLocation, auditStatuses } from "./citation-audit-shared";

const checkNames: Record<string, string> = { citation_identification: "识别引文", bibliography_identity: "书目匹配", version_page: "版本与页码核对", scan_ocr: "扫描文字识别" };
const relationNames: Record<string, string> = { support: "支持", different_conclusion: "不同结论", qualification: "限定条件", reframe: "转换解释", insufficient_evidence: "证据不足" };
const timestamp = (value: string) => new Date(value).toLocaleString("zh-CN");
const sourceAvailable = (reference: ResolvedEvidence) => reference.source_status === "available" && (!reference.anchors?.length || reference.anchors.every(anchor => anchor.source_status === "available"));

function SourceReference({ reference }: { reference: ResolvedEvidence }) {
  if (!sourceAvailable(reference)) return <p className="stl4-audit-print-note">原文当前不可访问或已变化；本报告不展示旧来源片段。请重新核对来源。</p>;
  const anchors = reference.anchors?.length ? reference.anchors : [reference];
  const href = researchReaderHref(reference);
  return <div className="stl4-audit-print-source">
    <p><strong>{reference.title || "原文材料"}</strong>{reference.authors?.length ? ` · ${reference.authors.join("、")}` : ""}</p>
    {reference.citation ? <p>{reference.citation}</p> : null}
    <p>{anchors.map(anchor => [anchor.pdf_page ? `PDF 第 ${anchor.pdf_page} 页` : "文件页码待核对", anchor.printed_label ? `书内页码 ${anchor.printed_label}` : ""].filter(Boolean).join(" · ")).join("；")}</p>
    {reference.quote || reference.text ? <blockquote>{reference.quote || reference.text}</blockquote> : <p>当前未提供可显示的原文文字。</p>}
    {href ? <p><a href={href}>返回书库核对原文</a></p> : null}
  </div>;
}

function Findings({ findings }: { findings: AuditFinding[] }) {
  return findings.length ? <>{findings.map((finding, index) => <section className="stl4-audit-print-finding" key={index}>
    <h5>{auditFindingNames[finding.kind] || "检查记录"} · {finding.status === "text_match" ? "规范化文字匹配" : finding.status === "not_requested" ? "未选择此项检查" : "待核对"}</h5>
    {finding.message ? <p>{finding.message}</p> : null}
    {finding.page_status ? <p>页码核对：{finding.page_status === "matched" ? "已匹配" : finding.page_status === "not_specified" ? "稿件未指定印刷页码" : "待核对"}{finding.claimed_printed_label ? `；稿件标注 ${finding.claimed_printed_label}` : ""}</p> : null}
    {finding.references?.map((reference, n) => <SourceReference key={`${researchEvidenceKey(reference)}:${n}`} reference={reference} />)}
    {finding.private_references?.map((reference, n) => <PrivateSourceReference key={`${reference.source_id}:${reference.unit_id}:${n}`} reference={reference} />)}
  </section>)}</> : <p>尚未形成检查结果。</p>;
}

function PrivateSourceReference({ reference }: { reference: PrivateCitationReference }) {
  if (reference.source_status !== "available") return <p className="stl4-audit-print-note">私人来源已移除、变化或不可访问；不展示旧片段。</p>;
  return <div className="stl4-audit-print-source"><p><strong>{reference.title || reference.filename || "本人来源文件"}</strong> · 本人选定来源</p>{reference.citation ? <p>{reference.citation}</p> : null}<p>{auditLocation(reference.location)}</p>{reference.quote ? <blockquote>{reference.quote}</blockquote> : <p>当前未提供可显示的原文文字。</p>}<p className="stl4-audit-print-note">此来源仅本人可见，未进入公共馆藏。文字匹配仍须核对版本、页码与上下文。</p></div>;
}

function Bibliography({ entries }: { entries: AuditEntry[] }) {
  return <section><h2>参考文献与版本对应</h2>{entries.length ? entries.map((entry, index) => {
    const selected = entry.selected_source_status === "available" ? entry.candidates.find(candidate => candidate.edition_id === entry.selected_edition_id && candidate.source_status === "available") : undefined;
    const privateSource = entry.selected_private_source_status === "available" ? entry.private_candidates?.find(candidate => candidate.source_id === entry.selected_private_source_id && candidate.source_status === "available") : undefined;
    return <section key={entry.id} className="stl4-audit-print-entry"><h3>{index + 1}. 稿件书目</h3><p>{entry.raw}</p>
      <p>{entry.identity_status === "private_confirmed" ? "本人已确认私人来源" : entry.identity_status === "user_confirmed" ? "本人已确认版本" : entry.identity_status === "identifier_matched" ? "标识匹配，仍需核对" : "出版版本待核对"}</p>
      {selected ? <p>对应馆藏：{selected.citation || [selected.title, selected.authors?.join("、"), selected.year, selected.version_label].filter(Boolean).join(" · ")}</p> : <p>{entry.selected_edition_id ? "已选馆藏版本当前不可用，请重新核对。" : "尚未选定馆藏版本。"}</p>}
      {entry.selected_private_source_id ? <p>{privateSource ? `本人已确认的私人来源：${privateSource.citation || privateSource.title || privateSource.filename}` : "已选私人来源当前不可用，请重新核对。"}</p> : null}
    </section>;
  }) : <p>当前未识别到参考文献。</p>}</section>;
}

function Occurrences({ rows, entries }: { rows: AuditOccurrence[]; entries: AuditEntry[] }) {
  const bibliography = new Map(entries.map(entry => [entry.id, entry]));
  return <>{rows.map((row, index) => <section key={row.id} className="stl4-audit-print-occurrence">
    <h3>{index + 1}. {auditLocation(row.location)}</h3><p className="stl4-audit-print-note">当前状态：{auditCategories[auditCategory(row)]}{row.checked_at ? ` · 最近核验 ${timestamp(row.checked_at)}` : ""}</p>
    <h4>稿件原句与上下文</h4><blockquote>{row.quote || row.raw || "未识别出直接引文。"}</blockquote>
    <p>{row.context || "未提供上下文。"}</p>{row.note_text ? <p>稿件脚注：{row.note_text}</p> : null}
    <h4>关联稿件书目</h4>{row.entry_ids.length ? row.entry_ids.map(id => <p key={id}>{bibliography.get(id)?.raw || "该书目对应关系待重新核对。"}</p>) : <p>尚未对应参考文献。</p>}
    <h4>分项检查与原文证据</h4><Findings findings={row.findings} />
    {row.support_analysis ? <section><h4>论断关系建议</h4><SourceReference reference={row.support_analysis.reference} />
      {sourceAvailable(row.support_analysis.reference) ? row.support_analysis.suggestions.map((suggestion, n) => <p key={n}>{relationNames[suggestion.relation || ""] || "待核对建议"}：{suggestion.reason || "尚未提供说明。"}</p>) : null}
      <p className="stl4-audit-print-note">关系建议需要本人回到原文判断，不能视为已确认结论。</p></section> : null}
    <h4>人工决定与修正</h4><AuditEvidenceNotice row={row} />{row.decision ? <><p>{auditDecisions[row.decision.value]} · {timestamp(row.decision.at)}</p><p>{row.decision.note || "未填写补充说明。"}</p>{row.decision.corrected_text ? <blockquote>本人校正：{row.decision.corrected_text}</blockquote> : null}</> : <p>尚未保存人工决定。</p>}
    {row.decision_history?.length ? <section><h4>前次人工决定</h4>{row.decision_history.map((decision, n) => <div key={n}><p>{auditDecisions[decision.value]} · {timestamp(decision.at)}</p><p>{decision.note || "无附注"}</p>{decision.corrected_text ? <blockquote>本人校正：{decision.corrected_text}</blockquote> : null}</div>)}</section> : null}
    {row.history?.length ? <section><h4>前次核验记录</h4>{row.history.map((version, n) => <div key={n}><p>第 {n + 1} 次 · {timestamp(version.checked_at)}</p><Findings findings={version.findings} /></div>)}</section> : null}
  </section>)}</>;
}

/** Only a fresh owner-verified export is passed here; screen rendering stays hidden. */
export function CitationAuditPrint({ record }: { record: ResearchRecord<AuditData> }) {
  const data = record.data;
  return createPortal(<article className="stl4-audit-print" aria-label="完整引文体检打印报告">
    <header><p>SOCIAL THEORY LIBRARY · 仅本人可见</p><h1>引文体检报告</h1><h2>{data.filename}</h2>
      <p>稿件版本 {data.manuscript_revision || 1} · 报告修订 {record.revision} · {auditStatuses[record.status || ""] || "已保存"}</p>
      <p>最后保存：{timestamp(record.updated_at)} · 本报告包含全部 {data.occurrences.length} 处引文和 {data.bibliography.length} 条参考文献。</p></header>
    <section><h2>检查范围与使用限制</h2><p>已选择：{data.checks?.map(check => checkNames[check] || check).join("、") || "检查项尚未记录"}</p>
      <p>{data.report_notice || "未找到原文的引文需要人工核对。"}</p>
      {data.location_notice ? <p>{data.location_notice}</p> : null}
      <p>报告记录导出时的结果，处理中的任务可能尚未完成。原文以打开时的内容和权限为准。人工修正保存在报告中，原稿不变。</p>
      {data.warnings?.map((warning, index) => <p key={index}>{warning.message}</p>)}
    </section>
    <section><h2>全部引文核验</h2>{data.occurrences.length ? <Occurrences rows={data.occurrences} entries={data.bibliography} /> : <p>尚未识别到可展示的引文位置，不能据此判断稿件没有问题。</p>}</section>
    <Bibliography entries={data.bibliography} />
    {data.parse_history?.length ? <section><h2>历史解析附录</h2><p>以下保留前次解析及人工记录；来源按本次导出时的可访问状态显示。</p>{data.parse_history.map((version, index) => <section key={index}><h2>历史解析 {index + 1}</h2><Occurrences rows={version.occurrences || []} entries={version.bibliography || []} /><Bibliography entries={version.bibliography || []} /></section>)}</section> : null}
  </article>, document.body);
}
