"use client";

import { useLayoutEffect, useRef, type RefObject, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { GripHorizontal } from "lucide-react";
import { createReaderFloatingLayout, type FloatingLayout } from "@/lib/reader-floating-layout.mjs";
import styles from "./reader-floating-controls.module.css";

export function useReaderFloatingLayout(root: RefObject<HTMLDivElement | null>, owner: string) {
  const controller = useRef<FloatingLayout | null>(null);
  useLayoutEffect(() => {
    if (!root.current) return;
    const layout = createReaderFloatingLayout(root.current, `stl-reader-layout-v1:${owner}`);
    controller.current = layout;
    return () => { layout.destroy(); controller.current = null; };
  }, [root, owner]);
  useLayoutEffect(() => { controller.current?.refresh(); });
  return () => controller.current?.reset();
}

export function ReaderGrip({ label }: { label: string }) {
  return <button type="button" data-reader-grip className={styles.grip} aria-label={`移动${label}`} title={`拖动${label}；方向键移动，Home 归位`}><GripHorizontal size={17} /></button>;
}

export type ReaderContextAction = { id?: string; label: string; icon: ReactNode; run(): void; disabled?: boolean; group?: boolean };
export function ReaderContextMenu({ x, y, actions, close, pageLabel }: { x: number; y: number; actions: ReaderContextAction[]; close(): void; pageLabel: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const reposition = () => {
      const rect = element.getBoundingClientRect();
      element.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
      element.style.top = `${Math.max(8, Math.min(y, window.innerHeight - rect.height - 8))}px`;
    };
    reposition();
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => { if (!element.contains(event.target as Node)) close(); };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', reposition);
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', reposition); if (element.contains(document.activeElement)) previous?.focus({ preventScroll: true }); };
  // Menu actions update without re-opening or moving keyboard focus.
  }, [x, y, close]);
  return <div ref={ref} className={styles.context} role="menu" aria-label="STL 阅读菜单" style={{ left: x, top: y }} onContextMenu={event => event.preventDefault()} onMouseDown={event => event.preventDefault()} onKeyDown={event => {
    if (event.key === 'Escape' || event.key === 'Tab') { event.preventDefault(); event.stopPropagation(); close(); return; }
    if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...(ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    buttons[event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
  }}>
    <div className={styles.menuHeading}><img src="/brand/stl-symbol-20261027.svg" alt="" /> <span>阅读工具<small>{pageLabel}</small></span></div>
    {actions.map(action => <button key={action.id || action.label} role="menuitem" className={action.group ? styles.group : undefined} disabled={action.disabled} onClick={() => { flushSync(close); action.run(); }}>{action.icon}<span>{action.label}</span></button>)}
    <small className={styles.hint}>Shift + 右键可使用浏览器菜单</small>
  </div>;
}
