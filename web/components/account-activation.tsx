"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { ApiRequestError, apiRequest } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AuthReturnContext } from "./auth-page-frame";

type Activation = components["schemas"]["ActivationOutput"];

export function AccountActivation() {
  const [result, setResult] = useState<Activation | null>(null), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [password, setPassword] = useState(""), [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false), [uncertain, setUncertain] = useState(false), [confirmed, setConfirmed] = useState(false);
  const controller = useRef<AbortController | null>(null), token = useRef(""), submitting = useRef(false);
  useUnsavedForm(result?.state !== "activated" && Boolean(password || uncertain), false);
  async function send(action: "inspect" | "activate", signal: AbortSignal, secret?: string) {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(30000)]);
    try { await apiRequest("/auth/login/", { cache: "no-store", signal: bounded }); }
    catch (cause) { throw new Error("暂时无法准备安全提交，请保留输入并重新核对。", { cause }); }
    return apiRequest<Activation>("/auth/activation/", { method: "POST", cache: "no-store", signal: bounded,
      body: JSON.stringify({ action, token: token.current, ...(action === "activate" ? { password: secret, confirmed: true } : {}) }) });
  }
  function accept(value: Activation) {
    setResult(value);
    if (value.state !== "ready") { setPassword(""); setConfirmation(""); setUncertain(false); }
    if (value.state === "activated") { token.current = ""; window.history.replaceState(null, "", window.location.pathname); }
  }
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    token.current = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    queueMicrotask(async () => {
      if (request.signal.aborted) return;
      if (!token.current) { setError("链接中没有邀请凭证，请联系管理员获取完整链接。"); return; }
      submitting.current = true; setBusy(true);
      try { const value = await send("inspect", request.signal); if (!request.signal.aborted) accept(value); }
      catch (reason) { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "无法读取邀请，请重试。"); }
      finally { submitting.current = false; if (!request.signal.aborted) setBusy(false); }
    });
    return () => request.abort();
  }, []);
  async function act(action: "inspect" | "activate") {
    const request = controller.current;
    if (!request || request.signal.aborted || submitting.current || !token.current) return;
    if (action === "activate" && (!confirmed || password !== confirmation)) { setError("请确认这是本人账户，并检查两次密码是否一致。"); return; }
    submitting.current = true; setBusy(true); setError("");
    if (action === "activate") setUncertain(true);
    try { const value = await send(action, request.signal, password); if (!request.signal.aborted) accept(value); }
    catch (reason) {
      if (!request.signal.aborted) {
        if (action === "activate" && reason instanceof ApiRequestError && reason.status === 400) setUncertain(false);
        setError(reason instanceof Error ? reason.message : "结果尚未确认，请保留原密码并核对激活结果。");
      }
    } finally { submitting.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void act("activate"); }
  return <div className="auth-atlas-page" data-mode="login"><nav className="auth-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><span>激活账户</span></nav>
    <header className="auth-heading"><h1>激活你的账户</h1><p>核对邀请账户，由你设置密码，保存本人的阅读与研究。</p></header>
    <div className="auth-atlas-columns"><div className="auth-panel"><form className="auth-form" onSubmit={submit} aria-busy={busy}>
      <nav className="auth-tabs" aria-label="账户入口"><span aria-current="page">激活账户</span><Link href="/login">登录</Link></nav>
      {result ? <p role="status" className="form-message">{result.detail}</p> : busy ? <p role="status">正在核对邀请…</p> : null}
      {result?.state === "ready" ? <><label>账户<input readOnly value={`${result.display_name} · ${result.username}`} /></label><label>邮箱<input readOnly value={result.email || ""} /></label><p>激活后角色：{result.role_label}</p><p className="field-help">有效至 {result.expires_at ? new Date(result.expires_at).toLocaleString("zh-CN") : "请重新核对"}。链接只供本人使用。</p>
        <label>设置密码<div className="password-input"><input type={visible ? "text" : "password"} autoComplete="new-password" minLength={10} maxLength={128} required value={password} disabled={busy || uncertain} onChange={event => setPassword(event.target.value)} /><button type="button" aria-label={visible ? "隐藏密码" : "显示密码"} aria-pressed={visible} onClick={() => setVisible(value => !value)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>
        <p className="field-help">至少10位，不使用常见、纯数字或与账户资料相近的密码。</p><label>确认密码<input type={visible ? "text" : "password"} autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy || uncertain} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
        <label className="auth-consent"><input type="checkbox" required disabled={busy || uncertain} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />这是本人账户，我已阅读<Link href="/help/account">账户与隐私说明</Link>。</label>
        <button className="button auth-submit" type="submit" disabled={busy || !confirmed}>{busy ? "正在核对…" : uncertain ? "重试原激活" : "设置密码并激活"}</button></> : null}
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {uncertain ? <p className="field-help">原激活结果待确认，请保留刚才设置的密码。查询或重试不会修改已经生效的密码。</p> : null}
      {result?.state === "activated" ? <Link className="button auth-submit" href="/login?next=%2Faccount">登录并前往读者中心</Link> : <button type="button" disabled={busy} onClick={() => void act("inspect")}>重新核对邀请与激活结果</button>}
    </form></div><AuthReturnContext destination="/account" /></div><div className="auth-guest"><Link href="/home">继续以访客身份浏览</Link><p>访客可浏览公开页面。阅读PDF、下载和检索请先登录。</p></div>
  </div>;
}
