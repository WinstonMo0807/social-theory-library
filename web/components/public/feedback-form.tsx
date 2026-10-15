"use client";

import { FormEvent, useState } from "react";
import { apiRequest } from "@/lib/api";

type FeedbackResponse = { message: string; id: string; status: string };

export function FeedbackForm() {
  const [category, setCategory] = useState("function");
  const [body, setBody] = useState("");
  const [contact, setContact] = useState("");
  const [state, setState] = useState<"idle" | "pending" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("pending"); setMessage("");
    try { const result = await apiRequest<FeedbackResponse>("/catalog/feedback/", { method: "POST", body: JSON.stringify({ category, body, contact, path: window.location.pathname }) }); setState("success"); setMessage(result.message); setBody(""); }
    catch (error) { setState("error"); setMessage(error instanceof Error ? error.message : "反馈暂时无法提交，请稍后重试。"); }
  }
  return <form className="stl4-feedback-form" onSubmit={submit}><label><span>反馈类型</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="content">内容</option><option value="function">功能</option><option value="citation">引用</option><option value="accessibility">无障碍</option><option value="other">其他</option></select></label><label><span>你想告诉我们什么？</span><textarea value={body} onChange={(event) => setBody(event.target.value)} required minLength={4} maxLength={5000} rows={8} placeholder="请描述出现问题的页面、操作步骤和你期待的结果。" /></label><label><span>联系邮箱（可选）</span><input type="email" value={contact} onChange={(event) => setContact(event.target.value)} placeholder="如果希望收到回复，请留下邮箱" /></label><button type="submit" disabled={state === "pending"}>{state === "pending" ? "正在提交……" : "提交反馈"}</button>{message ? <p className={state === "error" ? "is-error" : "is-success"} role={state === "error" ? "alert" : "status"}>{message}</p> : null}</form>;
}
