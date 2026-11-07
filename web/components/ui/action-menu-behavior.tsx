"use client";

import { useEffect } from "react";

/** Opt in action menus only. Reading disclosures and editing forms stay open. */
export function ActionMenuBehavior() {
  useEffect(() => {
    const openMenus = () => Array.from(document.querySelectorAll<HTMLDetailsElement>('details[data-action-menu][open]'));
    const close = (menu: HTMLDetailsElement, restore = false) => {
      menu.open = false;
      if (restore) menu.querySelector<HTMLElement>("summary")?.focus({ preventScroll: true });
    };
    const outside = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return;
      openMenus().forEach(menu => { if (!menu.contains(event.target as Node)) close(menu); });
    };
    const keys = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const menus = openMenus();
      if (menus.length) { event.preventDefault(); event.stopPropagation(); }
      menus.forEach(menu => { close(menu, menu.contains(document.activeElement)); });
    };
    const focus = (event: FocusEvent) => {
      if (event.target instanceof Node) openMenus().forEach(menu => { if (!menu.contains(event.target as Node)) close(menu); });
    };
    const position = (menu: HTMLDetailsElement) => {
      const panel = menu.querySelector<HTMLElement>(":scope > [data-menu-panel]");
      if (!panel) return;
      const anchor = menu.getBoundingClientRect();
      const width = Math.min(224, window.innerWidth - 32);
      panel.style.width = `${width}px`;
      panel.style.left = `${Math.max(16, Math.min(anchor.right - width, window.innerWidth - width - 16))}px`;
      panel.style.top = `${Math.max(16, anchor.bottom + panel.offsetHeight + 12 > window.innerHeight ? anchor.top - panel.offsetHeight - 8 : anchor.bottom + 8)}px`;
    };
    const toggle = (event: Event) => {
      const menu = event.target;
      if (!(menu instanceof HTMLDetailsElement) || !menu.hasAttribute("data-action-menu")) return;
      menu.querySelector("summary")?.setAttribute("aria-expanded", String(menu.open));
      if (!menu.open) return;
      openMenus().forEach(other => { if (other !== menu && !other.contains(menu)) close(other); });
      position(menu);
    };
    const activate = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("button,a[href]") : null;
      const menu = target?.closest<HTMLDetailsElement>('details[data-action-menu][open]');
      if (menu && !target?.closest("form")) close(menu);
    };
    const reposition = () => openMenus().forEach(position);
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", keys, true);
    document.addEventListener("focusin", focus);
    document.addEventListener("toggle", toggle, true);
    document.addEventListener("click", activate);
    window.addEventListener("resize", reposition);
    document.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", keys, true);
      document.removeEventListener("focusin", focus);
      document.removeEventListener("toggle", toggle, true);
      document.removeEventListener("click", activate);
      window.removeEventListener("resize", reposition);
      document.removeEventListener("scroll", reposition, true);
    };
  }, []);
  return null;
}
