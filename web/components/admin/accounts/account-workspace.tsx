"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { accountRequest, type AccountCommand, type AccountDirectory, type AccountHistory, type AccountInput, type AccountPreview, type AccountReceipt, type AccountRoles, type ManagedUser } from "@/lib/api/account-management.client";
import { Dialog } from "@/components/ui/dialog";
import styles from "./account-workspace.module.css";

const stamp = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "尚无登录记录";
const storageKey = (actor: string) => `stl-account-command:${actor}`;
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
  function clearRecovery() { sessionStorage.removeItem(storageKey(actor)); setRecovery(null); setBroken(false); }
  function pending(id: string) { sessionStorage.setItem(storageKey(actor), id); setRecovery(id); }
  async function lookup() {
    const request = controller.current;
    if (!recovery || !request || request.signal.aborted || recovering.current) return;
    recovering.current = true; setLocked(true); setMessage("");
    try {
      const result = await withPrivateOwner(actor, () => accountRequest<AccountReceipt>(actor, `receipt/?${new URLSearchParams({ request_id: recovery })}`, { signal: request.signal }), request.signal);
      if (result.request_id !== recovery) throw Error("返回回执与原请求不一致。");
      if (!request.signal.aborted) { clearRecovery(); setSelected(result.exists ? result.user_id : null); accounts.reload(); setMessage(result.exists ? "原操作已保存，已定位目标账户。" : "原操作已完成，目标账户随后已删除，不会重新创建。"); }
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "无法查回原请求，请先核对操作记录。"); }
    finally { recovering.current = false; if (!request.signal.aborted) setLocked(false); }
  }
  const blocked = locked || !ready || Boolean(recovery) || broken;
  const editor = edit ? <Editor actor={actor} edit={edit} canAssign={data?.can_assign_roles || false} onLocked={setLocked} onPending={pending} onClear={clearRecovery} onDone={receipt => { clearRecovery(); setEdit(null); setSelected(receipt.exists ? receipt.user_id : null); accounts.reload(); setMessage("账户操作已保存，操作记录已同步。"); }} onReload={row => { setEdit({ ...edit, original: row }); accounts.reload(); }} /> : null;
  return <main className={styles.page}><p className={styles.crumb}>系统 › 账户与权限</p><header className={styles.heading}><div><h1>账户、角色与权限</h1><p>管理谁能策划、发布和维护系统，不默认查看私人研究。</p></div><button className={styles.primary} disabled={blocked || Boolean(edit)} onClick={() => setEdit({ operation: "create", original: null })}>＋ 新建账户</button></header>
    <div className={styles.tabs}>{([["accounts", "账户列表"], ["roles", "角色与能力"], ["history", "操作记录"]] as const).map(([value, label]) => <button key={value} aria-pressed={tab === value} disabled={Boolean(edit)} onClick={() => setTab(value)}>{label}</button>)}</div>
    {message ? <p className={styles.notice} role="status">{message}</p> : null}
    {recovery || broken ? <div className={styles.notice}><p>原账户操作的结果尚未确认。只保留了请求标识，没有在浏览器保存密码或账户资料。</p>{recovery ? <button disabled={locked || Boolean(edit)} onClick={() => void lookup()}>查回原操作</button> : null}<button disabled={locked || Boolean(edit)} onClick={() => { if (window.confirm("请先核对操作记录与目标账户。确认结束本次请求恢复？已保存操作不会撤销。")) clearRecovery(); }}>已核对，结束恢复</button></div> : null}
    {tab === "roles" ? <Roles actor={actor} /> : tab === "history" ? <History actor={actor} /> : <div className={styles.grid}><section aria-label="账户列表"><form className={styles.filters} onSubmit={event => { event.preventDefault(); setQ(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }}><label className={styles.search}><input name="q" defaultValue={q} maxLength={180} placeholder="搜索姓名、账号或邮箱…" aria-label="搜索账户" /><button>搜索</button></label><label>角色<select value={role} onChange={event => { setRole(event.target.value); setPage(1); }}><option value="">全部角色</option><option value="reader">读者</option><option value="editor">内容编辑</option><option value="admin">系统管理员 / 馆长</option></select></label><label>状态<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option><option value="active">已启用</option><option value="inactive">已停用</option></select></label></form>
      {accounts.error ? <div className={styles.error} role="alert">{accounts.error}<button onClick={() => { setPage(1); accounts.reload(); }}>重新读取</button></div> : !data ? <p role="status">正在读取账户…</p> : <><table className={styles.table}><thead><tr><th>姓名 / 账号</th><th>角色</th><th>状态</th><th>最后登录</th></tr></thead><tbody>{data.results.map(row => <tr key={row.id} data-selected={selected === row.id}><td><button className={styles.name} disabled={Boolean(edit) || locked} onClick={() => setSelected(row.id)} aria-label={`查看${row.display_name}账户`}><strong>{row.display_name}</strong><small>{row.username}</small><small>{row.email}</small></button></td><td><span className={styles.badge}>{row.role_label}</span></td><td><span className={styles.status} data-active={row.is_active}>{row.is_active ? "已启用" : "已停用"}</span></td><td>{stamp(row.last_login)}</td></tr>)}</tbody></table>{!data.results.length ? <p className={styles.empty}>当前条件下没有账户。</p> : null}<Pager page={page} total={data.total_pages} count={data.count} onPage={setPage} /><label className={styles.muted}>每页 <select value={size} onChange={event => { setSize(Number(event.target.value)); setPage(1); }}>{[10, 20, 50].map(value => <option key={value}>{value}</option>)}</select> 个账户</label></>}
    </section><aside className={styles.detail}>{edit?.operation === "update" ? <><header className={styles.profile}><div><h2>编辑账户与角色</h2><p>{edit.original?.display_name} · {edit.original?.email}</p></div><button disabled={locked} onClick={() => setEdit(null)}>返回详情</button></header>{editor}</> : data?.selected ? <Detail key={`${data.selected.id}:${data.selected.version}`} actor={actor} user={data.selected} blocked={blocked} onEdit={operation => setEdit({ operation, original: data.selected })} /> : <div className={styles.empty}>选择一个账户，核对资料与实际能力。</div>}</aside></div>}
    {edit && edit.operation !== "update" ? <Dialog open onRequestClose={() => { if (!locked) setEdit(null); }} className={styles.dialog} aria-label={edit.operation === "create" ? "新建账户" : edit.operation === "password" ? "设置新密码" : "编辑账户与角色"}><header><h2>{edit.operation === "create" ? "新建账户" : edit.operation === "password" ? "设置新密码" : "编辑账户与角色"}</h2><button disabled={locked} aria-label="关闭" onClick={() => setEdit(null)}>×</button></header>{editor}</Dialog> : null}
  </main>;
}

function Detail({ actor, user, blocked, onEdit }: { actor: string; user: ManagedUser; blocked: boolean; onEdit: (operation: AccountInput["operation"]) => void }) {
  const [tab, setTab] = useState<"base" | "roles" | "history">("roles");
  return <><header className={styles.profile}><span className={styles.avatar} aria-hidden>{user.display_name.slice(0, 1) || "人"}</span><div><h2>{user.display_name}</h2><span className={styles.badge}>{user.role_label}</span><p>{user.email}</p><p>最后登录：{stamp(user.last_login)}</p></div><button disabled={blocked || !user.can_edit} onClick={() => onEdit("update")}>编辑账户</button></header><div className={styles.tabs}>{([["base", "基本信息"], ["roles", "角色与权限"], ["history", "操作记录"]] as const).map(([value, label]) => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</div>
    {tab === "history" ? <History actor={actor} userId={user.id} /> : tab === "base" ? <><dl className={styles.facts}><dt>账号</dt><dd>{user.username}</dd><dt>邮箱</dt><dd>{user.email}</dd><dt>注册时间</dt><dd>{stamp(user.date_joined)}</dd><dt>当前状态</dt><dd>{user.is_active ? "已启用" : "已停用"}</dd></dl><button disabled={blocked || !user.can_edit} onClick={() => onEdit("password")}>设置新密码</button></> : <><h3>当前角色</h3><span className={styles.badge}>{user.role_label}</span><p className={styles.muted}>共 {user.capabilities.length} 项后台能力。变更前会列出实际保留、新增和失去的能力。</p><p>{user.is_active ? "可管理本人的研究、笔记、书单与计划。" : "当前账户已停用；本人资料仍保留。"}</p><div className={styles.actions}><button disabled={blocked || !user.can_edit} onClick={() => onEdit("update")}>修改角色与状态</button></div></>}
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

function Editor(props: { actor: string; edit: Edit; canAssign: boolean; onLocked: (value: boolean) => void; onPending: (id: string) => void; onClear: () => void; onDone: (receipt: AccountReceipt) => void; onReload: (row: ManagedUser) => void }) {
  const { actor, edit, canAssign, onLocked, onPending, onClear, onDone, onReload } = props;
  const original = edit.original;
  const [name, setName] = useState(original?.display_name || ""), [username, setUsername] = useState(""), [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const [role, setRole] = useState<AccountInput["role"]>((original?.role === "reviewer" ? "editor" : original?.role || "reader") as AccountInput["role"]), [active, setActive] = useState(original?.is_active || false);
  const [prepared, setPrepared] = useState<{ input: AccountInput; preview: AccountPreview } | null>(null), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false), [invalid, setInvalid] = useState(false);
  const controller = useRef<AbortController | null>(null), sending = useRef(false), pending = useRef<AccountCommand | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; const off = subscribeToSessionChanges(() => request.abort()); return () => { request.abort(); off(); onLocked(false); }; }, [actor, onLocked]);
  const input: AccountInput = edit.operation === "create" ? { operation: "create", username, email, display_name: name, role: role || "reader", is_active: active, password } : edit.operation === "password" ? { operation: "password", user_id: original!.id, expected_version: original!.version, password } : { operation: "update", user_id: original!.id, expected_version: original!.version, ...(!original?.is_owner ? { display_name: name } : {}), is_active: active, ...(role !== (original?.role === "reviewer" ? "editor" : original?.role) ? { role } : {}) };
  const matches = prepared && JSON.stringify(prepared.input) === JSON.stringify(input);
  async function run<T>(action: (signal: AbortSignal) => Promise<T>, done: (value: T) => void) {
    const request = controller.current; if (!request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true); onLocked(true); setMessage("");
    try { const result = await withPrivateOwner(actor, () => action(request.signal), request.signal); if (!request.signal.aborted) done(result); }
    catch (reason) {
      if (request.signal.aborted) return;
      if (reason instanceof ApiRequestError && [401, 403].includes(reason.status)) setInvalid(true);
      if (reason instanceof ApiRequestError && [400, 404, 409].includes(reason.status)) { pending.current = null; setUncertain(false); onClear(); setPrepared(null); setConfirmed(false); }
      setMessage(reason instanceof Error ? reason.message : "操作结果尚未确认，请保留原请求。密码仅留在本次弹层内存。");
    } finally { sending.current = false; if (!request.signal.aborted) { setBusy(false); onLocked(false); } }
  }
  function preview(event: FormEvent) { event.preventDefault(); if (uncertain) return; void run(signal => accountRequest<AccountPreview>(actor, "preview/", { method: "POST", signal, body: JSON.stringify(input) }), value => { setPrepared({ input, preview: value }); setConfirmed(false); }); }
  function save() {
    if (sending.current || !matches || !confirmed) return;
    const data = pending.current || { ...prepared.input, request_id: crypto.randomUUID(), preview_hash: prepared.preview.preview_hash, confirmed: true };
    try { onPending(data.request_id); } catch { setMessage("无法保存最少请求标识，本次未提交，请允许会话存储后重试。"); return; }
    pending.current = data; setUncertain(true);
    void run(signal => accountRequest<AccountReceipt>(actor, "command/", { method: "POST", signal, body: JSON.stringify(data) }), value => { pending.current = null; setPassword(""); onDone(value); });
  }
  async function reload() {
    if (!original || uncertain || !window.confirm("读取最新账户资料会清空本弹层未保存的修改，继续吗？")) return;
    void run(signal => accountRequest<AccountDirectory>(actor, `workspace/?user_id=${original.id}`, { signal }), value => { if (value.selected) { setName(value.selected.display_name); setRole((value.selected.role === "reviewer" ? "editor" : value.selected.role) as AccountInput["role"]); setActive(value.selected.is_active); setPrepared(null); setConfirmed(false); setPassword(""); onReload(value.selected); } });
  }
  if (invalid) return <div className={styles.error} role="alert"><p>{message}</p><p>操作账户或凭证已变化。请重新登录，再从账户管理查回请求结果。</p><Link href="/login?next=%2Fadmin%2Fusers">重新登录</Link></div>;
  return <form className={styles.editor} onSubmit={preview}><fieldset disabled={busy || uncertain}>
    {edit.operation !== "password" ? <label>显示名<input required maxLength={120} value={name} disabled={Boolean(original?.is_owner)} onChange={event => setName(event.target.value)} /></label> : <p>目标账户：{original?.display_name} · {original?.email}</p>}
    {edit.operation === "create" ? <><label>账号<input required minLength={4} maxLength={20} pattern="[A-Za-z0-9_\u4e00-\u9fff]{4,20}" autoComplete="off" value={username} onChange={event => setUsername(event.target.value)} /></label><label>邮箱<input required type="email" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} /></label></> : null}
    {edit.operation !== "update" ? <label>新密码<input required type="password" minLength={10} maxLength={128} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /><small>不读取旧密码，不将密码写入操作记录或浏览器存储。</small></label> : null}
    {edit.operation !== "password" ? <><label>角色<select value={role} disabled={original ? !original.can_change_role : !canAssign} onChange={event => setRole(event.target.value as AccountInput["role"])}><option value="reader">读者</option><option value="editor">内容编辑</option><option value="admin">系统管理员</option></select><small>只有馆长可分配角色；此操作不能授予馆长身份。</small></label><label className={styles.check}><input type="checkbox" checked={active} disabled={Boolean(original?.is_owner || String(original?.id) === actor)} onChange={event => setActive(event.target.checked)} />启用账户，允许正常登录</label></> : null}
    <button type="submit" disabled={busy || uncertain}>预览账户与能力变化</button></fieldset>
    {message ? <p className={styles.error} role="alert">{message}</p> : null}
    {matches ? <><div className={styles.previewHeader}><strong>{prepared.preview.target.display_name}</strong><p>{original?.role_label || "新账户"} → {prepared.preview.target.role_label} · {prepared.preview.target.is_active ? "已启用" : "已停用"}</p><p>{prepared.preview.public_access}</p><p>{prepared.preview.private_access}</p></div><div className={styles.deltaGrid}>{(["retained", "gained", "lost"] as const).map(kind => <section className={styles.delta} data-kind={kind} key={kind}><h3>{({ retained: "保留", gained: "新增", lost: "失去" })[kind]} {prepared.preview[kind].length} 项能力</h3><ul>{prepared.preview[kind].map(cap => <li key={cap.id}>{cap.label}</li>)}</ul></section>)}</div><p className={styles.notice}>{prepared.preview.notice}</p>{prepared.preview.sessions_revoked ? <p>确认后此账户的旧登录凭证将失效，需要重新登录。</p> : null}<label className={styles.check}><input type="checkbox" checked={confirmed} disabled={busy || uncertain} onChange={event => setConfirmed(event.target.checked)} />我已核对目标账户、能力变化和登录影响</label><footer><button type="button" className={styles.primary} disabled={busy || !confirmed} onClick={save}>{busy ? "正在提交…" : uncertain ? "重试原请求" : "确认保存"}</button></footer></> : null}
    {uncertain ? <p className={styles.notice}>当前只可重试原请求。关闭弹层后可查回结果；不会据新输入自动重复创建账户或设置密码。</p> : null}{original && !uncertain ? <button type="button" disabled={busy} onClick={() => void reload()}>读取最新账户资料</button> : null}
  </form>;
}
