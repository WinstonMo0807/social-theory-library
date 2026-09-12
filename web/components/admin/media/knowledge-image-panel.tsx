"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ActionButton } from "@/components/action-feedback";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { knowledgeImageEndpoint, selectKnowledgeImage, type KnowledgeImageState, type KnowledgeImageType } from "@/lib/api/knowledge-media";
import styles from "./media-library.module.css";

type Props = { objectType: KnowledgeImageType; objectId: string; refreshKey?: string; onChanged: () => void };

export function KnowledgeImagePanel(props: Props) {
  const user = useAdminSession();
  return <ImageControls key={`${user?.id}:${props.objectType}:${props.objectId}`} {...props} />;
}

function ImageControls({ objectType, objectId, refreshKey = "", onChanged }: Props) {
  const user = useAdminSession();
  const resource = useApiResource<KnowledgeImageState>(knowledgeImageEndpoint(objectType, objectId), user ? getServerSessionCredential() : null, refreshKey);
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false), active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const canEdit = hasAdminCapability(user, "can_edit_draft_authority");
  async function clear() {
    if (!canEdit || !resource.data || sending.current || confirmation !== resource.data.fingerprint) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      await selectKnowledgeImage(objectType, objectId, null, resource.data.fingerprint);
      if (!active.current) return;
      setMessage("已保存清除图片的草稿。确认发布后才更新公开页面，原图保留。");
      resource.retry(); onChanged();
    } catch (error) { if (active.current) setMessage(error instanceof Error ? error.message : "未收到保存结果，请重新读取核对。"); }
    finally { sending.current = false; if (active.current) { setBusy(false); setConfirmation(""); } }
  }
  return <section className={`admin-panel ${styles.portraitPanel}`} aria-label="页面图片"><h3>页面图片</h3>
    {resource.error ? <p role="alert">{resource.error}</p> : resource.loading ? <p role="status">正在读取图片…</p> : resource.data ? <>
      {resource.data.preview_url ? <picture><img className={styles.preview} src={normalizePublicResourceUrl(resource.data.preview_url)} alt={resource.data.media?.alt_text || `${resource.data.name}图片预览`} /></picture> : <p>当前没有选择图片。</p>}
      <p>{resource.data.canonical_write_deferred ? "当前显示图片草稿，公开页面尚未改变。" : "当前显示已保存图片。"}</p>
      {canEdit ? <><Link className="button secondary" prefetch={false} href={`/admin/media?object_type=${objectType}&object_id=${encodeURIComponent(objectId)}`}>从媒体库选择页面图片</Link><ActionButton className="button secondary" disabled={busy || !resource.data.preview_url} onClick={() => setConfirmation(resource.data!.fingerprint)}>清除页面图片</ActionButton><p>进入媒体库前请保存其他未保存的内容。</p></> : null}
    </> : null}
    <ActionButton className="button secondary" disabled={busy} onClick={resource.retry}>重新读取页面图片</ActionButton>
    {message ? <p role="status">{message}</p> : null}
    <ConfirmDialog open={Boolean(resource.data) && confirmation === resource.data?.fingerprint && canEdit} title="清除页面图片" description="仅保存清除图片的草稿，不删除原图，确认发布后才生效。" confirmLabel="保存清除图片草稿" pending={busy} onCancel={() => setConfirmation("")} onConfirm={clear} />
  </section>;
}
