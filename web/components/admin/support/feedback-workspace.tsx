"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowUpRight, Check, Clock3, Inbox, MessageSquare, RefreshCw, Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { adminListHref, adminPageNumber } from "@/lib/admin-route-context";
import { adminFeedbackPath, feedbackCategories, feedbackDate, feedbackStatuses, updateFeedback, type AdminFeedbackDetail, type AdminFeedbackList, type FeedbackHandling, type FeedbackStatus } from "@/lib/api/admin-feedback.client";
import { safeFeedbackPath } from "@/lib/api/feedback.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./feedback.module.css";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const handling = (row: AdminFeedbackDetail): FeedbackHandling => ({ status: row.status, note: row.note, follow_up: row.follow_up });

function Pager({ page, count, size, label, change }: { page: number; count: number; size: number; label: string; change: (value: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / size));
  return <nav className={styles.pager} aria-label={label}><span>共 {count} 项 · 第 {page} / {pages} 页</span><button disabled={page <= 1} onClick={() => change(page - 1)}>上一页</button><button disabled={page >= pages} onClick={() => change(page + 1)}>下一页</button></nav>;
}

export function FeedbackWorkspace() {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (!user) return <p role="status">正在核对管理会话…</p>;
  if (!hasAdminCapability(user, "can_manage_users")) return <p role="alert">反馈中可能包含联系方式，仅管理员可查看和处理。</p>;
  return <Workspace key={`${user.id}:${epoch}`} ownerId={String(user.id)} />;
}

function Workspace({ ownerId }: { ownerId: string }) {
  const search = useSearchParams(), router = useRouter(), pathname = usePathname();
  const page = adminPageNumber(search.get("page")), q = (search.get("q") || "").slice(0, 100);
  const rawStatus = search.get("status") || "", status = Object.hasOwn(feedbackStatuses, rawStatus) ? rawStatus : "";
  const rawCategory = search.get("category") || "", category = Object.hasOwn(feedbackCategories, rawCategory) ? rawCategory : "";
  const item = search.get("item") || "", selected = uuid.test(item) ? item : "";
  const query = new URLSearchParams({ page: String(page), q, status, category });
  const resource = usePersistentWorkspace<AdminFeedbackList>(`${adminFeedbackPath()}?${query}`, ownerId);
  const dirty = useRef(false), busy = useRef(false);
  const change = (values: Record<string, string | number | null>) => {
    if (busy.current || dirty.current && !window.confirm("当前处理说明尚未保存，确定放弃这些输入吗？")) return;
    dirty.current = false;
    router.push(adminListHref(pathname, search.toString(), values));
  };
  const state = resource.data;
  return <main className={styles.workspace}>
    <header className={styles.heading}><div><p className={styles.eyebrow}>网站内容 / 读者反馈</p><h1>反馈处理</h1></div><button onClick={resource.reload}><RefreshCw size={15} />刷新列表</button></header>
    <div className={styles.notice}><MessageSquare size={18} /><p>反馈和联系方式仅供管理员处理本次问题。标记待回复不会发送邮件，处理说明不会公开展示。账户找回申请中的用户名和联系方式尚未经核实；先核对归属，再由有账户管理权限的人员在原用户管理中处理。</p></div>
    <nav className={styles.tabs} aria-label="反馈状态">
      {([["", "全部反馈", Inbox], ["submitted", "待处理", Clock3], ["reviewing", "处理中", MessageSquare], ["resolved", "已处理", Check]] as const).map(([key, label, Icon]) => <button key={key} aria-current={status === key ? "page" : undefined} onClick={() => change({ status: key || null, page: 1, item: null })}><Icon size={16} />{label}<span>{state ? state.counts[key || "total"] : "—"}</span></button>)}
    </nav>
    <form key={`${q}:${category}`} className={styles.filters} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); change({ q: String(form.get("q") || "").trim() || null, category: String(form.get("category") || "") || null, page: 1, item: null }); }}>
      <label><span className={styles.srOnly}>搜索反馈正文</span><Search size={16} /><input name="q" type="search" maxLength={100} defaultValue={q} placeholder="搜索反馈内容" /></label>
      <label><span className={styles.srOnly}>反馈类型</span><select name="category" defaultValue={category}><option value="">全部类型</option>{Object.entries(feedbackCategories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button>筛选</button><p>状态数量按当前关键词与类型统计</p>
    </form>
    {resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}
    <div className={styles.layout}>
      <section className={styles.list} aria-label="反馈列表"><header><h2>收到的反馈</h2><span>{state ? `${state.count} 项` : "读取中"}</span></header>
        {!state ? <p className={styles.empty} role="status">{resource.loading ? "正在读取反馈…" : "反馈暂不可读取，请重试。"}</p> : <>
          <ol>{state.results.map(row => <li key={row.id}><button className={styles.row} aria-pressed={row.id === selected} onClick={() => change({ item: row.id })}><span className={styles.rowMeta}><strong>{feedbackCategories[row.category] || row.category}</strong><span className={styles.badge} data-state={row.status}>{feedbackStatuses[row.status]}</span></span><span className={styles.excerpt}>{row.excerpt}</span><span className={styles.rowFoot}><time dateTime={row.created_at}>{feedbackDate(row.created_at)}</time>{row.follow_up ? <span>待人工回复</span> : null}</span></button></li>)}</ol>
          {!state.count ? <div className={styles.empty}><Inbox size={28} /><h3>{q || category || status ? "没有符合条件的反馈" : "暂未收到反馈"}</h3><p>{q || category || status ? "可调整关键词、类型或处理状态。" : "读者提交的反馈会显示在这里。"}</p></div> : null}
          <Pager page={state.page} count={state.count} size={state.page_size} label="反馈列表分页" change={value => change({ page: value, item: null })} />
        </>}
      </section>
      <section className={styles.detail} aria-label="反馈详情">{selected ? <Detail key={selected} id={selected} ownerId={ownerId} onSaved={resource.reload} onDirty={value => { dirty.current = value; }} onBusy={value => { busy.current = value; }} /> : <div className={styles.placeholder}><MessageSquare size={34} /><h2>选择一条反馈</h2><p>查看完整说明、来源页面和处理记录。</p></div>}</section>
    </div>
  </main>;
}

function Detail({ id, ownerId, onSaved, onDirty, onBusy }: { id: string; ownerId: string; onSaved: () => void; onDirty: (value: boolean) => void; onBusy: (value: boolean) => void }) {
  const resource = usePersistentWorkspace<AdminFeedbackDetail>(adminFeedbackPath(id), ownerId);
  const row = resource.data?.id === id ? resource.data : null;
  return <>
    {resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}
    {row ? <Editor row={row} resource={resource} ownerId={ownerId} onSaved={onSaved} onDirty={onDirty} onBusy={onBusy} /> : <p className={styles.empty} role="status">{resource.loading ? "正在读取反馈详情…" : "此反馈暂不可读取。"}</p>}
  </>;
}

function Editor({ row, resource, ownerId, onSaved, onDirty, onBusy }: {
  row: AdminFeedbackDetail; resource: ReturnType<typeof usePersistentWorkspace<AdminFeedbackDetail>>; ownerId: string;
  onSaved: () => void; onDirty: (value: boolean) => void; onBusy: (value: boolean) => void;
}) {
  const [base, setBase] = useState(row), [draft, setDraft] = useState(() => handling(row)), [message, setMessage] = useState("");
  const [unknown, setUnknown] = useState(false), pending = resource.pending, stale = row.revision !== base.revision;
  const dirty = useUnsavedForm(draft, handling(base));
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => { onBusy(pending); return () => onBusy(false); }, [pending, onBusy]);
  const sourcePath = ["page", "available"].includes(row.source.status) ? safeFeedbackPath(row.path) : row.source.status === "replaced" ? safeFeedbackPath(row.source.reader_url) : "";
  async function save() {
    if (pending || !dirty || stale && !unknown) return;
    setMessage("");
    const input = { ...draft, expected_revision: base.revision };
    try {
      const saved = await resource.mutate(JSON.stringify(input), async (_current, requestId) => {
        const result = await updateFeedback(row.id, { ...input, request_id: requestId });
        if (result.request_id !== requestId || result.record?.id !== row.id || !Number.isInteger(result.accepted_revision)
          || result.accepted_revision < input.expected_revision || !Number.isInteger(result.record.revision)
          || result.record.revision < result.accepted_revision) throw new Error("尚未确认本次处理结果，请重试原请求。");
        return result.record;
      });
      if (saved && alive.current) { setBase(saved); setDraft(handling(saved)); setUnknown(false); setMessage("处理记录已保存。"); onSaved(); }
    } catch (reason) {
      if (alive.current) setUnknown(!(reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500));
    }
  }
  return <>
    <header className={styles.detailHeading}><div><span className={styles.eyebrow}>{feedbackCategories[row.category]}</span><h2>反馈详情</h2><p><time dateTime={row.created_at}>{feedbackDate(row.created_at)}</time> · 第 {row.revision} 次修订</p></div><span className={styles.badge} data-state={row.status}>{feedbackStatuses[row.status]}</span></header>
    <div className={styles.submission}><h3>读者说明</h3><p className={styles.body}>{row.body}</p>
      {row.path ? <aside className={styles.source} aria-label="反馈来源状态">{row.source.cover_url ? <Image unoptimized width={45} height={64} src={normalizePublicResourceUrl(row.source.cover_url)} alt="来源封面" /> : null}<div><strong>{row.source.title}</strong>{row.source.authors.length || row.source.version_label ? <p>{[row.source.authors.join(" / "), row.source.version_label].filter(Boolean).join(" · ")}</p> : null}{row.source.location ? <p>{row.source.location}</p> : null}<p>{row.source.notice}</p>{sourcePath ? <Link href={sourcePath} target="_blank" rel="noopener noreferrer">{row.source.status === "replaced" ? "查看当前公开原文" : "查看公开页面"}<ArrowUpRight size={13} /></Link> : null}<small>核对时间：{feedbackDate(row.source.checked_at)}</small></div></aside> : <p className={styles.muted}>未提供可用的公开页面</p>}
      <dl><dt>联系邮箱</dt><dd>{row.contact || "未填写"}</dd><dt>用途同意</dt><dd>{row.consent_at ? `已同意用于处理本次反馈 · ${feedbackDate(row.consent_at)}` : "历史记录未留存用途同意，不能标记主动回复"}</dd></dl></div>
    <form className={styles.handling} onSubmit={event => { event.preventDefault(); void save(); }}>
      <header><h3>处理这条反馈</h3><span>{row.handled_by ? `最近处理人：${row.handled_by}` : "尚无处理记录"}</span></header>
      <fieldset disabled={pending || unknown}><label>处理状态<select value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value as FeedbackStatus })}>{Object.entries(feedbackStatuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>处理说明<textarea rows={5} maxLength={2000} value={draft.note} onChange={event => setDraft({ ...draft, note: event.target.value })} placeholder="记录问题核查、采取的处理及尚需补充的信息" /></label><p className={styles.muted}>{draft.note.length} / 2000 · 仅管理员可见，标为已处理时需填写说明</p><label className={styles.checkbox}><input type="checkbox" checked={draft.follow_up} disabled={!row.can_follow_up && !draft.follow_up} onChange={event => setDraft({ ...draft, follow_up: event.target.checked })} />标记需要人工回复</label><p className={styles.muted}>需要人工联系时，请仅围绕本次反馈使用邮箱。此操作不发送邮件。</p></fieldset>
      {stale && !unknown ? <div className={styles.warning}><p>其他管理员已修改此记录。你的输入仍保留，请核对最新处理后再继续。</p><p>最新状态：{feedbackStatuses[row.status]}；{row.note || "暂无说明"}</p><button type="button" onClick={() => { setBase(row); setMessage(""); }}>已核对，保留输入并采用最新修订</button></div> : null}
      {unknown ? <p className={styles.warning} role="status">尚未确认保存结果。请保留本次输入，使用原请求重试查询；不要重新提交另一条处理。</p> : null}
      {message ? <p className={styles.success} role="status">{message}</p> : null}
      <footer><span>{dirty ? "有未保存的修改" : "与当前记录一致"}</span><button className={styles.primary} disabled={pending || !dirty || stale && !unknown} type="submit">{pending ? "正在保存…" : unknown ? "重试原请求" : "保存处理记录"}</button></footer>
    </form>
    <History key={`${row.id}:${row.revision}`} row={row} ownerId={ownerId} />
  </>;
}

function History({ row, ownerId }: { row: AdminFeedbackDetail; ownerId: string }) {
  const [page, setPage] = useState(1);
  const resource = usePersistentWorkspace<AdminFeedbackDetail>(page > 1 ? `${adminFeedbackPath(row.id)}?history_page=${page}` : "", ownerId);
  const history = page === 1 ? row.history : resource.data?.id === row.id ? resource.data.history : null;
  return <section className={styles.history}><header><h3>处理历史</h3><span>原始反馈始终保留</span></header>{resource.error ? <p role="alert" className={styles.error}>{resource.error}<button onClick={resource.reload}>重试读取</button></p> : null}{history ? <>
    <ol>{history.results.map(event => <li key={event.id}><span className={styles.historyDot} /><div><p><strong>{event.actor}</strong><span>{feedbackStatuses[event.before.status]} → {feedbackStatuses[event.after.status]}</span></p><p className={styles.body}>{event.after.note || "未填写处理说明"}</p>{event.after.follow_up ? <small>标记待人工回复</small> : null}<time dateTime={event.created_at}>{feedbackDate(event.created_at)} · 修订 {event.after.revision}</time></div></li>)}</ol>{!history.count ? <p className={styles.muted}>暂未处理；原始反馈已保存。</p> : null}<Pager page={history.page} count={history.count} size={history.page_size} label="处理历史分页" change={setPage} />
  </> : <p role="status">正在读取历史…</p>}</section>;
}
