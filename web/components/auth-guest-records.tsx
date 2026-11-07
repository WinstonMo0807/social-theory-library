"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { FolderInput } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { GUEST_RECORDS_CHANGED, readGuestRecords, type GuestRecords } from "@/lib/guest-records";

type Transfer = { locked: boolean; setLocked: (value: boolean) => void; selected: boolean; setSelected: (value: boolean) => void; snapshot: GuestRecords; importForOwner: (owner: string, signal: AbortSignal) => Promise<string> };
const GuestTransferContext = createContext<Transfer | null>(null);
export const useGuestTransfer = () => useContext(GuestTransferContext);

export function GuestTransferProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<GuestRecords>({ records: [], available: true });
  const [selected, setSelected] = useState(false);
  const [locked, setLocked] = useState(false);
  useEffect(() => {
    const refresh = () => setSnapshot(readGuestRecords());
    refresh();
    window.addEventListener(GUEST_RECORDS_CHANGED, refresh);
    window.addEventListener("storage", refresh);
    return () => { window.removeEventListener(GUEST_RECORDS_CHANGED, refresh); window.removeEventListener("storage", refresh); };
  }, []);
  async function importForOwner(owner: string, signal: AbortSignal) {
    if (!selected || !snapshot.records.length) return "";
    const response = await apiRequest<components["schemas"]["GuestImportOutput"]>("/reading/guest-records/import/", {
      method: "POST", signal, headers: { "X-Reader-Owner": owner },
      body: JSON.stringify({ owner_id: owner, records: snapshot.records }),
    });
    if (response.owner_id !== owner) throw new Error("转存账户未能核对，本机原记录保留。");
    const remaining = response.results.filter(row => !["imported", "already_imported"].includes(row.state));
    return remaining.length ? `${remaining.length} 条记录未转存。${remaining[0].message}` : "";
  }
  return <GuestTransferContext.Provider value={{ locked, setLocked, selected, setSelected, snapshot, importForOwner }}>{children}</GuestTransferContext.Provider>;
}

export function GuestTransferChoice({ recovery = false, compact = false }: { recovery?: boolean; compact?: boolean }) {
  const transfer = useGuestTransfer();
  const count = transfer?.snapshot.records.length || 0;
  if (compact) return count ? <label className="auth-local-choice"><input type="checkbox" checked={transfer?.selected || false} disabled={transfer?.locked} onChange={event => transfer?.setSelected(event.target.checked)} /><span>将本机 {count} 条浏览记录存入我的账户<small>仅转存公开阅读与检索记录，原记录保留。</small></span></label> : null;
  return <section className="auth-local-records"><h3><FolderInput size={20} />本地访客记录</h3>
    <p>{transfer?.snapshot.available === false ? "暂时无法读取本机访客记录，已有内容未更改。" : count ? `我们检测到您在本设备上有 ${count} 条未保存的浏览记录。` : "本机没有待保存的浏览记录。"}</p>
    {!recovery ? <label className="auth-local-choice"><input type="checkbox" checked={transfer?.selected || false} disabled={!count || transfer?.locked} onChange={event => transfer?.setSelected(event.target.checked)} /><span>登录后将本地访客记录保存到我的账户<small>仅转存本设备的公开阅读与检索记录。原记录保留。</small></span></label> : <small>返回登录页后，可自行选择是否转存。</small>}
  </section>;
}
