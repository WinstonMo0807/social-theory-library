"use client";

type DialogOptions = { title?: string; confirmLabel?: string; cancelLabel?: string; tone?: "default" | "danger" };
export type DialogRequest = DialogOptions & { kind: "confirm" | "notice" | "reason"; description: string; defaultValue?: string };
type Result = boolean | string | null;
let current: DialogRequest | null = null;
let finish: ((value: Result) => void) | null = null;
const listeners = new Set<() => void>();

export const getDialogRequest = () => current;
export const getServerDialogRequest = () => null;
export function subscribeDialog(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function settleDialog(value: Result = false) {
  const resolve = finish;
  finish = null;
  current = null;
  listeners.forEach(listener => listener());
  resolve?.(value);
}

function requestDialog(request: DialogRequest): Promise<Result> {
  // One protected decision at a time. A second click must not queue another write.
  if (current || !listeners.size || typeof document === "undefined") return Promise.resolve(false);
  const opener = document.activeElement;
  const location = window.location.href;
  return new Promise(resolve => {
    current = request;
    finish = value => resolve(window.location.href === location && (!opener || opener.isConnected) ? value : false);
    listeners.forEach(listener => listener());
  });
}

export async function confirmAction(description: string, options: DialogOptions = {}): Promise<boolean> {
  return (await requestDialog({ kind: "confirm", description, ...options })) === true;
}
export async function showNotice(description: string, options: DialogOptions = {}): Promise<void> {
  await requestDialog({ kind: "notice", description, ...options });
}
export async function requestReason(description: string, defaultValue = ""): Promise<string | null> {
  const result = await requestDialog({ kind: "reason", description, defaultValue });
  return typeof result === "string" ? result : null;
}

/** Cancel the link synchronously; an asynchronous decision cannot cancel its old click. */
export async function confirmLinkNavigation(
  event: { preventDefault(): void; stopPropagation(): void; stopImmediatePropagation?: () => void },
  link: HTMLAnchorElement, mayLeave: () => boolean | Promise<boolean>, navigate: (href: string) => void,
) {
  const href = link.href;
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation?.();
  if (await mayLeave()) navigate(href);
}
