"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { TopicDirectory } from "@/lib/api/topics.types";
import styles from "./reader-booklists.module.css";

export function BooklistTopicPicker({ owner, selected, busy, onAdd }: { owner: string; selected: string[]; busy: boolean; onAdd: (id: string) => void }) {
  const [q, setQ] = useState(""), [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<TopicDirectory>(path, { signal, cache: "no-store" }, getServerSessionCredential(), false), []);
  const resource = usePersistentWorkspace(`/catalog/topics/?${new URLSearchParams({ q, page: String(page), sort: "name" })}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  function search(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setQ(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }
  return <div><p>选择已公开的主题，只保存到这份私人书单，不改写馆藏关系或分享范围。已主动关联 {selected.length} / 12 个。</p>
    <form onSubmit={search} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }}><label>查找主题<input name="q" type="search" maxLength={180} placeholder="输入主题名称…" disabled={busy} /></label><button disabled={busy} type="submit">搜索</button></form>
    {resource.error ? <div role="alert"><p>{resource.error}</p><button disabled={busy} onClick={() => { setPage(1); resource.reload(); }}>重新读取</button></div> : !data ? <LoadingState variant="compact" role="status">正在读取公开主题…</LoadingState> : <>
      <div className={styles.picker}>{data.results.length ? data.results.map(topic => <article key={topic.id}><div><strong>{topic.name}</strong><small>{topic.description.slice(0, 180) || "暂无主题说明"}</small></div><button disabled={busy || selected.includes(topic.id) || selected.length >= 12} onClick={() => onAdd(topic.id)}>{selected.includes(topic.id) ? "已关联" : "添加"}</button></article>) : <p>没有匹配的公开主题。可以调整关键词。</p>}</div>
      <nav className={styles.paging} aria-label="公开主题分页"><button disabled={busy || !data.previous} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button disabled={busy || !data.next} onClick={() => setPage(value => value + 1)}>下一页</button></nav>
    </>}
  </div>;
}
