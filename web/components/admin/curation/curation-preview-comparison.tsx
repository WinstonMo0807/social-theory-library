"use client";

import { useLayoutEffect, useRef } from "react";
import { PreviewSurface, type KnowledgePreviewPayload } from "../preview/knowledge-page-preview";
import type { CurationPreviewChange } from "./curation-preview-changes";
import styles from "./curation-preview-comparison.module.css";

/** Read-only copies of the real rendered modules preserve each public component's markup. */
export function CurationPreviewComparison({ payload, change, perspective }: { payload: KnowledgePreviewPayload; change?: CurationPreviewChange; perspective: "draft" | "published" }) {
  const currentRef = useRef<HTMLDivElement>(null);
  const publishedRef = useRef<HTMLDivElement>(null);
  const pageId = change?.pageId || "overview";
  const surface = payload.perspectives[perspective];

  useLayoutEffect(() => {
    const current = currentRef.current;
    if (!current || !change || !surface.available) return;
    const moduleAt = (root: HTMLElement | null) => Array.from(root?.querySelectorAll<HTMLElement>("[data-module-id]") || []).find(element => element.dataset.moduleId === (change.preview_anchor || change.module_id));
    const target = moduleAt(current);
    if (perspective === "published") {
      if (!target) return;
      target.classList.add(styles.focused);
      return () => target.classList.remove(styles.focused);
    }
    const original = moduleAt(publishedRef.current);
    if (!target && !original) return;
    const owner = current.ownerDocument;
    const comparison = owner.createElement("section");
    comparison.className = styles.comparison;
    comparison.setAttribute("aria-label", `${change.display_name}的未发布修改`);
    comparison.setAttribute("inert", "");
    const title = owner.createElement("h2");
    title.textContent = target?.querySelector("h2")?.textContent || original?.querySelector("h2")?.textContent || change.display_name;
    comparison.append(title);
    const columns = owner.createElement("div");
    columns.className = styles.columns;
    for (const [label, source] of [["当前线上", original], ["修改后", target]] as const) {
      const column = owner.createElement("div");
      const heading = owner.createElement("h3");
      heading.textContent = label;
      if (label === "修改后") {
        const badge = owner.createElement("small");
        badge.textContent = "尚未发布";
        heading.append(badge);
      }
      column.append(heading);
      if (source) {
        const copy = source.cloneNode(true) as HTMLElement;
        // Clones are inert snapshots, not another set of live controls or anchor identities.
        [copy, ...copy.querySelectorAll<HTMLElement>("[id], [data-module-id]")].forEach(element => { element.removeAttribute("id"); element.removeAttribute("data-module-id"); });
        const repeatedHeading = copy.querySelector("h2");
        if (repeatedHeading?.parentElement?.classList.contains("section-heading")) repeatedHeading.parentElement.remove();
        else repeatedHeading?.remove();
        if (label === "修改后") {
          const previousCards = Array.from(original?.querySelectorAll<HTMLElement>(".book-card") || []);
          copy.querySelectorAll<HTMLElement>(".book-card").forEach(card => {
            const href = card.querySelector("a.book-cover-link")?.getAttribute("href");
            const before = href ? previousCards.find(row => row.querySelector("a.book-cover-link")?.getAttribute("href") === href) : undefined;
            if (!before || before.innerHTML !== card.innerHTML) card.classList.add(styles.changedCard);
          });
        }
        column.append(copy);
      } else {
        const empty = owner.createElement("p");
        empty.textContent = "—";
        column.append(empty);
      }
      columns.append(column);
    }
    comparison.append(columns);
    const wasHidden = target?.hidden;
    if (target) { target.before(comparison); target.hidden = true; }
    else current.querySelector("main")?.append(comparison);
    const frame = owner.defaultView?.frameElement as HTMLIFrameElement | null;
    const viewport = frame?.closest<HTMLElement>(".selected-preview-viewport");
    const timer = requestAnimationFrame(() => {
      if (!frame || !viewport || !comparison.isConnected) return;
      const scale = frame.getBoundingClientRect().width / frame.clientWidth;
      const top = comparison.getBoundingClientRect().top * scale + frame.getBoundingClientRect().top;
      if (top > viewport.getBoundingClientRect().bottom - 140) viewport.scrollTop += top - viewport.getBoundingClientRect().top - 120;
    });
    return () => { cancelAnimationFrame(timer); comparison.remove(); if (target) target.hidden = Boolean(wasHidden); };
  }, [change, payload, perspective, surface.available]);

  return <div className={styles.root}>
    <div ref={currentRef} inert><PreviewSurface payload={{ ...payload, perspective: surface, active_perspective: perspective }} pageId={pageId}/></div>
    {perspective === "draft" && change && payload.perspectives.published.available ? <div ref={publishedRef} hidden aria-hidden="true" inert><PreviewSurface payload={{ ...payload, perspective: payload.perspectives.published, active_perspective: "published" }} pageId={pageId}/></div> : null}
  </div>;
}
