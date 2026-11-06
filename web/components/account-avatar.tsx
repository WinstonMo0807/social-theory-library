"use client";

import { useEffect, useState } from "react";
import { apiStreamRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./account-avatar.module.css";
import { subscribeAvatarUpdates } from "@/lib/avatar-updates";

export async function readAccountAvatar(owner: string, target: string, signal: AbortSignal) {
  return withPrivateOwner(owner, async () => {
    const response = await apiStreamRequest(`/auth/users/${encodeURIComponent(target)}/avatar/`, {
      headers: { "X-Reader-Owner": owner }, cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
    }, getServerSessionCredential(), false);
    if (!response.ok || !response.headers.get("Content-Type")?.startsWith("image/png")) throw Error("头像暂时无法读取，请重新核对账户。");
    const blob = await response.blob();
    if (!blob.size || blob.size > 300 * 1024) throw Error("头像数据不完整，请重新读取。");
    return blob;
  }, signal);
}

export function AccountAvatar({ owner, target, revision, name, className = "" }: {
  owner: string; target: string; revision: number | null; name: string; className?: string;
}) {
  const [image, setImage] = useState<{ key: string; url: string } | null>(null), [failed, setFailed] = useState("");
  const [currentRevision, setCurrentRevision] = useState(revision);
  useEffect(() => { setCurrentRevision(revision); }, [revision, owner, target]);
  useEffect(() => subscribeAvatarUpdates(value => { if (value.owner === target) setCurrentRevision(value.revision); }), [target]);
  const key = `${owner}:${target}:${currentRevision}`;
  useEffect(() => {
    if (currentRevision === null) return;
    const request = new AbortController(); let url = "";
    const off = subscribeToSessionChanges(() => { request.abort(); setImage(null); });
    void readAccountAvatar(owner, target, request.signal).then(blob => {
      if (request.signal.aborted) return;
      url = URL.createObjectURL(blob); setImage({ key, url }); setFailed("");
    }).catch(reason => { if (!request.signal.aborted) setFailed(reason instanceof Error ? reason.message : "头像暂时无法读取。"); });
    return () => { request.abort(); off(); if (url) URL.revokeObjectURL(url); };
  }, [owner, target, currentRevision, key]);
  return <span className={`${styles.avatar} ${className}`} title={failed || undefined}>{image?.key === key && currentRevision !== null ? <img src={image.url} alt={`${name}的头像`} /> : <span aria-hidden>{name.slice(0, 1) || "人"}</span>}</span>;
}
