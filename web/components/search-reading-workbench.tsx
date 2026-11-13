"use client";

import Link from "next/link";
import { SearchResearchDock } from "./research/search-research-dock";
import { SourceCitationPanel } from "./source-citation-panel";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useMediaQuery } from "@/lib/use-media-query";
import { ArrowRight, BookOpen, ChevronDown, Eye, FileText, Search, X } from "lucide-react";
import type { Work } from "@/lib/data";
import type { SearchFacetOption } from "@/lib/api/search.types";
import { BookCover } from "./ui";
import { SharedCitationButton } from "./shared-citation-overlay";
import { SaveWorkButton } from "./save-work-button";
import { AssetDownloadButton } from "./asset-download-button";
import { Dialog } from "./ui/dialog";
import styles from "./search-reading-workbench.module.css";

const PreviewContext = createContext<{ work?: Work; citation?: ResolvedEvidence; mobile?: boolean | null; inspect?: (ref:ResolvedEvidence)=>void; select: (work: Work, focus?: boolean) => void }>({ select: () => {} });

export function SearchReadingWorkbench({ works, children }: { works: Work[]; children: ReactNode }) {
  const scope = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const header = document.querySelector<HTMLElement>("header.site-header"), root = scope.current;
    if (!header || !root) return;
    const update = () => root.style.setProperty("--search-header-height", `${Math.ceil(header.getBoundingClientRect().height)}px`);
    update(); const observer = new ResizeObserver(update); observer.observe(header);
    return () => observer.disconnect();
  }, []);
  const [selected, setSelected] = useState<Work>();
  const [citation,setCitation]=useState<ResolvedEvidence>();
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobile = useMediaQuery("(max-width: 1100px)");
  const work = works.find(row => row.editionId === selected?.editionId && row.workId === selected?.workId) || works[0];
  function select(next: Work, focus = false) {
    setSelected(next);setCitation(undefined);
    if (window.matchMedia("(max-width: 1100px)").matches) setMobileOpen(true);
    else if (focus) document.getElementById("search-reading-preview")?.focus();
  }
  return <PreviewContext.Provider value={{ work, select, citation, mobile, inspect:ref=>{setCitation(ref);if(window.matchMedia("(max-width: 1100px)").matches)setMobileOpen(true);} }}><div ref={scope} className={styles.scope}>{children}</div>
    <Dialog open={mobile === true && mobileOpen} onRequestClose={() => setMobileOpen(false)} aria-label="作品预览" className={styles.mobilePreview}>
      <header><h2>作品预览</h2><button aria-label="关闭作品预览" onClick={() => setMobileOpen(false)}><X size={20}/></button></header>
      {mobile === true && mobileOpen ? citation ? <SourceCitationPanel input={{reference:citation}}/> : work ? <PreviewDetails key={`${work.workId}:${work.editionId}`} work={work}/> : null : null}
    </Dialog>
  </PreviewContext.Provider>;
}

function WorkActions({ work, preview = false }: { work: Work; preview?: boolean }) {
  const { select } = useContext(PreviewContext);
  return <div className={styles.actions}>
    {work.readerHref ? <Link className={styles.read} href={work.readerHref}><BookOpen size={16}/>在线阅读</Link> : <span className={styles.unavailable}>仅书目信息</span>}
    {preview ? <button onClick={() => select(work, true)}><Eye size={16}/>预览</button> : null}
    {work.editionId ? <SharedCitationButton editionId={work.editionId}>引用</SharedCitationButton> : null}
    <SaveWorkButton workId={work.workId}/>
  </div>;
}

export function SearchReadingCard({ work }: { work: Work }) {
  const { work: selected, select } = useContext(PreviewContext);
  return <article className={styles.card} tabIndex={0} aria-label={`选择《${work.title}》预览`} aria-current={selected?.editionId === work.editionId && selected?.workId === work.workId ? "true" : undefined}
    onClick={event => { if (!(event.target as Element).closest("button,a,input,summary,select") && !window.getSelection()?.toString()) select(work); }}
    onKeyDown={event => { if (event.target === event.currentTarget && ["Enter", " "].includes(event.key)) { event.preventDefault(); select(work, true); } }}>
    <button className={styles.cover} onClick={() => select(work, true)} aria-label={`预览《${work.title}》`}><BookCover work={work} size="small"/></button>
    <div className={styles.copy}><div className={styles.meta}><span>{work.kind}</span><span>{work.year}</span></div>
      <h3><button onClick={() => select(work, true)}>{work.title}</button></h3><p className={styles.author}>{work.author}</p>
      <p className={styles.summary}>{work.summary}</p><WorkActions work={work} preview/>
    </div>
  </article>;
}

function PreviewDetails({ work }: { work: Work }) {
  const [tab, setTab] = useState("citation");
  const tabId = useId();
  const versions = work.versions || (work.version ? [work.version] : []);
  const tabs = [["citation", "引用"], ["summary", "简介"], ["versions", `出版版本${versions.length ? ` · ${versions.length}` : ""}`]];
  return <div className={styles.details} key={work.editionId}>
    {tab!=="citation"&&<><div className={styles.previewCover}><BookCover work={work} size="normal"/></div>
    <p className={styles.meta}>{work.kind} · {work.year}</p><h2>{work.title}</h2><p className={styles.author}>{work.author}</p>
    <WorkActions work={work}/></>}
    <div className={styles.tabs} role="tablist" aria-label="作品资料">{tabs.map(([value, label], index) => <button key={value} id={`${tabId}-${value}`} type="button" role="tab" aria-controls={`${tabId}-panel`} aria-selected={tab === value} tabIndex={tab === value ? 0 : -1} onClick={() => setTab(value)} onKeyDown={event => {
      const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
      if (next < 0) return;
      event.preventDefault(); setTab(tabs[next][0]);
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
    }}>{label}</button>)}</div>
    <div id={`${tabId}-panel`} role="tabpanel" aria-labelledby={`${tabId}-${tab}`} tabIndex={0}>{tab === "citation" ? <SourceCitationPanel input={{editionId:work.editionId}}/> : tab === "summary" ? <div className={styles.prose}>{work.summary.split(/\n+/).filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}</div> : <div className={styles.versions}>{versions.map(version => <div key={version.id}><p>{[version.publisher, version.publication_year, version.version_label].filter(Boolean).join(" · ")}</p>{version.readable_asset ? <div><Link href={`/reader/${version.readable_asset.id}`}>在线阅读<ArrowRight size={14}/></Link><AssetDownloadButton assetId={version.readable_asset.id}/></div> : <span>仅书目信息</span>}<SharedCitationButton editionId={version.id}>引用此版本</SharedCitationButton></div>)}</div>}</div>
    <Link className={styles.fullDetail} href={`/works/${work.slug}`}>完整作品资料<ArrowRight size={16}/></Link>
  </div>;
}

export function SearchReadingResearch({question}:{question:string}) {
  const {work,inspect}=useContext(PreviewContext);
  return <SearchResearchDock question={question} searchPhase={work?'ready':question?'empty':'idle'} filters={work?.workId?{work_ids:[work.workId]}:{}} filterAvailable={Boolean(work?.workId)} materials={[]} onInspect={inspect} filterLabel="当前所选作品"/>;
}

export function SearchReadingPreview() {
  const { work, citation, mobile } = useContext(PreviewContext);
  return <aside className={styles.preview} id="search-reading-preview" tabIndex={-1} aria-label="作品预览"><header><FileText size={16}/><span>出处与引用</span></header>
    {mobile === false ? citation ? <SourceCitationPanel input={{reference:citation}}/> : work ? <PreviewDetails key={`${work.workId}:${work.editionId}`} work={work}/> : <p className={styles.empty}>选择一部文献，查看简介与出版版本。</p> : null}
  </aside>;
}

export function SearchableFacet({ title, name, options, selected, onSelectionChange, compact = false }: { title: string; name: string; options: SearchFacetOption[]; selected: string[]; onSelectionChange?: (values: string[]) => void; compact?: boolean }) {
  const fieldset = useRef<HTMLFieldSetElement>(null);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState(selected);
  const selectionKey = JSON.stringify(selected);
  useEffect(() => {
    const reset = () => { setChosen(JSON.parse(selectionKey)); setQuery(""); };
    setChosen(JSON.parse(selectionKey));
    const form = fieldset.current?.closest("form");
    form?.addEventListener("reset", reset);
    return () => form?.removeEventListener("reset", reset);
  }, [selectionKey]);
  const rows = [...options, ...selected.filter(value => !options.some(row => row.value === value)).map(value => ({ value, label: value, count: 0 }))];
  const matches = rows.filter(row => row.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <fieldset ref={fieldset} className={styles.facet}><legend>{title}</legend><details><summary><span>{compact?`${title}${chosen.length?` · ${chosen.length}`:''}`:chosen.length ? `已选 ${chosen.length} 项` : `全部${title}`}</span><ChevronDown size={15}/></summary><div className={styles.facetMenu}>
    <label className={styles.facetSearch}><Search size={15}/><input type="search" aria-label={`搜索${title}选项`} value={query} onChange={event => setQuery(event.target.value)} placeholder={`搜索${title}`}/></label>
    <div className={styles.facetOptions}>{rows.map(option => <label key={option.value} hidden={!matches.includes(option)}><input type="checkbox" name={name} value={option.value} checked={chosen.includes(option.value)} onChange={event => { const next = event.target.checked ? [...chosen, option.value] : chosen.filter(v => v !== option.value); setChosen(next); onSelectionChange?.(next); }}/><span>{option.label}</span><small>{option.count}</small></label>)}{!matches.length ? <p>{rows.length ? "没有匹配的选项" : "当前结果没有可用选项"}</p> : null}</div>
  </div></details></fieldset>;
}
