"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, apiRequest } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";

type Receipt = components["schemas"]["PublicFeedbackReceipt"];
type Input = components["schemas"]["AccountRecoveryAppealInputRequest"];

export function AccountRecoveryAppeal({ onGuardChange }: { onGuardChange?: (value: boolean) => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [receipt, setReceipt] = useState<Receipt | null>(null);
  const [uncertain, setUncertain] = useState(false), [dirty, setDirty] = useState(false);
  const [requestId, setRequestId] = useState("");
  const controller = useRef<AbortController | null>(null), pending = useRef<Input | null>(null), submitting = useRef(false);
  useUnsavedForm(!receipt && (dirty || uncertain || busy), false);
  useEffect(() => { onGuardChange?.(!receipt && (dirty || uncertain || busy)); return () => onGuardChange?.(false); }, [receipt, dirty, uncertain, busy, onGuardChange]);
  useEffect(() => { const request = new AbortController(); controller.current = request; return () => request.abort(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !controller.current || controller.current.signal.aborted) return;
    const form = new FormData(event.currentTarget);
    const payload = pending.current || { request_id: createRequestKey(), username: String(form.get("username") || "").trim(),
      contact: String(form.get("contact") || "").trim(), note: String(form.get("note") || "").trim(), consent: form.get("consent") === "on" };
    if (!payload.consent) { setError("请确认将填写内容用于本次账户找回。"); return; }
    pending.current = payload; setRequestId(payload.request_id); submitting.current = true; setBusy(true); setError(""); setUncertain(true);
    const request = controller.current, signal = AbortSignal.any([request.signal, AbortSignal.timeout(30000)]);
    try {
      await apiRequest("/auth/login/", { cache: "no-store", signal });
      const result = await apiRequest<Receipt>("/auth/recovery/appeal/", { method: "POST", cache: "no-store", signal, body: JSON.stringify(payload) });
      if (result.request_id !== payload.request_id) throw new Error("申请操作结果与本次编号不符，请保留输入并重新核对。");
      if (!request.signal.aborted) { setReceipt(result); setDirty(false); setUncertain(false); }
    } catch (reason) { if (!request.signal.aborted) {
      if (reason instanceof ApiRequestError && reason.status === 400) { pending.current = null; setUncertain(false); }
      setError(reason instanceof Error ? reason.message : "提交结果尚未确认，请重试原申请。");
    } }
    finally { submitting.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  function saveReceipt() {
    if (!receipt) return;
    const url = URL.createObjectURL(new Blob([`账户找回申请\n申请编号：${receipt.id}\n提交时间：${receipt.created_at}\n${receipt.message}\n`], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "account-recovery-receipt.txt"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section data-content-section id="account-recovery" className="auth-recovery-appeal"><header data-section-heading>无法访问邮箱？提交找回申请</header><p>提供记得的用户名及当前可联系的邮箱。只用于本次人工核对，请勿填写密码、验证码、证件或私人研究正文。</p>
    {receipt ? <div role="status"><p>{receipt.message}</p><p>申请编号 <code>{receipt.id}</code></p><button type="button" onClick={saveReceipt}>保存申请操作结果</button></div> : <form className="auth-form" onSubmit={submit} onChange={() => setDirty(true)} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }} aria-busy={busy}>
      <fieldset disabled={busy || uncertain}><label>用户名（可选）<input name="username" autoComplete="username" maxLength={150} /></label><label>可联系的邮箱<input name="contact" type="email" autoComplete="email" required maxLength={254} /></label><label>情况说明<textarea name="note" minLength={4} maxLength={300} rows={3} required /></label><label className="auth-consent"><input type="checkbox" name="consent" required />我同意管理员使用上述信息处理这次申请。</label></fieldset>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}{uncertain ? <p role="status">原申请结果尚未确认。输入暂时锁定，请使用原编号重试，避免重复提交。编号：{requestId}</p> : null}
      <button className="button secondary auth-submit" disabled={busy}>{busy ? "正在提交…" : uncertain ? "重试原找回申请" : "提交找回申请"}</button>
    </form>}
  </section>;
}
