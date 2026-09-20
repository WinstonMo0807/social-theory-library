"use client";

import Link from "next/link";
import { useState } from "react";
import { apiRequest, getServerSessionCredential, isAuthenticationError } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";

export function SaveIssueList({ slug }: { slug: string }) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [login, setLogin] = useState(false);
  const { startAction, finishAction } = useActionGuard();
  async function save() {
    if (!startAction("save-list")) return;
    setBusy(true); setMessage(""); setLogin(false);
    try {
      await apiRequest(`/catalog/recommendation-issues/${encodeURIComponent(slug)}/save-list/`, { method: "POST", body: "{}" }, getServerSessionCredential());
      setMessage("已保存到你的私人书单。计划项的说明保留在本期推荐中。");
    } catch (error) { setLogin(isAuthenticationError(error)); setMessage(error instanceof Error ? error.message : "保存失败，请重试。"); }
    finally { setBusy(false); finishAction("save-list"); }
  }
  return <section className="issue-save-banner"><div><h2>保存本期书单</h2><p>将已有馆藏加入你的私人书单，随时回来继续阅读。</p></div><button className="button" disabled={busy} onClick={save}>{busy ? "正在保存…" : "保存书单 ＋"}</button>{message ? <p role="status">{message} {login ? <Link href={`/login?next=${encodeURIComponent(`/recommendations/${slug}`)}`}>登录后保存</Link> : <Link href="/account">打开读者中心</Link>}</p> : null}</section>;
}
