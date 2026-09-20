"use client";

import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export function DraftConflict<T extends { edit_version: string }>({ endpoint, local, onUseRemote, onKeepLocal }: { endpoint: string; local: T; onUseRemote: (remote: T) => void; onKeepLocal: (remote: T) => void }) {
  const [remote, setRemote] = useState<T | null>(null), [message, setMessage] = useState("");
  async function compare() { try { setRemote(await apiRequest<T>(endpoint, {}, getServerSessionCredential())); } catch (error) { setMessage(error instanceof Error ? error.message : "读取失败"); } }
  return <section className="v307-conflict" role="alert"><h2>这份内容已被另一位管理员修改</h2><p>你的输入保留在左侧。先比较最新已保存内容，再决定使用哪一份；不会自动覆盖。</p>{!remote ? <button className="button secondary" onClick={compare}>读取最新内容并比较</button> : <><div className="v307-conflict-comparison"><section><h3>当前输入</h3><ContentSummary value={local} /></section><section><h3>最新已保存内容</h3><ContentSummary value={remote} /></section></div><div><button className="button secondary" onClick={() => onUseRemote(remote)}>使用最新已保存内容</button><button className="button secondary" onClick={() => onKeepLocal(remote)}>已比较，保留我的输入继续编辑</button></div><p>继续编辑后仍需明确保存；若其他人再次修改，保存会再次提示冲突。</p></>}{message ? <p>{message}</p> : null}</section>;
}
const hidden = new Set(["edit_version", "draft_revision_id", "id", "has_unpublished_changes", "match_candidates", "work_url", "reader_url", "status", "position", "created_at", "updated_at"]);
const labels: Record<string, string> = {title: "标题", slug: "地址名称", issue_label: "期名", introduction: "导语", public_byline: "公开署名", display_from: "展示时间", published_at: "发布时间", cover_url: "主图", body_blocks: "正文", text: "内容", source: "出处", url: "链接", items: "推荐书目", kind: "类型", authors: "作者", version_note: "版本说明", note: "推介语", config: "网站设置", about_blocks: "关于书库", key: "固定模块", body: "正文", visible: "显示", action_label: "链接文字", action_href: "链接地址", navigation: "导航", site_name: "书库名称", wordmark_lines: "标志文字", intro_lines: "导语", copyright_text: "版权文字", home_title_left_lines: "标题第一行", home_title_right_lines: "标题第二行", home_hero_image: "首页主图", home_hero_alt: "图片说明"};
function ContentSummary({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span>未填写</span>;
  if (Array.isArray(value)) return <ol>{value.map((item, index) => <li key={index}><ContentSummary value={item} /></li>)}</ol>;
  if (typeof value === "object") return <dl>{Object.entries(value).filter(([key]) => !hidden.has(key) && !key.endsWith("_id")).map(([key, item]) => <div key={key}><dt>{labels[key] || key}</dt><dd><ContentSummary value={item} /></dd></div>)}</dl>;
  if (typeof value === "boolean") return <span>{value ? "是" : "否"}</span>;
  return <span>{String(value)}</span>;
}
