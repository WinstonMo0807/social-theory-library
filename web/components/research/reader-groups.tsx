"use client";

import { writeClipboardText } from "@/lib/clipboard";
import { createRequestKey } from "../../lib/request-key";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { groupInviteLink, sharingRequest, type GroupCommand, type GroupDetail, type GroupDirectory, type GroupResult } from "@/lib/api/sharing.client";
import { Dialog } from "@/components/ui/dialog";
import { SharingAccount, SharingPagination, useSharingAction } from "./sharing-common";
import styles from "./sharing.module.css";

type Intent = { path: string; body: Record<string, unknown>; request_id: string; group_id?: string };
type Recovery = Pick<Intent, "request_id" | "group_id">;
type Confirm = { action: "archive" | "leave" | "remove"; title: string; group: string; revision: number; membership_id?: string };

export function ReaderGroups() {
  return <SharingAccount next="/account/groups">{owner => <Groups owner={owner} />}</SharingAccount>;
}

function Groups({ owner }: { owner: string }) {
  const [page, setPage] = useState(1), [invitePage, setInvitePage] = useState(1), [id, setId] = useState("");
  const [title, setTitle] = useState(""), [kind, setKind] = useState<"campus" | "team">("campus"), [username, setUsername] = useState("");
  const [rename, setRename] = useState(""), [confirm, setConfirm] = useState<Confirm | null>(null), [confirmed, setConfirmed] = useState(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null), [retryReady, setRetryReady] = useState(false), [reviewed, setReviewed] = useState(false);
  const [manual, setManual] = useState(""), [inviteToken, setInviteToken] = useState("");
  const pending = useRef<Intent | null>(null), action = useSharingAction(owner);
  const setMessage = action.setMessage;
  const key = `stl-group-request:${owner}`;
  const loadDirectory = useCallback((path: string, signal: AbortSignal) => sharingRequest<GroupDirectory>(owner, path, { signal }), [owner]);
  const directory = usePersistentWorkspace<GroupDirectory>(`/reading/groups/?page=${page}&invitation_page=${invitePage}`, owner, undefined, loadDirectory);
  const loadDetail = useCallback((path: string, signal: AbortSignal) => sharingRequest<GroupDetail>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<GroupDetail>(id ? `/reading/groups/${id}/` : "", owner, undefined, loadDetail);
  const data = resource.error ? null : resource.data, rows = directory.error ? null : directory.data;
  const blocked = action.busy || Boolean(recovery);
  useEffect(() => {
    const restore = () => {
      try {
        const value = JSON.parse(sessionStorage.getItem(key) || "null");
        if (value && /^[\da-f-]{36}$/i.test(value.request_id) && (!value.group_id || /^[\da-f-]{36}$/i.test(value.group_id))) setRecovery({ request_id: value.request_id, group_id: value.group_id });
      } catch { setMessage("恢复记录无法读取，请先核对现有小组和邀请。"); }
      const token = new URLSearchParams(window.location.hash.slice(1)).get("invite");
      if (token && /^[\w-]{32,80}$/.test(token)) setInviteToken(token);
    };
    restore(); window.addEventListener("hashchange", restore);
    return () => window.removeEventListener("hashchange", restore);
  }, [key, setMessage]);
  function remember(value: Recovery | null) {
    setRecovery(value);
    try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); }
    catch { action.setMessage("浏览器未保存恢复标识，请保持本页直到取得回执。"); }
  }
  function finish(value: GroupResult) {
    pending.current = null; setRetryReady(false); remember(null); setConfirm(null); setConfirmed(false);
    setId(value.available ? value.group_id : ""); directory.reload(); resource.reload();
    action.setMessage(value.available ? "小组操作已保存。请查看当前成员和邀请。" : "原操作已完成，该小组当前不再向本账户开放。");
  }
  function submit(intent: Intent) {
    if (pending.current && pending.current !== intent) return;
    if (blocked && !pending.current) return;
    pending.current = intent; setRetryReady(true); remember({ request_id: intent.request_id, group_id: intent.group_id });
    void action.run(signal => sharingRequest<GroupResult>(owner, intent.path, { method: "POST", body: JSON.stringify(intent.body), signal }), finish, reason => {
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) { pending.current = null; setRetryReady(false); remember(null); resource.reload(); }
    });
  }
  function command(value: Omit<GroupCommand, "request_id" | "expected_revision">, captured?: Confirm) {
    if (!data && !captured) return;
    const groupId = captured?.group || data!.group.id, revision = captured?.revision || data!.group.revision;
    const requestId = createRequestKey();
    submit({ path: `/reading/groups/${groupId}/`, group_id: groupId, request_id: requestId,
      body: { ...value, request_id: requestId, expected_revision: revision } });
  }
  function create() {
    const requestId = createRequestKey();
    submit({ path: "/reading/groups/", request_id: requestId, body: { request_id: requestId, title: title.trim(), kind } });
  }
  function accept(body: { token?: string; invitation_id?: string }) {
    void action.run(signal => sharingRequest<{ group_id: string }>(owner, "/reading/groups/accept/", { method: "POST", body: JSON.stringify(body), signal }), value => {
      setId(value.group_id); setInviteToken(""); window.history.replaceState(null, "", window.location.pathname + window.location.search);
      directory.reload(); resource.reload(); action.setMessage("已加入小组。之后仍需由分享者明确选择接收内容。");
    });
  }
  function copyInvite(invitationId: string) {
    void action.run(async signal => {
      const current = await sharingRequest<GroupDetail>(owner, `/reading/groups/${id}/`, { signal });
      const invite = current.invitations.find(row => row.id === invitationId);
      if (!invite?.token) throw Error("邀请已接受、撤回或到期，请重新读取当前邀请。");
      return groupInviteLink(invite.token);
    }, value => { void writeClipboardText(value).then(() => { setManual(""); action.setMessage("邀请链接已复制，请自行交给对应账户。链接不会授予其他账户成员身份。"); }).catch(() => setManual(value)); });
  }
  if (action.invalid) return <div className={styles.empty} role="alert"><p>当前账户或权限需要重新核对，已隐藏原账户的小组资料。</p><button onClick={() => window.location.reload()}>重新核对账户</button></div>;
  return <>
    <header className={styles.heading}><div><h1>我的小组</h1><p>邀请明确的账户，一起阅读和讨论。</p></div><span className={styles.privacy}>仅成员可见</span></header>
    {action.message ? <p className={styles.feedback} role="status">{action.message}</p> : null}
    {recovery ? <section className={styles.recovery}><h2>核对上次小组操作</h2><p>先查回原请求，避免重复创建或发出邀请。没有保存账户资料或邀请内容到浏览器。</p><div className={styles.actions}><button disabled={action.busy} onClick={() => void action.run(signal => sharingRequest<GroupResult>(owner, `/reading/groups/receipt/?${new URLSearchParams({ request_id: recovery.request_id, ...(recovery.group_id ? { group_id: recovery.group_id } : {}) })}`, { signal }), finish)}>查回原结果</button>{retryReady ? <button disabled={action.busy} onClick={() => { if (pending.current) submit(pending.current); }}>重试原操作</button> : <><label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />我已核对现有小组与邀请</label><button disabled={action.busy || !reviewed} onClick={() => { remember(null); setReviewed(false); }}>结束恢复</button></>}</div></section> : null}
    {inviteToken ? <section className={styles.panel}><h2>收到一份小组邀请</h2><p>只有邀请指定的账户可以接受。接受后可查看成员；不自动获得以前分享的资料。</p><button disabled={blocked} onClick={() => accept({ token: inviteToken })}>接受本账户的邀请</button></section> : null}
    <div className={styles.groupLayout}>
      <aside>
        <section className={styles.panel}><h2>已加入的小组</h2>{directory.error ? <p role="alert">{directory.error}<button onClick={directory.reload}>重新读取</button></p> : !rows ? <p role="status">正在读取…</p> : rows.groups.results.length ? <><div className={styles.objectList}>{rows.groups.results.map(row => <button key={row.id} aria-pressed={row.id === id} onClick={() => { setId(row.id); setRename(""); }}><strong>{row.title}</strong><small>{row.kind === "campus" ? "学术小组" : "合作研究团队"} · {row.member_count} 人{row.is_owner ? " · 我创建的" : ""}</small></button>)}</div><SharingPagination page={page} total={rows.groups.total_pages} onPage={setPage} /></> : <p className={styles.muted}>还没有加入小组。</p>}</section>
        <section className={styles.panel}><h2>创建小组</h2><form onSubmit={event => { event.preventDefault(); create(); }}><label>小组名称<input value={title} onChange={event => setTitle(event.target.value)} maxLength={80} required disabled={blocked} /></label><label>小组类型<select value={kind} onChange={event => setKind(event.target.value as typeof kind)} disabled={blocked}><option value="campus">学术小组</option><option value="team">合作研究团队</option></select></label><p className={styles.muted}>按账号邀请成员。学术小组不代表已验证院校身份。</p><button type="submit" disabled={blocked || !title.trim()}>创建</button></form></section>
        {rows?.invitations.results.length ? <section className={styles.panel}><h2>待处理的邀请</h2>{rows.invitations.results.map(invite => <article className={styles.invitation} key={invite.id}><strong>{invite.title}</strong><small>有效至 {new Date(invite.expires_at).toLocaleDateString("zh-CN")}</small><button disabled={blocked} onClick={() => accept({ invitation_id: invite.id })}>接受邀请</button></article>)}<SharingPagination page={invitePage} total={rows.invitations.total_pages} onPage={setInvitePage} /></section> : null}
      </aside>
      <section className={styles.panel}>
        {!id ? <div className={styles.empty}><h2>一起研究，从明确范围开始</h2><p>选择一个小组查看成员，或创建小组后邀请同伴。</p></div> : resource.error ? <p role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : !data ? <p role="status">正在读取小组…</p> : <>
          <div className={styles.heading}><h2>{data.group.title}</h2><button disabled={blocked} onClick={() => { setConfirm({ action: data.group.is_owner ? "archive" : "leave", title: data.group.title, group: id, revision: data.group.revision }); setConfirmed(false); }}>{data.group.is_owner ? "关闭小组" : "退出小组"}</button></div>
          <p className={styles.muted}>共享范围由每次分享单独确认。新成员不能自动读取入组前的受限分享。</p>
          <ul className={styles.members}>{data.members.map(member => <li key={member.membership_id}><span><strong>{member.name}</strong><small>{member.is_owner ? "创建者" : "成员"}{member.user_id === owner ? " · 我" : ""}</small></span>{data.group.is_owner && !member.is_owner ? <button disabled={blocked} onClick={() => { setConfirm({ action: "remove", title: member.name, group: id, revision: data.group.revision, membership_id: member.membership_id }); setConfirmed(false); }}>移除</button> : null}</li>)}</ul>
          {data.group.is_owner ? <>
            <form className={styles.inlineForm} onSubmit={event => { event.preventDefault(); command({ action: "rename", title: rename.trim() }); }}><label>修改小组名称<input value={rename} placeholder={data.group.title} maxLength={80} onChange={event => setRename(event.target.value)} disabled={blocked} /></label><button disabled={blocked || !rename.trim()} type="submit">保存名称</button></form>
            <form className={styles.inlineForm} onSubmit={event => { event.preventDefault(); command({ action: "invite", username: username.trim() }); }}><label>邀请账户<input autoComplete="off" value={username} placeholder="填写对方的账号名" maxLength={150} onChange={event => setUsername(event.target.value)} disabled={blocked} /></label><button disabled={blocked || !username.trim()} type="submit">创建邀请</button></form>
            <p className={styles.muted}>邀请保留 7 天，需对方明确接受。创建邀请不会发送邮件。</p>
            {data.invitations.length ? <><h3>待接受邀请</h3>{data.invitations.map(invite => <article className={styles.invitation} key={invite.id}><strong>{invite.recipient}</strong><small>有效至 {new Date(invite.expires_at).toLocaleDateString("zh-CN")}</small><div className={styles.actions}>{invite.token ? <button disabled={blocked} onClick={() => copyInvite(invite.id)}>复制邀请链接</button> : null}<button disabled={blocked} onClick={() => command({ action: "revoke_invite", invitation_id: invite.id })}>撤销邀请</button></div></article>)}</> : <p className={styles.muted}>暂无待接受的邀请。</p>}
          </> : null}
        </>}
      </section>
    </div>
    {manual ? <label className={styles.manual}>手动复制邀请链接<textarea readOnly value={manual} onFocus={event => event.currentTarget.select()} /><button onClick={() => setManual("")}>收起链接</button></label> : null}
    <Dialog open={Boolean(confirm)} onRequestClose={() => { if (!blocked) setConfirm(null); }} className={styles.dialog} aria-label="核对小组权限变更">{confirm ? <><h2>{confirm.action === "archive" ? "关闭小组" : confirm.action === "leave" ? "退出小组" : "移除成员"}</h2><p>{confirm.title}</p><p>{confirm.action === "archive" ? "全部成员将失去小组访问权，已有邀请和依赖小组的分享会失效。每个人自己的研究、书单和笔记仍然保留。" : "本次成员身份的受限分享会失效，重新加入也不会恢复这些旧授权。个人研究、笔记和账号仍然保留。"}</p><label className={styles.check}><input type="checkbox" checked={confirmed} disabled={blocked} onChange={event => setConfirmed(event.target.checked)} />我已核对影响</label><div className={styles.actions}><button disabled={blocked} onClick={() => setConfirm(null)}>取消</button><button disabled={blocked || !confirmed} onClick={() => command({ action: confirm.action, ...(confirm.membership_id ? { membership_id: confirm.membership_id } : {}) }, confirm)}>确认</button></div></> : null}</Dialog>
  </>;
}
