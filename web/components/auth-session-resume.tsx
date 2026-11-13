"use client";

import { useEffect, useState, type ReactNode } from "react";
import { bootstrapSession } from "@/lib/session";
import { safeAuthDestination } from "@/lib/auth-navigation";
import { LoadingState } from "@/components/ui/loading-state";

/** Recover only through the existing authenticated refresh flow. */
export function AuthSessionResume({ next, children }: { next?: string; children: ReactNode }) {
  const [pending, setPending] = useState(true);
  useEffect(() => {
    let active = true;
    bootstrapSession().then(session => {
      if (!active) return;
      if (session.status === "authenticated") window.location.replace(safeAuthDestination(next));
      else setPending(false);
    }).catch(() => { if (active) setPending(false); });
    return () => { active = false; };
  }, [next]);
  return pending ? <><LoadingState variant="page">正在恢复阅读会话…</LoadingState><noscript>{children}</noscript></> : children;
}
