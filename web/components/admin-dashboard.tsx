"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { useAdminSession } from "@/lib/admin-session";
import { queueWorkbenchHref, publicationPublicHref, type WorkflowQueueItem, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { withAdminReturn } from "@/lib/admin-route-context";
import { SelectedWorkPreview, SavedEditionCover } from "./admin/preview/selected-work-preview";
import { WORKFLOW_GROUPS } from "./admin/workflow/file-presentation";

function deduplicate(items: WorkflowQueueItem[]) {
  const seen = new Set<string>();
  return items.filter(item => {
    const key = item.edition_id || item.work_id || item.item_id || item.id;
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}

export function AdminDashboard() {
  const user = useAdminSession();
  const queue = useApiResource<WorkflowQueuePage>("/catalog/admin/workflows/queue/?category=all&page_size=8", user ? getServerSessionCredential() : null, String(user?.id ?? ""));
  const items = deduplicate(queue.data?.results ?? []);
  const [selectedId, setSelectedId] = useState("");
  const selected = selectedId ? items.find(item => item.id === selectedId) : items[0];
  const destination = selected ? queueWorkbenchHref(selected) : "";
  const cards = [
    { title: "待补信息", value: queue.data?.counts.continue, detail: "补齐书目信息", href: "/admin/review?category=continue" },
    { title: "处理失败", value: queue.data?.counts.exception, detail: "查看失败原因", href: "/admin/review?category=exception" },
    { title: "待发布", value: queue.data?.counts.publication_ready, detail: "完成编辑后发布", href: "/admin/review?category=publication_ready" },
  ];
  return <div className="admin-reference-split dashboard-reference">
    <section className="admin-reference-list">
      <header className="reference-list-heading"><h1>今日工作</h1><p>专注完成内容，建设更好的社会理论图书馆。</p></header>
      <section className="reference-metrics" aria-label="工作概况">{cards.map(card => <Link href={card.href} key={card.title}><strong>{card.value ?? "—"}</strong><span>{card.title}</span><small>{card.detail}</small></Link>)}</section>
      <h2 className="reference-list-label">待办事项{queue.data ? `（${items.length}）` : ""}</h2>
      {queue.error ? <p className="admin-error" role="alert">{queue.error}<button type="button" onClick={queue.retry}>重试工作队列</button></p> : null}
      {queue.loading ? <p role="status">正在读取待办…</p> : null}
      <div className="reference-task-list">{items.map(item => <button type="button" aria-pressed={selected?.id === item.id} className={selected?.id === item.id ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>
        <SavedEditionCover editionId={item.edition_id} coverUrl={item.cover_url ?? ""} title={item.title}/>
        <span className="reference-task-copy"><strong>{item.title || item.source_filename || "未命名馆藏"}</strong><small>{[item.contributors?.join("、"), item.publisher, item.publication_year ? `${item.publication_year} 版` : item.version_label].filter(Boolean).join(" · ") || "—"}</small><span className="reference-task-progress"><span>{WORKFLOW_GROUPS.findIndex(group => group.steps.some(step => step === item.current_step)) >= 0 ? `第 ${WORKFLOW_GROUPS.findIndex(group => group.steps.some(step => step === item.current_step)) + 1} / 4 步　` : ""}{WORKFLOW_GROUPS.find(group => group.steps.some(step => step === item.current_step))?.label || item.current_step_label}</span><small>{item.issues?.[0]?.message || (item.unresolved_count ? `${item.unresolved_count} 项待确认` : "核对预览与发布")}</small></span></span><ChevronRight size={18}/>
      </button>)}</div>
      {queue.data && !items.length ? <p className="admin-list-state">当前没有未完成的馆藏。</p> : null}
      <Link className="reference-all-link" href="/admin/review">查看全部待办 →</Link>
    </section>
    <SelectedWorkPreview key={selected?.id || "empty"} currentStep={selected?.current_step} editionId={selected?.edition_id} title={selected?.title} subtitle={selected ? [selected.contributors?.join("、"), selected.publisher, selected.publication_year ? `${selected.publication_year} 版` : selected.version_label].filter(Boolean).join(" · ") : ""} publicHref={publicationPublicHref(selected?.publication)} editHref={destination ? withAdminReturn(destination, "/admin", selected?.current_step) : ""}/>
  </div>;
}
