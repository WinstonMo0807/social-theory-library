"use client";

import Link from "next/link";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiRequest, announceAuthenticatedSession } from "@/lib/api";
import { authPageHref, safeAuthDestination } from "@/lib/auth-navigation";

export type AuthMode = "login" | "register" | "reset";

export function AuthForm({ mode, next, onModeChange, onSuccess, onGuardChange }: { mode: AuthMode; next?: string; onModeChange?: (mode: AuthMode) => void; onSuccess?: (destination: string) => void; onGuardChange?: (value: boolean) => void }) {
  const params = useSearchParams();
  const destination = safeAuthDestination(next || params.get("next"));
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [resetRequested, setResetRequested] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  useEffect(() => { onGuardChange?.(pending || Boolean(password)); return () => onGuardChange?.(false); }, [pending, password, onGuardChange]);
  const request = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  useEffect(() => { const controller = new AbortController(); request.current = controller; return () => controller.abort(); }, []);
  useEffect(() => { if (cooldown <= 0) return; const timer = setTimeout(() => setCooldown(value => value - 1), 1000); return () => clearTimeout(timer); }, [cooldown]);
  const navigate = (path: string) => { if (onSuccess) onSuccess(path); else window.location.assign(path); };
  const post = async (path: string, body: unknown) => {
    const signal = AbortSignal.any([request.current!.signal, AbortSignal.timeout(30000)]);
    await apiRequest("/auth/login/", { cache: "no-store", signal });
    signal.throwIfAborted();
    return apiRequest<{ user?: { role: string }; notice?: string; detail?: string }>(path, { method: "POST", cache: "no-store", signal, body: JSON.stringify(body) });
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || request.current?.signal.aborted) return;
    const form = new FormData(event.currentTarget);
    if (mode === "register" && form.get("confirmPassword") !== password) { setError("两次输入的密码不一致，请检查确认密码。"); return; }
    submitting.current = true; setPending(true); setError(""); setMessage("");
    try {
      if (mode === "login") {
        const result = await post("/auth/login/", { email: email.trim(), password, remember_me: form.get("remember") === "on" });
        if (request.current?.signal.aborted) return;
        announceAuthenticatedSession();
        navigate(next || params.get("next") ? destination : ["admin", "editor", "reviewer"].includes(result.user?.role || "") ? "/admin" : "/account");
      } else if (mode === "register") {
        const result = await post("/auth/register/", { email: email.trim(), username: form.get("username"), display_name: form.get("username"), password, next: destination });
        if (request.current?.signal.aborted) return;
        setRegistered(true); setPassword(""); setCooldown(60);
        setMessage(result.notice || "账户已创建。请验证邮箱或登录继续。");
      } else {
        const result = await post("/auth/password/request/", { email: email.trim(), next: destination });
        if (request.current?.signal.aborted) return;
        setMessage(result.detail || "恢复请求已受理，请查看邮箱中的24小时链接。"); setResetRequested(true); setCooldown(60);
      }
    } catch (reason) { if (!request.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "请求未完成，请保留输入并重试。"); }
    finally { submitting.current = false; if (!request.current?.signal.aborted) setPending(false); }
  }
  async function resend() {
    if (pending || cooldown > 0 || submitting.current) return;
    submitting.current = true; setPending(true); setError("");
    try { const result = await post(registered ? "/auth/email/request/" : "/auth/password/request/", { email: email.trim(), next: destination }); if (!request.current?.signal.aborted) { setCooldown(60); setMessage(result.detail || "邮件请求已受理，请使用最新收到的链接。"); } }
    catch (reason) { if (!request.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "发送失败，请重试。"); }
    finally { submitting.current = false; if (!request.current?.signal.aborted) setPending(false); }
  }
  const tab = (value: AuthMode, title: string) => onModeChange ? <button type="button" disabled={pending} aria-pressed={mode === value} onClick={() => onModeChange(value)}>{title}</button> : <Link aria-current={mode === value ? "page" : undefined} href={authPageHref(value, destination)}>{title}</Link>;
  if (registered) return <div className="auth-form"><h2>账户已创建</h2><p className="form-message" role="status">{message}</p><p>验证邮箱为 {email}。请打开最新邮件，并在24小时内由本人确认。登录和邮箱验证是两个独立步骤。</p>{error ? <p className="form-message error" role="alert">{error}</p> : null}<button className="button auth-submit" type="button" disabled={pending || cooldown > 0} onClick={() => void resend()}>{pending ? "正在申请…" : cooldown > 0 ? `${cooldown}秒后重新申请验证` : "重新发送验证链接"}</button><div className="auth-links"><Link href={authPageHref("login", destination)}>登录并继续</Link><Link href="/help/account">账户帮助</Link></div></div>;
  return <form className="auth-form" onSubmit={submit} aria-busy={pending} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }}>
    <nav className="auth-tabs" aria-label="账户入口">{tab("login", "登录")}{tab("register", "注册账户")}{tab("reset", "找回密码")}</nav>
    {mode === "reset" ? <div className="auth-form-intro"><h2>{resetRequested ? "请查看邮箱" : "找回账户"}</h2><p>通过注册邮箱获取24小时有效的链接，由本人确认后重置密码。</p></div> : null}
    {mode === "login" && params.get("registered") === "1" ? <p role="status" className="form-message success">账户已创建，请登录继续。</p> : null}
    {mode === "login" && params.get("reset") === "1" ? <p role="status" className="form-message success">密码已重置，原登录凭据已失效，请重新登录。</p> : null}
    <label><span>{mode === "login" ? "邮箱或用户名" : "邮箱地址"}</span><input type={mode === "login" ? "text" : "email"} name="email" autoComplete={mode === "login" ? "username" : "email"} maxLength={254} required value={email} readOnly={resetRequested || pending} onChange={event => setEmail(event.target.value)} /></label>
    {mode === "register" ? <><p className="field-help">我们将向此邮箱发送验证链接。邮箱用于登录与找回密码。</p><label><span>用户名</span><input name="username" autoComplete="username" minLength={4} maxLength={20} pattern="[a-zA-Z0-9_\u4e00-\u9fff]{4,20}" required /></label><p className="field-help">支持中文、英文字母、数字及下划线，4—20个字符。</p></> : null}
    {mode !== "reset" ? <><label><span>密码</span><div className="password-input"><input type={showPassword ? "text" : "password"} name="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? undefined : 10} maxLength={mode === "login" ? 4096 : 128} required value={password} onChange={event => setPassword(event.target.value)} /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>{mode !== "login" ? <><p className="field-help">至少10位，不使用常见或纯数字密码。</p><label><span>确认密码</span><input type={showPassword ? "text" : "password"} name="confirmPassword" autoComplete="new-password" minLength={10} maxLength={128} required /></label></> : null}</> : null}
    {mode === "login" ? <div className="auth-options"><label><input type="checkbox" name="remember" defaultChecked />保持登录状态（30天）</label>{onModeChange ? <button type="button" disabled={pending} onClick={() => onModeChange("reset")}>忘记密码？</button> : <Link href={authPageHref("reset", destination)}>忘记密码？</Link>}</div> : null}
    {mode === "register" ? <label className="auth-consent"><input type="checkbox" required />我已阅读<Link href="/help/account">账户与隐私说明</Link>。</label> : null}
    {error ? <p className="form-message error" role="alert">{error}</p> : null}{message ? <p className="form-message success" role="status">{message}</p> : null}
    {!resetRequested ? <button className="button auth-submit" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={17} /> : null}{mode === "login" ? "登录并继续" : mode === "register" ? "创建账户" : "发送重置链接"}{!pending ? <ArrowRight size={16} /> : null}</button> : null}
    {mode === "login" ? <div className="auth-external"><p>其他登录方式</p><div><button type="button" disabled>Apple 登录 · 未开放</button><button type="button" disabled>Google 登录 · 未开放</button></div></div> : null}
    {mode === "reset" ? resetRequested ? <div className="auth-links"><button type="button" disabled={pending || cooldown > 0} onClick={() => void resend()}>{cooldown > 0 ? cooldown + "秒后重新发送" : "重新发送"}</button><button type="button" disabled={pending} onClick={() => { setResetRequested(false); setMessage(""); setPassword(""); }}>更换邮箱</button></div> : <div className="auth-recovery-help"><strong>无法访问邮箱？</strong><p>请联系书库管理员核对账户归属，不能仅凭用户名重置密码。</p><a href="#account-recovery">提交找回申请 <ArrowRight size={14} /></a></div> : <p className="auth-policy">了解<Link href="/help">使用说明</Link>与<Link href="/help/account">账户隐私</Link>。</p>}
  </form>;
}
