import type { IssueBlock, IssueResolvedSource } from "@/lib/api/recommendation-issues.types";
import { CollectionLink } from "@/components/collection-link";
import { SharedCitationButton } from "@/components/shared-citation-overlay";

function SourceLink({ source }: { source: IssueResolvedSource }) {
  const href = source.reader_url || source.work_url || "";
  if (!/^\/(reader|works)\//.test(href) || /[\\\u0000-\u001f]/.test(href)) return <span>{source.title}</span>;
  return <CollectionLink href={href}>{source.title}{source.printed_label ? ` · 第 ${source.printed_label} 页` : source.page_start ? ` · PDF ${source.page_start}` : ""}</CollectionLink>;
}

/** The same published-source payload renders in the editor preview and public article. */
export function IssueBlockView({ block }: { block: IssueBlock }) {
  if (block.source_status === "unavailable") return <p>本段来源当前不可访问，原文与定位暂不展示。</p>;
  const sources = block.resolved_sources || [];
  if (block.type === "heading" || (block.type === "analysis" && block.style === "heading")) return <h3>{block.text}</h3>;
  if (block.type === "quote") return <blockquote><p>{block.text}</p><cite>{block.source}</cite></blockquote>;
  if (block.type === "link") return <p><a href={block.url} rel="noopener noreferrer">{block.text}</a></p>;
  if (block.type === "evidence") {
    const source = sources[0];
    return <div>{source?.text ? <blockquote><p>{source.text}</p><cite><SourceLink source={source} /></cite>{source.type === "span" ? <SharedCitationButton reference={{ evidence_span_id: source.id }} selectedText={source.text} /> : null}</blockquote> : <p>原文尚未核实。</p>}{block.text ? <p>{block.text}</p> : null}</div>;
  }
  if (block.type === "comparison") return <div>{block.text ? <p>{block.text}</p> : null}<table><caption>不同作者的论述与原文依据</caption><thead><tr><th scope="col">作者</th>{block.dimensions?.map(dimension => <th scope="col" key={dimension}>{dimension}</th>)}</tr></thead><tbody>{block.rows?.map(row => <tr key={row.person_id}><th scope="row">{sources.find(source => source.type === "person" && source.id === row.person_id)?.title || "作者身份待核对"}</th>{block.dimensions?.map(dimension => {
    const cell = row.cells.find(candidate => candidate.dimension === dimension);
    const references = cell?.evidence.map(reference => sources.find(source => source.type === reference.type && source.id === reference.id)).filter((source): source is IssueResolvedSource => Boolean(source)) || [];
    return <td key={dimension}><p>{cell?.text}</p>{references.map(source => <p key={source.id}><SourceLink source={source} /></p>)}{!references.length ? <small>此维度尚缺原文依据。</small> : null}</td>;
  })}</tr>)}</tbody></table></div>;
  if (!sources.length) return <p>{block.text}</p>;
  return <div><p>{block.text}</p><p>{block.type === "analysis" ? "策划说明所依据的材料：" : "关联馆藏："}{sources.map((source, index) => <span key={`${source.type}:${source.id}:${index}`}>{index ? "、" : ""}<SourceLink source={source} /></span>)}</p></div>;
}
