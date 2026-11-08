"use client";
import Link from "next/link";
import type { Dispatch, SetStateAction } from "react";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";
import { siteTextConfigFields as configFields, hasAboutConfiguration } from "@/lib/site-content";
import type { SiteConfig } from "@/lib/site-config";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";
export const siteTextSections = [
  { id: "home", label: "首页馆头", description: "编辑首页标题、导语和主图，栏目布局固定。" },
  { id: "brand", label: "品牌与导航" }, { id: "about", label: "关于书库" },
  { id: "about-why", label: "建库缘起" }, { id: "about-feature-source", label: "我们收录什么" },
  { id: "about-feature-reading", label: "如何阅读与引用" }, { id: "about-feature-knowledge", label: "内容与来源" },
  { id: "about-process", label: "入库说明" }, { id: "about-open", label: "开放原则" },
  { id: "about-copyright", label: "版权说明" }, { id: "about-privacy", label: "隐私说明" },
  { id: "about-notice", label: "使用提示" }, { id: "footer", label: "页脚" },
];


export function SiteTextFields({draft,setDraft,active,busy}:{draft:SiteContentDraft;setDraft:Dispatch<SetStateAction<SiteContentDraft|null>>;active:string;busy:boolean}){
  const updateConfig = (patch: Partial<SiteConfig>) => setDraft(current => current ? { ...current, config: { ...current.config, ...patch } } : current);
  const isAbout = active.startsWith("about");
  const blockKey = active === "about" ? "about-intro" : active;
  const block = draft.about_blocks.find(row => row.key === blockKey);
  const updateBlock = (patch: Record<string, unknown>) => setDraft(current => current ? { ...current, about_blocks: current.about_blocks.map(row => row.key === blockKey ? { ...row, ...patch } : row) } : current);
  const input = (key: keyof SiteConfig, label: string, multiline = false) => <label>{label}{multiline ? <textarea rows={4} value={Array.isArray(draft.config[key]) ? (draft.config[key] as string[]).join("\n") : String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: Array.isArray(draft.config[key]) ? event.target.value.split("\n") : event.target.value })} /> : <input value={String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: event.target.value })} />}</label>;
  return <fieldset disabled={busy}>
    {active === "home" ? <>{input("home_title_left_lines", "标题第一行", true)}{input("home_title_right_lines", "标题第二行", true)}{input("intro_lines", "首页导语（每行一段）", true)}{input("home_hero_alt", "主图说明")}<InlineMediaPicker onSelect={(id, url) => updateConfig({ home_hero_rendition_id: id, home_hero_image: url })} /><button type="button" className="button secondary" onClick={() => updateConfig({ home_hero_rendition_id: null, home_hero_image: "" })}>恢复默认装饰图</button><p>首页内容在本页选择与编排，来源正文在<Link href="/admin/recommendations">特别策划</Link>管理。</p></> : null}
    {active === "brand" ? <>{input("site_name", "书库名称")}{input("wordmark_lines", "标志文字（每行一行）", true)}{Object.entries(draft.config.navigation).map(([key, value]) => <label key={key}>导航 · {({ home: "首页", explore: "书库检索", theory_schools: "理论流派", scholars: "学者", topics: "主题", search: "搜索" } as Record<string, string>)[key]}<input value={value} onChange={event => updateConfig({ navigation: { ...draft.config.navigation, [key]: event.target.value } })} /></label>)}</> : null}
    {isAbout && block ? <><label>标题<input value={block.title} onChange={event => updateBlock({ title: event.target.value })} /></label><label>正文{block.key === "about-process" ? "（用 | 分隔各步骤）" : ""}<textarea rows={9} value={block.body} onChange={event => updateBlock({ body: event.target.value })} /></label>{block.action_href || block.block_type === "feature" || block.block_type === "action" ? <><label>链接文字<input value={block.action_label} onChange={event => updateBlock({ action_label: event.target.value })} /></label><label>链接地址<input value={block.action_href} onChange={event => updateBlock({ action_href: event.target.value })} /></label></> : null}<label className="switch-row"><input type="checkbox" checked={block.visible} onChange={event => updateBlock({ visible: event.target.checked })} />发布后显示此内容</label></> : isAbout && configFields[active] ? <>{hasAboutConfiguration(draft.about_blocks) ? <><p>这个模块当前没有公开显示。</p><button type="button" className="button secondary" onClick={() => setDraft({ ...draft, about_blocks: [...draft.about_blocks, { id: "", key: blockKey, block_type: active === "about" ? "intro" : active.includes("feature") ? "feature" : active === "about-process" ? "process" : active === "about-notice" ? "notice" : "principle", title: String(draft.config[configFields[active][0]] || ""), body: String(draft.config[configFields[active][1]] || ""), icon: "", action_label: "", action_href: "", sort_order: siteTextSections.findIndex(section => section.id === active), visible: true, configuration: {} }] })}>启用并编辑本模块</button></> : null}{input(configFields[active][0], "标题")}{input(configFields[active][1], "正文", true)}</> : null}
    {active === "footer" ? <>{input("copyright_text", "页脚版权文字")}{input("about_label", "关于入口文字")}</> : null}
  </fieldset>;
}
