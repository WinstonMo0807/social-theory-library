"use client";
import { SourceText } from "@/components/source-text";


import { BookOpen, FileText, Heading, Image, Lightbulb, Link, Quote, Route, Scale, Text, UserRound, Waypoints } from "lucide-react";
import type { IssueBlock, IssueResolvedSource } from "@/lib/api/recommendation-issues.types";
import { EditorialImage } from "@/components/public/editorial-directory";
import { safeEditorialLink } from "@/components/public/issue-prose";
import styles from "./issue-editor.module.css";

const icons = {paragraph:Text,heading:Heading,quote:Quote,link:Link,image:Image,evidence:BookOpen,span:BookOpen,work:BookOpen,edition:BookOpen,person:UserRound,concept:Lightbulb,node:Lightbulb,timeline:Waypoints,reading_path:Route,analysis:FileText,comparison:Scale};
export function IssueSourceThumbnail({kind,src="",className=""}:{kind:IssueBlock["type"]|IssueResolvedSource["type"];src?:string;className?:string}) {
  const Icon=icons[kind];
  return <span className={`${styles.sourceThumbnail} ${className}`} aria-hidden="true">{src?<EditorialImage key={src} src={src} portrait={kind==="person"}/>:<Icon size={22} strokeWidth={1.3}/>}</span>;
}

export function IssueSourceSummary({source}:{source:IssueResolvedSource}) {
  const book=["span","work","edition"].includes(source.type);
  const version=[source.edition_label,source.publisher,source.publication_year].filter(Boolean).map(String);
  const href=[source.reader_url,source.work_url,source.href].find(value=>value&&safeEditorialLink(value));
  return <section className={styles.sourceSummary} aria-label={`来源信息：${source.title}`}>
    {source.image_url?<IssueSourceThumbnail kind={source.type} src={source.image_url} className={styles.sourceCover}/>:null}
    <dl className={styles.sourceMetadata}>
      <div><dt>{book?"所引作品":"所引资料"}</dt><dd>{source.title}</dd></div>
      {book?<><div><dt>作者</dt><dd>{source.authors?.length?source.authors.join("、"):"当前来源未注明"}</dd></div><div><dt>准确版本</dt><dd>{[...new Set(version)].join(" · ")||"版本信息未注明"}</dd></div></>:null}
      {source.page_start?<><div><dt>PDF 页码</dt><dd>第 {source.page_start} 页</dd></div><div><dt>印刷页码</dt><dd>{source.printed_label||"尚未标注"}</dd></div></>:null}
      {source.section?<div><dt>引用位置</dt><dd>{source.section}</dd></div>:null}
      {source.summary&&!book?<div><dt>资料说明</dt><dd>{source.summary}</dd></div>:null}
    </dl>
    {source.text?<div className={styles.sourceExcerpt}><span>原文</span><blockquote><SourceText text={(source.text) || ""} /></blockquote></div>:null}
    <div className={styles.sourceActions}>{href?<a href={href} target="_blank" rel="noopener noreferrer"><BookOpen size={14}/>{source.reader_url===href?"查看原文":"查看资料"} ↗</a>:source.edit_url?.startsWith("/admin/")?<a href={source.edit_url} target="_blank" rel="noopener">查看处理状态 ↗</a>:null}</div>
  </section>;
}
