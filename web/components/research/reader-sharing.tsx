"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { writeClipboardText } from "@/lib/clipboard";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { destinationLabels, publicShare, sharingRequest, shareLink, type ShareBrief, type ShareContent, type ShareDetail,
  type ShareDirectory, type ShareNoticePage, type ShareReceipt } from "@/lib/api/sharing.client";
import { Dialog } from "@/components/ui/dialog";
import { SharingAccount, SharingPagination, SharedSummary, useSharingAction } from "./sharing-common";
import styles from "./sharing.module.css";

const date = (value: string) => new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const states = { submitted: "已提交", considering: "策划讨论中", declined: "未采用" };

export function ReaderSharing() {
  return <SharingAccount next="/account/sharing">{(owner, capabilities) => <Records owner={owner} reviewer={capabilities.includes("can_review_candidate")} />}</SharingAccount>;
}

function Records({ owner, reviewer }: { owner: string; reviewer: boolean }) {
  const location=useSearchParams();
  const [tab, setTab] = useState<"own" | "received" | "proposals" | "notices">(location.get("tab")==="notices"?"notices":"own"), [page, setPage] = useState(1);
  const [revoke, setRevoke] = useState<ShareBrief | null>(null), [confirmed, setConfirmed] = useState(false);
  const action = useSharingAction(owner);
  const load = useCallback((path: string, signal: AbortSignal) => sharingRequest<ShareDirectory>(owner, path, { signal }), [owner]);
  const records = usePersistentWorkspace<ShareDirectory>(tab === "notices" ? "" : `/reading/shares/?tab=${tab}&page=${page}`, owner, undefined, load);
  const loadNotices = useCallback((path: string, signal: AbortSignal) => sharingRequest<ShareNoticePage>(owner, path, { signal }), [owner]);
  const notices = usePersistentWorkspace<ShareNoticePage>(tab === "notices" ? `/reading/shares/notices/?page=${page}` : "", owner, undefined, loadNotices);
  const current = tab === "notices" ? notices : records;
  if (action.invalid) return <div className={styles.empty}><p>账户或权限已变化，已隐藏原账户的分享记录。</p><button onClick={() => window.location.reload()}>重新核对账户</button></div>;
  return <>
    <header className={styles.heading}><div><h1>分享与提交记录</h1></div><Link href="/account/sharing/new">分享或提交策划</Link></header>
    <div className={styles.tabs}>{([...["own", "received", "notices"] as const, ...(reviewer ? ["proposals" as const] : [])]).map(value => <button key={value} aria-pressed={tab === value} onClick={() => { setTab(value); setPage(1); }}>{({ own: "我的分享", received: "收到的分享", notices: "站内通知", proposals: "策划提案" })[value]}</button>)}</div>
    {action.message ? <p className={styles.feedback} role="status">{action.message}</p> : null}
    {current.error ? <p role="alert">{current.error}<button onClick={current.reload}>重新读取</button></p> : current.loading ? <LoadingState role="status">正在读取…</LoadingState> : tab === "notices" && notices.data ? <>
      <p className={styles.muted}>未读 {notices.data.unread} 条。通知不包含私人正文或附件。</p>
      <div className={styles.recordList}>{notices.data.results.map(row => <article key={row.id} className={styles.record}><div><strong>收到一项内容分享</strong><small>{date(row.created_at)} · {row.read_at ? "已读" : "未读"}</small></div><div className={styles.actions}><Link href={`/account/sharing/${row.share_id}`}>查看明确分享的摘要</Link>{!row.read_at ? <button disabled={action.busy} onClick={() => void action.run(signal => sharingRequest<{ marked: number }>(owner, "/reading/shares/notices/", { method: "POST", signal, body: JSON.stringify({ ids: [row.id] }) }), () => notices.reload())}>标记已读</button> : null}</div></article>)}</div>
      {!notices.data.results.length ? <div className={styles.empty}>还没有站内分享通知。</div> : null}
      <SharingPagination page={page} total={notices.data.total_pages} onPage={setPage} />
    </> : records.data ? <>
      <div className={styles.recordList}>{records.data.results.map(row => <article key={row.id} className={styles.record}><div><strong>{row.title}</strong><small>{destinationLabels[row.destination]} · {row.revoked ? "已撤回" : `有效至 ${date(row.expires_at)}`}</small><small>{row.destination === "proposal" ? states[row.review_state] : "仅包含确认范围内的内容"} · {date(row.created_at)}</small></div><div className={styles.actions}><Link href={`/account/sharing/${row.id}`}>查看内容</Link>{row.is_owner && !row.revoked ? <button disabled={action.busy} onClick={() => { setRevoke(row); setConfirmed(false); }}>撤回</button> : null}</div></article>)}</div>
      {!records.data.results.length ? <div className={styles.empty}>这里还没有分享记录。</div> : null}
      <SharingPagination page={page} total={records.data.total_pages} onPage={setPage} />
    </> : null}
    <Dialog open={Boolean(revoke)} onRequestClose={() => { if (!action.busy) setRevoke(null); }} className={styles.dialog} aria-label="撤回分享"><h2>撤回这项分享</h2><p>链接、接收范围和站内通知将失效。你的原研究、书单和笔记仍然保留。</p><label className={styles.check}><input type="checkbox" checked={confirmed} disabled={action.busy} onChange={event => setConfirmed(event.target.checked)} />我已核对撤回影响</label><div className={styles.actions}><button disabled={action.busy} onClick={() => setRevoke(null)}>取消</button><button disabled={action.busy || !confirmed || !revoke} onClick={() => { if (revoke) void action.run(signal => sharingRequest<ShareBrief>(owner, `/reading/shares/${revoke.id}/`, { method: "POST", signal, body: JSON.stringify({ action: "revoke", expected_revision: revoke.revision }) }), () => { setRevoke(null); records.reload(); action.setMessage("分享已撤回，原内容继续保留。"); }); }}>确认撤回</button></div></Dialog>
  </>;
}

export function ReaderSharedContent({ id }: { id: string }) {
  return <SharingAccount next={`/account/sharing/${id}`}>{(owner, capabilities) => <PrivateContent id={id} owner={owner} reviewer={capabilities.includes("can_review_candidate")} editor={capabilities.includes("can_edit_metadata") && capabilities.includes("access_back_office")} />}</SharingAccount>;
}

function PrivateContent({ id, owner, reviewer, editor }: { id: string; owner: string; reviewer: boolean; editor: boolean }) {
  const action = useSharingAction(owner), [manual, setManual] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => sharingRequest<ShareDetail>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<ShareDetail>(`/reading/shares/${id}/`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  function copy() {
    if (!data?.share.request_id) return;
    void action.run(async signal => {
      const result = await sharingRequest<ShareReceipt>(owner, `/reading/shares/receipt/?request_id=${data.share.request_id}`, { signal });
      if (!result.token) throw Error("此分享没有有效的公开链接。");
      return shareLink(id, result.token);
    }, link => { void writeClipboardText(link).then(() => action.setMessage("公开摘要链接已复制。")).catch(() => setManual(link)); });
  }
  if (action.invalid) return <p role="alert">账户或权限已变化，请重新核对登录后打开分享。</p>;
  return <><div className={styles.viewerHeader}><Link href="/account/sharing">返回分享记录</Link><span className={styles.muted}>只展示本次确认的摘要范围</span></div>
    {resource.error ? <div className={styles.empty} role="alert"><p>{resource.error}</p><button onClick={resource.reload}>重新核对内容</button><p>分享者可在分享记录中撤回失效记录，并重新选择内容。</p></div> : !data ? <LoadingState role="status">正在核对分享权限与原内容…</LoadingState> : <><header className={styles.heading}><h1>{data.content.source.title}</h1><small>有效至 {date(data.share.expires_at)}</small></header><SharedSummary value={data.content} showTitle={false} />
      <div className={styles.actions}>{data.share.is_owner && data.share.destination === "public" ? <button disabled={action.busy} onClick={copy}>复制公开摘要链接</button> : null}{reviewer && data.share.destination === "proposal" ? <><span>策划状态：{states[data.share.review_state]}</span>{(["considering", "declined"] as const).map(state => <button key={state} disabled={action.busy || data.share.review_state === state} onClick={() => void action.run(signal => sharingRequest<ShareBrief>(owner, `/reading/shares/${id}/`, { method: "POST", signal, body: JSON.stringify({ action: "review", expected_revision: data.share.revision, state }) }), () => { resource.reload(); action.setMessage("提案状态已保存；该操作不会发布原研究或书单。"); })}>{states[state]}</button>)}</> : null}</div>
      {reviewer && editor && data.share.destination === "proposal" ? <p className={styles.feedback}><Link href={`/admin/recommendations?view=legacy&proposal=${id}`}>接手提案并核对文章草稿</Link><br />只将明确选择的公开书目带入草稿；问题、私人笔记和附言继续在此评阅。</p> : null}
    </>}
    {action.message ? <p className={styles.feedback} role="status">{action.message}</p> : null}{manual ? <label className={styles.manual}>手动复制链接<textarea readOnly value={manual} onFocus={event => event.currentTarget.select()} /></label> : null}
  </>;
}

export function PublicSharedContent({ id }: { id: string }) {
  const [state, setState] = useState<{ content: ShareContent | null; error: string; loading: boolean }>({ content: null, error: "", loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let sequence = 0;
    let controller: AbortController | null = null;
    const load = () => {
      if (document.visibilityState !== "visible") return;
      controller?.abort(); controller = new AbortController();
      const request = controller, generation = ++sequence;
      setState({ content: null, error: "", loading: true });
      const key = new URLSearchParams(window.location.hash.slice(1)).get("key") || "";
      if (!/^[\w-]{32,80}$/.test(key)) { setState({ content: null, error: "分享链接缺少有效凭证，请使用分享者提供的完整链接。", loading: false }); return; }
      void publicShare(id, key, request.signal).then(content => { if (!request.signal.aborted && generation === sequence) setState({ content, error: "", loading: false }); })
        .catch((reason: unknown) => { if (!request.signal.aborted && generation === sequence) setState({ content: null, error: reason instanceof Error ? reason.message : "分享当前不可用。", loading: false }); });
    };
    load(); window.addEventListener("focus", load); window.addEventListener("pageshow", load); window.addEventListener("hashchange", load); document.addEventListener("visibilitychange", load);
    return () => { controller?.abort(); window.removeEventListener("focus", load); window.removeEventListener("pageshow", load); window.removeEventListener("hashchange", load); document.removeEventListener("visibilitychange", load); };
  }, [id, attempt]);
  return <main className={`${styles.page} ${styles.publicPage}`}><div className={styles.viewerHeader}><Link href="/home">社会理论书库</Link><span className={styles.muted}>读者分享的内容摘要</span></div>{state.loading ? <LoadingState role="status">正在核对分享范围和原来源…</LoadingState> : state.error ? <div className={styles.empty} role="alert"><h1>分享暂时不可用</h1><p>{state.error}</p><button onClick={() => setAttempt(value => value + 1)}>重新核对</button></div> : state.content ? <><p className={styles.muted}>有效至 {date(state.content.expires_at)}。原内容修改、删除或撤回后，旧链接不会自动公开新内容。</p><header className={styles.heading}><h1>{state.content.source.title}</h1></header><SharedSummary value={state.content} showTitle={false} /></> : null}</main>;
}
