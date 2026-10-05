"use client";

import { BookOpen, Check, Database, FileText, HardDrive, Info, RefreshCw, Save } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";

type Page<T> = { count: number; results: T[] };
type StorageSnapshot = {
  generated_at: string;
  storage: {
    nas: { status: string; configured: boolean; path?: string };
    r2_upload_staging: { enabled: boolean; configured: boolean; endpoint_configured: boolean; credential_configured: boolean };
  };
};
type StoredFile = { id: string; title?: string; source_filename: string; byte_size: number; status: string; asset: string | null; created_at: string };
type StorageCheck = { checked_at: string; components: { storage: { available: boolean | null; last_error: string; detail: string } } };
type Backup = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  include_originals: boolean;
  checksum: string;
  error_message: string;
  created_at: string;
  completed_at: string | null;
};

function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong", hour12: false }) : "—";
}

function fileSize(value: number) {
  if (!value) return "—";
  return value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function backupLabel(row: Backup) {
  return `${new Date(row.created_at).toLocaleDateString("zh-CN", { timeZone: "Asia/Hong_Kong" })} ${row.include_originals ? "含原件备份" : "数据库备份"}`;
}

const backupStates = { queued: "排队中", running: "备份中", completed: "已完成", failed: "失败" };

export function FileStorageAdmin() {
  const user = useAdminSession();
  const credential = getServerSessionCredential();
  const canInspect = hasAdminCapability(user, "can_view_system_status");
  const status = useApiResource<StorageSnapshot>(canInspect ? "/catalog/admin/system-status/" : "", credential);
  const files = useApiResource<Page<StoredFile>>(user ? "/ingestion/items/?page_size=5&ordering=-created_at" : "", credential);
  const [check, setCheck] = useState<StorageCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const nas = status.data?.storage.nas;
  const staging = status.data?.storage.r2_upload_staging;
  const nasAvailable = check?.components.storage.available;

  async function checkStorage() {
    if (!credential || !canInspect || checking) return;
    setChecking(true);
    setCheckError("");
    try {
      setCheck(await apiRequest<StorageCheck>("/ingestion/system-health/", {}, credential));
      status.retry();
    } catch (error) {
      setCheckError(error instanceof Error ? error.message : "存储检查失败，请重试。");
    } finally {
      setChecking(false);
    }
  }

  return <div className="admin-page storage-design-page">
    <header className="admin-page-title"><div><h1>文件存储</h1><span>查看文件保存情况，检查连接与存储状态</span></div><div className="admin-title-actions"><small>最后更新：{dateTime(status.data?.generated_at)}</small><button className="button secondary" type="button" onClick={() => { status.retry(); files.retry(); }} disabled={status.loading && files.loading}><RefreshCw size={16} />刷新</button></div></header>
    {status.error || checkError ? <p className="form-message" role="alert">{status.error || checkError}</p> : null}
    <div className="storage-zone-grid">
      <section className="admin-panel storage-zone">
        <header><span className="storage-zone-icon"><HardDrive size={25} /></span><div><h2>NAS 正式保存区</h2><span className="storage-state"><i className={nasAvailable === true ? "ok" : ""} />{nasAvailable === true ? "文件读取正常" : nasAvailable === false ? "文件读取失败" : nas?.status === "healthy" ? "保存目录可用" : nas?.status === "missing" ? "保存目录缺失" : "—"}</span></div><div className="storage-check"><small>上次检查</small><time>{dateTime(check?.checked_at)}</time><button className="button" type="button" onClick={() => void checkStorage()} disabled={checking || !canInspect}>{checking ? "检查中…" : "检查连接"}</button></div></header>
        <p>书籍文件、封面图片等正式内容保存到 NAS，供网站长期使用。</p>
        <div className="storage-usage"><strong>存储使用情况</strong><span>— / —</span><div className="storage-usage-track" aria-label="尚无容量数据" /></div>
        <dl className="storage-facts"><div><dt>保存位置</dt><dd>{nas?.path ? "部署配置的正式存储区" : "—"}</dd></div><div><dt>服务器地址</dt><dd>—</dd></div><div><dt>连接账号</dt><dd>—</dd></div></dl>
        {check?.components.storage.last_error ? <p role="alert" className="attempt-error">{check.components.storage.last_error}</p> : null}
        <footer><button type="button" className="button secondary" disabled title="尚未提供 NAS 配置保存接口">保存配置</button></footer>
      </section>
      <section className="admin-panel storage-zone">
        <header><span className="storage-zone-icon"><FileText size={25} /></span><div><h2>上传临时中转区</h2><span className="storage-state"><i />{staging ? staging.configured ? "已配置，连接待核实" : staging.enabled ? "配置未完成" : "未启用" : "—"}</span></div><div className="storage-check"><small>上次检查</small><time>—</time><button className="button" type="button" disabled title="尚未提供中转区连接检查接口">检查连接</button></div></header>
        <p>用户上传的文件先保存到临时区，完成处理后转存到 NAS。</p>
        <div className="storage-usage"><strong>存储使用情况</strong><span>— / —</span><div className="storage-usage-track" aria-label="尚无容量数据" /></div>
        <dl className="storage-facts"><div><dt>保存位置</dt><dd>{staging?.configured ? "R2 上传中转区" : "—"}</dd></div><div><dt>服务器地址</dt><dd>{staging ? staging.endpoint_configured ? "已配置" : "—" : "—"}</dd></div><div><dt>文件保留时间</dt><dd>按已配置的中转策略处理</dd></div></dl>
        <footer><button type="button" className="button secondary" disabled title="中转区由部署配置管理，尚未提供保存接口">保存配置</button></footer>
      </section>
    </div>
    <div className="storage-bottom-grid">
      <section className="admin-panel storage-files"><header><div><h2>近期书目文件保存记录</h2><p>最近上传的文件及其保存状态，可点击查看详情。</p></div><Link href="/admin/uploads">查看全部记录 →</Link></header><div className="storage-table-wrap"><table><thead><tr><th>书名</th><th>文件类型</th><th>大小</th><th>保存位置</th><th>状态</th><th>上传时间</th><th>操作</th></tr></thead><tbody>{files.data?.results.map((row) => <tr key={row.id}><td><strong>{row.title || row.source_filename}</strong><small>{row.title ? row.source_filename : ""}</small></td><td>{row.source_filename.split(".").at(-1)?.toUpperCase() || "—"}</td><td>{fileSize(row.byte_size)}</td><td>{row.asset ? "NAS" : "—"}</td><td><span className="storage-state"><i className={row.status === "failed" ? "failed" : row.asset ? "ok" : ""} />{row.status === "failed" ? "处理失败" : row.asset ? "已归档" : "处理中"}</span></td><td>{dateTime(row.created_at)}</td><td><Link href={`/admin/uploads?item=${encodeURIComponent(row.id)}`}>查看</Link></td></tr>)}</tbody></table></div>{files.error ? <p className="attempt-error" role="alert">{files.error}</p> : files.loading ? <p className="empty-state">正在读取文件记录…</p> : !files.data?.results.length ? <p className="empty-state">尚无文件保存记录。</p> : null}</section>
      <aside className="admin-panel storage-impact"><h2>上传后的影响 <Info size={15} /></h2><div className="storage-impact-copy"><BookOpen size={30} /><p>文件上传并处理完成后，会保存到 NAS 正式存储区，原件历史将被保留。网站前台可继续提供已发布 PDF 的阅读。</p></div><h3>常见操作</h3><div className="storage-operation"><RefreshCw size={18} /><span>检查连接<small>只读抽查 NAS 中最近的原始 PDF</small></span><button type="button" className="button secondary" disabled={checking || !canInspect} onClick={() => void checkStorage()}>立即检查</button></div><div className="storage-operation"><RefreshCw size={18} /><span>重试失败文件<small>查看失败原因后重试</small></span><Link className="button secondary" href="/admin/processing?status=failed">查看</Link></div><div className="storage-operation"><Save size={18} /><span>保存配置<small>存储位置、账号等设置</small></span><button type="button" className="button secondary" disabled>保存设置</button></div><details className="storage-technical"><summary><Info size={14} />技术详细信息</summary><p>NAS 检查只读取最近的原始 PDF。中转区当前仅能读取配置状态，容量统计、连接检查与配置保存暂缺。</p><p>凭据{staging?.credential_configured ? "已配置，不显示内容" : "状态待核实"}。</p></details></aside>
    </div>
  </div>;
}

export function BackupRestoreAdmin() {
  const user = useAdminSession();
  const credential = getServerSessionCredential();
  const canRunBackup = hasAdminCapability(user, "can_run_backup");
  const backups = useApiResource<Page<Backup>>(canRunBackup ? "/distribution/backups/" : "", credential);
  const [selectedId, setSelectedId] = useState("");
  const selected = backups.data?.results.find((row) => row.id === selectedId) ?? backups.data?.results.find((row) => row.status === "completed");
  const [target, setTarget] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [backupPath, setBackupPath] = useState("/data/backups");
  const [includeOriginals, setIncludeOriginals] = useState(true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");

  async function createBackup(event: FormEvent) {
    event.preventDefault();
    if (!credential || !canRunBackup || pending) return;
    setPending(true);
    setMessage("");
    try {
      await apiRequest("/distribution/backups/", { method: "POST", body: JSON.stringify({ destination_path: backupPath, include_originals: includeOriginals }) }, credential);
      setMessage("备份已进入任务队列。刷新记录可查看实际处理结果。");
      backups.retry();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "备份创建失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  return <div className="admin-page backup-design-page">
    <header className="admin-page-title"><div><h1>备份与恢复</h1><span>管理网站数据备份，并在需要时恢复到指定环境。仅系统所有者可执行恢复操作。</span></div><span>当前：第 {selected ? "2" : "1"} / 3 步</span></header>
    <ol className="backup-steps"><li className={selected ? "complete" : "current"}><b>{selected ? <Check size={18} /> : "1"}</b><span>1. 选择备份<small>从已有备份中选择</small></span></li><li className={selected ? "current" : ""}><b>2</b><span>2. 核对恢复目标<small>选择目标环境并确认影响</small></span></li><li><b>3</b><span>3. 确认恢复<small>最终确认并开始恢复</small></span></li></ol>
    {!canRunBackup ? <p className="form-message">仅系统所有者可以读取备份记录或创建备份。</p> : null}
    {backups.error ? <p className="form-message" role="alert">{backups.error}<button type="button" onClick={backups.retry}>重新读取</button></p> : null}
    <div className="backup-restore-grid">
      <section className="admin-panel backup-selection"><header><h2>已选择的备份</h2><button type="button" className="text-button" onClick={backups.retry} disabled={!canRunBackup}>刷新备份</button></header>
        <article className="backup-selected"><header><Database size={31} /><div><h3>{selected ? backupLabel(selected) : "尚未选择备份"}</h3><p>{selected ? selected.include_originals ? "包含数据库与原始文件" : "包含数据库" : "从下方已有备份中选择"}</p></div></header><dl><div><dt>备份范围</dt><dd>{selected ? selected.include_originals ? "数据库与原始文件" : "数据库" : "—"}</dd></div><div><dt>完成时间</dt><dd>{dateTime(selected?.completed_at)}</dd></div><div><dt>校验时间</dt><dd>—</dd></div><div><dt>校验结果</dt><dd>{selected?.checksum ? "已生成校验值，恢复待验证" : "—"}</dd></div><div><dt>状态</dt><dd>{selected ? backupStates[selected.status] : "—"}</dd></div></dl>{selected?.error_message ? <p className="attempt-error">{selected.error_message}</p> : null}</article>
        <h3>其他可用备份（共 {backups.data?.count ?? 0} 条）</h3><div className="backup-list">{backups.data?.results.map((row) => <button type="button" key={row.id} className={selected?.id === row.id ? "selected" : ""} disabled={row.status !== "completed"} onClick={() => { setSelectedId(row.id); setAcknowledged(false); }}><Database size={28} /><span><strong>{backupLabel(row)}</strong><small>完成 {dateTime(row.completed_at)}</small></span><span className="storage-state"><i className={row.status === "completed" ? "ok" : row.status === "failed" ? "failed" : ""} />{backupStates[row.status]}</span></button>)}</div>{canRunBackup && !backups.loading && !backups.data?.results.length ? <p className="empty-state">尚无备份记录。</p> : null}
        {canRunBackup ? <details className="backup-create"><summary>创建手动备份</summary><form onSubmit={(event) => void createBackup(event)}><label><span>容器内备份目录</span><input value={backupPath} onChange={(event) => setBackupPath(event.target.value)} required /></label><label className="backup-checkbox"><input type="checkbox" checked={includeOriginals} onChange={(event) => setIncludeOriginals(event.target.checked)} />同时备份原始文件</label><button type="submit" className="button secondary" disabled={pending}>{pending ? "正在提交备份…" : "立即创建备份"}</button></form></details> : null}
        {message ? <p className="form-message" role="status">{message}</p> : null}
      </section>
      <section className="admin-panel backup-target"><header><h2>核对恢复目标</h2><small>仅系统所有者可执行</small><span className="backup-notice"><Info size={14} />恢复执行暂未接入。</span></header><fieldset disabled={!selected || !canRunBackup}><legend>选择恢复目标</legend><label><input type="radio" name="restore-target" value="production" checked={target === "production"} onChange={(event) => { setTarget(event.target.value); setAcknowledged(false); }} /><span><strong>生产环境（当前线上网站）</strong><small>将所选备份恢复到线上网站，覆盖现有数据。</small></span></label><label><input type="radio" name="restore-target" value="test" checked={target === "test"} onChange={(event) => { setTarget(event.target.value); setAcknowledged(false); }} /><span><strong>测试环境</strong><small>将所选备份恢复到测试环境，用于验证数据。</small></span></label></fieldset>
        <h3>恢复后内容影响</h3><div className="backup-impact"><div><p><Database size={18} />如果执行恢复，以下内容将被替换为所选备份的状态：</p><ul><li>数据库中的网站内容与馆藏数据</li><li>用户账号与权限设置</li><li>网站系统配置</li><li>{selected?.include_originals ? "归档中包含的原始文件" : "本备份不包含原始文件"}</li></ul><small>实际恢复范围必须以备份清单核对。</small></div><aside><strong>请谨慎操作</strong><p>恢复操作将覆盖目标环境中的现有数据。应先在测试环境中完成恢复演练。</p></aside></div>
        <section className="backup-rehearsal"><header><h3>恢复演练记录（在测试环境中）</h3></header><p className="empty-state">—</p></section><footer><label className="backup-checkbox"><input type="checkbox" checked={acknowledged} disabled={!selected || !target} onChange={(event) => setAcknowledged(event.target.checked)} /><span>我已了解以上影响，确认要将所选备份恢复到目标环境。<small>尚无恢复执行接口，当前不会更改任何环境。</small></span></label><button className="button" type="button" disabled title="恢复执行及演练记录接口暂缺">下一步：确认恢复</button></footer>
      </section>
    </div>
  </div>;
}
