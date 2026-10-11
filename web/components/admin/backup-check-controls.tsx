"use client";

import { useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { createRequestKey } from "@/lib/request-key";

type CheckableBackup = { id: string; checksum: string; status: string; created_at: string; include_originals: boolean };
type Operation = "verify" | "restore_rehearsal";
type CheckRecord = {
  operation: Operation; request_key: string; status: "queued" | "running" | "completed" | "failed";
  requested_at: string; started_at: string | null; checked_at: string | null; archive_checksum: string;
  error_message: string; result: { database_restored?: boolean; isolated_database_removed?: boolean; originals_verified?: number };
};
type CheckState = {
  backup_id: string; verification: CheckRecord | null; rehearsal: CheckRecord | null;
  history: { count: number; page: number; next_page: number | null; previous_page: number | null; results: CheckRecord[] };
};
const labels = { queued: "排队中", running: "检查中", completed: "通过", failed: "失败" };
const time = (value?: string | null) => value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong", hour12: false }) : "—";

export function useBackupCheck(backup: CheckableBackup | undefined | null, allowed: boolean, credential: string | null) {
  const [historyPage, setHistoryPage] = useState({ id: "", page: 1 });
  const page = historyPage.id === backup?.id ? historyPage.page : 1;
  const resource = useApiResource<CheckState>(allowed && backup ? `/distribution/backups/${backup.id}/check/?page=${page}` : "", credential);
  const [submitted, setSubmitted] = useState<CheckState | null>(null);
  const [pending, setPending] = useState<Operation | null>(null), [error, setError] = useState("");
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const data = resource.data?.backup_id === backup?.id ? resource.data : null;
  const latest = (operation: Operation) => {
    const field = operation === "verify" ? "verification" : "rehearsal";
    const current = data?.[field] || null, queued = submitted && submitted.backup_id === backup?.id ? submitted[field] : null;
    return queued && (!current || queued.requested_at > current.requested_at) ? queued : current;
  };
  const verification = latest("verify"), rehearsal = latest("restore_rehearsal");
  const busy = Boolean(pending || [verification, rehearsal].some(item => item && ["queued", "running"].includes(item.status)));

  async function run(operation: Operation) {
    if (!backup || !allowed || !credential || busy) return false;
    const signature = `${backup.id}:${backup.checksum}:${operation}`;
    setPending(operation); setError("");
    try {
      if (retry.current?.signature !== signature) retry.current = { signature, key: createRequestKey() };
      const result = await apiRequest<CheckState>(`/distribution/backups/${backup.id}/check/`, {
        method: "POST", body: JSON.stringify({ operation, expected_checksum: backup.checksum,
          request_key: retry.current.key, confirm_isolated: operation === "restore_rehearsal" }),
      }, credential);
      setSubmitted(result); retry.current = null; resource.retry();
      return true;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "检查提交失败，请重新读取后重试。");
      resource.retry(); return false;
    } finally { setPending(null); }
  }

  return { verification, rehearsal, data, busy, pending, loading: resource.loading, error: error || resource.error,
    run, refresh: resource.retry, changePage: (page: number) => backup && setHistoryPage({ id: backup.id, page }) };
}
type Check = ReturnType<typeof useBackupCheck>;

export function BackupVerificationFields({ check, completed }: { check: Check; completed: boolean }) {
  return <>
    <div><dt>校验时间</dt><dd>{time(check.verification?.checked_at)}</dd></div>
    <div><dt>校验结果</dt><dd className="backup-verification-result"><span className="storage-state"><i className={check.verification?.status === "completed" ? "ok" : check.verification?.status === "failed" ? "failed" : ""} />{check.verification ? labels[check.verification.status] : "尚未校验"}</span><button className="text-button" type="button" disabled={!completed || check.busy || check.loading} onClick={() => void check.run("verify")}>{check.pending === "verify" ? "正在提交…" : "校验备份"}</button></dd></div>
  </>;
}

export function BackupRehearsalHistory({ check }: { check: Check }) {
  const history = check.data?.history;
  return <section className="backup-rehearsal"><header><h3>恢复演练记录（在测试环境中）</h3><button className="text-button" type="button" onClick={check.refresh} disabled={check.loading}>刷新记录</button></header>
    {check.error ? <p className="attempt-error" role="alert">{check.error}</p> : null}
    {check.verification?.status === "failed" ? <p className="attempt-error" role="alert">{check.verification.error_message}</p> : null}
    {check.rehearsal && ["queued", "running"].includes(check.rehearsal.status) ? <p role="status">{check.rehearsal.status === "queued" ? "恢复演练已排队，等待实际结果。" : "正在隔离测试库中恢复并核对。"}</p> : null}
    {history?.results.length ? <ol className="backup-rehearsal-records">{history.results.map(item => <li key={item.request_key} data-rehearsal-id={item.request_key}><span className="storage-state"><i className={item.status === "completed" ? "ok" : item.status === "failed" ? "failed" : ""} /></span><div><p><time>{time(item.checked_at || item.requested_at)}</time><strong>结果：{item.status === "completed" ? "成功" : labels[item.status]}</strong></p><small>{item.status === "completed" ? "数据库恢复与迁移记录核对通过，临时测试库已清理。" : item.error_message || "尚未得到完成结果。"}</small>{item.status === "completed" ? <small>原始文件校验 {item.result.originals_verified ?? 0} 份，未写入现有文件。</small> : null}</div></li>)}</ol> : <p className="empty-state">{check.loading ? "正在读取演练记录…" : "尚无这份备份的恢复演练记录。"}</p>}
    {history && history.count > 10 ? <nav className="backup-pagination" aria-label="恢复演练分页"><button className="button secondary" type="button" disabled={!history.previous_page || check.loading} onClick={() => check.changePage(history.previous_page!)}>上一页</button><span>第 {history.page} 页 · 共 {history.count} 条</span><button className="button secondary" type="button" disabled={!history.next_page || check.loading} onClick={() => check.changePage(history.next_page!)}>下一页</button></nav> : null}
  </section>;
}

export function BackupRestoreAction({ backup, target, acknowledged, allowed, check }: {
  backup?: CheckableBackup | null; target: string; acknowledged: boolean; allowed: boolean; check: Check;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [confirmation, setConfirmation] = useState<{ id: string; checksum: string; target: string } | null>(null);
  const eligible = allowed && backup?.status === "completed" && acknowledged && Boolean(target) && !check.busy && !check.loading;
  async function execute() {
    if (!backup || confirmation?.target !== "test" || confirmation.id !== backup.id || confirmation.checksum !== backup.checksum || !eligible) return;
    if (await check.run("restore_rehearsal")) dialog.current?.close();
  }
  return <>
    <button className="button" type="button" disabled={!eligible} onClick={() => {
      if (backup) { setConfirmation({ id: backup.id, checksum: backup.checksum, target }); dialog.current?.showModal(); }
    }}>下一步：确认恢复</button>
    <dialog ref={dialog} className="backup-confirmation" onClose={() => setConfirmation(null)}>
      <header><span>第 3 / 3 步</span><h2>{confirmation?.target === "test" ? "确认隔离恢复演练" : "核对生产恢复计划"}</h2></header>
      <p>所选备份：{time(backup?.created_at)} · {backup?.include_originals ? "数据库与原始文件" : "数据库"}</p>
      <p>校验时间：{time(check.verification?.checked_at)}</p>
      {confirmation?.target === "test" ? <p>将数据库恢复到新建的空白隔离测试库，核对实际内容和迁移记录后清理测试库。备份中的原始文件会校验，不写入现有馆藏。</p> : <p>生产恢复需通过维护发布流程核对当前备份、回退安排与批准。本页已保留所选备份，当前没有开始生产恢复。</p>}
      {check.error ? <p className="attempt-error" role="alert">{check.error}</p> : null}
      <footer><button className="button secondary" type="button" onClick={() => dialog.current?.close()} disabled={Boolean(check.pending)}>返回核对</button><button className="button" type="button" disabled={confirmation?.target !== "test" || !eligible} onClick={() => void execute()}>{check.pending ? "正在提交…" : confirmation?.target === "test" ? "执行隔离恢复演练" : "生产恢复需维护批准"}</button></footer>
    </dialog>
  </>;
}
