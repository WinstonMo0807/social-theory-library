"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Copy, SlidersHorizontal } from "lucide-react";
import { formatSourceText, omitSourceMarginalia } from "@/lib/source-text";
import { SourceText } from "./source-text";
import styles from "./source-excerpt.module.css";

/** Display controls never feed cleaned text back into citation/source APIs. */
export function SourceExcerpt({ text, label = "原文节选", location, marginalia = [], validateSource }: {
  text: string; label?: string; location?: string; marginalia?: readonly string[]; validateSource?: () => Promise<void>;
}) {
  const id = useId();
  const [mode, setMode] = useState<"reading" | "original" | "compare">("reading");
  const [join, setJoin] = useState(true);
  const [omit, setOmit] = useState(false);
  const [copied, setCopied] = useState(false);
  const [manual, setManual] = useState(false);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState("");
  const settings = useRef<HTMLDetailsElement>(null);
  useEffect(() => { setCopied(false); setManual(false); }, [text]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (settings.current && !settings.current.contains(event.target as Node)) settings.current.open = false; };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  const cleaned = useMemo(() => formatSourceText(omit ? omitSourceMarginalia(text, marginalia) : text, { joinSpacedLines: join }), [text, marginalia, omit, join]);
  async function copy() {
    if (copying) return;
    setCopying(true); setError(""); setManual(false); setCopied(false);
    try { await validateSource?.(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "来源核对失败，请重新读取。"); setCopying(false); return; }
    try { await navigator.clipboard.writeText(mode === "original" ? text : cleaned); setCopied(true); setManual(false); }
    catch { setManual(true); setCopied(false); }
    finally { setCopying(false); }
  }
  return <section className={styles.excerpt} aria-label={label}>
    <header className={styles.header}><strong>{label}</strong>{location ? <span>{location}</span> : null}</header>
    <div className={styles.toolbar}>
      <div className={styles.modes} role="group" aria-label={`${label}排版方式`}>
        {([["reading", "舒适阅读"], ["original", "原始换行"], ["compare", "对照"]] as const).map(([value, title]) => <button key={value} type="button" aria-pressed={mode === value} disabled={copying} onClick={() => { setMode(value); setCopied(false); setManual(false); if(settings.current) settings.current.open = false; }}>{title}</button>)}
      </div>
      <details ref={settings} className={styles.settings} onKeyDown={event => { if(event.key === "Escape" && settings.current?.open) { event.preventDefault(); event.stopPropagation(); settings.current.open = false; settings.current.querySelector("summary")?.focus(); } }}><summary><SlidersHorizontal size={15} />格式清洗</summary><div className={styles.popover}>
        <label><input type="checkbox" checked={join} onChange={event => { setJoin(event.target.checked); setCopied(false); setManual(false); }} />合并 OCR 段内空行</label>
        {marginalia.length ? <label><input type="checkbox" checked={omit} onChange={event => { setOmit(event.target.checked); setCopied(false); }} />隐藏已知页眉、页码</label> : null}
        <p>只整理显示，不改写文字或原件。</p>
      </div></details>
    </div>
    <div id={id} className={styles.texts} data-compare={mode === "compare" || undefined}>
      {mode !== "reading" ? <div>{mode === "compare" ? <small>原始换行</small> : null}<SourceText text={text} original /></div> : null}
      {mode !== "original" ? <div>{mode === "compare" ? <small>舒适阅读</small> : null}<SourceText text={cleaned} original /></div> : null}
    </div>
    <footer className={styles.footer}><button type="button" onClick={() => void copy()} disabled={copying} aria-busy={copying} aria-describedby={id}>{copied ? <Check size={14} /> : <Copy size={14} />}{copying ? "核对来源…" : copied ? "已复制" : mode === "original" ? "复制原始文字" : "复制排版文本"}</button><span role="status">{copied ? "已复制当前显示文字" : ""}</span></footer>
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    {manual ? <label className={styles.manual}>自动复制未完成，请选中文字复制<textarea readOnly value={mode === "original" ? text : cleaned} onFocus={event => event.currentTarget.select()} /></label> : null}
  </section>;
}
