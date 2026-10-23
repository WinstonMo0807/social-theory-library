"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { authorityRequest, type AuthorityDetail } from "@/lib/api/person-authority.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { isPersonId, personPage } from "@/lib/api/person-resolution";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useScholarSave } from "./use-scholar-save";
import styles from "./person-authority.module.css";

export function ExistingScholarStart({ owner, personId }: { owner: string; personId: string }) {
  const canCreate = hasAdminCapability(useAdminSession(), "can_create_authority");
  const router = useRouter(), command = useScholarSave(owner), sending = useRef(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDetail>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<AuthorityDetail>(isPersonId(personId) ? `${personId}/workspace/` : "", owner, undefined, load);
  const data = resource.error ? null : resource.data;
  async function create() {
    if (!data || !canCreate || sending.current) return;
    sending.current = true; setBusy(true); setError("");
    try {
      const result = await command.save<{ id: string }>("/catalog/admin/scholars/", JSON.stringify({ existing_person_id: data.id,
        preferred_name: data.values.preferred_name, editorial_status: "draft", short_description: "", curation: {} }), {}, "POST");
      router.replace(`/admin/scholars/${result.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "未收到建立档案的结果，请核对原请求。"); }
    finally { sending.current = false; setBusy(false); }
  }
  return <main className={styles.page}><nav className={styles.crumb}><Link href={personPage(personId)}>人物规范</Link><span>›</span><span>建立学者公开页草稿</span></nav><header className={styles.heading}><div><h1>学者公开页编辑</h1><p>使用已核对的人物身份建立一份公开页草稿。</p></div></header><section className={styles.panel}>
    {!isPersonId(personId) ? <p role="alert">人物编号无效，请从人物规范库重新进入。</p> : resource.error ? <p role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : !data ? <p role="status">正在核对原人物与关联学者档案…</p> : <><h2>{data.values.preferred_name}</h2><p>{data.values.original_name} · {data.values.birth_year ?? "生年未详"}{data.values.death_year !== null ? `—${data.values.death_year}` : ""}</p>{data.scholar_id ? <p>此人物已有学者档案。<Link href={`/admin/scholars/${data.scholar_id}`}>继续编辑原档案 →</Link></p> : data.can_edit && canCreate ? <><p>姓名、异名、生卒年、肖像和原作品贡献继续关联当前人物。此操作保存空的学者页面草稿，接着可以编排导读、代表作品与资料来源。</p><button className={styles.primary} disabled={busy || !command.ready || Boolean(command.recovery && !command.canRetry)} onClick={() => void create()}>{busy ? "正在建立…" : command.canRetry ? "重试同一次建立" : "建立草稿并继续编辑"}</button></> : <p>此人物已退役或当前账户不能编辑，请先核对规范记录。</p>}</>}
    {command.recovery ? <aside className={styles.notice}><p>有一次保存需要核对。读取回执不会再次建档。</p><button disabled={busy} onClick={() => void command.lookup().then(receipt => { if (receipt?.exists) router.replace(`/admin/scholars/${receipt.scholar_id}`); else if (receipt) setError(receipt.state === "cancelled" ? "原建档请求已停止，可以重新核对后建档。" : "原建档已完成，但档案后来已删除。未重复创建。"); })}>读取原请求回执</button><button type="button" disabled={busy} onClick={()=>{if(window.confirm("停止未确认建档？若已完成将返回原档案，尚未执行的请求将被阻止。"))void command.lookup(true).then(receipt=>{if(receipt?.exists)router.replace(`/admin/scholars/${receipt.scholar_id}`);else if(receipt)setError(receipt.state === "cancelled" ? "原请求已停止，尚未建档。" : "原档案后来已删除。");});}}>停止未确认建档</button></aside> : null}{error || command.error ? <p role="alert">{error || command.error}</p> : null}
  </section></main>;
}
