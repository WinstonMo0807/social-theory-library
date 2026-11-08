"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, ExternalLink, Network, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { SharedCitationButton } from "@/components/shared-citation-overlay";
import type { KnowledgeNodeDetail, NormalizedKnowledgeRelation, TheoryConceptUsage } from "@/lib/api/knowledge.types";
import styles from "./theory-detail.module.css";

const label = (usage: TheoryConceptUsage) => usage.title || usage.term;
const years = (person: { birth_year: number | null; death_year: number | null }) =>
  [person.birth_year, person.death_year].filter(value => value !== null).join(" — ");

export function UsageSource({ usage }: { usage: TheoryConceptUsage }) {
  const source = usage.source;
  return <div className={styles.source}>
    <blockquote>{source.text}</blockquote>
    <p>《{source.work_title}》{source.edition_label ? ` · ${source.edition_label}` : ""}{source.printed_label ? ` · 印刷页 ${source.printed_label}` : ` · PDF 第 ${source.page_start}${source.page_end !== source.page_start ? `–${source.page_end}` : ""} 页`}</p>
    <div className={styles.inlineActions}>
      <Link href={source.reader_url} target="_blank" rel="noopener noreferrer">阅读原文<ExternalLink size={14} /></Link>
      <SharedCitationButton reference={{ evidence_span_id: source.id, asset_id: source.asset_id, document_revision_id: source.document_revision_id, pdf_page: source.page_start }}>引用这段原文</SharedCitationButton>
    </div>
  </div>;
}

export function TheoryUsageExplorer({ usages, unavailableCount = 0, initialCompare = "" }: {
  usages: TheoryConceptUsage[]; unavailableCount?: number; initialCompare?: string;
}) {
  const available = (raw: string) => [...new Set(raw.split(",").filter(id => usages.some(usage => usage.id === id)))].slice(0, 2);
  const [selected, setSelected] = useState<string[]>(() => available(initialCompare));
  const [compareOpen, setCompareOpen] = useState(() => available(initialCompare).length === 2);
  const [detailId, setDetailId] = useState("");
  const [period, setPeriod] = useState(""), [context, setContext] = useState(""), [author, setAuthor] = useState("");
  const [notice, setNotice] = useState(initialCompare && available(initialCompare).length !== 2 ? "比较中的部分用法当前不可读取，请从已公开用法重新选择。" : "");
  const detail = usages.find(usage => usage.id === detailId);
  const chosen = selected.flatMap(id => usages.find(usage => usage.id === id) || []);
  const visible = usages.filter(usage => (!period || usage.period === period) && (!context || usage.context === context) && (!author || usage.author?.id === author));
  const periods = [...new Set(usages.map(usage => usage.period).filter(Boolean))];
  const contexts = [...new Set(usages.map(usage => usage.context).filter(Boolean))];
  const authors = [...new Map(usages.filter(usage => usage.author).map(usage => [usage.author!.id, usage.author!])).values()];

  useEffect(() => {
    const restore = () => {
      const raw = new URLSearchParams(window.location.search).get("compare") || "";
      const ids = [...new Set(raw.split(",").filter(id => usages.some(usage => usage.id === id)))].slice(0, 2);
      setSelected(ids); setCompareOpen(ids.length === 2); setDetailId("");
      setNotice(raw && ids.length !== 2 ? "比较中的部分用法当前不可读取，请重新选择。" : "");
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [usages]);
  function toggle(id: string) {
    if (selected.includes(id)) { setSelected(selected.filter(value => value !== id)); setNotice(""); }
    else if (selected.length < 2) { setSelected([...selected, id]); setNotice(""); }
    else setNotice("已选择两个用法。请先移除其中一个，再选择其他用法。");
  }
  function compare() {
    if (chosen.length !== 2) { setNotice("请选择两个已公开的用法。"); return; }
    const address = new URL(window.location.href);
    address.searchParams.set("compare", selected.join(","));
    window.history.pushState(null, "", `${address.pathname}${address.search}${address.hash}`);
    setCompareOpen(true); setDetailId("");
  }
  function closeCompare() {
    setCompareOpen(false);
    const address = new URL(window.location.href);
    address.searchParams.delete("compare");
    window.history.replaceState(null, "", `${address.pathname}${address.search}${address.hash}`);
  }
  return <section id="usages" className={styles.section} aria-labelledby="theory-usages-heading">
    <header className={styles.sectionHeading}><div><h2 id="theory-usages-heading">核心用法 <small>（{selected.length}/{usages.length}）</small></h2><p>选择两个用法进行比较，深入理解同一概念在不同语境中的含义。</p></div><button className={styles.primary} type="button" disabled={chosen.length !== 2} onClick={compare}>比较所选用法（{chosen.length}）<ArrowRight size={15} /></button></header>
    {usages.length ? <section data-content-section className={styles.usageFilters}><header data-section-heading>筛选用法{author || period || context ? " · 已筛选" : ""}<ChevronDown size={13} /></header><div className={styles.filters}>
      <label>作者<select data-stl-select value={author} onChange={event => setAuthor(event.target.value)}><option value="">所有作者</option>{authors.map(person => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
      {periods.length ? <label>时期<select data-stl-select value={period} onChange={event => setPeriod(event.target.value)}><option value="">所有时期</option>{periods.map(value => <option key={value}>{value}</option>)}</select></label> : null}
      {contexts.length ? <label>语境<select data-stl-select value={context} onChange={event => setContext(event.target.value)}><option value="">所有语境</option>{contexts.map(value => <option key={value}>{value}</option>)}</select></label> : null}
      {author || period || context ? <button type="button" onClick={() => { setAuthor(""); setPeriod(""); setContext(""); }}>清除筛选</button> : null}
    </div></section> : null}
    <div className={styles.usageGrid}>{visible.map(usage => <article className={`${styles.usageCard} ${selected.includes(usage.id) ? styles.selected : ""}`} key={usage.id} id={`usage-${usage.id}`}>
      <label className={styles.selectUsage}><input type="checkbox" checked={selected.includes(usage.id)} onChange={() => toggle(usage.id)} aria-label={`将${usage.author?.name || "本条"}的${label(usage)}加入比较`} /><span>{selected.includes(usage.id) ? "已选" : "加入比较"}</span></label>
      <button className={styles.usageSummary} type="button" onClick={() => setDetailId(usage.id)}>
        {usage.author?.portrait_url ? <MediaPlacement uses={usage.author.portrait_media?.display_uses}><img src={usage.author.portrait_url} alt="" loading="lazy" /></MediaPlacement> : <span className={styles.portraitEmpty} aria-hidden="true"><BookOpen size={23} /></span>}
        <span><strong>{usage.author?.name || "作者资料待补"}{usage.author && years(usage.author) ? <small>（{years(usage.author)}）</small> : null}</strong>{usage.author?.original_name ? <small>{usage.author.original_name}</small> : null}<b>{label(usage)}</b><span className={styles.usageMeaning}>{usage.interpretation || "查看原文与已确认的用法。"}</span>{usage.context ? <em>{usage.context}</em> : null}</span><ArrowRight size={16} />
      </button>
      <footer><button type="button" onClick={() => setDetailId(usage.id)}>查看用法细节<ArrowRight size={14} /></button><Link href={usage.source.reader_url} target="_blank" rel="noopener noreferrer">查看原文<ExternalLink size={13} /></Link></footer>
    </article>)}</div>
    {!visible.length ? <p className={styles.empty}>{usages.length ? "当前筛选下没有已公开用法。可清除筛选继续查看。" : "尚无已确认并公开的作者用法。概念说明与相关馆藏仍可继续阅读。"}</p> : null}
    {unavailableCount > 0 ? <p className={styles.notice}>另有 {unavailableCount} 处用法的原文当前不可读取，暂不参与展示与比较。</p> : null}
    {notice ? <p className={styles.notice} role="status">{notice}</p> : null}
    {chosen.length ? <div className={styles.comparisonTray} aria-label="已选择的用法">
      <div>{chosen.map(usage => <span key={usage.id}><strong>{usage.author?.name || label(usage)}</strong><small>{label(usage)}</small><button type="button" aria-label={`移除${label(usage)}`} onClick={() => toggle(usage.id)}><X size={15} /></button></span>)}</div>
      <button type="button" className={styles.primary} disabled={chosen.length !== 2} onClick={compare}>开始比较（{chosen.length}）<ArrowRight size={15} /></button><button type="button" onClick={() => { setSelected([]); setNotice(""); }}>清空选择</button>
    </div> : null}
    <Dialog open={Boolean(detail)} onRequestClose={() => setDetailId("")} className={styles.dialog} aria-labelledby="theory-usage-title">
      {detail ? <><header><div><small>{detail.author?.name || "作者资料待补"}的用法</small><h2 id="theory-usage-title">{label(detail)}</h2></div><button type="button" aria-label="关闭用法详情" onClick={() => setDetailId("")}><X size={20} /></button></header>
        <div className={styles.dialogBody}><p className={styles.prose}>{detail.interpretation || "当前用法尚无独立释义，请直接核对下列原文。"}</p>
          <dl className={styles.facts}>{[["解释对象", detail.explanatory_object], ["时期", detail.period], ["使用语境", detail.context], ["归属说明", detail.attribution_note]].filter(([, value]) => value).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
          {detail.author?.scholar_slug ? <Link href={`/scholars/${detail.author.scholar_slug}`}>查看{detail.author.name}的学者条目<ArrowRight size={14} /></Link> : null}
          <h3>原文与版本</h3><UsageSource usage={detail} />
        </div><footer><button type="button" onClick={() => toggle(detail.id)}>{selected.includes(detail.id) ? <Check size={15} /> : null}{selected.includes(detail.id) ? "从比较中移除" : "加入比较"}</button><button type="button" className={styles.primary} disabled={chosen.length !== 2} onClick={compare}>比较所选用法</button></footer></> : null}
    </Dialog>
    <Dialog open={compareOpen && chosen.length === 2} onRequestClose={closeCompare} className={`${styles.dialog} ${styles.compareDialog}`} aria-labelledby="theory-compare-title">
      <header><button type="button" onClick={closeCompare}><ArrowLeft size={16} />返回条目</button><h2 id="theory-compare-title">用法对比（2）</h2><button type="button" onClick={closeCompare}>替换用法<X size={16} /></button></header>
      <div className={styles.dialogBody}><div className={styles.compareTable} role="region" aria-label="两个用法的比较" tabIndex={0}><table><thead><tr><th scope="col">比较维度</th>{chosen.map(usage => <th scope="col" key={usage.id}>{usage.author?.portrait_url ? <MediaPlacement uses={usage.author.portrait_media?.display_uses}><img src={usage.author.portrait_url} alt="" /></MediaPlacement> : null}<strong>{usage.author?.name || "作者资料待补"}</strong>{usage.author ? <small>{years(usage.author)}</small> : null}</th>)}</tr></thead>
        <tbody>{([
          ["用法标题", (usage: TheoryConceptUsage) => label(usage)],
          ["核心含义", (usage: TheoryConceptUsage) => usage.interpretation],
          ["解释对象", (usage: TheoryConceptUsage) => usage.explanatory_object],
          ["时期与语境", (usage: TheoryConceptUsage) => [usage.period, usage.context].filter(Boolean).join(" · ")],
          ["归属说明", (usage: TheoryConceptUsage) => usage.attribution_note],
        ] as const).map(([name, value]) => <tr key={name}><th scope="row">{name}</th>{chosen.map(usage => <td key={usage.id}>{value(usage) || "尚未编写此项说明，请核对原文。"}</td>)}</tr>)}
          <tr><th scope="row">原文与版本</th>{chosen.map(usage => <td key={usage.id}><UsageSource usage={usage} /></td>)}</tr>
        </tbody></table></div><p className={styles.notice}>这里并列呈现已经公开的用法与原文，不根据段落顺序或相似词语推断作者立场。</p></div>
    </Dialog>
  </section>;
}

export function TheoryRelations({ node }: { node: KnowledgeNodeDetail }) {
  const [mode, setMode] = useState<"graph" | "list" | "evidence">("graph");
  const [selectedId, setSelectedId] = useState(node.direct_relations[0]?.id || "");
  const [group, setGroup] = useState<"related" | "distinct">("related");
  const distinct = (row: NormalizedKnowledgeRelation) => ["criticizes", "competes_with"].includes(row.relation_type);
  const rows = node.node_type === "theory_tradition" ? node.direct_relations.filter(row => distinct(row) === (group === "distinct")) : node.direct_relations;
  const selected = rows.find(row => row.id === selectedId) || rows[0];
  const target = (row: NormalizedKnowledgeRelation) => row.source_node === node.id
    ? { name: row.target_name, slug: row.target_slug } : { name: row.source_name, slug: row.source_slug };
  const title = node.node_type === "theory_tradition" ? "相关与区别的学派" : "关系与图谱";
  const graphRows = rows.slice(0, 7);
  const points = graphRows.map((row, index) => ({ row, x: 200 + Math.cos(-Math.PI / 2 + index * 2 * Math.PI / graphRows.length) * 133, y: 174 + Math.sin(-Math.PI / 2 + index * 2 * Math.PI / graphRows.length) * 123 }));
  return <section id="relations" data-module-id="theory-relations" className={styles.section} aria-labelledby="theory-relations-heading">
    <header className={styles.sectionHeading}><h2 id="theory-relations-heading">{title}</h2><Link href={`/theories/graph?center=${encodeURIComponent(node.slug)}`}>打开完整图谱<ArrowRight size={15} /></Link></header>
    {node.node_type === "theory_tradition" ? <div className={styles.segmentButtons}><button type="button" aria-pressed={group === "related"} onClick={() => setGroup("related")}>相关学派（{node.direct_relations.filter(row => !distinct(row)).length}）</button><button type="button" aria-pressed={group === "distinct"} onClick={() => setGroup("distinct")}>区别学派（{node.direct_relations.filter(distinct).length}）</button></div> : null}
    {rows.length ? <>
      <div className={styles.segmentButtons} aria-label="关系展示方式">{([["graph", "关系图谱"], ["list", "关系列表"], ["evidence", "关系依据"]] as const).map(([value, name]) => <button type="button" key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{name}</button>)}</div>
      <div className={styles.relationsLayout}>
        {mode === "graph" ? <div className={styles.graph}><svg viewBox="0 0 400 350" role="group" aria-label={`${node.canonical_name_zh}与${graphRows.length}个已公开条目的直接关系；选择节点查看依据`}>
          {points.map(({ row, x, y }) => <g key={`edge-${row.id}`}><line x1="200" y1="174" x2={x} y2={y} className={row.id === selected?.id ? styles.activeEdge : ""} /><text x={(200 + x) / 2} y={(174 + y) / 2 - 5} textAnchor="middle" className={styles.edgeLabel}>{row.relation_label}</text></g>)}
          <circle cx="200" cy="174" r="48" className={styles.graphCenter} /><text x="200" y="180" textAnchor="middle" className={styles.centerLabel}>{node.canonical_name_zh}</text>
          {points.map(({ row, x, y }) => <g key={row.id} className={`${styles.graphNode} ${row.id === selected?.id ? styles.activeNode : ""}`} role="button" tabIndex={0} aria-pressed={row.id === selected?.id} aria-label={`查看${target(row).name}的${row.relation_label}依据`} onClick={() => setSelectedId(row.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(row.id); } }}><title>{target(row).name} · {row.relation_label}</title><circle cx={x} cy={y} r="32" /><text x={x} y={y + 4} textAnchor="middle">{target(row).name.length > 8 ? `${target(row).name.slice(0, 7)}…` : target(row).name}</text></g>)}
        </svg><p className={styles.graphLegend}><i />核心条目<span />相关条目<Network size={13} />已确认关系</p>{rows.length > 7 ? <p className={styles.notice}>图中展示前 7 项；全部 {rows.length} 项可在关系列表查看。</p> : null}
        </div> : null}
        <div className={mode === "evidence" ? styles.fullWidth : styles.relationList}>
          {mode !== "evidence" ? <div className={styles.relationChoices}>{rows.map(row => <button key={row.id} type="button" aria-pressed={row.id === selected?.id} onClick={() => setSelectedId(row.id)}><span>{target(row).name}</span><small>{row.relation_label}</small><ChevronDown size={14} /></button>)}</div> : <label className={styles.relationSelect}>选择关系<select data-stl-select value={selected?.id || ""} onChange={event => setSelectedId(event.target.value)}>{rows.map(row => <option key={row.id} value={row.id}>{target(row).name} · {row.relation_label}</option>)}</select></label>}
          {selected ? <article className={styles.relationEvidence} aria-live="polite"><header><h3>{selected.source_name} {selected.direction === "undirected" ? "—" : selected.direction === "bidirectional" ? "↔" : "→"} {selected.target_name}</h3><span>{selected.relation_label}</span></header>{selected.description ? <p>{selected.description}</p> : null}
            {(selected.evidence || []).length ? selected.evidence!.map(evidence => <div key={evidence.id}><blockquote>{evidence.quote}</blockquote><p>《{evidence.work_title}》 · {evidence.printed_page_label || `PDF 第 ${evidence.page_number} 页`}</p>{evidence.reader_href ? <Link href={evidence.reader_href} target="_blank" rel="noopener noreferrer">核对这条关系的原文<ExternalLink size={14} /></Link> : null}</div>) : <p className={styles.notice}>这条关系尚无可公开定位的原文依据。关系说明与馆藏原文分开展示。</p>}
            {selected.evidence_source ? <p className={styles.notice}>关系来源说明：{selected.evidence_source}</p> : null}
            <Link href={`/theories/nodes/${target(selected).slug}`}>查看{target(selected).name}<ArrowRight size={14} /></Link>
          </article> : null}
        </div>
      </div>
    </> : <p className={styles.empty}>此分类尚无已确认并公开的关系。</p>}
  </section>;
}
