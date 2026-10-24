import type { AboutPageBlock } from "./api/site.types";
import type { SiteConfig } from "./site-config";

export type PublicSiteContent={configured:boolean;blocks:AboutPageBlock[]};
export const isSiteAnnouncement=(block:Pick<AboutPageBlock,"key">)=>block.key.startsWith("announcement-");
export const hasAboutConfiguration=(blocks:AboutPageBlock[])=>blocks.some(block=>!isSiteAnnouncement(block));
export const siteTextConfigFields:Record<string,[keyof SiteConfig,keyof SiteConfig]>={
  about:["about_title","about_body"],"about-why":["about_why_title","about_why_body"],
  "about-feature-source":["about_feature_search_title","about_feature_search_body"],
  "about-feature-reading":["about_feature_read_title","about_feature_read_body"],
  "about-feature-knowledge":["about_feature_knowledge_title","about_feature_knowledge_body"],
  "about-process":["about_ingestion_title","about_ingestion_body"],"about-open":["about_access_title","about_access_body"],
  "about-copyright":["about_rights_title","about_rights_body"],"about-privacy":["about_privacy_title","about_privacy_body"],
  "about-notice":["about_warning_title","about_warning_body"],
};

export function publicSiteText(config:SiteConfig,about:PublicSiteContent|null|undefined,key:string){
  if(!about)return null;
  const block=about.blocks.find(row=>row.key===(key==="about"?"about-intro":key));
  if(block)return block.visible?block:null;
  if(about.configured||!siteTextConfigFields[key])return null;
  const fields=siteTextConfigFields[key];
  return {title:String(config[fields[0]]||""),body:String(config[fields[1]]||""),action_label:"",action_href:""};
}
