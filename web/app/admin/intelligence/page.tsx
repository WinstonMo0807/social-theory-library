"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LoadingState } from "@/components/ui/loading-state";

export default function RetiredIntelligencePage() {
  const query = useSearchParams(), router = useRouter();
  const changeset = query.get("changeset"), work = query.get("work_id"), revision = query.get("revision");
  useEffect(() => {
    const context = new URLSearchParams();
    if (changeset) context.set("changeset", changeset);
    if (work) context.set("work_id", work);
    if (revision) context.set("revision", revision);
    const target = changeset ? "/admin/knowledge/review" : work || revision ? "/admin/sources" : "/admin/knowledge";
    router.replace(`${target}${context.size ? `?${context}` : ""}`);
  }, [changeset, work, revision, router]);
  return <LoadingState>正在打开知识工作区…</LoadingState>;
}
