
import { SourceText } from "@/components/source-text";
import { DefaultCover } from "@/components/default-cover";
import Link from "next/link";
import { IssueProse } from "./issue-prose";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { PlacementState, PlacementGroup, PlacementSource } from "@/lib/api/curation-workspace.client";
import styles from "./placement-list.module.css";

export const placementAuthors = (source: PlacementSource | null) => Array.isArray(source?.authors) ? source.authors.map((row: Record<string, unknown>) => String(row.name || row.preferred_name || "")).filter(Boolean).join("、") : "";
export const placementType = (value: unknown) => ({book:"图书",journal_article:"期刊论文",journal_issue:"整期期刊",thesis:"学位论文",report:"研究报告"})[String(value) as "book"] || "";
export const placementGroupKey = (group: PlacementGroup) => JSON.stringify([group.area, group.name]);
export function placementGroups(items: PlacementState["items"], groups: PlacementGroup[] = []) {
  const output = [...groups];
  for (const row of items) if (!output.some(group => group.area === (row.area || "main") && group.name === (row.group || ""))) output.push({area:row.area || "main",name:row.group || ""});
  return output;
}
export function PlacementList({items,groups,selected,onSelect}:{items:PlacementState["items"];groups?:PlacementGroup[];selected?:string;onSelect?:(id:string)=>void}) {
  const available = items.filter(row => row.source?.public_eligible && !row.concept_usage);
  return <div className={styles.page}>{placementGroups(available,groups).map(group => {
    const rows = available.filter(row => (row.area || "main") === group.area && (row.group || "") === group.name);
    if (!rows.length) return null;
    return <section key={placementGroupKey(group)} className={styles.group}><h2>{group.name || "延伸阅读"}</h2><div className={styles.list}>{rows.map(row => {
      const source = row.source!, fields = row.display_fields || ["authors","year","type","tags"], href = String(source.work_url || source.href || source.reader_url || ""), cover = normalizePublicResourceUrl(String(source.image_url || ""));
      const content = <><div className={styles.cover}>{cover ? <img src={cover} alt="" loading="lazy"/> : <DefaultCover title={source.title} author={placementAuthors(source)} />}</div><div><h3>{onSelect?<button type="button" className={styles.select} onClick={()=>onSelect(row.id)}>{source.title}</button>:source.title}</h3>{fields.includes("authors") && placementAuthors(source) ? <p>{placementAuthors(source)}</p>:null}<small>{[fields.includes("year") ? source.publication_year : "",fields.includes("type") ? placementType(source.document_type) : ""].filter(Boolean).join(" · ")}</small>{row.reason ? <div className={styles.reason}><IssueProse block={{type:"paragraph",text:row.reason,...row.reason_format}}/></div>:null}{row.local_text ? <p>{row.local_text}</p>:null}{source.type === "span" && source.text ? <blockquote><SourceText text={(source.text) || ""} /></blockquote>:null}{fields.includes("tags") && Array.isArray(source.tags) ? <small>{source.tags.join(" · ")}</small>:null}</div></>;
      return <article key={row.id} className={styles.item} data-selected={selected === row.id}>{content}{!onSelect ? <>{href ? <Link href={href} className={styles.detail}>查看来源</Link>:null}{source.reader_url ? <Link href={source.reader_url}>阅读原文</Link>:null}</>:null}</article>;
    })}</div></section>;
  })}</div>;
}
