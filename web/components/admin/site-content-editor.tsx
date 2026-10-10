"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Bold, Italic, Link2, List, ListOrdered, Quote, Info } from "lucide-react";
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
import { FixedPageEditor, PreviewViewport } from "@/components/admin/curation/fixed-page-editor";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";

const sections = [
  { id: "home", label: "顶部介绍", description: "出现在首页最上方，通常包含主标题、两行导语和一张配图。" },
  { id: "brand", label: "页眉内容设置", description: "这些内容将显示在网站顶部导航栏。" },
  { id: "about", label: "关于书库" }, { id: "about-why", label: "建库缘起" },
  { id: "about-feature-source", label: "原始出处" }, { id: "about-feature-reading", label: "阅读整理" },
  { id: "about-feature-knowledge", label: "知识关系" }, { id: "about-process", label: "入库说明" },
  { id: "about-open", label: "开放原则", description: "这部分内容将展示我们如何向公众开放资源与知识。" },
  { id: "about-copyright", label: "版权与隐私" }, { id: "about-privacy", label: "隐私说明" },
  { id: "about-notice", label: "使用提示" }, { id: "footer", label: "页脚" },
];
const chapters = ["about-why", "about-feature-source", "about-feature-reading", "about-open", "about-copyright"];
const navigation = [
  { key: "home", label: "首页", path: "/" }, { key: "explore", label: "探索", path: "/explore" },
  { key: "theory_schools", label: "理论流派", path: "/theories" },
  { key: "scholars", label: "学者", path: "/scholars" }, { key: "topics", label: "主题", path: "/topics" },
] as const;
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
  const requestedSection = useSearchParams().get("section") || "home";
  const [draft, setDraft] = useState<SiteContentDraft | null>(null), [saved, setSaved] = useState<SiteContentDraft | null>(null);
  const [active, setActive] = useState(() => sections.some(row => row.id === requestedSection) ? requestedSection : "home");
  const [step, setStep] = useState(requestedSection === "brand" ? 1 : 0);
  const [selectedNav, setSelectedNav] = useState<(typeof navigation)[number]["key"]>("theory_schools");
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [conflict, setConflict] = useState(false);
  const [initialError, setInitialError] = useState(""), [loadAttempt, setLoadAttempt] = useState(0);
  const [mediaOpen, setMediaOpen] = useState(false);
  const lastSection = useRef(requestedSection);
  const dirty = useUnsavedForm(draft, saved);
  const user = useAdminSession();
  const { startAction, finishAction } = useActionGuard();
  useEffect(() => {
    if (lastSection.current === requestedSection || !sections.some(row => row.id === requestedSection)) return;
    lastSection.current = requestedSection;
    const timer = window.setTimeout(() => { setActive(requestedSection); setStep(requestedSection === "brand" ? 1 : 0); }, 0);
    return () => window.clearTimeout(timer);
  }, [requestedSection]);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    apiRequest<SiteContentDraft>(`/catalog/admin/site-content/${fullPreview ? "preview/" : ""}`, { signal: controller.signal }, getServerSessionCredential())
      .then(data => { if (alive) { setDraft(current => current ?? data); setSaved(data); setInitialError(""); } })
      .catch(error => { if (alive) setInitialError(controller.signal.aborted ? "读取网站内容超时，请重试。" : error instanceof Error ? error.message : "网站内容读取失败。"); })
      .finally(() => window.clearTimeout(timeout));
    return () => { alive = false; window.clearTimeout(timeout); controller.abort(); };
  }, [fullPreview, loadAttempt]);
  async function persist(publish = false) {
    if (!draft || busy || (publish && (dirty || !draft.has_unpublished_changes)) || !startAction("persist")) return;
    const submitted = draft;
    setBusy(true); setMessage("");
    try {
      const data = await apiRequest<SiteContentDraft>(`/catalog/admin/site-content/${publish ? "publish/" : ""}`, {
        method: publish ? "POST" : "PUT", body: JSON.stringify(publish ? { edit_version: submitted.edit_version, confirm: true } : submitted),
      }, getServerSessionCredential());
      setDraft(current => current === submitted ? data : current ? { ...current, edit_version: data.edit_version, has_unpublished_changes: data.has_unpublished_changes } : data);
      setSaved(data); setConflict(false);
      setMessage(publish ? "已发布网站内容。" : "已保存网站草稿，原公开页面保持不变。");
    } catch (error) {
      setConflict(error instanceof ApiRequestError && error.status === 409);
      setMessage(`${error instanceof Error ? error.message : "保存失败"} 当前输入已保留。`);
    } finally { setBusy(false); finishAction("persist"); }
  }
  if (!draft) return <section className="admin-panel" aria-busy={!initialError}><p role={initialError ? "alert" : "status"}>{initialError || "正在读取网站内容…"}</p>{initialError ? <button type="button" className="button secondary" onClick={() => { setInitialError(""); setLoadAttempt(value => value + 1); }}>重试读取</button> : null}</section>;
  const updateConfig = (patch: Partial<SiteConfig>) => setDraft(current => current ? { ...current, config: { ...current.config, ...patch } } : current);
  const isAbout = active.startsWith("about"), isBrand = active === "brand";
  const blockKey = active === "about" ? "about-intro" : active;
  const block = draft.about_blocks.find(row => row.key === blockKey);
  const updateBlock = (patch: Record<string, unknown>) => setDraft(current => current ? { ...current, about_blocks: current.about_blocks.map(row => row.key === blockKey ? { ...row, ...patch } : row) } : current);
  const currentSection = sections.find(row => row.id === active)!;
  const currentChapterTitle = block?.title ?? (configFields[active] ? String(draft.config[configFields[active][0]]) : currentSection.label);
  const titleField = configFields[active]?.[0], bodyField = configFields[active]?.[1];
  const chapterBody = block?.body ?? (bodyField ? String(draft.config[bodyField] || "") : "");
  const input = (key: keyof SiteConfig, label: string, multiline = false) => <label>{label}{multiline ? <textarea rows={3} data-preview-field={key} value={Array.isArray(draft.config[key]) ? (draft.config[key] as string[]).join("\n") : String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: Array.isArray(draft.config[key]) ? event.target.value.split("\n") : event.target.value })} /> : <input data-preview-field={key} value={String(draft.config[key] || "")} onChange={event => updateConfig({ [key]: event.target.value })} />}</label>;
  const changeSection = (id: string, field?: string) => { setActive(id); if (field || id !== active) setStep(id === "brand" && field !== "wordmark_lines" ? 1 : 0); };
  const headerPath = isAbout ? "/about" : "/";
  const pagePreview = isAbout
    ? <AboutPublicView config={draft.config} stats={stats} activeSection={active} about={{ configured: draft.about_blocks.length > 0, blocks: draft.about_blocks.filter(row => row.visible) }} />
    : <HomePublicView {...home} config={draft.config} />;
  const preview = <div className="site-content-public-preview" data-selected-navigation={isBrand ? selectedNav : undefined}><SiteHeader config={draft.config} preview previewPath={headerPath} editablePreview />{pagePreview}<SiteFooterView config={draft.config} preview /></div>;
  if (fullPreview) return <div className="v307-site-full-preview"><p className="private-preview-label">已保存草稿预览 · 仅后台可见</p><nav className="v307-admin-tabs"><button onClick={() => setActive("home")}>首页</button><button onClick={() => setActive("about")}>关于书库</button></nav>{preview}</div>;
  const stepLabels = isBrand ? ["基本信息", "导航与页眉", "预览与发布"] : ["编辑内容", "预览检查", "完成发布"];
  const stepDescriptions = isBrand ? ["", "", ""] : ["主标题 · 导语 · 配图", "在不同设备查看效果", "保存并上线"];
  const saveButton = <button type="button" className="button secondary" onClick={() => persist()} disabled={busy || !dirty}>{busy ? "正在保存…" : "保存草稿"}</button>;
  const publishButton = hasAdminCapability(user, "can_publish_authority") ? <button type="button" className="button" onClick={() => persist(true)} disabled={busy || dirty || !draft.has_unpublished_changes}>确认发布</button> : null;
  const footer = <footer className="site-editor-actions">{!isAbout ? <button type="button" className="button secondary" disabled={busy || step === 0} onClick={() => setStep(value => Math.max(0, value - 1))}>上一步</button> : null}{saveButton}{isAbout ? <button type="button" className="button" onClick={() => setStep(value => value === 0 ? 1 : 0)}>{step ? "返回编辑" : "查看发布预览"}</button> : step < 2 ? <button type="button" className="button" onClick={() => setStep(value => value + 1)}>下一步：{stepLabels[step + 1]} <ArrowRight size={16}/></button> : publishButton}</footer>;
  const chapterNavigation = chapters.includes(active) ? chapters : [...chapters, active];
  const fields = <fieldset disabled={busy}>
    {step === 2 || (isAbout && step === 1) ? <div className="site-publish-check"><h3>{isAbout ? "核对页面内容" : "核对发布内容"}</h3><dl><div><dt>页面</dt><dd>{isAbout ? `关于书库 · ${currentChapterTitle}` : isBrand ? "品牌与导航" : currentSection.label}</dd></div><div><dt>当前状态</dt><dd>{dirty ? "当前输入尚未保存" : draft.has_unpublished_changes ? "已保存草稿，等待发布" : "当前没有待发布的修改"}</dd></div></dl><p>保存后核对右侧预览，再确认发布。公开页面在确认发布前保持原内容。</p>{isAbout ? publishButton : null}</div> : <>
      {active === "home" ? <>
        <label>主标题 <span className="site-required">*</span><input maxLength={50} data-preview-field="home_title_left_lines" value={draft.config.home_title_left_lines.join("")} onChange={event => updateConfig({ home_title_left_lines: event.target.value.split("\n") })}/><small>{draft.config.home_title_left_lines.join("").length} / 50</small></label>
        {[0, 1].map(index => <label key={index}>{index ? "第二行导语" : "第一行导语"} <span className="site-required">*</span><input maxLength={50} data-preview-field={`intro-${index}`} value={draft.config.intro_lines[index] || ""} onChange={event => { const lines = [...draft.config.intro_lines]; lines[index] = event.target.value; updateConfig({ intro_lines: lines }); }}/><small>{(draft.config.intro_lines[index] || "").length} / 50</small></label>)}
        <section className="site-hero-picker"><h3>配图</h3><div>{draft.config.home_hero_image ? <img src={draft.config.home_hero_image} alt={draft.config.home_hero_alt || "首页配图"}/> : <div className="site-image-empty" aria-label="尚未设置首页配图"/>}<div><button type="button" className="button secondary" data-preview-field="home_hero_image" onClick={() => setMediaOpen(value => !value)}>{draft.config.home_hero_image ? "更换图片" : "选择图片"}</button><p>支持 JPG、PNG 格式<br/>建议尺寸：1200 × 800 像素</p><button type="button" className="site-remove-image" disabled={!draft.config.home_hero_image} onClick={() => updateConfig({ home_hero_rendition_id: null, home_hero_image: "" })}>删除图片</button></div></div>{mediaOpen ? <InlineMediaPicker onSelect={(id, url, alt) => { updateConfig({ home_hero_rendition_id: id, home_hero_image: url, home_hero_alt: alt || "" }); setMediaOpen(false); }}/> : null}</section>
      </> : null}
      {isBrand ? <>{step === 0 ? <>{input("site_name", "书库名称")}{input("wordmark_lines", "标识文字（每行一行）", true)}</> : <>
        {input("site_name", "书库名称")}<p className="site-field-note">标识文字在上一步的基本信息中设置。</p>
        <section className="site-navigation-fields"><h3>导航栏目</h3>{navigation.map((row, index) => <label key={row.key} data-selected={selectedNav === row.key}><span>{index + 1}</span><input type="radio" name="site-navigation-selection" aria-label={`定位导航 · ${row.label}`} checked={selectedNav === row.key} onChange={() => setSelectedNav(row.key)}/><input aria-label={`导航 · ${row.label}`} data-preview-field={row.key} value={draft.config.navigation[row.key]} onFocus={() => setSelectedNav(row.key)} onChange={event => updateConfig({ navigation: { ...draft.config.navigation, [row.key]: event.target.value } })}/></label>)}</section>
        <label>搜索框提示文字<input value="" disabled aria-describedby="site-search-contract"/><small id="site-search-contract">—</small></label>
      </>}</> : null}
      {isAbout ? <>
        <label>章节标题<input maxLength={50} data-preview-field="title" value={currentChapterTitle} onChange={event => block ? updateBlock({ title: event.target.value }) : titleField ? updateConfig({ [titleField]: event.target.value }) : undefined}/><small>{currentChapterTitle.length} / 50</small></label>
        <div className="site-chapter-body"><label htmlFor="site-chapter-body">正文内容</label><div className="site-chapter-toolbar" role="group" aria-label="正文格式"><button type="button" disabled>正文⌄</button>{[[Bold, "粗体"], [Italic, "斜体"], [List, "无序列表"], [ListOrdered, "有序列表"], [Quote, "引用"], [Link2, "链接"]].map(([Icon, label]) => { const Control = Icon as typeof Bold; return <button key={String(label)} type="button" disabled aria-label={String(label)} title="当前正文保存为纯文本"><Control size={16}/></button>; })}</div><textarea maxLength={2000} id="site-chapter-body" data-preview-field="body" value={chapterBody} onChange={event => block ? updateBlock({ body: event.target.value }) : bodyField ? updateConfig({ [bodyField]: event.target.value }) : undefined}/><small>{chapterBody.length} / 2000</small></div>
        {!block && draft.about_blocks.length ? <p className="site-block-state">这个模块当前没有公开显示。<button type="button" className="button secondary" onClick={() => setDraft(current => current ? { ...current, about_blocks: [...current.about_blocks, { id: "", key: blockKey, block_type: active === "about" ? "intro" : active.includes("feature") ? "feature" : active === "about-process" ? "process" : active === "about-notice" ? "notice" : "principle", title: currentChapterTitle, body: chapterBody, icon: "", action_label: "", action_href: "", sort_order: sections.findIndex(row => row.id === active), visible: true, configuration: {} }] } : current)}>启用本章节</button></p> : null}
        {block ? <label className="site-chapter-visible"><input type="checkbox" checked={block.visible} onChange={event => updateBlock({ visible: event.target.checked })}/>发布后显示此内容</label> : null}
        {block && (block.action_href || block.block_type === "feature" || block.block_type === "action") ? <details className="site-chapter-link"><summary>章节链接</summary><label>链接文字<input value={block.action_label} onChange={event => updateBlock({ action_label: event.target.value })}/></label><label>链接地址<input value={block.action_href} onChange={event => updateBlock({ action_href: event.target.value })}/></label></details> : null}
        <aside className="site-edit-tip"><strong><Info size={13}/>编辑提示</strong><p>这部分内容将显示在「关于书库」页面的对应章节，建议用清晰、平实的语言，向读者传达我们的开放理念。</p></aside>
      </> : null}
      {active === "footer" ? <>{input("copyright_text", "页脚版权文字")}{input("about_label", "关于入口文字")}</> : null}
    </>}
  </fieldset>;
  const modules = <section className="site-other-modules"><h3>其他首页模块 <small>（跳转到对应管理页面）</small></h3>{[
    { label: "推荐文章", note: "管理首页展示的每日荐读文章", href: "/admin/recommendations/issues", image: home.issue?.cover_url },
    { label: "学者入口", note: "管理首页的学者卡片与展示方式", href: "/admin/recommendations?placement=home_scholars", image: home.scholars[0]?.portrait },
    { label: "主题入口", note: "管理首页的主题分组与图标", href: "/admin/recommendations?placement=home_topics", image: home.topics[0]?.heroImage },
  ].map(row => <Link href={row.href} key={row.label}>{row.image ? <img src={row.image} alt=""/> : <span className="site-module-image-empty"/>}<span><strong>{row.label}</strong><small>{row.note}</small></span><span>去编辑 <ArrowRight size={14}/></span></Link>)}</section>;
  return <div className={`v307-admin-editor site-reference-editor site-reference-${isAbout ? "about" : isBrand ? "brand" : active === "home" ? "home" : "footer"} site-reference-step-${step + 1}`}>
    <header className="v307-editor-heading"><div><h1>{isAbout ? "编辑页面内容" : isBrand ? "编辑页眉文字" : active === "home" ? "编辑首页：顶部介绍" : "编辑页脚"}</h1><p>{isAbout ? "完善关于书库的公开介绍，让更多读者了解我们的理念与方式。" : isBrand ? "设置书库名称、标识与导航。修改后将显示在网站所有页面的顶部。" : "修改页面最上方的主标题、导语与配图，向读者呈现书库的核心理念。"}</p></div>{!isAbout ? <div className="site-editor-progress"><p>当前：第 {step + 1} / 3 步</p><nav aria-label="网站内容编辑步骤">{stepLabels.map((label, index) => <button type="button" key={label} aria-current={step === index ? "step" : undefined} data-complete={index < step} onClick={() => setStep(index)}><b>{index < step ? "✓" : index + 1}</b><span>{label}<small>{stepDescriptions[index]}</small></span></button>)}</nav></div> : null}</header>
    {message ? <p role="status" className="v307-save-status">{message}</p> : null}
    {conflict ? <DraftConflict endpoint="/catalog/admin/site-content/" local={draft} onUseRemote={remote => { setDraft(remote); setSaved(remote); setConflict(false); }} onKeepLocal={remote => { setSaved(remote); setDraft(current => current ? { ...current, edit_version: remote.edit_version } : remote); setConflict(false); }}/> : null}
    <FixedPageEditor sections={sections} navigationSections={isAbout ? sections.filter(row => chapterNavigation.includes(row.id)) : []} activeSection={active} onSectionChange={changeSection} dirty={dirty} previewDescription={isAbout ? undefined : isBrand ? "这是网站的实际显示效果，修改将应用到全站页面。" : "此为网站首页的实际效果预览。"} previewHref={`/admin/about/preview?section=${active}`} publishedHref={isAbout ? "/about" : "/"} preview={preview} fields={fields} fieldHeading={isAbout ? `编辑：${currentChapterTitle}` : undefined} fieldHeader={isAbout ? <header className="site-chapter-heading"><h2>编辑：{currentChapterTitle}</h2><p>{currentSection.description}</p></header> : undefined} hideFieldHeading={isAbout} toolbar={active === "home" ? <>{step === 0 ? modules : null}{footer}</> : isAbout ? footer : undefined} previewToolbar={<div className="site-preview-location"><span>页面位置：{isAbout ? `关于书库 › ${currentChapterTitle}` : "首页（主页面）"}</span>{isAbout ? <a href="/about" target="_blank" rel="noopener">在网站中查看 ↗</a> : null}</div>} previewFooter={isBrand ? <section className="site-mobile-header-preview"><div><h3>手机端页眉预览</h3><p>在手机上的显示效果。</p></div><div className="site-phone-frame"><span aria-hidden="true">9:41</span><PreviewViewport device="mobile"><div className="site-mobile-header-content" inert><SiteHeader config={draft.config} preview previewPath={headerPath}/></div></PreviewViewport></div><aside><strong>{dirty ? "当前输入 · 尚未保存" : "已保存内容预览"}</strong><p>左侧为修改后的预览效果。请确认导航文字与选中状态是否符合预期。</p></aside></section> : undefined}/>
    {!isAbout && active !== "home" ? footer : null}
  </div>;
}
