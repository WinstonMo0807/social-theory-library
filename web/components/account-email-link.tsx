"use client";

import { LoadingState } from "@/components/ui/loading-state";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Eye, EyeOff, MailCheck } from "lucide-react";
import { ApiRequestError, apiRequest, clearStoredSession } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { authPageHref, safeAuthDestination } from "@/lib/auth-navigation";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AuthReturnContext } from "./auth-page-frame";

type LinkState = components["schemas"]["MailLinkOutput"];

export function AccountEmailLink({ purpose, destination }: { purpose: "password" | "verify"; destination: string }) {
  const [state, setState] = useState<LinkState | null>(null), [error, setError] = useState("");
  const [hasToken, setHasToken] = useState(true), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [password, setPassword] = useState(""), [confirmation, setConfirmation] = useState(""), [visible, setVisible] = useState(false);
  const [confirmed, setConfirmed] = useState(false), [uncertain, setUncertain] = useState(false), [cooldown, setCooldown] = useState(0);
  const token = useRef(""), controller = useRef<AbortController | null>(null), submitting = useRef(false);
  const reset = purpose === "password";
  useUnsavedForm(state?.state !== "completed" && Boolean(password || uncertain || busy), false);
  useEffect(() => { if (cooldown < 1) return; const timer = setTimeout(() => setCooldown(value => value - 1), 1000); return () => clearTimeout(timer); }, [cooldown]);
  async function post<T>(path: string, body: unknown, signal: AbortSignal) {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(30000)]);
    await apiRequest("/auth/login/", { cache: "no-store", signal: bounded });
    return apiRequest<T>(path, { method: "POST", cache: "no-store", signal: bounded, body: JSON.stringify(body) });
  }
  function accept(result: LinkState, clearSession = false) {
    setState(result);
    if (result.state !== "ready") { setPassword(""); setConfirmation(""); setUncertain(false); }
    if (result.state === "completed") {
      if (clearSession) clearStoredSession();
      token.current = "";
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    }
  }
  async function act(action: "inspect" | "confirm") {
    const request = controller.current;
    if (!request || request.signal.aborted || submitting.current || !token.current) return;
    if (action === "confirm" && (!confirmed || reset && password !== confirmation)) { setError("请确认这是本人操作，并检查两次密码是否一致。"); return; }
    submitting.current = true; setBusy(true); setError("");
    if (action === "confirm") setUncertain(true);
    try {
      const result = await post<LinkState>(reset ? "/auth/password/link/" : "/auth/email/verify/", { action, token: token.current,
        ...(action === "confirm" ? { confirmed: true, password } : {}) }, request.signal);
      if (!request.signal.aborted) accept(result, reset && action === "confirm");
    } catch (reason) { if (!request.signal.aborted) {
      if (reason instanceof ApiRequestError && reason.status === 400) {
        setUncertain(false);
        if (action === "inspect") setState({ state: "unavailable", detail: "链接不可用，请重新申请完整链接。" });
      }
      setError(reason instanceof Error ? reason.message : "结果尚未确认，请重新核对原链接。");
    } }
    finally { submitting.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    token.current = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    queueMicrotask(() => { if (!request.signal.aborted) { setHasToken(Boolean(token.current)); if (token.current) void act("inspect"); } });
    return () => request.abort();
    // The link is inspected once per mounted route, never consumed by merely opening it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function requestLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || cooldown > 0 || !controller.current || controller.current.signal.aborted) return;
    const email = String(new FormData(event.currentTarget).get("email") || "");
    const request = controller.current; submitting.current = true; setBusy(true); setError(""); setMessage("");
    try {
      const result = await post<{ detail: string }>(reset ? "/auth/password/request/" : "/auth/email/request/", { email, next: destination }, request.signal);
      if (!request.signal.aborted) { setMessage(result.detail); setCooldown(60); }
    } catch (reason) { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "请求未受理，请稍后重试。"); }
    finally { submitting.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void act("confirm"); }
  return <div className="auth-form" aria-busy={busy}>
    <nav className="auth-tabs" aria-label="账户入口"><span aria-current="page">{reset ? "设置新密码" : "验证邮箱"}</span><Link href={authPageHref("login", destination)}>登录</Link></nav>
    <div className="auth-form-intro"><h2><MailCheck size={24} />{reset ? "恢复你的账户" : "确认你的邮箱"}</h2><p>{reset ? "设置新密码后，原登录凭据将失效，已保存的私人资料保留。" : "请同时核对邮件链接和账户密码。验证不会自动登录、调整角色或合并任何资料。"}</p></div>
    {state ? <p role="status" className="form-message">{state.detail}</p> : busy ? <LoadingState role="status">正在核对链接…</LoadingState> : null}
    {hasToken && state?.state === "ready" ? <form onSubmit={submit} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }}>
      <p className="field-help">有效至 {state.expires_at ? new Date(state.expires_at).toLocaleString("zh-CN") : "请重新核对"}。链接只供本人使用。</p>
      <label>{reset ? "新密码" : "账户密码"}<div className="password-input"><input type={visible ? "text" : "password"} autoComplete={reset ? "new-password" : "current-password"} minLength={reset ? 10 : undefined} maxLength={reset ? 128 : 4096} required disabled={busy || uncertain} value={password} onChange={event => setPassword(event.target.value)} /><button type="button" aria-label={visible ? "隐藏密码" : "显示密码"} aria-pressed={visible} onClick={() => setVisible(value => !value)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>{reset ? <><p className="field-help">至少10位，不使用常见、纯数字或与账户资料相近的密码。</p><label>确认密码<input type={visible ? "text" : "password"} autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy || uncertain} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label></> : <p className="field-help">填写注册时设置的密码。若已忘记，请先<Link href={authPageHref("reset", destination)}>找回密码</Link>，再重新申请验证链接。</p>}
      <label className="auth-consent"><input type="checkbox" required disabled={busy || uncertain} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />这是我本人发起的{reset ? "密码恢复" : "邮箱验证"}。</label>
      <button className="button auth-submit" disabled={busy || !confirmed} type="submit">{busy ? "正在提交…" : uncertain ? "重试原确认" : reset ? "确认重置密码" : "确认邮箱归属"}</button>
    </form> : null}
    {error ? <p role="alert" className="form-message error">{error}</p> : null}
    {uncertain ? <p className="field-help">结果尚未确认，请保留刚才的输入，核对原链接。已经完成的操作不会重复改写密码。</p> : null}
    {hasToken && state?.state !== "completed" ? <button className="auth-link-recheck" type="button" disabled={busy} onClick={() => void act("inspect")}>重新核对链接与处理结果</button> : null}
    {state?.state === "completed" ? <Link className="button auth-submit" href={authPageHref("login", destination)}>登录并继续</Link> : !hasToken || state?.state === "expired" || state?.state === "unavailable" ? <form onSubmit={requestLink}><label>邮箱地址<input name="email" type="email" autoComplete="email" maxLength={254} required disabled={busy} /></label><button className="button auth-submit" disabled={busy || cooldown > 0}>{cooldown > 0 ? `${cooldown}秒后可重新申请` : reset ? "重新申请恢复链接" : "发送验证链接"}</button>{message ? <p className="form-message" role="status">{message}</p> : null}</form> : <Link href={authPageHref("reset", destination)}>重新申请恢复链接</Link>}
  </div>;
}

export function EmailVerificationPage() {
  const params = useSearchParams(), destination = safeAuthDestination(params.get("next"));
  return <div className="auth-atlas-page"><nav className="auth-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><span>验证邮箱</span></nav><header className="auth-heading"><h1>验证邮箱</h1><p>确认邮箱归属，保留账户恢复渠道。</p></header><div className="auth-atlas-columns"><div className="auth-panel"><AccountEmailLink purpose="verify" destination={destination} /></div><AuthReturnContext destination={destination} /></div></div>;
}
