"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { accountRequest, type AccountCommand, type AccountDirectory, type AccountHistory, type AccountInput, type AccountPreview, type AccountReceipt, type AccountRoles, type ManagedUser } from "@/lib/api/account-management.client";
import { Dialog } from "@/components/ui/dialog";
import styles from "./account-workspace.module.css";
import { AccountInvitation } from "./account-invitation";
import { AccountAvatar } from "@/components/account-avatar";

const stamp = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "尚无登录记录";
const storageKey = (actor: string) => `stl-account-command:${actor}`;
const activationLabel = (user: ManagedUser) => ({ active: "已启用", inactive: "已停用", pending_activation: "待激活", invitation_expired: "邀请已过期", invitation_changed: "邀请待更新", invitation_revoked: "邀请已撤销" })[user.activation_state] || "待核对";
const editTitle = (operation: AccountInput["operation"]) => ({create: "新建账户", update: "编辑账户与角色", password: "设置新密码", invite: "重新生成邀请", revoke_invite: "撤销邀请"})[operation];
type Edit = { operation: AccountInput["operation"]; original: ManagedUser | null };

export function AccountWorkspace() {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (!user) return <p role="status">正在核对管理账户…</p>;
  if (!hasAdminCapability(user, "can_manage_users")) return <main className={styles.page}><h1>账户、角色与权限</h1><div className={styles.empty}><h2>没有权限访问此功能</h2><p>此处仅向具有账户管理能力的账户开放。</p><Link href="/admin">返回今日工作</Link></div></main>;
  return <Workspace key={`${user.id}:${epoch}`} actor={String(user.id)} />;
}

function Pager({ page, total, count, onPage }: { page: number; total: number; count: number; onPage: (page: number) => void }) {
  return <nav className={styles.pager} aria-label="分页"><span>共 {count} 项 · {page}/{total}</span><button disabled={page <= 1} onClick={() => onPage(page - 1)}>上一页</button><button disabled={page >= total} onClick={() => onPage(page + 1)}>下一页</button></nav>;
}

function Workspace({ actor }: { actor: string }) {
  const [tab, setTab] = useState<"accounts" | "roles" | "history">("accounts"), [page, setPage] = useState(1);
  const [q, setQ] = useState(""), [role, setRole] = useState(""), [status, setStatus] = useState(""), [size, setSize] = useState(10), [selected, setSelected] = useState<number | null>(null);
  const [edit, setEdit] = useState<Edit | null>(null), [locked, setLocked] = useState(false), [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false), [closing, setClosing] = useState(false), [stopping, setStopping] = useState(false);
  const [recovery, setRecovery] = useState<string | null>(null), [ready, setReady] = useState(false), [broken, setBroken] = useState(false);
  const controller = useRef<AbortController | null>(null), recovering = useRef(false);
  const load = useCallback((path: string, signal: AbortSignal) => accountRequest<AccountDirectory>(actor, path, { signal }), [actor]);
  const query = new URLSearchParams({ page: String(page), page_size: String(size), q, role, state: status, ...(selected ? { user_id: String(selected) } : {}) });
  const accounts = usePersistentWorkspace<AccountDirectory>(`workspace/?${query}`, actor, undefined, load);
  const data = accounts.error ? null : accounts.data;
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    const off = subscribeToSessionChanges(() => request.abort());
    queueMicrotask(() => {
      if (request.signal.aborted) return;
      try { const id = sessionStorage.getItem(storageKey(actor)); if (id) { if (!/^[\da-f-]{36}$/i.test(id)) throw Error("原请求标识无法读取，请先核对操作记录。"); setRecovery(id); } }
      catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "原请求暂时无法读取。"); }
      setReady(true);
    });
    return () => { request.abort(); off(); };
  }, [actor]);
  function clearRecovery() {
    try { sessionStorage.removeItem(storageKey(actor)); setRecovery(null); setBroken(false); return true; }
    catch { setMessage("服务器结果已确认，但本机请求标识暂时无法清除；请恢复会话存储后再次查回。不会重复提交。"); return false; }
  }
  function pending(id: string) { sessionStorage.setItem(storageKey(actor), id); setRecovery(id); }
  function closeEditor() { if (locked) return; if (dirty || recovery) setClosing(true); else setEdit(null); }
  async function lookup(stop = false) {
    const request = controller.current;
    if (!recovery || !request || request.signal.aborted || recovering.current) return;
    recovering.current = true; setLocked(true); setMessage("");
    try {
      const result = await withPrivateOwner(actor, () => accountRequest<AccountReceipt>(actor, stop ? "receipt/" : `receipt/?${new URLSearchParams({ request_id: recovery })}`, {
        signal: request.signal, ...(stop ? { method: "POST", body: JSON.stringify({ request_id: recovery, action: "cancel_pending" }) } : {}),
      }), request.signal);
      if (result.request_id !== recovery || !["applied", "cancelled"].includes(result.state)) throw Error("返回回执与原请求不一致。");
      if (!request.signal.aborted && clearRecovery()) { setEdit(null); setStopping(false); setSelected(result.exists ? result.user_id : null); accounts.reload(); setMessage(result.state === "cancelled" ? "原请求尚未执行，现已停止；迟到请求不会再修改账户。" : result.exists ? "原操作已保存，已定位目标账户；不会再次执行或撤销。" : "原操作已完成，目标账户随后已删除，不会重新创建。"); }
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "无法查回原请求，请先核对操作记录。"); }
    finally { recovering.current = false; if (!request.signal.aborted) setLocked(false); }
  }
  useUnsavedForm(Boolean(recovery) && !edit, false);
  const blocked = locked || !ready || Boolean(recovery) || broken;
  const editor = edit ? <Editor actor={actor} edit={edit} canAssign={data?.can_assign_roles || false} onDirty={setDirty} onLocked={setLocked} onPending={pending} onClear={clearRecovery} onDone={receipt => { if (!clearRecovery()) return false; setEdit(null); setSelected(receipt.exists ? receipt.user_id : null); accounts.reload(); setMessage("账户操作已保存，操作记录已同步。"); return true; }} onReload={row => { setEdit({ ...edit, original: row }); accounts.reload(); }} /> : null;
  return <main className={styles.page}><p className={styles.crumb}>系统 › 账户与权限</p><header className={styles.heading}><div><h1>账户、角色与权限</h1><p>管理谁能策划、发布和维护系统，不默认查看私人研究。</p></div><button className={styles.primary} disabled={blocked || Boolean(edit)} onClick={() => setEdit({ operation: "create", original: null })}>＋ 新建账户</button></header>
    <div className={styles.tabs}>{([["accounts", "账户列表"], ["roles", "角色与能力"], ["history", "操作记录"]] as const).map(([value, label]) => <button key={value} aria-pressed={tab === value} disabled={Boolean(edit)} onClick={() => setTab(value)}>{label}</button>)}</div>
    {message ? <p className={styles.notice} role="status">{message}</p> : null}
    {recovery || broken ? <div className={styles.notice}><p>原账户操作的结果尚未确认。只保留了请求标识，没有在浏览器保存密码或账户资料。</p>{recovery ? <><button disabled={locked || Boolean(edit)} onClick={() => void lookup()}>查回原操作</button><button disabled={locked || Boolean(edit)} onClick={() => setStopping(true)}>停止尚未执行的原请求</button></> : <p>请恢复会话存储后重新打开本页读取原编号；无法读取时请先核对操作记录，不能直接开始另一项写入。</p>}</div> : null}
    {tab === "roles" ? <Roles actor={actor} /> : tab === "history" ? <History actor={actor} /> : <div className={styles.grid}><section aria-label="账户列表"><form className={styles.filters} onSubmit={event => { event.preventDefault(); setQ(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }}><label className={styles.search}><input name="q" defaultValue={q} maxLength={180} placeholder="搜索姓名、账号或邮箱…" aria-label="搜索账户" /><button>搜索</button></label><label>角色<select value={role} onChange={event => { setRole(event.target.value); setPage(1); }}><option value="">全部角色</option><option value="reader">读者</option><option value="editor">内容编辑</option><option value="admin">系统管理员 / 馆长</option></select></label><label>状态<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option><option value="active">已启用</option><option value="inactive">已停用 / 邀请已撤销</option><option value="pending_activation">待激活（含过期）</option></select></label></form>
      {accounts.error ? <div className={styles.error} role="alert">{accounts.error}<button onClick={() => { setPage(1); accounts.reload(); }}>重新读取</button></div> : !data ? <p role="status">正在读取账户…</p> : <><table className={styles.table}><thead><tr><th>姓名 / 账号</th><th>角色</th><th>状态</th><th>最后登录</th></tr></thead><tbody>{data.results.map(row => <tr key={row.id} data-selected={selected === row.id}><td><button className={styles.name} disabled={Boolean(edit) || locked} onClick={() => setSelected(row.id)} aria-label={`查看${row.display_name}账户`}><span className={styles.identity}><AccountAvatar owner={actor} target={String(row.id)} revision={row.avatar_revision} name={row.display_name} className={styles.listAvatar} /><span><strong>{row.display_name}</strong><small>{row.username}</small><small>{row.email}</small></span></span></button></td><td><span className={styles.badge}>{row.role_label}</span></td><td><span className={styles.status} data-active={row.is_active} data-pending={row.activation_state.startsWith("invitation_") && row.activation_state !== "invitation_revoked" || row.activation_state === "pending_activation"}>{activationLabel(row)}</span></td><td>{stamp(row.last_login)}</td></tr>)}</tbody></table>{!data.results.length ? <p className={styles.empty}>当前条件下没有账户。</p> : null}<Pager page={page} total={data.total_pages} count={data.count} onPage={setPage} /><label className={styles.muted}>每页 <select value={size} onChange={event => { setSize(Number(event.target.value)); setPage(1); }}>{[10, 20, 50].map(value => <option key={value}>{value}</option>)}</select> 个账户</label></>}
    </section><aside className={styles.detail}>{edit?.operation === "update" ? <><header className={styles.profile}><div><h2>编辑账户与角色</h2><p>{edit.original?.display_name} · {edit.original?.email}</p></div><button disabled={locked} onClick={closeEditor}>返回详情</button></header>{editor}</> : data?.selected ? <Detail key={`${data.selected.id}:${data.selected.version}`} actor={actor} user={data.selected} blocked={blocked} onEdit={operation => setEdit({ operation, original: data.selected })} /> : <div className={styles.empty}>选择一个账户，核对资料与实际能力。</div>}</aside></div>}
    {edit && edit.operation !== "update" ? <Dialog open onRequestClose={closeEditor} className={styles.dialog} aria-label={editTitle(edit.operation)}><header><h2>{editTitle(edit.operation)}</h2><button disabled={locked} aria-label="关闭" onClick={closeEditor}>×</button></header>{editor}</Dialog> : null}
    <Dialog open={closing} onRequestClose={() => setClosing(false)} className={styles.dialog} aria-label="离开账户编辑"><h2>离开当前编辑？</h2><p>{recovery ? "原操作结果仍待确认。关闭后将保留原编号，可查回结果或停止尚未执行的请求；密码和其他未保存输入会清除。" : "当前输入尚未保存，关闭后将丢弃本次修改。"}</p><div className={styles.actions}><button onClick={() => setClosing(false)}>继续编辑</button><button disabled={locked} onClick={() => { setClosing(false); setEdit(null); }}>关闭编辑</button></div></Dialog>
    <Dialog open={stopping} onRequestClose={() => { if (!locked) setStopping(false); }} className={styles.dialog} aria-label="停止尚未执行的账户请求"><h2>核对并停止原请求</h2><p>先核对服务器记录。若已执行，将返回已保存结果；若尚未执行，将停止该请求并阻止迟到的原提交。不会撤销已保存账户、重置密码或创建新账户。</p><div className={styles.actions}><button disabled={locked} onClick={() => setStopping(false)}>返回</button><button disabled={locked} onClick={() => void lookup(true)}>{locked ? "正在核对…" : "核对并停止"}</button></div>{message ? <p role="status">{message}</p> : null}</Dialog>
  </main>;
}

function Detail({ actor, user, blocked, onEdit }: { actor: string; user: ManagedUser; blocked: boolean; onEdit: (operation: AccountInput["operation"]) => void }) {
  const [tab, setTab] = useState<"base" | "roles" | "history">("roles");
  return <><header className={styles.profile}><AccountAvatar owner={actor} target={String(user.id)} revision={user.avatar_revision} name={user.display_name} className={styles.avatar} /><div><h2>{user.display_name}</h2><span className={styles.badge}>{user.role_label}</span><p>{user.email}</p><p>最后登录：{stamp(user.last_login)}</p></div><button disabled={blocked || !user.can_edit} onClick={() => onEdit("update")}>编辑账户</button></header><div className={styles.tabs}>{([["base", "基本信息"], ["roles", "角色与权限"], ["history", "操作记录"]] as const).map(([value, label]) => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</div>
    {tab === "history" ? <History actor={actor} userId={user.id} /> : tab === "base" ? <><dl className={styles.facts}><dt>账号</dt><dd>{user.username}</dd><dt>邮箱</dt><dd>{user.email}</dd><dt>注册时间</dt><dd>{stamp(user.date_joined)}</dd><dt>当前状态</dt><dd>{activationLabel(user)}</dd></dl><button disabled={blocked || !user.can_edit} onClick={() => onEdit("password")}>设置新密码</button></> : <><h3>当前角色</h3><span className={styles.badge}>{user.role_label}</span><p className={styles.muted}>共 {user.capabilities.length} 项后台能力。变更前会列出实际保留、新增和失去的能力。</p><p>{user.is_active ? "可管理本人的研究、笔记、书单与计划。" : `${activationLabel(user)}；目前不能登录，本人资料仍保留。`}</p><div className={styles.actions}><button disabled={blocked || !user.can_edit} onClick={() => onEdit("update")}>修改角色与状态</button></div></>}
    {user.can_edit && (user.can_renew_invitation || user.can_revoke_invitation) ? <AccountInvitation actor={actor} user={user} blocked={blocked} onEdit={onEdit} /> : null}
    <p className={styles.notice}>{user.notice}</p>
  </>;
}

function Roles({ actor }: { actor: string }) {
  const load = useCallback((path: string, signal: AbortSignal) => accountRequest<AccountRoles>(actor, path, { signal }), [actor]);
  const resource = usePersistentWorkspace<AccountRoles>("roles/", actor, undefined, load);
  return resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : !resource.data ? <p role="status">正在读取实际能力定义…</p> : <><p className={styles.notice}>权限由服务器按当前账户核对。馆长来自既有身份配置，不能通过分配普通角色取得。旧审核角色沿现有兼容规则显示为内容编辑。</p><div className={styles.roleGrid}>{resource.data.roles.map(role => <article key={role.id}><h2>{role.label}</h2><p>{role.public_access}</p><p>{role.private_access}</p><ul>{role.capabilities.map(cap => <li key={cap.id}>{cap.label}</li>)}</ul>{!role.capabilities.length ? <p className={styles.muted}>没有后台管理能力。</p> : null}</article>)}</div></>;
}

function History({ actor, userId }: { actor: string; userId?: number }) {
  const [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => accountRequest<AccountHistory>(actor, path, { signal }), [actor]);
  const resource = usePersistentWorkspace<AccountHistory>(`history/?page=${page}${userId ? `&user_id=${userId}` : ""}`, actor, undefined, load);
  const data = resource.error ? null : resource.data;
  return resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={() => { setPage(1); resource.reload(); }}>重新读取</button></p> : !data ? <p role="status">正在读取操作记录…</p> : <><table className={styles.table}><thead><tr><th>时间</th><th>操作者</th><th>操作内容</th></tr></thead><tbody>{data.results.map(row => <tr key={row.id}><td>{stamp(row.created_at)}</td><td>{row.actor}</td><td>{row.action}<small>账户 #{row.user_id}</small>{Object.entries(row.after).map(([key, value]) => <small key={key}>{({ display_name: "显示名", role: "角色", is_active: "状态" })[key] || key}：{key === "is_active" ? value ? "已启用" : "已停用" : key === "role" ? ({ admin: "系统管理员", editor: "内容编辑", reviewer: "原审核角色", reader: "读者" })[String(value)] || String(value) : String(value)}</small>)}{row.password_reset ? <small>已设置新密码，不记录密码内容。</small> : null}{row.sessions_revoked ? <small>原登录凭证已失效。</small> : null}</td></tr>)}</tbody></table>{!data.results.length ? <p className={styles.empty}>暂无账户操作记录。</p> : null}<Pager page={page} total={data.total_pages} count={data.count} onPage={setPage} /></>;
}

function Editor(props: { actor: string; edit: Edit; canAssign: boolean; onDirty: (value: boolean) => void; onLocked: (value: boolean) => void; onPending: (id: string) => void; onClear: () => boolean; onDone: (receipt: AccountReceipt) => boolean; onReload: (row: ManagedUser) => void }) {
  const { actor, edit, canAssign, onDirty, onLocked, onPending, onClear, onDone, onReload } = props;
  const original = edit.original;
  const identityEditing = edit.operation === "create" || edit.operation === "update";
  const [invite, setInvite] = useState(edit.operation === "create");
  const [name, setName] = useState(original?.display_name || ""), [username, setUsername] = useState(""), [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const [role, setRole] = useState<AccountInput["role"]>((original?.role === "reviewer" ? "editor" : original?.role || "reader") as AccountInput["role"]), [active, setActive] = useState(original?.is_active || false);
  const [prepared, setPrepared] = useState<{ input: AccountInput; preview: AccountPreview } | null>(null), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false), [invalid, setInvalid] = useState(false);
  const controller = useRef<AbortController | null>(null), sending = useRef(false), pending = useRef<AccountCommand | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; const off = subscribeToSessionChanges(() => request.abort()); return () => { request.abort(); off(); onLocked(false); }; }, [actor, onLocked]);
  const input: AccountInput = edit.operation === "create" ? { operation: "create", username, email, display_name: name, role: role || "reader", is_active: invite ? false : active, invite, ...(!invite ? { password } : {}) } : edit.operation === "password" ? { operation: "password", user_id: original!.id, expected_version: original!.version, password } : edit.operation === "update" ? { operation: "update", user_id: original!.id, expected_version: original!.version, ...(!original?.is_owner ? { display_name: name } : {}), is_active: active, ...(role !== (original?.role === "reviewer" ? "editor" : original?.role) ? { role } : {}) } : { operation: edit.operation, user_id: original!.id, expected_version: original!.version };
  const draft = { name, username, email, password, role, active, uncertain, invite };
  const dirty = useUnsavedForm(draft, { name: original?.display_name || "", username: "", email: "", password: "", role: original?.role === "reviewer" ? "editor" : original?.role || "reader", active: original?.is_active || false, uncertain: false, invite: edit.operation === "create" });
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  const matches = prepared && JSON.stringify(prepared.input) === JSON.stringify(input);
  async function run<T>(action: (signal: AbortSignal) => Promise<T>, done: (value: T) => void) {
    const request = controller.current; if (!request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true); onLocked(true); setMessage("");
    try { const result = await withPrivateOwner(actor, () => action(request.signal), request.signal); if (!request.signal.aborted) done(result); }
    catch (reason) {
      if (request.signal.aborted) return;
      if (reason instanceof ApiRequestError && [401, 403].includes(reason.status)) setInvalid(true);
      if (reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && [400, 409].includes(reason.status) && onClear()) { pending.current = null; setUncertain(false); setPrepared(null); setConfirmed(false); }
      setMessage(reason instanceof Error ? reason.message : "操作结果尚未确认，请保留原请求。密码仅留在本次弹层内存。");
    } finally { sending.current = false; if (!request.signal.aborted) { setBusy(false); onLocked(false); } }
  }
  function preview(event: FormEvent) { event.preventDefault(); if (uncertain) return; void run(signal => accountRequest<AccountPreview>(actor, "preview/", { method: "POST", signal, body: JSON.stringify(input) }), value => { setPrepared({ input, preview: value }); setConfirmed(false); }); }
  function save() {
    if (sending.current || !matches || !confirmed) return;
    const data = pending.current || { ...prepared.input, request_id: createRequestKey(), preview_hash: prepared.preview.preview_hash, confirmed: true };
    try { onPending(data.request_id); } catch { setMessage("无法保存最少请求标识，本次未提交，请允许会话存储后重试。"); return; }
    pending.current = data; setUncertain(true);
    void run(signal => accountRequest<AccountReceipt>(actor, "command/", { method: "POST", signal, body: JSON.stringify(data) }), value => { if (value.request_id !== data.request_id || value.state !== "applied" || !value.user_id) throw Error("返回回执与原账户请求不一致，请查回核对。"); if (onDone(value)) { pending.current = null; setPassword(""); } });
  }
  async function reload() {
    if (!original || uncertain || !window.confirm("读取最新账户资料会清空本弹层未保存的修改，继续吗？")) return;
    void run(signal => accountRequest<AccountDirectory>(actor, `workspace/?user_id=${original.id}`, { signal }), value => { if (value.selected) { setName(value.selected.display_name); setRole((value.selected.role === "reviewer" ? "editor" : value.selected.role) as AccountInput["role"]); setActive(value.selected.is_active); setPrepared(null); setConfirmed(false); setPassword(""); onReload(value.selected); } });
  }
  if (invalid) return <div className={styles.error} role="alert"><p>{message}</p><p>操作账户或凭证已变化。请重新登录，再从账户管理查回请求结果。</p><Link href="/login?next=%2Fadmin%2Fusers">重新登录</Link></div>;
  return <form className={styles.editor} onSubmit={preview}><fieldset disabled={busy || uncertain}>
    {identityEditing ? <label>显示名<input required maxLength={120} value={name} disabled={Boolean(original?.is_owner)} onChange={event => setName(event.target.value)} /></label> : <p>目标账户：{original?.display_name} · {original?.email}</p>}
    {edit.operation === "create" ? <><label>账号<input required minLength={4} maxLength={20} pattern="[A-Za-z0-9_\u4e00-\u9fff]{4,20}" autoComplete="off" value={username} onChange={event => setUsername(event.target.value)} /></label><label>邮箱<input required type="email" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} /></label></> : null}
    {edit.operation === "create" ? <label>开通方式<select value={invite ? "invite" : "password"} onChange={event => { setInvite(event.target.value === "invite"); setPassword(""); setActive(false); setPrepared(null); }}><option value="invite">邀请本人设置密码后激活</option><option value="password">由管理员设置初始密码</option></select><small>邀请有效期24小时，保存后在账户详情复制链接，由你交给本人。</small></label> : null}
    {edit.operation === "password" || edit.operation === "create" && !invite ? <label>新密码<input required type="password" minLength={10} maxLength={128} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /><small>不读取旧密码，不将密码写入操作记录或浏览器存储。</small></label> : null}
    {identityEditing ? <><label>角色<select value={role} disabled={original ? !original.can_change_role : !canAssign} onChange={event => setRole(event.target.value as AccountInput["role"])}><option value="reader">读者</option><option value="editor">内容编辑</option><option value="admin">系统管理员</option></select><small>只有馆长可分配角色；此操作不能授予馆长身份。</small></label><label className={styles.check}><input type="checkbox" checked={invite ? false : active} disabled={invite || Boolean(original?.is_owner || String(original?.id) === actor)} onChange={event => setActive(event.target.checked)} />启用账户，允许正常登录</label></> : null}
    <button type="submit" disabled={busy || uncertain}>预览账户与能力变化</button></fieldset>
    {message ? <p className={styles.error} role="alert">{message}</p> : null}
    {matches ? <><div className={styles.previewHeader}><strong>{prepared.preview.target.display_name}</strong><p>{original?.role_label || "新账户"} → {prepared.preview.target.role_label} · {prepared.preview.target.is_active ? "已启用" : input.invite || edit.operation === "invite" ? "待本人激活" : "未启用"}</p><p>{prepared.preview.public_access}</p><p>{prepared.preview.private_access}</p></div><div className={styles.deltaGrid}>{(["retained", "gained", "lost"] as const).map(kind => <section className={styles.delta} data-kind={kind} key={kind}><h3>{({ retained: "保留", gained: "新增", lost: "失去" })[kind]} {prepared.preview[kind].length} 项能力</h3><ul>{prepared.preview[kind].map(cap => <li key={cap.id}>{cap.label}</li>)}</ul></section>)}</div><p className={styles.notice}>{prepared.preview.notice}</p>{input.invite || edit.operation === "invite" ? <section className={styles.delta}><h3>本人激活后获得 {prepared.preview.activation_capabilities.length} 项后台能力</h3>{prepared.preview.activation_capabilities.length ? <ul>{prepared.preview.activation_capabilities.map(cap => <li key={cap.id}>{cap.label}</li>)}</ul> : <p>仅使用本人读者中心，不授予后台能力。</p>}</section> : null}{prepared.preview.sessions_revoked ? <p>确认后此账户的旧登录凭证将失效，需要重新登录。</p> : null}<label className={styles.check}><input type="checkbox" checked={confirmed} disabled={busy || uncertain} onChange={event => setConfirmed(event.target.checked)} />我已核对目标账户、能力变化和登录影响</label><footer><button type="button" className={styles.primary} disabled={busy || !confirmed} onClick={save}>{busy ? "正在提交…" : uncertain ? "重试原请求" : "确认保存"}</button></footer></> : null}
    {uncertain ? <p className={styles.notice}>当前只可重试原请求。关闭弹层后可查回结果；不会据新输入自动重复创建账户或设置密码。</p> : null}{original && !uncertain ? <button type="button" disabled={busy} onClick={() => void reload()}>读取最新账户资料</button> : null}
  </form>;
}
