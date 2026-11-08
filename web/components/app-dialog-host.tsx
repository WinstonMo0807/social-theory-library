"use client";

import { useEffect, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { ConfirmDialog } from "./confirm-dialog";
import { getDialogRequest, getServerDialogRequest, settleDialog, subscribeDialog } from "@/lib/ui-dialog";

export function AppDialogHost() {
  const request = useSyncExternalStore(subscribeDialog, getDialogRequest, getServerDialogRequest);
  const pathname = usePathname();
  useEffect(() => () => settleDialog(), [pathname]);
  if (!request) return null;
  const notice = request.kind === "notice", reason = request.kind === "reason";
  return <ConfirmDialog open title={request.title || (notice ? "请先完成当前操作" : reason ? "恢复公开版本" : "确认操作")}
    description={request.description} confirmLabel={request.confirmLabel || (notice ? "知道了" : reason ? "确认恢复" : "确认并继续")}
    cancelLabel={request.cancelLabel} tone={request.tone} notice={notice}
    reasonLabel={reason ? "恢复原因" : undefined} reasonDefault={request.defaultValue} reasonRequired={reason}
    onCancel={() => settleDialog()} onConfirm={value => settleDialog(reason ? value : true)} />;
}
