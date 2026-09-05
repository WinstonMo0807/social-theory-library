"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ConfirmDialog } from "@/components/confirm-dialog";

type TopicOption = { id: string; name: string; editorial_status: string };
type MergePreview = {
  target: { id: string; name: string } | null;
  impact: Array<{ label: string; count: number }>;
  published_editions: number;
  blockers: Array<{ code: string; label: string }>;
  can_merge: boolean;
  fingerprint: string;
  guidance: string;
};

export function TopicMergePanel({ topicId, name, status }: { topicId: string; name: string; status: string }) {
  const router = useRouter();
  const { state } = useSessionBootstrap();
  const allowed = state.user?.capabilities?.includes("can_merge_authority") === true;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<TopicOption[]>([]);
  const [targetId, setTargetId] = useState("");
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    if (!allowed || !open) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      apiRequest<{ results: TopicOption[] }>(
        `/catalog/admin/topics/?search=${encodeURIComponent(query.trim())}&page_size=30`,
        { signal: controller.signal }, getServerSessionCredential(),
      ).then((data) => {
        if (!controller.signal.aborted) setOptions(data.results.filter((topic) => topic.id !== topicId && topic.editorial_status === "published"));
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "馆内主题暂时无法读取。");
      });
    }, 300);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [allowed, open, query, topicId]);

  async function loadPreview() {
    if (!targetId) return;
    setWorking(true);
    setMessage("");
    setPreview(null);
    try {
      setPreview(await apiRequest<MergePreview>(
        `/catalog/admin/topics/${topicId}/merge-preview/?target_topic=${targetId}`,
        {}, getServerSessionCredential(),
      ));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "合并影响暂时无法读取。");
    } finally { setWorking(false); }
  }

  async function merge(changeNote: string) {
    if (!preview?.can_merge || !preview.target || working) return;
    setWorking(true);
    setMessage("");
    try {
      const result = await apiRequest<{ target_id: string; detail: string }>(
        `/catalog/admin/topics/${topicId}/merge/`,
        { method: "POST", body: JSON.stringify({ target_topic: preview.target.id, fingerprint: preview.fingerprint, confirmed: true, change_note: changeNote }) },
        getServerSessionCredential(),
      );
      setConfirm(false);
      setMessage(result.detail);
      router.replace(`/admin/topics/${result.target_id}`);
    } catch (error) {
      setConfirm(false);
      setPreview(null);
      setMessage(error instanceof Error ? error.message : "主题未合并成功，请重新查看影响范围。");
    } finally { setWorking(false); }
  }

  if (!allowed || status === "archived") return null;
  return <section className="admin-panel">
    <h3>合并重复主题</h3>
    <p>将当前主题的正式关系、推荐和读者收藏归入另一个馆内主题，原记录保留供审计。</p>
    {!open ? <button className="button secondary" type="button" onClick={() => setOpen(true)}>选择合并目标</button> : <>
      <label><span>搜索馆内主题</span><input value={query} disabled={working} onChange={(event) => { setQuery(event.target.value); setTargetId(""); setPreview(null); }} /></label>
      <label><span>保留的主题</span><select value={targetId} disabled={working} onChange={(event) => { setTargetId(event.target.value); setPreview(null); }}>
        <option value="">请选择已发布主题</option>
        {options.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
      </select></label>
      <button className="button secondary" type="button" disabled={!targetId || working} onClick={() => void loadPreview()}>{working ? "正在处理" : "查看合并影响"}</button>
      {preview ? <div>
        <p>{preview.guidance}</p>
        <ul>{preview.impact.filter((row) => row.count > 0).map((row) => <li key={row.label}>{row.label} {row.count} 项</li>)}<li>更新 {preview.published_editions} 个已发布版本的主题信息</li></ul>
        {preview.blockers.map((blocker, index) => <p className="form-message" key={`${blocker.code}-${index}`}>{blocker.label}</p>)}
        <button className="button" type="button" disabled={!preview.can_merge || working} onClick={() => setConfirm(true)}>确认合并</button>
      </div> : null}
    </>}
    {message ? <p className="form-message" role="status">{message}</p> : null}
    <ConfirmDialog open={confirm} title="确认合并主题" description={`将${name}合并到${preview?.target?.name ?? "所选主题"}。当前主题将下线，正式关系和收藏随之迁移。`} confirmLabel="合并并更新馆内关系" pending={working} reasonLabel="合并说明" reasonRequired onCancel={() => setConfirm(false)} onConfirm={merge} />
  </section>;
}
