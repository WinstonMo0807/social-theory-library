"use client";

import Link from "next/link";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiRequest, markSessionActive } from "@/lib/api";

type Mode = "login" | "register" | "reset";

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const params = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [resetRequested, setResetRequested] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      if (mode === "login") {
        const payload = await apiRequest<{
          user: { role: string };
        }>("/auth/login/", {
          method: "POST",
          body: JSON.stringify({
            email: form.get("email"),
            password: form.get("password"),
          }),
        });
        markSessionActive();
        const requestedDestination = params.get("next");
        const safeDestination = requestedDestination?.startsWith("/")
          && !requestedDestination.startsWith("//")
          ? requestedDestination
          : null;
        const destination =
          safeDestination ??
          (["admin", "editor", "reviewer"].includes(payload.user.role)
            ? "/admin"
            : "/account");
        router.push(destination);
      } else if (mode === "register") {
        await apiRequest("/auth/register/", {
          method: "POST",
          body: JSON.stringify({
            email: form.get("email"),
            display_name: form.get("displayName"),
            password: form.get("password"),
          }),
        });
        router.push("/login?registered=1");
      } else if (!resetRequested) {
        await apiRequest("/auth/password/request/", {
          method: "POST",
          body: JSON.stringify({ email: form.get("email") }),
        });
        setMessage("如果该邮箱已经注册，验证码会发送到邮箱。");
        setResetRequested(true);
      } else {
        await apiRequest("/auth/password/confirm/", {
          method: "POST",
          body: JSON.stringify({
            email: form.get("email"),
            code: form.get("code"),
            new_password: form.get("newPassword"),
          }),
        });
        router.push("/login?reset=1");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "请求失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  const title =
    mode === "login" ? "登录读者账户" : mode === "register" ? "注册读者账户" : "重置密码";
  const intro =
    mode === "login"
      ? "同步阅读进度、批注、笔记、书签和收藏。"
      : mode === "register"
        ? "阅读和下载无需账户。注册后可以保存个人阅读资料。"
        : "输入注册邮箱，我们会发送一次性验证码。";

  return (
    <form className="auth-form" onSubmit={submit}>
      <p className="eyebrow">社会理论书库</p>
      <h1>{title}</h1>
      <p className="auth-intro">{intro}</p>
      {mode === "register" ? (
        <label>
          <span>显示名称</span>
          <input name="displayName" autoComplete="name" required />
        </label>
      ) : null}
      <label>
        <span>邮箱</span>
        <input type="email" name="email" autoComplete="email" required />
      </label>
      {mode === "reset" && resetRequested ? (
        <>
          <label>
            <span>验证码</span>
            <input name="code" inputMode="numeric" minLength={6} maxLength={12} required />
          </label>
          <label>
            <span>新密码</span>
            <div className="password-input">
              <input
                type={showPassword ? "text" : "password"}
                name="newPassword"
                minLength={10}
                autoComplete="new-password"
                required
              />
              <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>
        </>
      ) : null}
      {mode !== "reset" ? (
        <label>
          <span>密码</span>
          <div className="password-input">
            <input
              type={showPassword ? "text" : "password"}
              name="password"
              minLength={10}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
            <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"}>
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </label>
      ) : null}
      {mode === "register" ? <p className="field-help">至少 10 位，不使用常见或纯数字密码。</p> : null}
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {message ? <p className="form-message success" role="status">{message}</p> : null}
      <button className="button auth-submit" type="submit" disabled={pending}>
        {pending ? <LoaderCircle className="spin" size={17} /> : null}
        {mode === "login" ? "登录" : mode === "register" ? "创建账户" : resetRequested ? "确认重置" : "发送验证码"}
        {!pending ? <ArrowRight size={16} /> : null}
      </button>
      <div className="auth-links">
        {mode === "login" ? (
          <>
            <Link href="/reset-password">忘记密码</Link>
            <Link href="/register">注册新账户</Link>
          </>
        ) : (
          <Link href="/login">返回登录</Link>
        )}
      </div>
    </form>
  );
}
