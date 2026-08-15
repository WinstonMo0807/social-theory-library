"use client";

import { AlertCircle, BookOpen, CheckCircle2, ExternalLink, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiBlob, apiRequest, getStoredAccessToken } from "@/lib/api";
import { ItemPublicationControl, type PublicationPreflight } from "./item-publication-control";

type ImpactItem = { label: string; href: string };

type PublicationItem = {
  id: string;
  source_filename: string;
  status: string;
  updated_at: string;
  publication_preflight: PublicationPreflight;
  can_manage_publication: boolean;
  review_data: null | {
    edition_id: string;
    title: string;
    document_type: string;
    language: string;
    publication_state: string;
    ocr_status: string;
    semantic_index_status: string;
    page_label_status: string;
    review_status: string;
    review_progress: number;
    reader_rendition_policy: "auto" | "original" | "ocr";
    publication_year: number | null;
    publisher: string;
    publication_place: string;
    authors: string[];
    public_slug: string | null;
    page_count: number;
    release_impact: {
      work: ImpactItem;
      scholars: ImpactItem[];
      disciplines: ImpactItem[];
      theories: ImpactItem[];
      subdisciplines: ImpactItem[];
      topics: ImpactItem[];
      search: ImpactItem;
    };
  };
};

type Paginated<T> = { count: number; results: T[] };
type PublicationFilter = "attention" | "all" | "published" | "withdrawn";

const stateLabels: Record<string, string> = {
  draft: "草稿",
  ready: "待发布",
  published: "已发布",
  withdrawn: "已下架",
};

const documentLabels: Record<string, string> = {
  book: "图书",
  journal_article: "期刊论文",
  thesis: "学位论文",
  report: "研究报告",
};

export function PublicationDesk() {
  const [items, setItems] = useState<PublicationItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState<PublicationFilter>("attention");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");

  const load = useCallback(async () => {
    const token = getStoredAccessToken();
    if (!token) return;
    try {
      const payload = await apiRequest<Paginated<PublicationItem>>(
        "/ingestion/items/?scope=publication&ordering=-updated_at&page_size=100",
        {},
        token,
      );
      const available = payload.results.filter((item) => item.review_data);
      setItems(available);
      setSelectedId((current) => {
        const fromUrl = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("item") ?? "" : "";
        const candidate = current || fromUrl;
        if (candidate && available.some((item) => item.id === candidate)) return candidate;
        return available.find((item) => item.review_data?.publication_state !== "published")?.id ?? available[0]?.id ?? "";
      });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发布台加载失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const filtered = useMemo(() => items.filter((item) => {
    const state = item.review_data?.publication_state;
    if (filter === "published") return state === "published";
    if (filter === "withdrawn") return state === "withdrawn";
    if (filter === "attention") return state !== "published";
    return true;
  }), [filter, items]);

  const active = filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? null;

  useEffect(() => {
    const token = getStoredAccessToken();
    if (!token || !active) {
      const timer = window.setTimeout(() => setPreviewUrl(""), 0);
      return () => window.clearTimeout(timer);
    }
    let alive = true;
    let objectUrl = "";
    void apiBlob(`/ingestion/items/${active.id}/preview/`, token)
      .then((blob) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch(() => {
        if (alive) setPreviewUrl("");
      });
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [active]);

  const counts = useMemo(() => ({
    attention: items.filter((item) => item.review_data?.publication_state !== "published").length,
    published: items.filter((item) => item.review_data?.publication_state === "published").length,
    withdrawn: items.filter((item) => item.review_data?.publication_state === "withdrawn").length,
    all: items.length,
  }), [items]);

  function selectItem(itemId: string) {
    setSelectedId(itemId);
    const url = new URL(window.location.href);
    url.searchParams.set("item", itemId);
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  return (
    <div className="admin-page publication-desk-page">
      <header className="admin-page-title">
        <div><p>发布与发现</p><h1>发布台</h1><span>保存元数据与最终公开分开。管理员在这里预览、核对影响并决定发布或下架。</span></div>
        <button className="button secondary" type="button" onClick={() => void load()}><RefreshCw size={15} />刷新</button>
      </header>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {error ? <p className="review-error" role="alert"><AlertCircle size={16} />{error}</p> : null}
      <nav className="publication-filter-tabs" aria-label="发布状态筛选">
        {(["attention", "all", "published", "withdrawn"] as const).map((value) => (
          <button type="button" className={filter === value ? "active" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)} key={value}>
            {{ attention: "待处理", all: "全部", published: "已发布", withdrawn: "已下架" }[value]} <strong>{counts[value]}</strong>
          </button>
        ))}
      </nav>
      {loading ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取馆藏……</p> : null}
      {!loading && !items.length ? <p className="admin-list-state">尚无可进入发布台的馆藏记录。</p> : null}
      {items.length ? (
        <div className="publication-desk-layout">
          <aside className="publication-item-list admin-panel" aria-label="馆藏发布列表">
            {filtered.map((item) => {
              const review = item.review_data!;
              const warningCount = item.publication_preflight.warnings.length;
              const blockerCount = item.publication_preflight.blockers.length;
              return (
                <button type="button" className={item.id === active?.id ? "active" : ""} onClick={() => selectItem(item.id)} key={item.id}>
                  <FileText size={17} />
                  <span><strong>{review.title || item.source_filename}</strong><small>{documentLabels[review.document_type] ?? review.document_type} · {review.publication_year || "年份待补"}</small></span>
                  <b>{stateLabels[review.publication_state] ?? review.publication_state}</b>
                  <small>{blockerCount ? `${blockerCount} 个阻止项` : warningCount ? `${warningCount} 个警告` : "检查通过"}</small>
                </button>
              );
            })}
            {!filtered.length ? <p>当前筛选下没有馆藏。</p> : null}
          </aside>
          {active?.review_data ? (
            <main className="publication-workspace">
              <section className="publication-preview admin-panel">
                <div className="publication-preview-document">
                  {previewUrl ? <iframe title={`发布预览：${active.review_data.title}`} src={previewUrl} /> : <div><BookOpen size={28} /><span>PDF 预览正在准备</span></div>}
                </div>
                <div className="publication-preview-metadata">
                  <header><div><p>{documentLabels[active.review_data.document_type] ?? active.review_data.document_type}</p><h2>{active.review_data.title}</h2></div><span>{stateLabels[active.review_data.publication_state] ?? active.review_data.publication_state}</span></header>
                  <dl>
                    <div><dt>作者</dt><dd>{active.review_data.authors.join("、") || "待补"}</dd></div>
                    <div><dt>出版信息</dt><dd>{[active.review_data.publication_place, active.review_data.publisher, active.review_data.publication_year].filter(Boolean).join(" · ") || "待补"}</dd></div>
                    <div><dt>PDF</dt><dd>{active.review_data.page_count || "待确认"} 页</dd></div>
                    <div><dt>人工复核</dt><dd>{active.review_data.review_progress}%</dd></div>
                  </dl>
                  <div className="publication-preview-actions">
                    <Link className="button secondary" href={`/admin/review/${active.id}`}>编辑复核内容</Link>
                    {active.review_data.public_slug && active.review_data.publication_state === "published" ? <Link className="button secondary" href={`/works/${active.review_data.public_slug}`} target="_blank">查看公网 <ExternalLink size={14} /></Link> : null}
                  </div>
                </div>
              </section>
              <section className="publication-impact-summary admin-panel">
                <header><div><h2>公开影响预览</h2><p>发布后只在已确认关系对应的页面展示。</p></div><CheckCircle2 size={18} /></header>
                <div>
                  <ImpactGroup label="学科" values={active.review_data.release_impact.disciplines} />
                  <ImpactGroup label="子学科" values={active.review_data.release_impact.subdisciplines} />
                  <ImpactGroup label="理论流派" values={active.review_data.release_impact.theories} />
                  <ImpactGroup label="学者" values={active.review_data.release_impact.scholars} />
                  <ImpactGroup label="主题" values={active.review_data.release_impact.topics} />
                </div>
              </section>
              <ItemPublicationControl
                key={`${active.id}-${active.updated_at}`}
                itemId={active.id}
                editionId={active.review_data.edition_id}
                publicationState={active.review_data.publication_state}
                ocrStatus={active.review_data.ocr_status}
                semanticStatus={active.review_data.semantic_index_status}
                pageLabelStatus={active.review_data.page_label_status}
                reviewStatus={active.review_data.review_status}
                reviewProgress={active.review_data.review_progress}
                readerPolicy={active.review_data.reader_rendition_policy}
                initialPreflight={active.publication_preflight}
                canManagePublication={active.can_manage_publication}
                onChanged={load}
                onMessage={setMessage}
              />
            </main>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ImpactGroup({ label, values }: { label: string; values: ImpactItem[] }) {
  return <article><strong>{label}</strong><span>{values.length ? values.map((item) => item.label).join("、") : "未关联"}</span></article>;
}
