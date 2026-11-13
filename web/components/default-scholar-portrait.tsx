"use client";

import { useEffect, useRef, type CSSProperties } from "react";
import { defaultScholarPortraitVariant, scholarNameSize, scholarPortraitBackgrounds } from "@/lib/default-scholar-portrait";
import styles from "./default-scholar-portrait.module.css";

/** Retains each surface's existing portrait dimensions while sharing the artwork. */
export function ScholarPortraitFallback({ name, identity, className }: { name: string; identity: string; className?: string }) {
  return <span className={className} style={{ position: "relative", display: "block", overflow: "hidden", flexShrink: 0 }}><DefaultScholarPortrait name={name} identity={identity}/></span>;
}

export function DefaultScholarPortrait({ name, identity, className, eager = false }: {
  name: string; identity: string; className?: string; eager?: boolean;
}) {
  const box = useRef<HTMLSpanElement>(null);
  const text = useRef<HTMLSpanElement>(null);
  const variant = defaultScholarPortraitVariant(identity || name);
  const background = `/images/scholars/default-${scholarPortraitBackgrounds[variant]}`;

  useEffect(() => {
    const frame = box.current, label = text.current;
    if (!frame || !label) return;
    let active = true, scheduled = 0;
    function fit() {
      if (!active || !frame || !label || !frame.clientWidth || !frame.clientHeight) return;
      label.style.removeProperty("font-size");
      const fits = () => label.scrollHeight <= frame.clientHeight + 1 && label.scrollWidth <= frame.clientWidth + 1;
      if (fits()) return;
      let low = 1, high = parseFloat(getComputedStyle(label).fontSize);
      for (let step = 0; step < 9; step++) {
        const size = (low + high) / 2;
        label.style.fontSize = `${size}px`;
        if (fits()) low = size; else high = size;
      }
      label.style.fontSize = `${low}px`;
    }
    function schedule() { cancelAnimationFrame(scheduled); scheduled = requestAnimationFrame(fit); }
    const observer = new ResizeObserver(schedule);
    observer.observe(frame);
    schedule();
    void document.fonts.ready.then(() => { if (active) schedule(); });
    document.fonts.addEventListener("loadingdone", schedule);
    return () => {
      active = false;
      observer.disconnect();
      cancelAnimationFrame(scheduled);
      document.fonts.removeEventListener("loadingdone", schedule);
    };
  }, [name]);

  return <span className={[styles.portrait, className].filter(Boolean).join(" ")} data-default-portrait={"JKLM"[variant]}
    role="img" aria-label={`${name}，姓名卡片`} style={{ "--scholar-name-size": `${scholarNameSize(name)}cqi` } as CSSProperties}>
    <img className={styles.art} src={`${background}-640.webp`} srcSet={`${background}-640.webp 640w, ${background}-1280.webp 1280w`}
      sizes="(max-width: 760px) 60vw, 420px" width={1280} height={1280} alt="" aria-hidden="true" loading={eager ? "eager" : "lazy"}/>
    <span className={styles.copy} ref={box} aria-hidden="true"><span className={styles.name} ref={text}>{name.split(/(?<=[·・‧-])/u).map((part, index) => <span className={styles.part} key={index}>{part}</span>)}</span></span>
  </span>;
}
