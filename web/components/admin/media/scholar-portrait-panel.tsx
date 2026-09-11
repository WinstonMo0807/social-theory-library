"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ActionButton } from "@/components/action-feedback";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { scholarPortraitEndpoint, selectScholarPortrait, type ScholarPortraitState } from "@/lib/api/scholar-media";
import styles from "./media-library.module.css";

type PortraitPanelProps = { scholarId: string; refreshKey: string; onChanged: () => void };

export function ScholarPortraitPanel(props: PortraitPanelProps) {
  const user = useAdminSession();
  return <PortraitPanel key={`${user?.id}:${props.scholarId}`} {...props} />;
}

function PortraitPanel({ scholarId, refreshKey, onChanged }: PortraitPanelProps) {
  const user = useAdminSession();
  const resource = useApiResource<ScholarPortraitState>(scholarPortraitEndpoint(scholarId), user ? getServerSessionCredential() : null, `${user?.id}:${refreshKey}`);
  const [confirmed, setConfirmed] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const canEdit = hasAdminCapability(user, "can_edit_metadata");
  const confirmationKey = JSON.stringify([resource.data?.person_id, resource.data?.editorial_revision_id, resource.data?.preview_url]);
  const sending = useRef(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function clear() {
    if (!resource.data || sending.current || confirmed !== confirmationKey || !canEdit) return;
    sending.current = true;
    setBusy(true); setMessage("");
    try {
      await selectScholarPortrait(scholarId, { media_id: null, expected_person_id: resource.data.person_id, fingerprint: resource.data.fingerprint });
      if (!active.current) return;
      setMessage("已保存清除肖像的草稿，原图片保留。请在编辑版本中确认发布。");
      resource.retry();
      onChanged();
    } catch (reason) { if (active.current) setMessage(reason instanceof Error ? reason.message : "未收到保存结果，请重新读取肖像核对。"); }
    finally { sending.current = false; if (active.current) { setBusy(false); setConfirmed(""); } }
  }
  return <section className={`admin-panel ${styles.portraitPanel}`} aria-label="学者肖像"><h3>学者肖像</h3>
    {resource.error ? <p role="alert">{resource.error}</p> : resource.loading ? <p role="status">正在读取肖像…</p> : resource.data ? <>
      {resource.data.preview_url ? <picture><img className={styles.preview} src={normalizePublicResourceUrl(resource.data.preview_url)} alt={resource.data.media?.alt_text || `${resource.data.name}肖像预览`} /></picture> : <p>当前没有选择肖像。</p>}
      <p>{resource.data.canonical_write_deferred ? "当前显示已保存的肖像草稿，公开图片尚未更改。" : "当前显示已保存的肖像。"}</p>
      {resource.data.media ? <p>{[resource.data.media.source_label, resource.data.media.license, resource.data.media.credit].filter(Boolean).join(" · ") || "来源与使用说明可在媒体库中填写。"}</p> : null}
      {canEdit ? <><Link className="button secondary" prefetch={false} href={`/admin/media?scholar=${encodeURIComponent(scholarId)}`}>从媒体库选择肖像</Link><ActionButton className="button secondary" disabled={busy || !resource.data.preview_url} onClick={() => setConfirmed(confirmationKey)}>清除肖像选择</ActionButton><p>进入媒体库前请先保存正在编辑的其他资料。</p></> : null}
    </> : null}
    <ActionButton className="button secondary" disabled={busy} onClick={resource.retry}>重新读取肖像</ActionButton>
    {message ? <p role="status">{message}</p> : null}
    <ConfirmDialog key={confirmationKey} open={confirmed === confirmationKey && Boolean(resource.data) && canEdit} title="清除肖像选择" description="只保存清除图片的草稿，不删除原图。确认发布后公开页面才会改变。" confirmLabel="保存清除草稿" pending={busy} onCancel={() => setConfirmed("")} onConfirm={clear} />
  </section>;
}
