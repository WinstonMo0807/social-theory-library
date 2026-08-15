"use client";

import Link from "next/link";
import {
  ArrowRight,
  CircleAlert,
  FileCheck2,
  Filter,
  LoaderCircle,
  RefreshCw,
  Search,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";

type Candidate = {
  field_name: string;
  confidence: number;
};

type ReviewItem = {
  id: string;
  source_filename: string;
  status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  publication_reasons: string[];
  can_publish: boolean;
  updated_at: string;
  review_data: null | {
    title: string;
    document_type: "book" | "journal_article" | "thesis" | "report";
  };
  metadata_candidates: Candidate[];
};

type Paginated<T> = {
  count: number;
  results: T[];
};

const statusLabels: Record<string, string> = {
  needs_review: "待人工确认",
  failed: "处理失败",
  ready: "等待后台处理",
};

const documentLabels: Record<string, string> = {
  book: "图书",
  journal_article: "期刊论文",
  thesis: "学位论文",
  report: "研究报告",
};

function lowestCandidate(item: ReviewItem) {
  const candidates = item.metadata_candidates.filter((candidate) => candidate.confidence > 0);
  if (!candidates.length) return null;
  return candidates.reduce((lowest, candidate) => (
    candidate.confidence < lowest.confidence ? candidate : lowest
  ));
}

export function ReviewQueue() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [count, setCount] = useState(0);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const load = useCallback(async () => {
    const token = getStoredAccessToken();
    if (!token) {
      setError("请先登录后台。");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const search = query.trim() ? `&search=${encodeURIComponent(query.trim())}` : "";
      const payload = await apiRequest<Paginated<ReviewItem>>(
        `/ingestion/items/?scope=review&ordering=-updated_at${search}`,
        {},
        token,
      );
      setItems(payload.results);
      setCount(payload.count);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取复核队列。");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, revision]);

  const visible = useMemo(
    () => status === "all" ? items : items.filter((item) => item.status === status),
    [items, status],
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    setRevision((value) => value + 1);
  }

  return (
    <div className="admin-page review-queue-page">
      <header className="admin-page-title">
        <div>
          <p>入库管理</p>
          <h1>元数据复核队列</h1>
          <span>这里显示真实上传记录。人工确认、发布条件和失败日志使用同一条记录。</span>
        </div>
        <strong>{count} 个待处理</strong>
      </header>
      <form className="admin-list-toolbar" onSubmit={submit}>
        <label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或题名……" /></label>
        <label className="review-status-filter">
          <Filter size={15} />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">全部状态</option>
            <option value="needs_review">待人工确认</option>
            <option value="failed">处理失败</option>
            <option value="ready">等待后台处理</option>
          </select>
        </label>
        <button type="button" onClick={() => setRevision((value) => value + 1)} aria-label="刷新复核队列"><RefreshCw size={15} />刷新</button>
      </form>
      <section className="review-list admin-panel">
        <header><span>文件与类型</span><span>当前状态</span><span>最低候选</span><span>待处理原因</span><span>操作</span></header>
        {loading ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取真实记录……</p> : null}
        {error ? <p className="admin-list-state review-error"><CircleAlert size={18} />{error}</p> : null}
        {!loading && !error && visible.map((item) => {
          const candidate = lowestCandidate(item);
          const reason = item.error_message || item.publication_reasons[0] || "等待后台重新检查";
          return (
            <article key={item.id}>
              <p>
                {item.can_publish ? <FileCheck2 size={17} /> : <CircleAlert size={17} />}
                <span>
                  <strong>{item.review_data?.title || item.source_filename}</strong>
                  <small>{item.source_filename} · {documentLabels[item.review_data?.document_type ?? ""] ?? "待识别"}</small>
                </span>
              </p>
              <span>{statusLabels[item.status] ?? item.status} · {item.stage_progress}%</span>
              <b>{candidate ? `${Math.round(candidate.confidence * 100)}%` : "人工值"}</b>
              <span title={reason}>{reason}</span>
              <Link href={`/admin/review/${item.id}`}>开始复核 <ArrowRight size={14} /></Link>
            </article>
          );
        })}
        {!loading && !error && !visible.length ? (
          <p className="admin-list-state"><FileCheck2 size={18} />当前没有需要处理的真实记录。</p>
        ) : null}
      </section>
    </div>
  );
}
