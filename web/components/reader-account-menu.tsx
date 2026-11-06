"use client";

import Link from "next/link";
import { ArrowRightLeft, ChevronDown, LogOut, Settings, ShieldCheck, UserRound, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { SessionUser } from "@/lib/session";
import { subscribeToSessionChanges } from "@/lib/api";
import { SelfAccountAvatar } from "./account-avatar";
import { Dialog } from "./ui/dialog";
import styles from "./reader-account-menu.module.css";

export function ReaderAccountMenu({ user, onLogout, onPreferences, pending, error }: { user: SessionUser; onPreferences: () => void; onLogout: () => Promise<void>; pending: boolean; error: string }) {
  const [open, setOpen] = useState(false), [switching, setSwitching] = useState(false);
  const titleId = useId(), closeButton = useRef<HTMLButtonElement>(null);
  const owner = String(user.id);
  useEffect(() => subscribeToSessionChanges(() => { setOpen(false); }), [owner]);
  const portrait = <SelfAccountAvatar owner={owner} name={user.display_name} />;
  const close = () => { if (!pending) { setOpen(false); setSwitching(false); } };
  return <>
    <button className={styles.trigger} type="button" aria-label="打开本人账户菜单" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>{portrait}<ChevronDown size={14} /></button>
    {open ? <Dialog open className={styles.panel} aria-labelledby={titleId} initialFocusRef={closeButton} onRequestClose={close}>
      <header><h2 id={titleId}>{switching ? "切换账户" : "我的账户"}</h2><button ref={closeButton} type="button" aria-label="关闭账户菜单" disabled={pending} onClick={close}><X size={18} /></button></header>
      <div className={styles.identity}>{portrait}<div><strong>{user.display_name || "读者"} <small>当前账户</small></strong><span>{user.email}</span></div></div>
      {switching ? <><p className={styles.note}>请登录另一个账户。已保存资料分别属于各自账户，切换不会合并研究、笔记或历史；本机记录仍由你明确选择是否转存。</p><footer><button type="button" onClick={() => setSwitching(false)}>返回</button><Link data-auth-full-page href="/login?next=%2Faccount" onClick={close}>登录另一账户 <ArrowRightLeft size={15} /></Link></footer></> : <>
        <nav aria-label="本人账户"><Link href="/account" onClick={close}><UserRound size={16} />我的资料</Link><Link href="/account?section=settings" onClick={close}><Settings size={16} />账户设置与头像</Link><Link href="/account/settings/privacy" onClick={close}><ShieldCheck size={16} />隐私与资料</Link>{user.capabilities?.includes("access_back_office") ? <Link href="/admin" onClick={close}><Settings size={16} />管理后台</Link> : null}</nav>
        <div className={styles.actions}><button type="button" disabled={pending} onClick={() => { close(); onPreferences(); }}><Settings size={16} />显示与阅读偏好</button><button type="button" disabled={pending} onClick={() => setSwitching(true)}><ArrowRightLeft size={16} />切换账户</button><button type="button" disabled={pending} onClick={() => void onLogout()}><LogOut size={16} />{pending ? "正在退出…" : "退出登录"}</button></div>
      </>}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </Dialog> : null}
  </>;
}
