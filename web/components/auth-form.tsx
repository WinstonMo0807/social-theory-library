"use client";

import Link from "next/link";
import { CheckCircle2, Eye, EyeOff, LoaderCircle, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiRequest, announceAuthenticatedSession } from "@/lib/api";
import { useGuestTransfer } from "./auth-guest-records";
import { authPageHref, safeAuthDestination } from "@/lib/auth-navigation";

export type AuthMode = "login" | "register" | "reset";

export function AuthForm({ mode, next, onModeChange, onSuccess, onGuardChange }: { mode: AuthMode; next?: string; onModeChange?: (mode: AuthMode) => void; onSuccess?: (destination: string) => void; onGuardChange?: (value: boolean) => void }) {
  const transfer = useGuestTransfer();
  const [loggedInDestination, setLoggedInDestination] = useState("");
  const [transferOwner, setTransferOwner] = useState("");
  const params = useSearchParams();
  const destination = safeAuthDestination(next || params.get("next"));
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  useEffect(() => { transfer?.setLocked(pending); return () => transfer?.setLocked(false); }, [pending, transfer?.setLocked]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [resetRequested, setResetRequested] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation,setConfirmation]=useState(""),[username,setUsername]=useState("");
  const passwordScore=password.length>=10?Math.min(4,1+Number(/[a-z]/.test(password)&&/[A-Z]/.test(password))+Number(/\d/.test(password))+Number(/[^a-zA-Z0-9]/.test(password))):password?1:0;
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
    return apiRequest<{ user?: { id: number; role: string }; notice?: string; detail?: string }>(path, { method: "POST", cache: "no-store", signal, body: JSON.stringify(body) });
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
        setTransferOwner(String(result.user?.id ?? ""));
        const target = next || params.get("next") ? destination : ["admin", "editor", "reviewer"].includes(result.user?.role || "") ? "/admin" : "/account";
        try {
          if (transfer?.selected && result.user?.id !== undefined) {
            const warning = await transfer.importForOwner(String(result.user.id), AbortSignal.any([request.current!.signal, AbortSignal.timeout(30000)]));
            if (warning) { setMessage(`登录成功。${warning}`); setPassword(""); setLoggedInDestination(target); return; }
          }
        } catch (reason) {
          if (request.current?.signal.aborted) return;
          setMessage(`登录成功，本机记录转存尚未完成。${reason instanceof Error ? reason.message : "请稍后重试，原记录保留。"}`);
          setPassword(""); setLoggedInDestination(target); return;
        }
        if (!request.current?.signal.aborted) navigate(target);
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
  async function retryTransfer() {
    if (pending || !transferOwner || !transfer) return;
    setPending(true);
    try {
      const warning = await transfer.importForOwner(transferOwner, AbortSignal.any([request.current!.signal, AbortSignal.timeout(30000)]));
      if (warning) setMessage(`登录成功。${warning}`);
      else navigate(loggedInDestination);
    } catch (reason) { if (!request.current?.signal.aborted) setMessage(reason instanceof Error ? reason.message : "转存尚未完成，原记录保留。"); }
    finally { if (!request.current?.signal.aborted) setPending(false); }
  }
  async function resend() {
    if (pending || cooldown > 0 || submitting.current) return;
    submitting.current = true; setPending(true); setError("");
    try { const result = await post(registered ? "/auth/email/request/" : "/auth/password/request/", { email: email.trim(), next: destination }); if (!request.current?.signal.aborted) { setCooldown(60); setMessage(result.detail || "邮件请求已受理，请使用最新收到的链接。"); } }
    catch (reason) { if (!request.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "发送失败，请重试。"); }
    finally { submitting.current = false; if (!request.current?.signal.aborted) setPending(false); }
  }
  const tab = (value: AuthMode, title: string) => onModeChange ? <button type="button" disabled={pending} aria-pressed={mode === value} onClick={() => onModeChange(value)}>{title}</button> : <Link aria-current={mode === value ? "page" : undefined} href={authPageHref(value, destination)}>{title}</Link>;
  if (loggedInDestination) return <div className="auth-form"><h2>已登录</h2><p className="form-message" role="status">{message}</p><p>未转存的记录仍保存在本设备，账户隐私设置保持不变。</p><div className="auth-links"><button type="button" disabled={pending} onClick={() => void retryTransfer()}>{pending ? "正在转存…" : "重试转存"}</button><button className="button auth-submit" type="button" disabled={pending} onClick={() => navigate(loggedInDestination)}>继续原来的阅读</button></div></div>;
  if (registered) return <div className="auth-form"><h2>账户已创建</h2><p className="form-message" role="status">{message}</p><p>验证邮箱为 {email}。请打开最新邮件，并在24小时内由本人确认。登录和邮箱验证是两个独立步骤。</p>{error ? <p className="form-message error" role="alert">{error}</p> : null}<button className="button auth-submit" type="button" disabled={pending || cooldown > 0} onClick={() => void resend()}>{pending ? "正在申请…" : cooldown > 0 ? `${cooldown}秒后重新申请验证` : "重新发送验证链接"}</button><div className="auth-links"><Link href={authPageHref("login", destination)}>登录并继续</Link><Link href="/help/account">账户帮助</Link></div></div>;
  return <form className="auth-form" data-auth-mode={mode} onSubmit={submit} aria-busy={pending} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }}>
    <nav className="auth-tabs" aria-label="账户入口">{mode!=="register"?tab("login", "登录"):null}{tab("register", "注册账户")}{tab("reset",mode==="reset"?"找回账户":"找回密码")}</nav>
    {mode === "reset" ? <div className="auth-form-intro"><h2>{resetRequested ? "请查看邮箱" : "找回账户"}</h2><p>通过注册邮箱获取24小时有效的链接，由本人确认后重置密码。</p></div> : null}
    {mode === "login" && params.get("registered") === "1" ? <p role="status" className="form-message success">账户已创建，请登录继续。</p> : null}
    {mode === "login" && params.get("reset") === "1" ? <p role="status" className="form-message success">密码已重置，原登录凭据已失效，请重新登录。</p> : null}
    <label><span>{mode === "login" ? "邮箱或用户名" : mode==="reset"?"注册邮箱":"邮箱地址"}{mode==="register"?<em aria-hidden="true">*</em>:null}</span><div className="auth-clearable"><input type={mode === "login" ? "text" : "email"} name="email" autoComplete={mode === "login" ? "username" : "email"} maxLength={254} required value={email} readOnly={resetRequested || pending} onChange={event => setEmail(event.target.value)} />{email?<button type="button" disabled={resetRequested||pending} onClick={()=>setEmail("")} aria-label="清除邮箱或用户名"><X size={16}/></button>:null}</div></label>{mode==="reset"?<p className="field-help">请输入您注册时使用的邮箱地址。</p>:null}
    {mode === "register" ? <><p className="field-help">我们将向此邮箱发送验证链接。邮箱用于登录与找回密码。</p><label><span>用户名<em aria-hidden="true">*</em></span><div className="auth-clearable"><input value={username} onChange={event=>setUsername(event.target.value)} name="username" autoComplete="username" minLength={4} maxLength={20} pattern="[a-zA-Z0-9_\u4e00-\u9fff]{4,20}" required />{/^[a-zA-Z0-9_一-鿿]{4,20}$/.test(username)?<CheckCircle2 className="auth-valid" size={17} aria-label="用户名格式符合要求"/>:null}</div></label><p className="field-help">支持中文、英文字母、数字及下划线，4—20个字符。</p></> : null}
    {mode !== "reset" ? <><label><span>密码{mode==="register"?<em aria-hidden="true">*</em>:null}</span><div className="password-input"><input type={showPassword ? "text" : "password"} name="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? undefined : 10} maxLength={mode === "login" ? 4096 : 128} required value={password} onChange={event => setPassword(event.target.value)} /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>{mode !== "login" ? <><div className="auth-password-strength" data-level={passwordScore} aria-live="polite"><span>{[1,2,3,4].map(value=><i key={value} data-filled={value<=passwordScore}/>)}</span><small>{password?`密码强度：${passwordScore>=3?"较强":passwordScore===2?"一般":"较弱"}`:""}</small></div><p className="field-help">至少10位，不使用常见或纯数字密码。</p><label><span>确认密码<em aria-hidden="true">*</em></span><div className="password-input"><input type={showPassword ? "text" : "password"} name="confirmPassword" autoComplete="new-password" minLength={10} maxLength={128} required value={confirmation} onChange={event=>setConfirmation(event.target.value)}/><button type="button" onClick={()=>setShowPassword(value=>!value)} aria-label={showPassword?"隐藏确认密码":"显示确认密码"}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>{confirmation?<p className="field-help" data-match={confirmation===password}>{confirmation===password?"两次输入的密码一致。":"两次输入的密码不一致。"}</p>:null}</> : null}</> : null}
    {mode === "login" ? <div className="auth-options"><label><input type="checkbox" name="remember" defaultChecked />保持登录状态（30天）</label>{onModeChange ? <button type="button" disabled={pending} onClick={() => onModeChange("reset")}>忘记密码？</button> : <Link href={authPageHref("reset", destination)}>忘记密码？</Link>}</div> : null}
    {mode === "register" ? <label className="auth-consent"><input type="checkbox" required />我已阅读并同意<Link href="/help/terms">《服务条款》</Link>与<Link href="/help/account#site-privacy">《隐私政策》</Link>。</label> : null}
    {error ? <p className="form-message error" role="alert">{error}</p> : null}{message ? <p className="form-message success" role="status">{message}</p> : null}
    {!resetRequested ? <button className="button auth-submit" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={17} /> : null}{mode === "login" ? onModeChange?"登录并继续":"登录" : mode === "register" ? "创建账户" : "发送重置链接"}</button> : null}
    {mode === "reset" ? resetRequested ? <div className="auth-links"><button type="button" disabled={pending || cooldown > 0} onClick={() => void resend()}>{cooldown > 0 ? cooldown + "秒后重新发送" : "重新发送"}</button><button type="button" disabled={pending} onClick={() => { setResetRequested(false); setMessage(""); setPassword(""); }}>更换邮箱</button></div> : null : <p className="auth-policy">继续即表示您同意<Link href="/help/terms">《服务条款》</Link>与<Link href="/help/account#site-privacy">《隐私政策》</Link>。</p>}
  </form>;
}
