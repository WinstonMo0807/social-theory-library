"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Check, CircleAlert, CircleHelp, FileText, Lightbulb, LockKeyhole, MessageCircle, MoreHorizontal, RefreshCw, Settings, X } from "lucide-react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { safeFeedbackPath, submitPublicFeedback, type FeedbackCategory, type FeedbackInput, type FeedbackReceipt } from "@/lib/api/feedback.client";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { FeedbackSourceCard } from "./feedback-source-card";

const categories = [["content", "内容错误", CircleAlert], ["function", "功能问题", Settings], ["usage", "使用咨询", CircleHelp], ["suggestion", "改进建议", Lightbulb], ["other", "其他", MoreHorizontal]] as const;
export function feedbackCategory(value?: string): FeedbackCategory { return categories.find(([key]) => key === value)?.[0] ?? "content"; }

export function FeedbackForm({ initialCategory = "content", initialPath = "" }: { initialCategory?: FeedbackCategory; initialPath?: string }) {
  const router = useRouter();
  const [category, setCategory] = useState(initialCategory), [body, setBody] = useState(""), [contact, setContact] = useState(""), [consent, setConsent] = useState(false);
  const [path, setPath] = useState(() => safeFeedbackPath(initialPath)), [pathDraft, setPathDraft] = useState(""), [editingPath, setEditingPath] = useState(false), [pathError, setPathError] = useState("");
  const [state, setState] = useState<"idle" | "pending" | "error" | "unknown">("idle"), [message, setMessage] = useState(initialPath && !safeFeedbackPath(initialPath) ? "未关联该地址。反馈只接受站内公开页面，不接受账户资料或外部链接。" : ""), [receipt, setReceipt] = useState<FeedbackReceipt | null>(null);
  const operation = useRef<AbortController | null>(null), alive = useRef(true), epoch = useRef(0), nonce = useRef<{ fingerprint: string; request_id: string } | null>(null);
  const baseline = { category: initialCategory, body: "", contact: "", consent: false, path: safeFeedbackPath(initialPath), unsavedPath: "" };
  const dirty = useUnsavedForm(receipt ? null : { category, body, contact, consent, path, unsavedPath: editingPath && pathDraft !== path ? pathDraft : "" }, receipt ? null : baseline);
  useEffect(() => {
    alive.current = true;
    const unsubscribe = subscribeToSessionChanges(() => {
      epoch.current += 1; operation.current?.abort(); operation.current = null; nonce.current = null;
      setBody(""); setContact(""); setConsent(false); setReceipt(null); setState("idle"); setEditingPath(false); setPathDraft(""); setPathError("");
      setMessage("登录状态已变化，已清除前次反馈正文与联系信息。提交结果请以收到的回执为准。");
    });
    return () => { alive.current = false; operation.current?.abort(); unsubscribe(); };
  }, []);
  const pending = state === "pending", uncertain = state === "unknown";
  async function submit(event: FormEvent) {
    event.preventDefault(); if (operation.current || !consent || body.trim().length < 4 || body.trim().length > 500) return;
    const data = { category, body: body.trim(), contact: contact.trim(), path: safeFeedbackPath(path), consent: true as const };
    const fingerprint = JSON.stringify(data);
    if (nonce.current?.fingerprint !== fingerprint) nonce.current = { fingerprint, request_id: crypto.randomUUID() };
    const input: FeedbackInput = { ...data, request_id: nonce.current.request_id };
    const request = new AbortController(), version = epoch.current; operation.current = request; setState("pending"); setMessage("");
    try {
      const result = await submitPublicFeedback(input, request.signal);
      if (!alive.current || version !== epoch.current || request.signal.aborted) return;
      setReceipt(result); setBody(""); setContact(""); setConsent(false); setState("idle"); setMessage("");
    } catch (error) {
      if (!alive.current || version !== epoch.current) return;
      const unknown = !(error instanceof ApiRequestError) || error.status === 0 || error.status >= 500 || [408, 429].includes(error.status);
      setState(unknown ? "unknown" : "error");
      setMessage(unknown ? "尚未确认服务器是否收到反馈。输入和原请求已保留，请重试本次提交以取得回执，避免重复发送。" : error instanceof Error ? error.message : "反馈未能提交，输入仍保留。");
    } finally { if (operation.current === request) operation.current = null; }
  }
  function cancel() {
    if (pending) return;
    if ((dirty || uncertain) && !window.confirm(uncertain ? "本次反馈可能已被接收。离开将放弃本页草稿和重试入口，确定离开吗？" : "当前反馈尚未提交，确定放弃输入并返回帮助首页吗？")) return;
    operation.current?.abort(); setBody(""); setContact(""); setConsent(false); router.push("/help");
  }
  function closePath() {
    if (pathDraft !== path && !window.confirm("尚未保存关联页面，确定放弃本次修改吗？")) return;
    setEditingPath(false);
  }
  function savePath() {
    const normalized = safeFeedbackPath(pathDraft);
    if (pathDraft.trim() && !normalized) { setPathError("请输入站内公开页面路径，例如 /help/citation。不能关联账户、管理后台、外部链接或下载签名地址。"); return; }
    setPath(normalized); setEditingPath(false); setPathError("");
  }
  if (receipt) return <section className="stl4-feedback-success" aria-label="反馈提交结果"><span className="stl4-feedback-success-mark"><Check size={32} /></span><h2>提交成功</h2><p>{receipt.message || "感谢你的说明，反馈已接收。"}</p><dl><div><dt>反馈编号</dt><dd>{receipt.id}</dd></div><div><dt>接收时间</dt><dd>{new Date(receipt.created_at).toLocaleString("zh-CN")}</dd></div><div><dt>当前状态</dt><dd>{{ submitted: "已提交", reviewing: "处理中", resolved: "已处理" }[receipt.status]}</dd></div></dl><p>请保留反馈编号。提交成功表示服务已接收，不代表问题已处理完成。</p><div><Link className="stl4-support-primary" href="/help">返回帮助中心</Link><button type="button" onClick={() => { setReceipt(null); nonce.current = null; setCategory(initialCategory); setPath(safeFeedbackPath(initialPath)); }}>继续提交反馈</button></div></section>;
  return <><form className="stl4-feedback-form" onSubmit={event => void submit(event)} aria-busy={pending}><header><h2>提交反馈</h2><p>你可以报告内容错误、提出改进建议或咨询使用问题。不填写邮箱也可以提交。</p></header><fieldset disabled={pending || uncertain}><legend>反馈类型 <span aria-hidden="true">*</span></legend><div className="stl4-feedback-categories">{categories.map(([value, label, Icon]) => <label key={value}><input type="radio" name="category" value={value} checked={category === value} onChange={() => setCategory(value)} /><Icon size={18} /><span>{label}</span></label>)}</div><label className="stl4-feedback-field"><span>问题描述 <span aria-hidden="true">*</span></span><textarea value={body} onChange={event => setBody(event.target.value)} required minLength={4} maxLength={500} rows={5} placeholder="请简要描述遇到的问题、具体位置或改进建议。" /><small className="stl4-feedback-count" aria-live="polite">{body.length} / 500</small></label><div className="stl4-feedback-field"><span>相关页面（可选）</span>{path ? <div className="stl4-feedback-related"><FeedbackSourceCard path={path} /><button type="button" onClick={() => { setPathDraft(path); setPathError(""); setEditingPath(true); }}><RefreshCw size={14} />更换页面</button><button type="button" aria-label="移除相关页面" onClick={() => setPath("")}><X size={18} /></button></div> : <button className="stl4-feedback-add-page" type="button" onClick={() => { setPathDraft(""); setPathError(""); setEditingPath(true); }}><FileText size={17} />关联公开页面</button>}<small>仅发送所选公开路径；私人资料、检索词和下载令牌不会附带提交。</small></div><label className="stl4-feedback-field"><span>联系方式（可选）</span><input type="email" value={contact} onChange={event => setContact(event.target.value)} maxLength={254} placeholder="email@example.com" autoComplete="email" /><small>用于本次反馈处理。你也可以不提供。</small></label><label className="stl4-feedback-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} required /><span>我同意以上内容用于处理本次反馈并改进书库。联系方式不会公开。<Link href="/help/account">查看隐私说明</Link></span></label></fieldset>{message ? <p className="stl4-support-status" role={state === "error" || uncertain ? "alert" : "status"}>{message}</p> : null}<div className="stl4-feedback-actions"><button type="button" disabled={pending} onClick={cancel}>取消</button><button className="stl4-support-primary" type="submit" disabled={pending || !consent || body.trim().length < 4}>{pending ? "正在提交…" : uncertain ? "重试本次提交" : "提交反馈"}</button></div></form><Dialog open={editingPath} onRequestClose={closePath} className="stl4-support-path-dialog" aria-labelledby="feedback-path-title"><header><h2 id="feedback-path-title">关联公开页面</h2><button type="button" aria-label="关闭关联页面" onClick={closePath}><X size={20} /></button></header><label>站内公开页面路径<input value={pathDraft} maxLength={400} onChange={event => setPathDraft(event.target.value)} placeholder="/reader/文件标识?page=88" autoFocus /></label><p>可以粘贴站内路径。仅保留公开页面与 Reader 的 PDF 页码，其他查询参数会移除。</p>{pathError ? <p role="alert">{pathError}</p> : null}<footer><button type="button" onClick={closePath}>取消</button><button className="stl4-support-primary" type="button" onClick={savePath}>关联页面</button></footer></Dialog></>;
}

export function FeedbackAside() {
  return <aside className="stl4-feedback-aside" aria-label="反馈说明"><nav><a href="#feedback-form"><MessageCircle size={22} /><span><strong>提交反馈</strong><small>报告问题、提出建议或询问</small></span></a><a href="#feedback-process"><Check size={22} /><span><strong>反馈处理流程</strong><small>提交、查看回执与处理状态</small></span></a><a href="#feedback-privacy"><LockKeyhole size={22} /><span><strong>隐私说明</strong><small>只提交处理问题所需的信息</small></span></a></nav><details id="feedback-process"><summary>我们如何处理反馈</summary><p>提交成功后会提供回执。状态分为已提交、处理中和已处理；处理时效取决于具体问题，不作固定回复时间承诺。</p></details><details id="feedback-privacy"><summary>可以反馈哪些内容</summary><p>内容错误、功能问题、使用咨询与改进建议均可提交。请勿发送密码、登录令牌、私人稿件或未获同意的他人资料。</p></details><div><h3><CircleHelp size={22} />常见问题</h3><Link href="/help/search">找不到想要的书？</Link><Link href="/help/citation">引用格式如何生成？</Link><Link href="/help/source">如何报告来源错误？</Link><Link href="/help?section=faq">查看全部问题</Link></div></aside>;
}
