"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Copy, SlidersHorizontal } from "lucide-react";
import { formatSourceText, omitSourceMarginalia } from "@/lib/source-text";
import { SourceText } from "./source-text";
import styles from "./source-excerpt.module.css";

/** Display controls never feed cleaned text back into citation/source APIs. */
export function SourceExcerpt({ text, label = "原文节选", location, marginalia = [], validateSource, preserveLayout = false }: {
  text: string; label?: string; location?: string; marginalia?: readonly string[]; validateSource?: () => Promise<void>; preserveLayout?: boolean;
}) {
  const id = useId();
  const [join, setJoin] = useState(!preserveLayout);
  const [omit, setOmit] = useState(true);
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
  const cleaned = useMemo(() => { const visible=omit ? omitSourceMarginalia(text, marginalia) : text; return preserveLayout?visible:formatSourceText(visible, { joinSpacedLines: join }); }, [text, marginalia, omit, join, preserveLayout]);
  async function copy() {
    if (copying) return;
    setCopying(true); setError(""); setManual(false); setCopied(false);
    try { await validateSource?.(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "来源核对失败，请重新读取。"); setCopying(false); return; }
    try { await navigator.clipboard.writeText(cleaned); setCopied(true); setManual(false); }
    catch { setManual(true); setCopied(false); }
    finally { setCopying(false); }
  }
  return <section className={styles.excerpt} aria-label={label}>
    <header className={styles.header}><strong>{label}</strong>{location ? <span>{location}</span> : null}</header>
    <div className={styles.toolbar}>
      <details ref={settings} className={styles.settings} onKeyDown={event => { if(event.key === "Escape" && settings.current?.open) { event.preventDefault(); event.stopPropagation(); settings.current.open = false; settings.current.querySelector("summary")?.focus(); } }}><summary><SlidersHorizontal size={15} />格式清洗</summary><div className={styles.popover}>
        {!preserveLayout&&<label><input type="checkbox" checked={join} onChange={event => { setJoin(event.target.checked); setCopied(false); setManual(false); }} />合并 OCR 段内空行</label>}
        {marginalia.length ? <label><input type="checkbox" checked={omit} onChange={event => { setOmit(event.target.checked); setCopied(false); setManual(false); }} />隐藏已知页眉、页码</label> : null}
        <p>只整理显示，不改写文字或原件。</p>
      </div></details>
    </div>
    <div id={id} className={styles.texts}>{cleaned.split(/\n{2,}/).map((paragraph,index)=><p key={index}><SourceText text={paragraph} original /></p>)}</div>
    <footer className={styles.footer}><button type="button" onClick={() => void copy()} disabled={copying} aria-busy={copying} aria-describedby={id}>{copied ? <Check size={14} /> : <Copy size={14} />}{copying ? "核对来源…" : copied ? "已复制" : "复制原文"}</button><span role="status">{copied ? "已复制当前显示文字" : ""}</span></footer>
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    {manual ? <label className={styles.manual}>自动复制未完成，请选中文字复制<textarea readOnly value={cleaned} onFocus={event => event.currentTarget.select()} /></label> : null}
  </section>;
}
