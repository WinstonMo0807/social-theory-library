import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { SiteConfig } from "@/lib/site-config";
import { isSiteAnnouncement, publicSiteText, type PublicSiteContent } from "@/lib/site-content";

export function siteContentHref(value:string){
  if(!value||/[\\\u0000-\u001f\u007f]/.test(value)||value.startsWith("//"))return "";
  try{return ["http:","https:","mailto:"].includes(new URL(value,"https://site.invalid").protocol)?value:"";}catch{return "";}
}
export function SiteCopyLink({label,href}:{label:string;href:string}){
  const safe=siteContentHref(href);
  return safe&&label?<Link href={safe}>{label} <ArrowRight size={15}/></Link>:null;
}
export function SiteAnnouncements({about}:{about:PublicSiteContent|null|undefined}){
  const rows=about?.blocks.filter(row=>isSiteAnnouncement(row)&&row.visible).sort((a,b)=>a.sort_order-b.sort_order||a.key.localeCompare(b.key))||[];
  return <section className="stl4-support-section"><h2>公告与更新</h2>{!about?<p className="stl4-support-status" role="alert">已发布公告暂时无法读取，请稍后重新打开本页。</p>:!rows.length?<p className="stl4-support-lead">目前没有已发布公告。</p>:rows.map(row=><article className="stl4-support-update" key={row.key} id={row.key}><time dateTime={String(row.configuration.published_date||"")}>{String(row.configuration.published_date||"未署期")}</time><div><h3>{row.title}</h3><p style={{whiteSpace:"pre-line"}}>{row.body}</p><SiteCopyLink label={row.action_label} href={row.action_href}/></div></article>)}</section>;
}
export function SitePublicExplanations({config,about}:{config:SiteConfig;about:PublicSiteContent|null|undefined}){
  const keys=["about-why","about-process","about-open","about-copyright","about-privacy","about-notice"];
  const rows=keys.flatMap(key=>{const copy=publicSiteText(config,about,key);return copy?[{key,...copy}]:[];});
  return <section className="stl4-support-section"><h2>内容与公共说明</h2>{!about?<p className="stl4-support-status" role="alert">已发布说明暂时无法读取，请稍后重试。</p>:!rows.length?<p>目前没有已公开的说明模块。</p>:<div className="stl4-support-explanation-grid">{rows.map(row=><article key={row.key} id={row.key}><h3>{row.title}</h3><p style={{whiteSpace:"pre-line"}}>{row.body}</p><SiteCopyLink label={row.action_label} href={row.action_href}/></article>)}</div>}</section>;
}
