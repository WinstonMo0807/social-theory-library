"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import { accountRequest, type ManagedUser } from "@/lib/api/account-management.client";
import type { components } from "@/lib/api/generated/schema";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./account-workspace.module.css";

export function AccountInvitation({ actor, user, blocked, onEdit }: {
  actor: string; user: ManagedUser; blocked: boolean; onEdit: (operation: "invite" | "revoke_invite") => void;
}) {
  const [result, setResult] = useState<components["schemas"]["InvitationOutput"] | null>(null);
  const [url, setUrl] = useState(""), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null), reading = useRef(false);
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    const off = subscribeToSessionChanges(() => request.abort());
    return () => { request.abort(); off(); };
  }, [actor, user.id, user.version]);
  async function read() {
    const request = controller.current;
    if (!request || request.signal.aborted || reading.current || blocked) return;
    reading.current = true; setBusy(true); setMessage(""); setUrl(""); setResult(null);
    try {
      const value = await withPrivateOwner(actor, () => accountRequest<components["schemas"]["InvitationOutput"]>(actor, `${user.id}/invitation/`, { signal: request.signal }), request.signal);
      if (value.user_id !== user.id) throw Error("邀请所属账户不一致，请重新读取。");
      if (!request.signal.aborted) {
        setResult(value);
        if (value.token) setUrl(`${window.location.origin}/activate#${new URLSearchParams({ token: value.token })}`);
        else setMessage("当前邀请不可使用。请重新读取账户详情，再决定是否生成新邀请。");
      }
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "无法读取邀请，请重试。"); }
    finally { reading.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  async function copy() {
    const request = controller.current;
    if (!url || blocked || !request || request.signal.aborted) return;
    try {
      await withPrivateOwner(actor, async () => { request.signal.throwIfAborted(); await navigator.clipboard.writeText(url); }, request.signal);
      if (!request.signal.aborted) setMessage("邀请链接已复制，请只交给目标账户本人。");
    } catch { if (!request.signal.aborted) setMessage("未能确认复制成功；可选中链接手动复制，请只交给本人。"); }
  }
  return <section className={styles.editor} aria-label="账户邀请"><h3>本人激活</h3><p>由本人设置密码后启用账户。邀请只在24小时内有效，重新生成会使旧链接失效。</p>
    <div className={styles.actions}><button disabled={blocked || busy} onClick={() => void read()}>{busy ? "正在读取…" : "查看邀请链接"}</button><button disabled={blocked || busy || !user.can_renew_invitation} onClick={() => onEdit("invite")}>重新生成邀请</button><button disabled={blocked || busy || !user.can_revoke_invitation || user.activation_state === "invitation_revoked"} onClick={() => onEdit("revoke_invite")}>撤销邀请</button></div>
    {url ? <><label>仅交给本人<input readOnly value={url} onFocus={event => event.target.select()} aria-label="账户激活链接" /></label><button disabled={blocked || busy} onClick={() => void copy()}>复制邀请链接</button></> : null}
    {result?.expires_at ? <p>到期时间：{new Date(result.expires_at).toLocaleString("zh-CN")}</p> : null}
    <p className={styles.muted}>{result?.notice || "系统不会自动发送邮件，未激活前不能登录。"}</p>{message ? <p role="status" className={styles.notice}>{message}</p> : null}
  </section>;
}
