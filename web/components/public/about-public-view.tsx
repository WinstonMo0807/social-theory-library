"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import type { AboutPageBlock, SiteStats } from "@/lib/api/site.types";
import type { SiteConfig } from "@/lib/site-config";

export function AboutPublicView({ config, stats, about, activeSection }: { config: SiteConfig; stats: SiteStats; about: { configured: boolean; blocks: AboutPageBlock[] }; activeSection?: string }) {
  const [selected,setSelected]=useState("about-why");
  const byKey=new Map(about.blocks.map(block=>[block.key,block]));
  const content=(key:string,title:string,body:string)=>{const block=byKey.get(key);return block ? {key,title:block.title,body:block.body} : about.configured ? null : {key,title,body};};
  const chapters=[content("about-why",config.about_why_title,config.about_why_body),content("about-feature-source",config.about_feature_search_title,config.about_feature_search_body),content("about-feature-reading",config.about_feature_read_title,config.about_feature_read_body),content("about-open",config.about_access_title,config.about_access_body),content("about-copyright",config.about_rights_title,config.about_rights_body),content("about-privacy",config.about_privacy_title,config.about_privacy_body)].filter((row):row is NonNullable<typeof row>=>Boolean(row));
  const requested=activeSection || selected;
  const current=chapters.find(row=>row.key===requested) || chapters[0];
  const next=current ? chapters[chapters.indexOf(current)+1] : null;
  const intro=content("about-intro",config.about_title,config.about_body);
  return <div className="page-shell about-reference-page"><header className="about-reference-hero" data-edit-section="about"><div>{intro ? <><h1>{intro.title}</h1><p>{intro.body}</p></> : null}</div><span aria-hidden="true"/></header><div className="about-reference-body"><nav aria-label="关于书库章节">{chapters.map(row=><button type="button" key={row.key} aria-current={current?.key===row.key ? "true" : undefined} data-edit-section={row.key} onClick={()=>setSelected(row.key)}>{row.title}</button>)}</nav><div>{current ? <article data-edit-section={current.key}><h2>{current.title}</h2>{current.body.split(/\n\s*\n/).map((paragraph,index)=><p key={index}>{paragraph}</p>)}</article> : <p>—</p>}{next ? <button type="button" className="about-reference-next" data-edit-section={next.key} onClick={()=>setSelected(next.key)}><small>下一节</small><strong>{next.title}</strong><ArrowRight size={18}/></button> : null}</div></div><footer><Link href="/explore">进入书库</Link><span>{stats.version}</span></footer></div>;
}
