"use client";
import type { Dispatch, SetStateAction } from "react";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";
import type { AboutPageBlock } from "@/lib/api/site.types";

export function SiteAnnouncementFields({draft,setDraft,active,busy}:{draft:SiteContentDraft;setDraft:Dispatch<SetStateAction<SiteContentDraft|null>>;active:string;busy:boolean}){
  const block=draft.about_blocks.find(row=>row.key===active);
  if(!block)return <p>这条公告已不在当前草稿中，请从左侧重新选择。</p>;
  const update=(patch:Partial<AboutPageBlock>)=>setDraft(current=>current?{...current,about_blocks:current.about_blocks.map(row=>row.key===active?{...row,...patch}:row)}:current);
  return <fieldset disabled={busy}><label>公告标题<input maxLength={240} value={block.title} onChange={event=>update({title:event.target.value})}/></label><label>公告日期<input type="date" value={String(block.configuration.published_date||"")} onChange={event=>update({configuration:{published_date:event.target.value}})}/></label><p>日期用于公告署期。确认网站发布后即可显示，不会按未来日期自动排期。</p><label>公告正文<textarea rows={9} maxLength={30000} value={block.body} onChange={event=>update({body:event.target.value})}/></label><label>相关链接文字（可选）<input maxLength={120} value={block.action_label} onChange={event=>update({action_label:event.target.value})}/></label><label>相关链接（可选）<input maxLength={400} value={block.action_href} onChange={event=>update({action_href:event.target.value})}/></label><label className="switch-row"><input type="checkbox" checked={block.visible} onChange={event=>update({visible:event.target.checked})}/>发布后在帮助页显示</label><p>关闭显示后保存并发布，公告会从公开列表收起，已保存的内容和历史记录仍保留。</p></fieldset>;
}
