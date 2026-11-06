"use client";

import { useState, type Dispatch, type SetStateAction } from "react";
import { ArrowDown, ArrowUp, BookOpen, Plus, X } from "lucide-react";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";
import { normalizePublicResourceUrl } from "@/lib/api";
import { welcomeContent, welcomeTextLabels, type WelcomeConfig, type WelcomeCopy } from "@/lib/welcome";
import { SiteHomePicker } from "./site-home-picker";
import styles from "./welcome-fields.module.css";

export const welcomeSections = [
  ["welcome-copy", "首屏三版文案"], ["welcome-books", "展示书籍"],
  ["welcome-history", "学科史演示"], ["welcome-body", "页面介绍"],
] as const;

export function WelcomeFields({ owner, draft, setDraft, active, busy }: {
  owner: string; draft: SiteContentDraft; setDraft: Dispatch<SetStateAction<SiteContentDraft | null>>; active: string; busy: boolean;
}) {
  const [variant, setVariant] = useState(0), [picker, setPicker] = useState(false);
  const content = welcomeContent(draft.config.welcome);
  const config = draft.config.welcome || {};
  const ids = config.edition_ids;
  const books = draft.config.welcome_books || [];
  function update(patch: Partial<WelcomeConfig>) {
    setDraft(current => current ? { ...current, config: { ...current.config, welcome: { ...current.config.welcome, ...patch } } } : current);
  }
  function updateCopy(patch: Partial<WelcomeCopy>) { update({ copies: content.copies.map((copy, index) => index === variant ? { ...copy, ...patch } : copy) }); }
  function move(index: number, offset: number) { const next = [...(ids || [])]; next.splice(index + offset, 0, ...next.splice(index, 1)); update({ edition_ids: next }); }
  const textKeys = Object.keys(welcomeTextLabels) as Array<keyof typeof welcomeTextLabels>;
  const fields = <>{textKeys.filter(key => key.startsWith("history_") === (active === "welcome-history")).map(key => <label key={key}>{welcomeTextLabels[key]}<textarea rows={key.endsWith("body") ? 3 : 2} maxLength={key.endsWith("body") ? 600 : 80} value={content.texts[key]} onChange={event => update({ texts: { ...config.texts, [key]: event.target.value } })} /></label>)}</>;
  return <>
    <fieldset disabled={busy} className={styles.fields}>
      {active === "welcome-copy" ? <>
        <p className={styles.note}>每次打开欢迎页，随机呈现其中一版。</p>
        <nav className={styles.variants} aria-label="编辑欢迎文案">{content.copies.map((copy, index) => <button type="button" key={copy.id} aria-pressed={variant === index} onClick={() => setVariant(index)}>{copy.label}</button>)}</nav>
        <label>标题第一行<input maxLength={24} value={content.copies[variant].title[0]} onChange={event => updateCopy({ title: [event.target.value, content.copies[variant].title[1]] })} /></label>
        <label>标题第二行<input maxLength={24} value={content.copies[variant].title[1]} onChange={event => updateCopy({ title: [content.copies[variant].title[0], event.target.value] })} /></label>
        <label>引言<textarea rows={3} maxLength={160} value={content.copies[variant].lead} onChange={event => updateCopy({ lead: event.target.value })} /></label>
        {([["question", "演示提问", 60], ["results", "检索结果标题", 24], ["reader", "原文阅读标题", 24], ["saved", "保存材料提示", 40]] as const).map(([key, label, max]) => <label key={key}>{label}<input maxLength={max} value={content.copies[variant][key]} onChange={event => updateCopy({ [key]: event.target.value })} /></label>)}
      </> : active === "welcome-books" ? <>
        <div className={styles.variants}><button type="button" aria-pressed={ids == null} onClick={() => update({ edition_ids: null })}>跟随馆藏推荐</button><button type="button" aria-pressed={ids != null} onClick={() => { if (ids == null) update({ edition_ids: [] }); }}>自选书籍</button></div>
        {ids == null ? <p className={styles.note}>使用公开馆藏推荐的前三本。切换到自选后，可固定书籍与顺序。</p> : <>
          <ol className={styles.books}>{ids.map((id, index) => { const book = books.find(row => row.id === id); return <li key={id}>
            {book?.coverImage ? <img src={normalizePublicResourceUrl(book.coverImage)} alt="" width={46} height={66} /> : <BookOpen size={30} />}
            <div><strong>{book?.title || "来源不可用"}</strong>{book?.available === false ? <span role="alert">请更换或移除</span> : null}</div>
            <div className={styles.bookActions}><button type="button" disabled={index === 0} aria-label={`上移${book?.title || "书籍"}`} onClick={() => move(index, -1)}><ArrowUp size={16} /></button><button type="button" disabled={index === ids.length - 1} aria-label={`下移${book?.title || "书籍"}`} onClick={() => move(index, 1)}><ArrowDown size={16} /></button><button type="button" aria-label={`移除${book?.title || "书籍"}`} onClick={() => update({ edition_ids: ids.filter(value => value !== id) })}><X size={16} /></button></div>
          </li>; })}</ol>
          <button type="button" disabled={ids.length >= 3} onClick={() => setPicker(true)}><Plus size={16} />选择书籍（{ids.length}/3）</button>
          {!ids.length ? <p className={styles.note}>未选书籍时，演示使用阅读示意，不显示具体书目。</p> : null}
        </>}
      </> : active === "welcome-history" ? fields : <>
        <div className={styles.sections}>{content.chapters.map((chapter, index) => <details key={chapter.href} open={index === 0}><summary>{chapter.title || `功能介绍 ${index + 1}`}</summary>{(["title", "text", "action"] as const).map(key => <label key={key}>{{ title: "标题", text: "介绍", action: "按钮文字" }[key]}<textarea rows={key === "text" ? 3 : 2} maxLength={{ title: 40, text: 240, action: 16 }[key]} value={chapter[key]} onChange={event => update({ chapters: content.chapters.map((row, position) => ({ title: row.title, text: row.text, action: row.action, ...(position === index ? { [key]: event.target.value } : {}) })) })} /></label>)}</details>)}</div>
        <details className={styles.sections}><summary>其他页面文字</summary>{fields}</details>
      </>}
    </fieldset>
    {picker ? <SiteHomePicker owner={owner} area="featured" onlyEditions used={(ids || []).map(id => ({ type: "edition", id }))} disabled={busy || (ids?.length || 0) >= 3} onClose={() => setPicker(false)} onChoose={choice => {
      if (busy || (ids?.length || 0) >= 3 || ids?.includes(choice.target.id)) return;
      setDraft(current => current ? { ...current, config: { ...current.config, welcome: { ...current.config.welcome, edition_ids: [...(current.config.welcome?.edition_ids || []), choice.target.id] }, welcome_books: [...(current.config.welcome_books || []).filter(row => row.id !== choice.target.id), { id: choice.target.id, title: choice.source.title, author: "", coverImage: choice.source.image_url, available: true }] } } : current);
      setPicker(false);
    }} /> : null}
  </>;
}
