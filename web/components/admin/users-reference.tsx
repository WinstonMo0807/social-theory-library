"use client";

import { useState, type FormEvent } from "react";
import { LockKeyhole, Plus, Search } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { useActionGuard } from "@/lib/use-action-guard";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { PageHeader } from "@/components/admin-ui";

type Account = { id: number; email: string; display_name: string; role: "reader" | "reviewer" | "editor" | "admin"; is_active: boolean; date_joined: string; last_login: string | null; is_library_owner: boolean; can_manage_admin_role: boolean };
type AccountPage = { count: number; previous: string | null; next: string | null; results: Account[] };
const roles = { reader: "读者", reviewer: "内容编辑", editor: "内容编辑", admin: "系统管理员" };
const roleDescriptions = [
  ["系统所有者", "拥有系统的全部权限，包括用户管理、系统设置和数据维护。角色变更、人物合并、正式备份恢复及版本切换仅系统所有者可以执行。"],
  ["系统管理员", "可编辑和发布内容，并维护处理任务与运行服务，管理用户账户。"],
  ["内容编辑", "可编辑和发布网站的内容，包括馆藏、理论流派、学者、每日荐读及网站页面。"],
  ["读者", "可阅读公开内容，并管理自己的私人阅读内容；不能进入管理端。"],
];
const timestamp = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const formFor = (account: Account) => ({ display_name: account.display_name, role: account.role === "reviewer" ? "editor" : account.role, is_active: account.is_active });

export function UsersAdmin() {
  const actor = useAdminSession();
  const allowed = hasAdminCapability(actor, "can_manage_users");
  const [page, setPage] = useState(1), [search, setSearch] = useState("");
  const resource = useApiResource<AccountPage>(allowed ? `/auth/users/?page=${page}&search=${encodeURIComponent(search)}` : "", getServerSessionCredential());
  const [selected, setSelected] = useState<Account | null>(null);
  const [draft, setDraft] = useState<ReturnType<typeof formFor> | null>(null);
  const [saved, setSaved] = useState<ReturnType<typeof formFor> | null>(null);
  const [tab, setTab] = useState("permissions"), [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [failed, setFailed] = useState(false);
  const dirty = useUnsavedForm(draft, saved);
  const { startAction, finishAction } = useActionGuard();
  const canManageRoles = hasAdminCapability(actor, "can_manage_roles");
  const canEditSelected = Boolean(selected && (!selected.is_library_owner || canManageRoles) && (selected.role !== "admin" || selected.id === actor?.id || canManageRoles));
  function select(account: Account) {
    if (busy || (dirty && !window.confirm("当前账户修改尚未保存，确定切换并放弃修改吗？"))) return;
    setSelected(account); setDraft(formFor(account)); setSaved(formFor(account)); setNewPassword(""); setMessage("");
  }
  async function saveAccount() {
    if (!selected || !draft || !canEditSelected || busy || !startAction("account")) return;
    setBusy(true); setMessage(""); setFailed(false);
    try {
      const result = await apiRequest<Partial<Account>>(`/auth/users/${selected.id}/`, { method: "PATCH", body: JSON.stringify(draft) }, getServerSessionCredential());
      const updated = { ...selected, ...result };
      setSelected(updated); setDraft(formFor(updated)); setSaved(formFor(updated)); resource.retry(); setMessage("账户修改已保存。");
    } catch (reason) { setFailed(true); setMessage(reason instanceof Error ? reason.message : "账户更新失败，当前输入已保留。"); }
    finally { setBusy(false); finishAction("account"); }
  }
  async function reset(event: FormEvent) {
    event.preventDefault();
    if (!selected || !canEditSelected || busy || !startAction("account")) return;
    setBusy(true); setMessage(""); setFailed(false);
    try { await apiRequest(`/auth/users/${selected.id}/set-password/`, { method: "POST", body: JSON.stringify({ new_password: newPassword }) }, getServerSessionCredential()); setNewPassword(""); setMessage("新密码已设置。"); }
    catch (reason) { setFailed(true); setMessage(reason instanceof Error ? reason.message : "设置失败。"); }
    finally { setBusy(false); finishAction("account"); }
  }
  if (!allowed) return <div className="admin-page"><PageHeader title="当前账户没有用户管理权限" /></div>;
  return <div className="admin-page users-reference"><PageHeader title="编辑账号" description="管理用户的登录信息与权限，控制其在网站后台的可用功能。" />
    <div className="users-reference-grid"><section className="admin-panel users-reference-list"><header><h2>用户列表</h2><button className="button" type="button" disabled title="当前没有管理员新建用户接口"><Plus size={16}/>新建用户</button></header>
      <form className="reference-search" onSubmit={event => { event.preventDefault(); setSearch(String(new FormData(event.currentTarget).get("search") || "")); setPage(1); }}><Search size={17}/><input name="search" aria-label="搜索用户姓名或邮箱" placeholder="搜索用户姓名或邮箱"/><button type="submit">搜索</button></form>
      {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重试</button></p> : null}
      <div className="admin-table-scroll"><table><thead><tr><th>姓名</th><th>角色</th><th>账号状态</th><th>最后登录</th><th>操作</th></tr></thead><tbody>{resource.data?.results.map(account => <tr key={account.id} data-selected={account.id === selected?.id}><td><button type="button" className="users-reference-name" disabled={busy} onClick={() => select(account)}><span className="reference-avatar">{(account.display_name || account.email).slice(0, 1)}</span><span><strong>{account.display_name}</strong><small>{account.email}</small></span></button></td><td>{account.is_library_owner ? "系统所有者" : roles[account.role]}</td><td><span className="reference-account-status" data-active={account.is_active}>{account.is_active ? "正常" : "已停用"}</span></td><td><time>{timestamp(account.last_login)}</time></td><td><button className="text-link" type="button" disabled={busy} onClick={() => select(account)}>编辑</button></td></tr>)}</tbody></table></div>
      {resource.loading ? <p role="status">正在读取用户…</p> : resource.data && !resource.data.results.length ? <p className="empty-state">没有符合条件的用户。</p> : null}
      {resource.data ? <nav className="reference-pagination" aria-label="用户分页"><button type="button" disabled={busy || !resource.data.previous} onClick={() => setPage(page - 1)}>上一页</button><span>共 {resource.data.count} 人 · 第 {page} 页</span><button type="button" disabled={busy || !resource.data.next} onClick={() => setPage(page + 1)}>下一页</button></nav> : null}
    </section><section className="admin-panel users-reference-detail"><h2>用户信息与权限</h2>{selected && draft ? <><header className="reference-account-summary"><span className="reference-avatar">{(selected.display_name || selected.email).slice(0, 1)}</span><div><h3>{selected.display_name} <span className="reference-account-status" data-active={selected.is_active}>{selected.is_active ? "正常" : "已停用"}</span></h3><p>{selected.email}　|　加入时间：{timestamp(selected.date_joined)}　|　上次登录：{timestamp(selected.last_login)}</p></div></header>
      <nav className="reference-tabs" aria-label="账号编辑区域">{[["basic", "基本信息"], ["permissions", "权限设置"], ["actions", "可执行的操作"]].map(([id, label]) => <button key={id} type="button" aria-current={tab === id ? "true" : undefined} onClick={() => setTab(id)}>{label}</button>)}</nav>
      {tab === "basic" ? <fieldset disabled={busy || !canEditSelected} className="reference-account-form"><label>显示名<input value={draft.display_name} onChange={event => setDraft({ ...draft, display_name: event.target.value })}/></label><label>登录邮箱<input value={selected.email} readOnly/></label><label className="switch-row"><input type="checkbox" checked={draft.is_active} disabled={selected.is_library_owner || selected.id === actor?.id} onChange={event => setDraft({ ...draft, is_active: event.target.checked })}/>账号正常使用</label></fieldset> : null}
      {tab === "permissions" ? <><h3>用户角色</h3><div className="reference-role-box"><div><strong>{selected.is_library_owner ? "系统所有者" : roles[draft.role as keyof typeof roles]}</strong>{canManageRoles && !selected.is_library_owner ? <select value={draft.role} disabled={busy || selected.id === actor?.id} aria-label="用户角色" onChange={event => setDraft({ ...draft, role: event.target.value as typeof draft.role })}><option value="reader">读者</option><option value="editor">内容编辑</option><option value="admin">系统管理员</option></select> : <p>{roleDescriptions[selected.is_library_owner ? 0 : selected.role === "admin" ? 1 : selected.role === "reader" ? 3 : 2][1]}</p>}</div>{!canManageRoles ? <p><LockKeyhole size={17}/>只有系统所有者可以修改用户角色。</p> : null}</div><h3>角色说明</h3><dl className="reference-role-descriptions">{roleDescriptions.map(([label, detail]) => <div key={label}><dt>{label}</dt><dd>{detail}</dd></div>)}</dl></> : null}
      {tab === "actions" ? <form className="reference-account-form" onSubmit={reset}><h3>设置新密码</h3><label>新密码<input type="password" minLength={10} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required disabled={busy || !canEditSelected}/></label><button className="button secondary" type="submit" disabled={busy || !canEditSelected}>设置新密码</button></form> : null}
      {message ? <p role={failed ? "alert" : "status"}>{message}</p> : null}<footer><button className="button secondary" type="button" disabled={busy} onClick={() => { setDraft(saved); setNewPassword(""); setMessage(""); }}>取消</button><button className="button" type="button" disabled={busy || !canEditSelected || !dirty} onClick={() => void saveAccount()}>{busy ? "正在保存…" : "保存账号修改"}</button></footer>
    </> : <p className="empty-state">选择左侧用户以编辑账号。</p>}</section></div>
  </div>;
}
