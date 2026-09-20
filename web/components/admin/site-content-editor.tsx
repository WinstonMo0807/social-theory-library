"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential, ApiRequestError } from "@/lib/api";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import { SiteHeader } from "@/components/site-header";
import { SiteFooterView } from "@/components/public/site-footer-view";
import { useActionGuard } from "@/lib/use-action-guard";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";
import type { SiteStats } from "@/lib/api/site.types";
import type { SiteConfig } from "@/lib/site-config";
import { HomePublicView, type HomeViewData } from "@/components/public/home-public-view";
import { AboutPublicView } from "@/components/public/about-public-view";
import { FixedPageEditor } from "@/components/admin/curation/fixed-page-editor";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";

const sections = [
  { id: "home", label: "首页馆头", description: "编辑首页标题、导语和主图，栏目布局固定。" },
  { id: "brand", label: "品牌与导航" }, { id: "about", label: "关于书库" },
  { id: "about-why", label: "建库缘起" }, { id: "about-feature-source", label: "寻找原始出处" },
  { id: "about-feature-reading", label: "阅读与整理" }, { id: "about-feature-knowledge", label: "知识关系" },
  { id: "about-process", label: "入库说明" }, { id: "about-open", label: "开放原则" },
  { id: "about-copyright", label: "版权说明" }, { id: "about-privacy", label: "隐私说明" },
  { id: "about-notice", label: "使用提示" }, { id: "footer", label: "页脚" },
];
const configFields: Record<string, [keyof SiteConfig, keyof SiteConfig]> = {
  about: ["about_title", "about_body"], "about-why": ["about_why_title", "about_why_body"],
  "about-feature-source": ["about_feature_search_title", "about_feature_search_body"],
  "about-feature-reading": ["about_feature_read_title", "about_feature_read_body"],
  "about-feature-knowledge": ["about_feature_knowledge_title", "about_feature_knowledge_body"],
  "about-process": ["about_ingestion_title", "about_ingestion_body"], "about-open": ["about_access_title", "about_access_body"],
  "about-copyright": ["about_rights_title", "about_rights_body"], "about-privacy": ["about_privacy_title", "about_privacy_body"],
  "about-notice": ["about_warning_title", "about_warning_body"],
};

export function SiteContentEditor({ home, stats, fullPreview = false }: { home: HomeViewData; stats: SiteStats; fullPreview?: boolean }) {
  const [draft, setDraft] = useState<SiteContentDraft | null>(null), [saved, setSaved] = useState<SiteContentDraft | null>(null);
  const [active, setActive] = useState("home"), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [conflict, setConflict] = useState(false);
  const [initialError, setInitialError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const dirty = useUnsavedForm(draft, saved);
  const user = useAdminSession();
  const { startAction, finishAction } = useActionGuard();
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    apiRequest<SiteContentDraft>(`/catalog/admin/site-content/${fullPreview ? "preview/" : ""}`, { signal: controller.signal }, getServerSessionCredential())
      .then(data => { if (alive) { setDraft(data); setSaved(data); setInitialError(""); } })
      .catch(error => { if (alive) setInitialError(controller.signal.aborted ? "读取网站内容超时，请重试。" : error instanceof Error ? error.message : "网站内容读取失败。"); })
      .finally(() => window.clearTimeout(timeout));
    return () => { alive = false; window.clearTimeout(timeout); controller.abort(); };
  }, [fullPreview, loadAttempt]);
  async function persist(publish = false) {
    if (!draft || busy || (publish && dirty) || !startAction("persist")) return;
    setBusy(true); setMessage("");
    try { const data = await apiRequest<SiteContentDraft>(`/catalog/admin/site-content/${publish ? "publish/" : ""}`, { method: publish ? "POST" : "PUT", body: JSON.stringify(publish ? { edit_version: draft.edit_version, confirm: true } : draft) }, getServerSessionCredential()); setDraft(data); setSaved(data); setConflict(false); setMessage(publish ? "已发布网站内容。" : "已保存网站草稿，原公开页面保持不变。"); }
    catch (error) { setConflict(error instanceof ApiRequestError && error.status === 409); setMessage(`${error instanceof Error ? error.message : "保存失败"} 当前输入已保留。`); }
    finally { setBusy(false); finishAction("persist"); }
  }
  if (!draft) return <section className="admin-panel" aria-busy={!initialError}><p role={initialError ? "alert" : "status"}>{initialError || "正在读取网站内容…"}</p>{initialError ? <button type="button" className="button secondary" onClick={() => { if (!draft) { setInitialError(""); setLoadAttempt(value => value + 1); } }}>重试读取</button> : null}</section>;
  const updateConfig = (patch: Partial<SiteConfig>) => setDraft(current => current ? { ...current, config: { ...current.config, ...patch } } : current);
  const isAbout = active.startsWith("about");
  const blockKey = active === "about" ? "about-intro" : active;
  const block = draft.about_blocks.find(row => row.key === blockKey);
  const updateBlock = (patch: Record<string, unknown>) => setDraft(current => current ? { ...current, about_blocks: current.about_blocks.map(row => row.key === blockKey ? { ...row, ...patch } : row) } : current);
  const input = (key: keyof SiteConfig, label: string, multiline = false) => <label>{label}{multiline ? <textarea rows={4} value={Array.isArray(draft.config[key]) ? (draft.config[key] as string[]).join("\n") : String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: Array.isArray(draft.config[key]) ? event.target.value.split("\n") : event.target.value })} /> : <input value={String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: event.target.value })} />}</label>;
  const pagePreview = isAbout ? <AboutPublicView config={draft.config} stats={stats} about={{ configured: draft.about_blocks.length > 0, blocks: draft.about_blocks.filter(block => block.visible) }} /> : <HomePublicView {...home} config={draft.config} />;
  const preview = <><SiteHeader config={draft.config} preview />{pagePreview}<SiteFooterView config={draft.config} preview /></>;
  if (fullPreview) return <div className="v307-site-full-preview"><p className="private-preview-label">已保存草稿预览 · 仅后台可见</p><nav className="v307-admin-tabs"><button onClick={() => setActive("home")}>首页</button><button onClick={() => setActive("about")}>关于书库</button></nav>{preview}</div>;
  return <div className="v307-admin-editor"><header className="v307-editor-heading"><div><p className="eyebrow">Website content</p><h1>网站与关于书库</h1></div><div><button className="button secondary" onClick={() => persist()} disabled={busy || !dirty}>保存草稿</button>{hasAdminCapability(user, "can_publish_authority") ? <button className="button" onClick={() => persist(true)} disabled={busy || dirty || !draft.has_unpublished_changes}>确认发布</button> : null}</div></header>{message ? <p role="status" className="v307-save-status">{message}</p> : null}{conflict ? <DraftConflict endpoint="/catalog/admin/site-content/" local={draft} onUseRemote={remote => { setDraft(remote); setSaved(remote); setConflict(false); }} onKeepLocal={remote => { setSaved(remote); setDraft({ ...draft, edit_version: remote.edit_version }); setConflict(false); }} /> : null}<FixedPageEditor sections={sections} activeSection={active} onSectionChange={setActive} dirty={dirty} previewHref="/admin/about/preview" preview={preview} fields={<fieldset disabled={busy}>
    {active === "home" ? <>{input("home_title_left_lines", "标题第一行", true)}{input("home_title_right_lines", "标题第二行", true)}{input("intro_lines", "首页导语（每行一段）", true)}{input("home_hero_alt", "主图说明")}<InlineMediaPicker onSelect={(id, url) => updateConfig({ home_hero_rendition_id: id, home_hero_image: url })} /><button type="button" className="button secondary" onClick={() => updateConfig({ home_hero_rendition_id: null, home_hero_image: "" })}>恢复默认装饰图</button><p>本期文章与精选内容在<Link href="/admin/recommendations">推荐与随机</Link>管理。这里不改变栏目顺序。</p></> : null}
    {active === "brand" ? <>{input("site_name", "书库名称")}{input("wordmark_lines", "标志文字（每行一行）", true)}{Object.entries(draft.config.navigation).map(([key, value]) => <label key={key}>导航 · {({ home: "首页", explore: "探索", theory_schools: "理论流派", scholars: "学者", topics: "主题", search: "搜索" } as Record<string, string>)[key]}<input value={value} onChange={event => updateConfig({ navigation: { ...draft.config.navigation, [key]: event.target.value } })} /></label>)}</> : null}
    {isAbout && block ? <><label>标题<input value={block.title} onChange={event => updateBlock({ title: event.target.value })} /></label><label>正文{block.key === "about-process" ? "（用 | 分隔各步骤）" : ""}<textarea rows={9} value={block.body} onChange={event => updateBlock({ body: event.target.value })} /></label>{block.action_href || block.block_type === "feature" || block.block_type === "action" ? <><label>链接文字<input value={block.action_label} onChange={event => updateBlock({ action_label: event.target.value })} /></label><label>链接地址<input value={block.action_href} onChange={event => updateBlock({ action_href: event.target.value })} /></label></> : null}<label className="switch-row"><input type="checkbox" checked={block.visible} onChange={event => updateBlock({ visible: event.target.checked })} />发布后显示此内容</label></> : isAbout && configFields[active] ? <>{draft.about_blocks.length ? <><p>这个模块当前没有公开显示。</p><button type="button" className="button secondary" onClick={() => setDraft({ ...draft, about_blocks: [...draft.about_blocks, { id: "", key: blockKey, block_type: active === "about" ? "intro" : active.includes("feature") ? "feature" : active === "about-process" ? "process" : active === "about-notice" ? "notice" : "principle", title: String(draft.config[configFields[active][0]] || ""), body: String(draft.config[configFields[active][1]] || ""), icon: "", action_label: "", action_href: "", sort_order: sections.findIndex(section => section.id === active), visible: true, configuration: {} }] })}>启用并编辑本模块</button></> : null}{input(configFields[active][0], "标题")}{input(configFields[active][1], "正文", true)}</> : null}
    {active === "footer" ? <>{input("copyright_text", "页脚版权文字")}{input("about_label", "关于入口文字")}</> : null}
  </fieldset>} /></div>;
}
