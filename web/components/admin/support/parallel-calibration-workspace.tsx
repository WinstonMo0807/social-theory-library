"use client";

import Link from "next/link";
import { ArrowUpRight, BookOpen, Check, GitCompareArrows, RefreshCw } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { adminListHref, adminPageNumber } from "@/lib/admin-route-context";
import { calibrationAdminPath, calibrationDate, calibrationReaderPath, calibrationScopes, calibrationStatuses, alignmentStatuses, commandCalibration,
  type AdminCalibration, type AdminCalibrationList, type CalibrationAction, type CalibrationSource } from "@/lib/api/parallel-calibration-admin.client";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import styles from "./feedback.module.css";
import parallel from "./parallel-calibration.module.css";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const actionLabels = { review: "确认审核", publish: "发布公共校准", reject: "退回校准" };

export function ParallelCalibrationWorkspace() {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (!user) return <p role="status">正在核对管理会话…</p>;
  if (!hasAdminCapability(user, "can_review_candidate")) return <p role="alert">当前账户没有公共校准审核权限。</p>;
  return <Workspace key={`${user.id}:${epoch}`} ownerId={String(user.id)} canPublish={hasAdminCapability(user, "can_publish_authority")} />;
}

function Workspace({ ownerId, canPublish }: { ownerId: string; canPublish: boolean }) {
  const search = useSearchParams(), router = useRouter(), pathname = usePathname();
  const page = adminPageNumber(search.get("page")), rawStatus = search.get("status") || "";
  const status = Object.hasOwn(calibrationStatuses, rawStatus) ? rawStatus : "";
  const item = search.get("item") || "", selected = uuid.test(item) ? item : "";
  const resource = usePersistentWorkspace<AdminCalibrationList>(`${calibrationAdminPath()}?${new URLSearchParams({ page: String(page), status })}`, ownerId);
  const dirty = useRef(false), busy = useRef(false), state = resource.data;
  const change = (values: Record<string, string | number | null>) => {
    if (busy.current || dirty.current && !window.confirm("当前处理说明尚未保存，确定放弃这些输入吗？")) return;
    dirty.current = false;
    router.push(adminListHref(pathname, search.toString(), values));
  };
  return <main className={styles.workspace}>
    <header className={styles.heading}><div><p className={styles.eyebrow}>网站内容 / 并读校准</p><h1>公共校准</h1><p>核对不同版本的对应关系，按投稿范围审核与发布。</p></div><button onClick={resource.reload}><RefreshCw size={15} />刷新列表</button></header>
    <div className={styles.notice}><GitCompareArrows size={18} /><p>这里只处理读者明确提交的校准。私人笔记与术语说明不会进入投稿；通过审核后仍需有发布权限的管理员确认公开。</p></div>
    <nav className={styles.tabs} aria-label="校准状态">
      <button aria-current={!status ? "page" : undefined} onClick={() => change({ status: null, page: 1, item: null })}>全部校准</button>
      {Object.entries(calibrationStatuses).map(([key, label]) => <button key={key} aria-current={status === key ? "page" : undefined} onClick={() => change({ status: key, page: 1, item: null })}>{label}</button>)}
    </nav>
    {resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}
    <div className={styles.layout}>
      <section className={styles.list} aria-label="公共校准列表"><header><h2>收到的校准</h2><span>{state ? `${state.count} 项` : "读取中"}</span></header>
        {!state ? <p className={styles.empty} role="status">{resource.loading ? "正在读取校准…" : "校准列表暂不可读取，请重试。"}</p> : <>
          <ol>{state.results.map(row => <li key={row.id}><button className={styles.row} aria-pressed={selected === row.id} onClick={() => change({ item: row.id })}>
            <span className={styles.rowMeta}><strong>{calibrationScopes[row.scope]}</strong><span className={styles.badge}>{calibrationStatuses[row.status]}</span></span>
            <span className={styles.excerpt}>{row.pair_sources ? [row.pair_sources.left, row.pair_sources.right].map(value => [value.title, value.version_label].filter(Boolean).join(" · ")).join(" ↔ ") : "来源当前不可用"}</span>
            <span className={styles.rowFoot}><time dateTime={row.created_at}>{calibrationDate(row.created_at)}</time><span>修订 {row.revision}</span></span>
          </button></li>)}</ol>
          {!state.count ? <div className={styles.empty}><BookOpen size={28} /><h3>{status ? "当前状态下没有校准" : "暂未收到公共校准"}</h3><p>并读中的私人保存不会自动出现在这里。</p></div> : null}
          <nav className={styles.pager} aria-label="公共校准列表分页"><span>共 {state.count} 项 · 第 {page} / {Math.max(1, Math.ceil(state.count / 20))} 页</span><button disabled={!state.previous} onClick={() => change({ page: page - 1, item: null })}>上一页</button><button disabled={!state.next} onClick={() => change({ page: page + 1, item: null })}>下一页</button></nav>
        </>}
      </section>
      <section className={styles.detail} aria-label="公共校准详情">{selected ? <Detail key={selected} id={selected} ownerId={ownerId} canPublish={canPublish} onSaved={resource.reload} onDirty={value => { dirty.current = value; }} onBusy={value => { busy.current = value; }} /> : <div className={styles.placeholder}><GitCompareArrows size={34} /><h2>选择一条校准</h2><p>核对两侧版本、公开范围与投稿依据。</p></div>}</section>
    </div>
  </main>;
}

function Source({ value, side }: { value: CalibrationSource | null | undefined; side: string }) {
  const href = calibrationReaderPath(value?.reader_url);
  return <div className={parallel.source}><h4>{side}</h4><strong>{value?.title || "来源当前不可用"}</strong>{value ? <p>{[value.authors.join(" / "), value.version_label].filter(Boolean).join(" · ") || "版本说明未提供"}</p> : null}{href ? <Link href={href} target="_blank" rel="noopener noreferrer">核对当前原文<ArrowUpRight size={12} /></Link> : null}</div>;
}

function Passage({ value, side, absent }: { value: ResolvedEvidence | null; side: string; absent: string }) {
  const available = value?.source_status === "available";
  const href = available ? calibrationReaderPath(value.reader_url) : "";
  return <div className={parallel.source}><h4>{side}</h4>{!value ? <p>{absent}</p> : !available ? <p role="status">此段原文已变化或不可用，已收起原文内容。</p> : <>
    <strong>{value.title || "当前原文"}</strong><p>{value.pdf_page ? `PDF 第 ${value.pdf_page} 页` : "页码待核对"}{value.printed_label ? ` · 书内页码 ${value.printed_label}` : ""}</p>
    <blockquote>{value.quote || value.text || "此定位没有可显示的原文。"}</blockquote>
    {href ? <Link href={href} target="_blank" rel="noopener noreferrer">查看原文位置<ArrowUpRight size={12} /></Link> : null}
  </>}</div>;
}

function Detail({ id, ownerId, canPublish, onSaved, onDirty, onBusy }: { id: string; ownerId: string; canPublish: boolean; onSaved: () => void; onDirty: (value: boolean) => void; onBusy: (value: boolean) => void }) {
  const resource = usePersistentWorkspace<AdminCalibration>(calibrationAdminPath(id), ownerId);
  const row = resource.data?.id === id ? resource.data : null;
  return <>
    {resource.error ? <p className={styles.error} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}
    {row ? <Editor row={row} resource={resource} canPublish={canPublish} onSaved={onSaved} onDirty={onDirty} onBusy={onBusy} /> : <p className={styles.empty} role="status">{resource.loading ? "正在读取校准详情…" : "此条校准暂不可读取。"}</p>}
  </>;
}

function Editor({ row, resource, canPublish, onSaved, onDirty, onBusy }: {
  row: AdminCalibration; resource: ReturnType<typeof usePersistentWorkspace<AdminCalibration>>; canPublish: boolean;
  onSaved: () => void; onDirty: (value: boolean) => void; onBusy: (value: boolean) => void;
}) {
  const [base, setBase] = useState(row), [note, setNote] = useState(""), [message, setMessage] = useState("");
  const [unknown, setUnknown] = useState<CalibrationAction | null>(null), [confirm, setConfirm] = useState(false);
  const pending = resource.pending, stale = row.revision !== base.revision;
  const dirty = useUnsavedForm(Boolean(note || unknown), false), alive = useRef(true), cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => { onBusy(pending || Boolean(unknown)); return () => onBusy(false); }, [pending, unknown, onBusy]);
  async function command(action: CalibrationAction) {
    if (pending || unknown && unknown !== action || stale && !unknown) return;
    if (action === "reject" && !note.trim()) { setMessage("请填写退回原因；已公开的校准退回后会停止公开。"); return; }
    setMessage("");
    const input = { expected_revision: base.revision, note: note.trim() };
    try {
      const saved = await resource.mutate(JSON.stringify({ action, ...input }), async (_current, requestId) => {
        const result = await commandCalibration(row.id, action, { ...input, request_id: requestId });
        if (result.id !== row.id || result.request_id !== requestId || !Number.isInteger(result.applied_revision)
          || result.applied_revision <= input.expected_revision || !Number.isInteger(result.revision)
          || result.revision < result.applied_revision) throw new Error("尚未确认处理结果，请保留原请求重试。");
        return result;
      });
      if (saved && alive.current) {
        setBase(saved); setNote(""); setUnknown(null); setConfirm(false);
        setMessage(`${actionLabels[action]}已保存。当前状态：${calibrationStatuses[saved.status]}。`); onSaved();
      }
    } catch (reason) {
      if (alive.current) {
        setConfirm(false);
        setUnknown(reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500 ? null : action);
      }
    }
  }
  const blocked = pending || Boolean(unknown) || stale;
  return <>
    <header className={styles.detailHeading}><div><span className={styles.eyebrow}>{calibrationScopes[row.scope]}</span><h2>核对公共校准</h2><p><time dateTime={row.created_at}>{calibrationDate(row.created_at)}</time> · 修订 {row.revision}</p></div><span className={styles.badge}>{calibrationStatuses[row.status]}</span></header>
    <div className={styles.submission}>
      <div className={parallel.pair}><Source side="左侧版本" value={row.pair_sources?.left} /><Source side="右侧版本" value={row.pair_sources?.right} /></div>
      <h3>投稿依据</h3><p className={styles.body}>{row.data.basis || "未提供说明"}</p>
      <p className={styles.muted}>{row.scope === "bibliography" ? "公开范围仅含两侧书目信息与依据，不含段落原文、私人对齐与术语笔记。" : "公开范围仅含本次明确提交的段落对应与依据，不含私人笔记或其他对齐。"}</p>
      <p className={row.source_available ? styles.muted : styles.warning} role="status">{row.notice || (row.source_available ? "两侧来源当前可用，发布时仍会重新核对。" : "来源已变化或不可用，暂不能审核或发布。")}</p>
      {row.scope === "passages" ? <ol className={parallel.alignments} aria-label="提交的段落对应">{row.data.alignments.map((alignment, index) => <li key={alignment.id}><h4>对应 {index + 1} · {alignmentStatuses[alignment.status]}</h4><div className={parallel.pair}>
        <Passage value={alignment.left} side="左侧段落" absent={alignment.status === "addition" ? "此处为右侧增补内容，左侧没有对应段落。" : "未提供左侧段落。"} />
        <Passage value={alignment.right} side="右侧段落" absent="投稿标记为未找到对应段落，请核对依据。" />
      </div></li>)}</ol> : null}
    </div>
    <section className={styles.handling} aria-label="审核与发布"><header><h3>处理这条校准</h3><span>公开范围由投稿人确定</span></header>
      {row.review_note ? <div><p className={styles.muted}>最近处理说明 · {calibrationDate(row.updated_at)}</p><p className={styles.body}>{row.review_note}</p></div> : null}
      <label>本次处理说明<textarea rows={4} maxLength={2000} value={note} disabled={pending || Boolean(unknown)} onChange={event => setNote(event.target.value)} placeholder="记录核对依据或退回原因，最多 2000 字" /></label>
      <p className={styles.muted}>退回时必须说明原因。已公开内容退回后停止公开；私人并读记录继续保留。</p>
      {stale && !unknown ? <div className={styles.warning}><p>校准已有新修订，你的说明仍保留。请核对上方最新状态和处理说明。</p><button onClick={() => { setBase(row); setMessage(""); }}>已核对，采用最新修订继续</button></div> : null}
      {unknown ? <div className={styles.warning} role="status"><p>尚未确认“{actionLabels[unknown]}”的处理结果。说明和原请求仍保留，请重试查回。</p><button disabled={pending} onClick={() => void command(unknown)}>{pending ? "正在查回…" : "重试原请求"}</button></div> : null}
      {message ? <p role="status" className={styles.success}>{message}</p> : null}
      <div className={parallel.actions}>
        <button disabled={blocked || !row.source_available || !["submitted", "rejected"].includes(row.status)} onClick={() => void command("review")}><Check size={15} />确认审核</button>
        <button className={styles.primary} disabled={blocked || !canPublish || !row.source_available || row.status !== "reviewed"} onClick={() => setConfirm(true)}>发布公共校准</button>
        <button disabled={blocked || row.status === "rejected" || !note.trim()} onClick={() => void command("reject")}>{row.status === "published" ? "撤下并退回" : "退回校准"}</button>
      </div>
      {!canPublish ? <p className={styles.muted}>当前账户可以审核和退回，发布需具有公开发布权限的管理员处理。</p> : null}
      <Dialog open={confirm} aria-labelledby="calibration-publish-title" className={parallel.dialog} initialFocusRef={cancelRef} onRequestClose={() => { if (!pending) setConfirm(false); }}>
        <h2 id="calibration-publish-title">确认公开这条校准</h2><p>将按“{calibrationScopes[row.scope]}”范围公开当前修订的书目、投稿依据{row.scope === "passages" ? "与所选段落对应" : ""}。</p><p>私人笔记与术语说明不会公开。来源或修订发生变化时，发布将被阻止。</p>
        <footer><button ref={cancelRef} disabled={pending} onClick={() => setConfirm(false)}>继续核对</button><button className={styles.primary} disabled={blocked || row.status !== "reviewed" || !row.source_available || !canPublish} onClick={() => void command("publish")}>{pending ? "正在发布…" : "确认发布"}</button></footer>
      </Dialog>
    </section>
  </>;
}
