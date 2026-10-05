"use client";

import { ArrowDown, ArrowUp, Check, RefreshCw, Search } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { normalizePublicResourceUrl } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import type { RecommendationItem, RecommendationPlacement } from "@/lib/api/recommendations.types";
import { PreviewViewport } from "@/components/admin/curation/fixed-page-editor";
import { HomePublicView, type HomeViewData } from "@/components/public/home-public-view";
import { SiteHeader } from "@/components/site-header";
import { adaptApiScholar, adaptApiTopic, adaptRecommendationWork } from "@/lib/public-data-adapters";
import type { ApiScholar } from "@/lib/api/people.types";
import type { ApiTopic } from "@/lib/api/topics.types";
import type { ApiWork } from "@/lib/api/public-catalog";

type TargetType = "work" | "topic" | "scholar";
type Candidate = { id: string; slug?: string; title?: string; name?: string; preferred_name?: string; description?: string; short_description?: string; hero_image?: string; portrait?: string; cover?: string; cover_image?: string; public_eligible?: boolean; person?: {preferred_name: string; portrait?: string} };
type Preview = { placement: string; source: string; preview_token: string; expected_updated_at: string; expected_snapshot_id: string | null; items: Array<{ id: string; name: string; target_type: string; target: ApiWork | ApiTopic | ApiScholar | null }> };

const tabs: Array<{ placement: string; label: string; target: TargetType; description: string }> = [
  { placement: "home_scholars", label: "学者聚焦", target: "scholar", description: "首页展示的学者顺序" },
  { placement: "home_topics", label: "精选主题", target: "topic", description: "首页展示的主题顺序" },
  { placement: "home_random", label: "随机馆藏", target: "work", description: "读者随机看到的公开馆藏" },
];

function targetEndpoint(target: TargetType) {
  return target === "scholar" ? "/catalog/admin/scholars/" : target === "topic" ? "/catalog/admin/topics/" : "/catalog/works/";
}

function labelOf(candidate: Candidate) { return candidate.title || candidate.name || candidate.preferred_name || candidate.person?.preferred_name || "未命名内容"; }
function linkedLabel(target: RecommendationItem["target"]): string {
  if ("title" in target && target.title) return String(target.title);
  if ("name" in target && target.name) return String(target.name);
  if ("preferred_name" in target && target.preferred_name) return String(target.preferred_name);
  return String(target.id);
}
function imageOf(candidate: Candidate, target: TargetType) { return normalizePublicResourceUrl(target === "scholar" ? candidate.portrait || candidate.person?.portrait || "" : target === "topic" ? candidate.hero_image || "" : candidate.cover || candidate.cover_image || ""); }

export function RecommendationHomeCuration({ initialPlacement = "home_scholars", home }: { initialPlacement?: string; home: HomeViewData }) {
  const router = useRouter();
  const credential = getServerSessionCredential();
  const policies = useApiResource<RecommendationPlacement[]>("/catalog/admin/recommendations/", credential);
  const [placement, setPlacement] = useState(() => tabs.some(tab => tab.placement === initialPlacement) ? initialPlacement : "home_scholars");
  const [searchDraft, setSearchDraft] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedByPolicy, setSelectedByPolicy] = useState<Record<string, string[]>>({});
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [images, setImages] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"draft" | "live">("draft");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [replacing, setReplacing] = useState<string | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const enlarged = useRef<HTMLDialogElement>(null);
  const busyRef = useRef(false);
  const retryRequest = useRef<{ signature: string; body: Record<string, unknown> } | null>(null);
  const tab = tabs.find(item => item.placement === placement) || tabs[0];
  const policy = policies.data?.find(item => item.placement === placement) || null;
  const currentIds = policy?.current?.items.filter(item => placement !== "home_scholars" || policy.current?.source !== "manual" || item.reason === "管理员策展").map(item => item.target.id) || [];
  const selected = selectedByPolicy[policy?.id || ""] ?? currentIds;
  const selectedSet = new Set(selected);
  const candidateQuery = new URLSearchParams({ editorial_status: "published", page: String(page) });
  if (query) candidateQuery.set("search", query);
  const candidateResource = useApiResource<{ count: number; next: string | null; previous: string | null; results: Candidate[] }>(`${targetEndpoint(tab.target)}?${candidateQuery.toString()}`, credential, `${placement}:${page}:${query}`);
  const candidateById = new Map<string, Candidate>((candidateResource.data?.results || []).map(candidate => [candidate.id, candidate]));
  const currentById = new Map((policy?.current?.items || []).map(item => [item.target.id, item.target]));

  function updateSelected(updater: (value: string[]) => string[]) {
    if (!policy || busyRef.current) return;
    setPreview(null); retryRequest.current = null; setMessage("");
    setSelectedByPolicy(value => ({ ...value, [policy.id]: updater(value[policy.id] ?? currentIds) }));
  }
  function selectPlacement(value: string) {
    if (busyRef.current) return;
    setPlacement(value); setPage(1); setQuery(""); setSearchDraft(""); setPreview(null); setMessage(""); setReplacing(null); retryRequest.current = null;
  }
  function submitSearch(event: FormEvent) { event.preventDefault(); setPage(1); setQuery(searchDraft.trim()); }
  function move(index: number, offset: -1 | 1) {
    updateSelected(value => { const target = index + offset; if (target < 0 || target >= value.length) return value; const next = [...value]; [next[index], next[target]] = [next[target], next[index]]; return next; });
  }
  function selectedLabel(id: string): string { return String(labels[id] || (candidateById.get(id) ? labelOf(candidateById.get(id)!) : null) || (currentById.get(id) ? linkedLabel(currentById.get(id)!) : null) || id); }
  function selectedImage(id: string) { return images[id] || imageOf(candidateById.get(id) || currentById.get(id) as Candidate || { id }, tab.target); }
  function toggle(candidate: Candidate) {
    const id = candidate.id; const checked = selectedSet.has(id);
    setLabels(value => ({ ...value, [id]: labelOf(candidate) })); setImages(value => ({ ...value, [id]: imageOf(candidate, tab.target) }));
    if (replacing) {
      if (checked && id !== replacing) return;
      updateSelected(value => value.map(item => item === replacing ? id : item)); setReplacing(null); return;
    }
    updateSelected(value => checked ? value.filter(item => item !== id) : value.length < (policy?.item_count || 4) ? [...value, id] : value);
  }
  async function previewSelection() {
    if (!policy || busyRef.current) return;
    busyRef.current = true; setBusy(true); setMessage(""); setPreview(null);
    try {
      const result = await apiRequest<Preview>(`/catalog/admin/recommendations/${placement}/preview/`, { method: "POST", body: JSON.stringify({ items: selected.map(id => ({ target_type: tab.target, id })) }) }, credential);
      setPreview(result);
      setMode("draft");
      setMessage("已生成预览，读者页面尚未改变。请核对名单和顺序后确认发布。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "预览未能生成，当前推荐未改变。"); }
    finally { busyRef.current = false; setBusy(false); }
  }
  async function publish() {
    if (!policy || !preview || busyRef.current || preview.expected_updated_at !== policy.updated_at) return;
    if (!window.confirm("确认发布当前预览的首页推荐？确认后读者页面才会更新。")) return;
    busyRef.current = true; setBusy(true); setMessage("");
    const items = preview.items.map(({ target_type, id }) => ({ target_type, id }));
    const signature = JSON.stringify({ placement, items, token: preview.preview_token });
    if (retryRequest.current?.signature !== signature) retryRequest.current = { signature, body: { confirm: true, request_key: createRequestKey(), expected_snapshot_id: preview.expected_snapshot_id, expected_updated_at: preview.expected_updated_at, preview_token: preview.preview_token, items } };
    try {
      const result = await apiRequest<RecommendationPlacement & { publication_effective: boolean }>(`/catalog/admin/recommendations/${placement}/refresh/`, { method: "POST", body: JSON.stringify(retryRequest.current.body) }, credential);
      retryRequest.current = null; setPreview(null); setSelectedByPolicy(value => { const next = { ...value }; delete next[policy.id]; return next; }); setMessage(result.publication_effective ? "首页推荐已发布，读者现在可以看到。" : "命令已接受，但推荐状态已有变化，请重新读取后核对。"); policies.retry(); router.refresh();
    } catch (error) {
      if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) { retryRequest.current = null; setPreview(null); policies.retry(); }
      setMessage(error instanceof Error ? error.message : "暂时未能确认发布结果；可重试同一操作。");
    } finally { busyRef.current = false; setBusy(false); }
  }
  const displayItems = selected.map(id => ({ id, label: selectedLabel(id), image: selectedImage(id) }));
  const previewHome = {...home};
  if (preview) {
    if (placement === "home_scholars") previewHome.scholars = preview.items.flatMap(item=>item.target && item.target_type === "scholar" ? [adaptApiScholar(item.target as ApiScholar)] : []);
    if (placement === "home_topics") previewHome.topics = preview.items.flatMap(item=>item.target && item.target_type === "topic" ? [adaptApiTopic(item.target as ApiTopic)] : []);
    if (placement === "home_random") previewHome.randomWorks = preview.items.flatMap(item=>item.target && item.target_type === "work" ? [adaptRecommendationWork(item.target as ApiWork)] : []);
  }
  const draftPreview = preview ? <div className="recommendation-home-document" data-preview-placement={placement}><SiteHeader config={home.config} preview previewPath="/"/><div className="page-shell"><HomePublicView {...previewHome}/></div></div> : <p className="empty-state">点击“预览名单”，查看当前选择与自动补足后的完整首页。</p>;
  return <div className="recommendation-curation-v2">
    <header className="recommendation-v2-heading"><div><p className="eyebrow">网站内容 · 首页推荐</p><h1>首页推荐 · 学者、主题与随机</h1><p>保留首页的学者聚焦、精选主题和随机馆藏，先选择与排序，再预览确认。</p></div><span className="recommendation-v2-state">当前：第 {preview ? 3 : 2} / 3 步</span></header>
    <div className="recommendation-v2-steps" aria-label="首页推荐步骤"><span className="done"><Check size={15}/>1 选择展示位置</span><span className={preview ? "done" : "active"}>2 选择与排序</span><span className={preview ? "active" : ""}>3 预览确认</span></div>
    {policies.error || candidateResource.error ? <p className="recommendation-v2-alert" role="alert">{policies.error || candidateResource.error}<button type="button" onClick={() => { policies.retry(); candidateResource.retry(); }}>重新读取</button></p> : null}
    <div className="recommendation-v2-grid">
      <section className="recommendation-v2-control">
        <nav className="recommendation-v2-tabs" aria-label="选择首页展示位置">{tabs.map(item => <button type="button" key={item.placement} disabled={busy} className={item.placement === placement ? "active" : ""} onClick={() => selectPlacement(item.placement)}>{item.label}</button>)}</nav>
        <h2>选择内容并调整顺序</h2><p className="recommendation-v2-help">首页将展示 {policy?.item_count || 4} 项。手动选择的内容优先，不足时按已设置的候选规则补足。</p>
        <div className="recommendation-v2-selected">{displayItems.map((item, index) => <article key={item.id}><span className="recommendation-v2-order">{index + 1}</span>{item.image ? <img src={item.image} alt="" /> : <span className="recommendation-v2-image-empty" /> }<div><strong>{item.label}</strong><small>{tab.description}</small></div><div className="recommendation-v2-row-actions"><button type="button" aria-label={`上移${item.label}`} disabled={busy || index === 0} onClick={() => move(index, -1)}><ArrowUp size={14}/></button><button type="button" aria-label={`下移${item.label}`} disabled={busy || index === displayItems.length - 1} onClick={() => move(index, 1)}><ArrowDown size={14}/></button><button type="button" aria-label={`替换${item.label}`} disabled={busy} onClick={() => { setReplacing(item.id); searchInput.current?.focus(); }}>替换</button></div></article>)}{!displayItems.length ? <p className="recommendation-v2-empty">尚未选择内容。</p> : null}</div>
        <form id="recommendation-candidate-search" className="recommendation-v2-search" onSubmit={submitSearch}><label><Search size={16}/><input ref={searchInput} type="search" aria-label="搜索推荐候选" value={searchDraft} onChange={event => setSearchDraft(event.target.value)} placeholder={tab.target === "scholar" ? "搜索公开学者" : tab.target === "topic" ? "搜索公开主题" : "搜索公开馆藏"} /></label><button type="submit">查找</button></form>
        {replacing ? <p className="recommendation-v2-help">选择一项替换“{selectedLabel(replacing)}” <button type="button" onClick={() => setReplacing(null)}>取消替换</button></p> : null}
        {candidateResource.loading ? <p role="status">正在读取公开候选…</p> : null}<div className="recommendation-v2-candidates">{(candidateResource.data?.results || []).map(candidate => { const checked = selectedSet.has(candidate.id); return <label key={candidate.id} className={checked ? "selected" : ""}><input type="checkbox" checked={checked} disabled={busy || Boolean(replacing && checked && candidate.id !== replacing) || (!replacing && !checked && selected.length >= (policy?.item_count || 4))} onChange={() => toggle(candidate)} /><span>{labelOf(candidate)}</span>{checked ? <Check size={14}/> : null}</label>; })}</div>
        <nav className="recommendation-v2-pagination" aria-label="首页推荐候选分页"><button type="button" disabled={!candidateResource.data?.previous || page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}>上一页</button><span>第 {page} 页 · 共 {candidateResource.data?.count ?? 0} 项</span><button type="button" disabled={!candidateResource.data?.next} onClick={() => setPage(value => value + 1)}>下一页</button></nav>
        <div className="recommendation-v2-rule"><strong>自动补足规则（简要）</strong><p>手动选择的内容优先；不足时按已设置的候选规则补足。先预览名单，再确认展示。</p></div>
        <footer className="recommendation-v2-actions"><button type="button" className="button secondary" disabled={busy || !policy} onClick={() => void previewSelection()}><RefreshCw size={15}/>预览名单</button><button type="button" className="button" disabled={busy || !preview || preview.expected_updated_at !== policy?.updated_at} onClick={() => void publish()}>保存选择并确认发布 →</button></footer>
      </section>
      <section className="recommendation-v2-reader"><header><div><h2>读者会看到什么</h2><p>首页推荐 · {mode === "draft" ? "当前选择" : "当前线上"}</p></div><div className="recommendation-v2-view-tools"><button type="button" className={mode === "draft" ? "active" : ""} aria-pressed={mode === "draft"} onClick={() => setMode("draft")}>修改后</button><button type="button" className={mode === "live" ? "active" : ""} aria-pressed={mode === "live"} onClick={() => setMode("live")}>当前线上</button><button type="button" className={device === "desktop" ? "active" : ""} aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>电脑</button><button type="button" className={device === "mobile" ? "active" : ""} aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>手机</button><button type="button" onClick={() => enlarged.current?.showModal()}>放大查看</button></div></header><PreviewViewport device={device}>{mode === "live" ? <iframe title="当前公开首页" src="/" className="recommendation-live-frame" /> : draftPreview}</PreviewViewport><p className="recommendation-v2-preview-note">{mode === "live" ? "当前公开页面" : preview ? "完整预览名单已生成 · 读者页面尚未改变" : "当前输入 · 尚未生成发布预览"}</p></section>
      <dialog ref={enlarged} className="recommendation-preview-dialog"><header><strong>{mode === "live" ? "当前线上" : "当前选择的首页推荐"}</strong><button type="button" onClick={() => enlarged.current?.close()}>关闭</button></header><PreviewViewport device={device}>{mode === "live" ? <iframe title="当前公开首页放大预览" src="/" className="recommendation-live-frame" /> : draftPreview}</PreviewViewport></dialog>
    </div>
    {message ? <p className="recommendation-v2-message" role="status">{message}</p> : null}
  </div>;
}
