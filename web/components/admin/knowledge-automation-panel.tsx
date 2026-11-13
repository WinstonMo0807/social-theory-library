"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { knowledgeCall } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";

type Policy = { version: number; mode: "retrieval" | "draft"; profile_key: string; applies_after: string | null;
  can_manage: boolean; profiles: { key: string; model: string; enabled: boolean }[] };

export function KnowledgeAutomationPanel() {
  const [policy, setPolicy] = useState<Policy | null>(null), [mode, setMode] = useState<Policy["mode"]>("retrieval");
  const [profile, setProfile] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false), [attempt, setAttempt] = useState(0);
  function adopt(value: Policy) { setPolicy(value); setMode(value.mode); setProfile(value.profile_key || value.profiles[0]?.key || ""); }
  useEffect(() => {
    const controller = new AbortController(); setError("");
    void knowledgeCall<Policy>("/knowledge/automation/", undefined, controller.signal).then(adopt)
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [attempt]);
  async function save() {
    if (!policy || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await knowledgeCall<Policy>("/knowledge/automation/", { version: policy.version, mode, profile_key: profile });
      adopt(value); setNotice(value.mode === "draft" ? "已保存。此后首次上架的新馆藏将自动进入待审编纂。" : "已保存。新馆藏仅维护检索，已有书目的编纂设置保留。");
    } catch (e) { setError(e instanceof Error ? e.message : "设置未保存，请重试。"); }
    finally { setBusy(false); }
  }
  const selected = policy?.profiles.find(p => p.key === profile);
  return <details className={s.automation}>
    <summary><span>新馆藏如何进入知识库</span><small>{policy ? policy.mode === "draft" ? "检索与待审编纂" : "仅维护检索" : "读取设置"}</small></summary>
    {error && <p role="alert" className={s.error}>{error} <button disabled={busy} onClick={() => setAttempt(v => v+1)}>重新读取设置</button></p>}
    {policy ? <form onSubmit={e => { e.preventDefault(); void save(); }}>
      <div className={s.automationLayout}>
        <fieldset disabled={busy || !policy.can_manage}><legend>新书上架后的处理</legend>
          <label><input type="radio" name="new-source-mode" checked={mode === "retrieval"} onChange={() => { setMode("retrieval"); setNotice(""); }} />维护原文与检索</label>
          <label><input type="radio" name="new-source-mode" checked={mode === "draft"} onChange={() => { setMode("draft"); setNotice(""); }} />同时生成 Wiki 待审草稿</label>
          {mode === "draft" && <label className={s.automationModel}>编纂模型<select value={profile} onChange={e => { setProfile(e.target.value); setNotice(""); }}>
            {policy.profiles.map(p => <option key={p.key} value={p.key}>{p.model || "尚未指定模型"} · {p.key}{p.enabled ? "" : "（未启用）"}</option>)}
          </select></label>}
        </fieldset>
        <div className={s.automationPreview} aria-live="polite"><h3>新书的处理路径</h3>
          <ol><li><strong>上架与正文就绪</strong><span>采用已发布的版本和原文，保留历史来源。</span></li>
            <li><strong>增量检索</strong><span>关键词独立更新；向量按现有模型配置补齐。</span></li>
            {mode === "draft" && <li><strong>{selected?.enabled ? "章节分析与持续编纂" : "等待配置编纂模型"}</strong><span>{selected?.enabled ? "按章节读取，提出有原文依据的局部修改。" : "保留任务，不调用未启用的模型；启用后自动接续。"}</span></li>}
            {mode === "draft" && <li><strong>审核后发布</strong><span>修改进入同一审核区，保留人工内容与冲突。</span></li>}
          </ol>
        </div>
      </div>
      <p>启用后只纳入首次上架的新馆藏。已有书目沿用各自的范围和暂停设置。私人笔记与读者问答不纳入。</p>
      <div className={s.sectionBar}>{policy.can_manage && <button className={s.primary} disabled={busy || mode === "draft" && !profile} type="submit">{busy ? "正在保存…" : "保存自动维护设置"}</button>}<Link href="/admin/processing/settings#ai">管理模型</Link></div>
      {notice && <p role="status">{notice}</p>}
    </form> : !error && <p role="status">正在读取自动维护设置…</p>}
  </details>;
}
