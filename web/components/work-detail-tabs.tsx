"use client";
import { useEffect, useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import styles from "./work-detail.module.css";

export type WorkDetailPresentation = "publication" | "contents" | "bibliography" | "reading";

export function WorkDetailSummary({ summary }: { summary: string }) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  return <div className={styles.summary}><p id={id} className="work-summary" data-expanded={expanded}>{summary}</p>{summary ? <button type="button" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)}>{expanded ? "收起" : "展开更多"}<ChevronRight size={15} aria-hidden="true"/></button> : null}</div>;
}

export function WorkDetailTabs({ panels, children, aside, introduction, presentation = "publication" }: {
  panels: { id: string; label: string; content: ReactNode }[];
  children?: ReactNode;
  aside?: ReactNode;
  introduction?: ReactNode;
  presentation?: WorkDetailPresentation;
}) {
  const [selected, setSelected] = useState(panels[0]?.id);
  const active = panels.some(panel => panel.id === selected) ? selected : panels[0]?.id;
  const scope = useId();
  const vertical = presentation === "contents";
  useEffect(() => {
    const locate = () => { if (window.location.hash === "#citation") setSelected("edition"); };
    const timer = window.setTimeout(locate, 0);
    window.addEventListener("hashchange", locate);
    return () => { window.clearTimeout(timer); window.removeEventListener("hashchange", locate); };
  }, []);
  return <div className={styles.layout} data-presentation={presentation}>
    {children}
    {aside ? <aside className={styles.aside}>{aside}</aside> : null}
    {introduction ? <section className={styles.introduction}>{introduction}</section> : null}
    <nav className={`${styles.navigation} work-detail-tabs`} aria-label="图书内容">
      {vertical ? <h2>在本书中</h2> : null}
      <div role="tablist" aria-label="图书内容" aria-orientation={vertical ? "vertical" : "horizontal"}>
        {panels.map((panel, index) => <button key={panel.id} type="button" role="tab" id={`${scope}-${panel.id}-tab`} aria-controls={`${scope}-${panel.id}`} aria-selected={active === panel.id} tabIndex={active === panel.id ? 0 : -1} onClick={() => setSelected(panel.id)} onKeyDown={event => {
          const nextKey = vertical ? "ArrowDown" : "ArrowRight";
          const previousKey = vertical ? "ArrowUp" : "ArrowLeft";
          const next = event.key === nextKey ? (index + 1) % panels.length : event.key === previousKey ? (index + panels.length - 1) % panels.length : event.key === "Home" ? 0 : event.key === "End" ? panels.length - 1 : -1;
          if (next < 0) return;
          event.preventDefault();
          setSelected(panels[next].id);
          event.currentTarget.ownerDocument.getElementById(`${scope}-${panels[next].id}-tab`)?.focus();
        }}>{panel.label}{vertical ? <ChevronRight size={16} aria-hidden="true"/> : null}</button>)}
      </div>
    </nav>
    {panels.map(panel => <section className={`${styles.panel} work-detail-tab-panel`} role="tabpanel" tabIndex={0} aria-labelledby={`${scope}-${panel.id}-tab`} id={`${scope}-${panel.id}`} key={panel.id} hidden={active !== panel.id}>{panel.content}</section>)}
  </div>;
}
