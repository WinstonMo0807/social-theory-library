"use client";

import { confirmAction, confirmLinkNavigation } from "@/lib/ui-dialog";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export async function confirmUnsavedBeforeAccountChange() {
  const event = new CustomEvent<{ handled: boolean; confirmation?: Promise<boolean> }>("stl:before-account-change", { cancelable: true, detail: { handled: false } });
  if (!window.dispatchEvent(event)) return false;
  return await event.detail.confirmation ?? true;
}

/** Explicit-save forms must keep input on cancellation, including SPA links. */
export function useUnsavedForm(draft: unknown, saved: unknown) {
  const router = useRouter();
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useEffect(() => {
    if (!dirty) return;
    const accountChange = (raw: Event) => {
      if (!(raw instanceof CustomEvent) || !raw.detail || typeof raw.detail.handled !== "boolean") return;
      const event = raw as CustomEvent<{ handled: boolean; confirmation?: Promise<boolean> }>;
      if (event.detail.handled) return;
      event.detail.handled = true;
      event.detail.confirmation = confirmAction("当前有未保存输入或待核对请求。退出账户会收起私人页面，未保存输入可能丢失，已提交任务可能仍在继续。确定继续吗？", { title: "退出账户前确认", confirmLabel: "继续退出" });
    };
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!link || link.target === "_blank" || link.hasAttribute("download") || link.href === window.location.href || link.getAttribute("href")?.startsWith("#")) return;
      void confirmLinkNavigation(event, link, () => confirmAction("当前输入尚未保存，确定离开并放弃这些输入吗？", { title: "放弃未保存的输入", confirmLabel: "放弃并离开", cancelLabel: "继续编辑" }), href => router.push(href));
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    window.addEventListener("stl:before-account-change", accountChange);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); window.removeEventListener("stl:before-account-change", accountChange); };
  }, [dirty, router]);
  return dirty;
}
