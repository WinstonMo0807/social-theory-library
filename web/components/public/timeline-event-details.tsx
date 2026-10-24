"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { MediaPlacement } from "@/components/media-placement";
import { ArrowRight, BookOpen, FileText } from "lucide-react";
import { CollectionLink } from "@/components/collection-link";
import { AssetDownloadButton } from "@/components/asset-download-button";
import { timelineDate, timelineHref, timelineTypeLabels, type TimelineEventDetail, type TimelineFilters } from "@/lib/api/timeline.types";
import styles from "./theory-timeline.module.css";

const tabs = ["事件详情", "相关事件", "引用与影响", "原文片段"];
const precisionLabels = { month:"月份已确认", day:"日期已确认", unknown: "时间不确定", year: "年份已确认", approximate: "约年", range: "时间区间" };
const sourceLabels = {
  available: "已有可阅读的原文来源",
  unavailable: "原文来源当前不可用",
  citation_only: "仅有来源说明，尚无可定位的原文",
  missing: "来源未明，尚无可核验的原文",
};

export function TimelineEventDetails({ event, actionPath = "/theories/timeline", filters = {}, standalone = false }: {
  event: TimelineEventDetail; actionPath?: string; filters?: TimelineFilters; standalone?: boolean;
}) {
  const [tab, setTab] = useState(0);
  const id = useId();
  const subject = event.subject_edition;
  const source = event.evidence_source;
  const subjectMessage = event.subject_status === "unavailable" ? "事件版本当前不可用" : "未明确事件的出版版本";
  const feedbackHref = `/feedback?${new URLSearchParams({ category: "content", path: `/theories/events/${event.id}` })}`;
  const cover = subject?.cover_url || event.image_url;
  const Heading = standalone ? "h1" : "h2";
  return <section className={`${styles.detail} ${standalone ? styles.standalone : ""}`} aria-label="所选事件详情">
    <header className={styles.detailHeader}>
      <div className={styles.cover}>{cover ? <img src={cover} alt="" /> : <FileText size={34} strokeWidth={1} aria-hidden="true" />}</div>
      <div className={styles.detailIdentity}>
        <p className={styles.detailDate}>{timelineDate(event)}</p>
        <Heading>{event.title}</Heading>
        {subject ? <p>{subject.author || "作者资料未详"}{subject.version_label ? ` · ${subject.version_label}` : ""}</p> : event.scholars.length ? <p>{event.scholars.map(row => row.name).join("、")}</p> : null}
        <div className={styles.badges}><span>{timelineTypeLabels[event.event_type] || event.event_type}</span><span>{precisionLabels[event.date_precision]}</span></div>
        <div className={styles.subjectActions}>
          {subject?.reader_href ? <CollectionLink href={subject.reader_href}><BookOpen size={14} aria-hidden="true" />阅读作品</CollectionLink> : <span className={styles.unavailable}>{subject ? "作品原文当前不可用" : subjectMessage}</span>}
          {subject?.detail_href ? <Link href={subject.detail_href}>查看书目信息<ArrowRight size={13} aria-hidden="true" /></Link> : event.subject_work?.detail_href ? <Link href={event.subject_work.detail_href}>查看作品信息<ArrowRight size={13} aria-hidden="true" /></Link> : null}
        </div>
        {subject?.asset_id ? <div className={styles.downloadActions} role="group" aria-label="事件版本下载"><AssetDownloadButton assetId={subject.asset_id} /></div> : null}
      </div>
    </header>
    <div className={styles.tabs} role="tablist" aria-label="事件内容">
      {tabs.map((label, index) => <button key={label} type="button" role="tab" id={`${id}-tab-${index}`} aria-controls={`${id}-panel-${index}`} aria-selected={tab === index} tabIndex={tab === index ? 0 : -1} onClick={() => setTab(index)} onKeyDown={e => {
        let next = index;
        if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (e.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
        else if (e.key === "Home") next = 0;
        else if (e.key === "End") next = tabs.length - 1;
        else return;
        e.preventDefault(); setTab(next);
        e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
      }}>{label}</button>)}
    </div>
    {tabs.map((label, index) => <div key={label} id={`${id}-panel-${index}`} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} tabIndex={0} hidden={tab !== index} className={styles.tabPanel}>
      {index === 0 ? <>
        <h3>事件信息</h3>
        <dl className={styles.facts}>
          <dt>时间</dt><dd>{timelineDate(event)}<small>{precisionLabels[event.date_precision]}{event.start_year !== null && event.end_year !== null && event.start_year !== event.end_year ? ` · ${event.start_year}—${event.end_year} 年` : ""}</small></dd>
          <dt>类型</dt><dd>{timelineTypeLabels[event.event_type] || event.event_type}</dd>
          <dt>事件版本</dt><dd>{subject ? `${subject.title}${subject.version_label ? ` · ${subject.version_label}` : ""}` : subjectMessage}</dd>
          <dt>来源状态</dt><dd>{sourceLabels[event.source_status]}</dd>
        </dl>
        <h3>事件介绍</h3>
        {event.description ? <div className={styles.description}><p>{event.description}</p></div> : <p className={styles.muted}>尚无公开的事件介绍。</p>}
        <details className={styles.moreInfo}><summary>展开更多事件资料</summary>
          {event.scholars.length ? <><h3>相关学者</h3><div className={styles.people}>{event.scholars.map(person => <Link href={person.href} key={person.id}>{person.portrait_url ? <MediaPlacement uses={person.portrait_media?.display_uses}><img src={person.portrait_url} alt="" /></MediaPlacement> : null}<span>{person.name}</span></Link>)}</div></> : null}
          {event.topics.length ? <><h3>相关主题</h3><div className={styles.chips}>{event.topics.map(topic => <Link href={topic.href} key={topic.id}>{topic.name}</Link>)}</div></> : null}
          {event.relations.length ? <><h3>涉及对象</h3><ul className={styles.objectList}>{event.relations.map((row, rowIndex) => <li key={`${row.type}-${row.id}-${rowIndex}`}>{row.href ? <Link href={row.href}>{row.name}<ArrowRight size={12} aria-hidden="true" /></Link> : <span>{row.name}</span>}{row.description ? <p>{row.description}</p> : null}</li>)}</ul></> : <p className={styles.muted}>没有可公开的关联对象。</p>}
          {event.source ? <><h3>来源说明</h3><p>{event.source}</p></> : null}
        </details>
        {!standalone ? <Link className={styles.textLink} href={`/theories/events/${event.id}`}>查看事件完整页面<ArrowRight size={13} aria-hidden="true" /></Link> : null}
      </> : index === 1 ? <>
        <h3>相关事件 <small>{event.related_count}</small></h3>
        <p className={styles.muted}>按共同关联的公开作品、学者或理论对象整理，不据此判定引用或影响。</p>
        {event.related_events.length ? <ul className={styles.relatedList}>{event.related_events.map(row => <li key={row.id}><Link href={timelineHref("/theories/timeline", {}, { focus: row.id })}><time>{timelineDate(row)}</time><strong>{row.title}</strong><ArrowRight size={14} aria-hidden="true" /></Link></li>)}</ul> : <p className={styles.emptySmall}>暂无已公开的相关事件。</p>}
        {event.related_count > event.related_events.length ? <Link className={styles.textLink} href={timelineHref("/theories/timeline", {}, { related_to: event.id })}>查看全部 {event.related_count} 个相关事件<ArrowRight size={13} aria-hidden="true" /></Link> : null}
      </> : index === 2 ? <>
        <h3>已确认的引用与影响关系</h3>
        <p className={styles.muted}>仅列出本事件明确关联的理论对象之间已发布的关系；关系依据与事件出处分别核验。</p>
        {event.knowledge_relations.length ? <>
          <p className={styles.rangeNote}>展示 {event.knowledge_relations.length} / {event.knowledge_relation_count} 条正式关系</p>
          <ul className={styles.influences}>{event.knowledge_relations.map(relation => <li key={relation.id}>
            <div><Link href={`/theories/nodes/${relation.source_slug}`}>{relation.source_name}</Link><span>{relation.direction === "undirected" ? "—" : "→"} {relation.relation_label} {relation.direction === "undirected" ? "—" : "→"}</span><Link href={`/theories/nodes/${relation.target_slug}`}>{relation.target_name}</Link></div>
            {relation.description ? <p>{relation.description}</p> : null}
            {relation.evidence_source ? <p className={styles.muted}>{relation.evidence_source}</p> : null}
            {relation.evidence?.length ? relation.evidence.map(evidence => <blockquote key={evidence.id}><p>{evidence.quote}</p>{evidence.reader_href ? <CollectionLink href={evidence.reader_href}>{evidence.work_title} · {evidence.printed_page_label || `PDF 第 ${evidence.page_number} 页`}</CollectionLink> : <span>关系原文当前不可用</span>}</blockquote>) : <p className={styles.muted}>这条关系尚无可阅读的原文片段。</p>}
            <Link className={styles.textLink} href={`/theories/nodes/${relation.source_slug}/relations`}>查看该理论对象的关系</Link>
          </li>)}</ul>
        </> : <p className={styles.emptySmall}>暂无已确认的引用与影响关系。</p>}
      </> : <>
        <h3>原文来源</h3>
        {source ? <>
          <p className={styles.sourceIdentity}>{source.title}{source.edition_label ? ` · ${source.edition_label}` : ""}</p>
          <p className={styles.muted}>{source.printed_page_label ? `印刷页 ${source.printed_page_label} · ` : ""}PDF 第 {source.pdf_page} 页</p>
          {subject && source.edition_id !== subject.edition_id ? <p className={styles.sourceNotice}>此处引用来自独立的证据版本，与事件版本分别对应。</p> : null}
          {source.quote ? <blockquote className={styles.sourceQuote}>{source.quote}</blockquote> : <p className={styles.muted}>该来源未公开摘录，请在原文中核对。</p>}
          <CollectionLink className={styles.sourceButton} href={source.reader_href}>打开来源原文<BookOpen size={15} aria-hidden="true" /></CollectionLink>
          <div className={styles.downloadActions} role="group" aria-label="证据版本下载"><AssetDownloadButton assetId={source.asset_id} /></div>
        </> : <p className={styles.emptySmall}>{sourceLabels[event.source_status]}。</p>}
        {event.source ? <p className={styles.muted}>来源说明：{event.source}</p> : null}
        <Link className={styles.textLink} href={feedbackHref}>{source ? "反馈来源问题" : "提交来源线索"}<ArrowRight size={13} aria-hidden="true" /></Link>
      </>}
    </div>)}
    {standalone ? <Link className={styles.textLink} href={timelineHref(actionPath, filters, { focus: event.id, year: null, page: null })}>在时间线中查看此事件<ArrowRight size={14} aria-hidden="true" /></Link> : null}
  </section>;
}
