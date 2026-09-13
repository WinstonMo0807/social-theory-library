"use client";

import type { ComponentPropsWithoutRef, KeyboardEvent, ReactNode } from "react";
import { Button } from "./controls";

export type TabItem<T extends string> = {
  value: T;
  label: ReactNode;
  id: string;
  panelId: string;
  disabled?: boolean;
};

export type TabsProps<T extends string> = Omit<ComponentPropsWithoutRef<"div">, "onChange" | "children"> & {
  "aria-label": string;
  items: readonly TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
};

/** Automatic activation with one tab stop and the standard horizontal keys. */
export function Tabs<T extends string>({ items, value, onChange, ...props }: TabsProps<T>) {
  function navigate(event: KeyboardEvent<HTMLButtonElement>, current: T) {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    const enabled = items.filter((item) => !item.disabled);
    if (!enabled.length) return;
    event.preventDefault();
    const index = enabled.findIndex((item) => item.value === current);
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + enabled.length) % enabled.length;
    const next = enabled[nextIndex];
    onChange(next.value);
    document.getElementById(next.id)?.focus();
  }

  const focusValue = items.some((item) => item.value === value && !item.disabled) ? value : items.find((item) => !item.disabled)?.value;
  return <div {...props} role="tablist" aria-orientation="horizontal">
    {items.map((item) => <Button key={item.value} id={item.id} role="tab" className={value === item.value ? "active" : ""}
      aria-selected={value === item.value} aria-controls={item.panelId} tabIndex={item.value === focusValue ? 0 : -1}
      disabled={item.disabled} onKeyDown={(event) => navigate(event, item.value)} onClick={() => onChange(item.value)}>
      {item.label}
    </Button>)}
  </div>;
}
