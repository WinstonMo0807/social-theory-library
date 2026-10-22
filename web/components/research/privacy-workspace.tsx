"use client";

import Link from "next/link";
import { BookOpen, ChevronRight, Clock3, Database, Download, FileText, Globe2, Info, LockKeyhole, RefreshCw, Settings, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { commandPrivacyOperation, downloadPrivacyOperation, operationPath, preparePrivacyOperation, privacyActive, privacyPath, savePrivacyPreferences,
  type EraseCategory, type ExportCategory, type PrivacyItem, type PrivacyItems, type PrivacyOperation, type PrivacyOperations, type PrivacySummary, type RetentionKey } from "@/lib/api/privacy.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import styles from "./privacy.module.css";

const retentionLabels: Record<RetentionKey, string> = { reading_history: "阅读历史", search_history: "搜索记录", personal_notes: "个人笔记", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", saved_knowledge: "知识条目、图谱视图与私人书单" };
const retentionCopy: Record<RetentionKey, string> = { reading_history: "保存以后阅读的位置记录，阅读进度单独保留。", search_history: "仅在开启后保存新的检索词与筛选条件。", personal_notes: "允许新建阅读笔记、个人认识与私人并读对齐（含术语笔记），已有内容仍可编辑。", followed_topics: "允许新增主题收藏，已有收藏不会自动删除；主题档案更新关注单独管理。", source_follows: "允许关注公开来源、学者与主题档案，并保存后续正式更新。关闭后停止记录更新，已有记录仍保留。", saved_knowledge: "允许收藏理论、概念与争论，以及保存私人图谱范围、布局和文章书单。关闭后不新增，已有记录仍可取消或删除。" };
const exportLabels: Record<ExportCategory, string> = { article_comments: "文章评论", research: "研究资料", notes: "笔记内容", plans: "阅读计划与公共跟读", audits: "引文报告", source_follows: "来源、学者与主题关注", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
const exportCopy: Record<ExportCategory, string> = { article_comments: "本人明确提交的评论、公开署名及审核状态，包含已公开与未公开内容", research: "研究问题、选材与轮次（含来源与版本）", notes: "阅读笔记、已保存认识与私人并读对齐及术语笔记", plans: "本人创建或另存的阅读计划、公共路径收藏及跟读进度与笔记", audits: "引文报告与本人来源信息（不含原件）", source_follows: "本人来源、学者与主题关注及站内状态历史（不含原文）", saved_knowledge: "本人收藏的作品、理论与概念入口，以及私人图谱名称、范围和布局，以及私人书单与作品顺序；不含来源正文或候选关系。" };
const eraseLabels: Record<EraseCategory, string> = { article_comments: "文章评论", reading_history: "阅读历史", search_history: "搜索记录", personal_notes: "个人笔记", reading_plans: "阅读计划与公共跟读", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
const leafLabels: Record<string, string> = { saved_items: "作品收藏", article_comments: "文章评论", reading_history: "阅读历史", search_history: "搜索记录", annotations: "阅读笔记", memories: "个人认识", parallel_alignments: "私人并读对齐与术语笔记", plans: "阅读计划与公共跟读", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", research: "研究资料", audits: "引文报告", citation_sources: "本人来源信息", graph_views: "私人图谱视图", reading_lists: "私人书单", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
const statusLabels: Record<PrivacyOperation["status"], string> = { preview: "等待确认影响", queued: "等待处理", running: "处理中", completed: "已完成", partial: "部分完成", failed: "未能完成", canceled: "已取消" };
const failureLabels: Record<string, string> = { revision_changed: "内容已修改，请重新预览", record_unavailable: "资料已删除或不可用", content_limit: "内容超过单次限制", preparation_failed: "处理失败，可重试", queue_unavailable: "任务暂未进入队列，可重试", task_interrupted: "处理已中断，可恢复剩余项目" };
const dateLabel = (value: string) => Number.isNaN(Date.parse(value)) ? "时间未记录" : new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const poll = (data: PrivacySummary) => data.operations.some(row => privacyActive(row.status)) ? 2500 : null;

export function PrivacyWorkspace({ exportOnly = false }: { exportOnly?: boolean }) {
  const { state: session, retry } = useSessionBootstrap();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  useEffect(() => { if (session.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(`/account/settings/privacy${exportOnly ? "/export" : ""}`)}`); }, [session.status, exportOnly]);
  if (session.status !== "authenticated" || !session.user) return <div className={styles.page}><div className={styles.empty} role="status"><h1>隐私与资料</h1><p>{session.message || "正在验证登录状态…"}</p>{["temporary_error", "forbidden"].includes(session.status) ? <button onClick={retry}>重新验证</button> : null}</div></div>;
  return <PrivacyContent key={`${session.user.id}:${epoch}`} ownerId={String(session.user.id)} exportOnly={exportOnly} />;
}

function PrivacyContent({ ownerId, exportOnly }: { ownerId: string; exportOnly: boolean }) {
  const summary = usePersistentWorkspace<PrivacySummary>(privacyPath, ownerId, poll);
  const [category, setCategory] = useState<EraseCategory>("reading_history");
  const [page, setPage] = useState(1);
  const items = usePersistentWorkspace<PrivacyItems>(`${privacyPath}items/?category=${category}&page=${page}`, ownerId);
  const [selected, setSelected] = useState<PrivacyItem[]>([]);
  const [exports, setExports] = useState<ExportCategory[]>(["research", "notes"]);
  const [draft, setDraft] = useState<{ revision: number; retention: Record<RetentionKey, boolean> } | null>(null);
  const [mobileTab, setMobileTab] = useState(exportOnly ? "export" : "settings");
  const [focused, setFocused] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [notice, setNotice] = useState("");
  const [invalid, setInvalid] = useState(false);
  const alive = useRef(true);
  const requestAbort = useRef<AbortController | null>(null);
  useEffect(() => { alive.current = true; requestAbort.current = new AbortController(); return () => { alive.current = false; requestAbort.current?.abort(); }; }, []);
  useUnsavedForm(Boolean(draft), false);
  const data = summary.data;
  const rows = items.data?.results || [];
  const selectedTotal = data ? exports.reduce((sum, key) => sum + data.export_counts[key], 0) : 0;
  function failed(reason: unknown) {
    if (!alive.current) return;
    setNotice(reason instanceof Error ? reason.message : "操作暂未完成，选择仍保留。");
    if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) { setInvalid(true); setSelected([]); setDraft(null); setFocused(null); }
  }
  async function savePreferences() {
    if (!draft) return;
    try {
      const saved = await summary.mutate(JSON.stringify(draft), () => savePrivacyPreferences(ownerId, draft.revision, draft.retention, requestAbort.current?.signal));
      if (saved && alive.current) { setDraft(null); setNotice("隐私设置已保存，现有资料仍然保留。"); }
    } catch (reason) { failed(reason); }
  }
  async function prepare(kind: "export" | "erase", targets = selected) {
    if (!data) return;
    const input = kind === "export" ? { kind, categories: exports } as const : { kind, targets: targets.map(({ category: leaf, id, revision }) => ({ category: leaf, id, revision })) } as const;
    setNotice("");
    try {
      const result = await summary.mutate(JSON.stringify(input), async (current, requestId) => {
        const operation = await preparePrivacyOperation(ownerId, requestId, input, requestAbort.current?.signal);
        return { ...current, operations: [operation, ...current.operations.filter(row => row.id !== operation.id)] };
      });
      if (result && alive.current) { setFocused(result.operations[0].id); setNotice(kind === "erase" ? "已准备删除影响，请核对后明确确认。" : "导出任务已保存，可离开后在历史记录中继续查看。"); }
    } catch (reason) { failed(reason); }
  }
  function changed() { summary.reload(); items.reload(); setSelected([]); }
  if (invalid) return <div className={styles.page}><div className={styles.empty} role="alert"><p>登录账户暂时无法确认，私人内容已收起。</p><button onClick={() => window.location.reload()}>重新验证账户</button></div></div>;
  return <div className={styles.page}><div className={styles.shell}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/account">读者中心</Link><ChevronRight size={12} /><Link href="/account/settings/privacy">隐私与资料</Link>{exportOnly ? <><ChevronRight size={12} /><span>导出与删除</span></> : null}<span className={styles.private}><LockKeyhole size={12} />仅本人可见</span></nav>
    <header className={styles.heading}><h1>{exportOnly ? "导出与删除资料" : "隐私与资料"}</h1><p>让你决定保存什么、如何使用以及如何带走资料。</p></header>
    <nav className={styles.mobileTabs} aria-label="隐私资料分区">{[["settings", "隐私设置"], ["export", "导出资料"], ["erase", "删除资料"]].map(([key, label]) => <button key={key} aria-current={mobileTab === key ? "page" : undefined} onClick={() => setMobileTab(key)}>{label}</button>)}</nav>
    <div className={styles.layout}>
      <aside className={styles.sidebar}><nav aria-label="账户设置"><Link className={!exportOnly ? styles.active : ""} href="/account/settings/privacy"><LockKeyhole size={15} />隐私与资料</Link><Link href="/account?section=settings"><Settings size={15} />账号设置</Link><Link href="/account?section=settings"><BookOpen size={15} />阅读偏好</Link><Link href="/account/confirmed-notes"><FileText size={15} />研究与笔记</Link><Link className={exportOnly ? styles.active : ""} href="/account/settings/privacy/export"><Download size={15} />导出与下载</Link><button onClick={() => setHistory(true)}><Clock3 size={15} />历史记录</button></nav><div className={styles.help}><strong>需要帮助？</strong><p>导出保留可用来源信息。删除前可逐项查看影响。</p><a href="#privacy-notices">资料处理说明 <ChevronRight size={12} /></a></div></aside>
      <div className={styles.main} data-mobile-tab={mobileTab}>
        {summary.error ? <div className={styles.error} role="alert">{summary.error}<button onClick={summary.reload}><RefreshCw size={14} />重新读取</button></div> : null}
        {notice ? <p className={styles.feedback} role="status">{notice}</p> : null}
        {!data ? <div className={styles.empty} role="status">{summary.loading ? "正在读取本人隐私设置…" : "当前资料尚未读取，请重试。"}</div> : <>
          {!exportOnly || mobileTab === "settings" ? <div className={styles.settingsSections}>
            <Section number="01" title="笔记使用范围"><div className={styles.scope}><p>仅在你主动选定的研究或阅读计划中使用已确认的笔记。</p><p>默认关闭；取消使用不会删除原笔记。</p><Link href="/account/confirmed-notes">选择笔记与使用范围 <ChevronRight size={13} /></Link></div>
              <div className={styles.overview}><div><FileText size={21} /><span>本人主动确认的笔记</span><strong>{data.confirmed_notes} 条</strong></div><div><BookOpen size={21} /><span>当前研究 / 计划授权范围</span><strong>{data.authorized_contexts} 个</strong></div><div><Globe2 size={21} /><span>全局自动使用</span><strong>默认关闭</strong></div></div>
            </Section>
            <Section number="02" title="保留哪些记录" subtitle="保存记录不等于允许个性化使用。关闭后，已有资料继续保留。"><div className={styles.retention}>{(Object.keys(retentionLabels) as RetentionKey[]).map(key => <label key={key}><input type="checkbox" checked={(draft?.retention || data.retention)[key]} onChange={event => setDraft(current => ({ revision: current?.revision ?? data.revision, retention: { ...(current?.retention || data.retention), [key]: event.target.checked } }))} /><span><strong>{retentionLabels[key]}</strong><small>{retentionCopy[key]}</small></span></label>)}</div><p className={styles.info}><Info size={15} />当前检索任务所需临时会话按原有时限保留，不属于长期搜索记录。</p>{draft ? <div className={styles.actions}><button onClick={() => setDraft(null)}>读取最新设置并重新选择</button><button className={styles.primary} disabled={summary.pending} onClick={() => void savePreferences()}>保存设置</button></div> : null}</Section>
          </div> : null}
          <div className={styles.exportSection}>
            <Section number={exportOnly ? "01" : "03"} title="导出资料" subtitle="选择要导出的内容类型，保留来源与版本信息，不默认包含原件。"><div className={styles.exportOptions}>{(Object.keys(exportLabels) as ExportCategory[]).map(key => <label key={key} data-selected={exports.includes(key)}><input type="checkbox" checked={exports.includes(key)} onChange={event => setExports(current => event.target.checked ? [...current, key] : current.filter(value => value !== key))} /><span><strong>{exportLabels[key]}</strong><small>{exportCopy[key]}</small></span></label>)}</div><p className={styles.info}><Info size={15} />只导出本人选择的资料。取消勾选不会删除内容。</p><div className={styles.actions}><span>导出格式：<strong>JSON</strong></span><button className={styles.primary} disabled={summary.pending || selectedTotal === 0 || selectedTotal > data.max_operation_items} onClick={() => void prepare("export")}><Download size={15} />准备导出</button></div>{selectedTotal === 0 ? <div className={styles.emptyExport}><FileText size={22} /><strong>无可导出内容</strong><p>所选类别暂时没有资料。可以重新选择，或先创建研究、笔记与阅读计划。</p></div> : selectedTotal > data.max_operation_items ? <p className={styles.error}>所选 {selectedTotal} 项超过单次 {data.max_operation_items} 项限制，请分类型或在相应工作台逐项导出。</p> : null}
              {data.operations.filter(row => row.kind === "export").slice(0, 2).map(row => <OperationStrip key={row.id} operation={row} onOpen={() => setFocused(row.id)} />)}
            </Section>
          </div>
          <div className={styles.eraseSection}>
            <Section number={exportOnly ? "02" : "04"} title="删除资料" subtitle="先预览影响，再明确确认。这里的操作不会删除公开馆藏或你的账户。"><div className={styles.categoryTabs} aria-label="删除资料分类">{(Object.keys(eraseLabels) as EraseCategory[]).map(key => <button key={key} aria-pressed={category === key} onClick={() => { setCategory(key); setPage(1); setSelected([]); }}>{eraseLabels[key]}<span>{data.erase_counts[key]}</span></button>)}</div>
              {items.error ? <div className={styles.error} role="alert">{items.error}<button onClick={items.reload}>重新读取</button></div> : null}
              {items.loading ? <p role="status">正在读取资料…</p> : items.data ? rows.length ? <div className={styles.tableWrap}><table><thead><tr><th><input type="checkbox" aria-label="选择本页资料" checked={Boolean(rows.length) && rows.every(row => selected.some(value => value.id === row.id))} onChange={event => setSelected(event.target.checked ? rows : [])} /></th><th>内容</th><th>来源 / 版本</th><th>更新时间</th><th>操作</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><input type="checkbox" aria-label={`选择：${row.title}`} checked={selected.some(value => value.id === row.id)} onChange={event => setSelected(current => event.target.checked ? [...current, row] : current.filter(value => value.id !== row.id))} /></td><td><div className={styles.itemTitle}>{row.source.cover_url ? <img src={row.source.cover_url} alt="" /> : <FileText size={24} />}<span><strong>{row.title}</strong><small>{leafLabels[row.category]}</small></span></div></td><td>{row.source.title || "本人资料"}{row.source.edition ? <small>{row.source.edition}</small> : null}</td><td><time dateTime={row.updated_at}>{dateLabel(row.updated_at)}</time></td><td>{row.category === "saved_knowledge" && row.source.path?.startsWith("/theories/nodes/") ? <Link href={row.source.path}>打开条目</Link> : null}{row.category === "graph_views" && row.source.path?.startsWith("/theories/graph?saved_view=") ? <Link href={row.source.path}>恢复图谱</Link> : null}<button disabled={summary.pending} onClick={() => void prepare("erase", [row])}>预览影响</button></td></tr>)}</tbody></table></div> : <div className={styles.emptyList}><FileText size={22} /><p>暂无{eraseLabels[category]}。</p>{category === "search_history" && !data.retention.search_history ? <small>搜索记录默认不保存，开启后才会记录新的检索。</small> : null}</div> : null}
              <div className={styles.pagination}><span>共 {items.data?.count ?? "—"} 项</span><button disabled={page === 1} onClick={() => { setPage(value => value - 1); setSelected([]); }}>上一页</button><span>第 {page} 页</span><button disabled={!items.data || page * items.data.page_size >= items.data.count} onClick={() => { setPage(value => value + 1); setSelected([]); }}>下一页</button></div><div className={styles.selection}><span>已选择 {selected.length} 项资料</span><button disabled={!selected.length} onClick={() => setSelected([])}>取消选择</button><button className={styles.danger} disabled={!selected.length || summary.pending || !items.data} onClick={() => void prepare("erase")}><Trash2 size={14} />提交删除预览</button></div>
              {data.operations.filter(row => row.kind === "erase" && privacyActive(row.status)).map(row => <OperationStrip key={row.id} operation={row} onOpen={() => setFocused(row.id)} />)}
            </Section>
          </div>
          <section className={styles.notices} id="privacy-notices"><h2>注意事项</h2><div><p><Database size={18} /><span><strong>保留来源信息</strong>下载时重新核对来源资格；失效来源保留身份信息，不提供旧原文。</span></p><p><ShieldCheck size={18} /><span><strong>不删除公开馆藏</strong>只处理本人选择的记录。笔记与独立认识的关系会在预览中说明。</span></p><p><Clock3 size={18} /><span><strong>历史记录参考</strong>删除结果保留对象标识与操作状态，不复制已删除正文。备份按既有保留期清理。</span></p></div></section>
        </>}
      </div>
      <aside className={styles.statusSidebar}>{data ? <>
        <section><h2>{exportOnly ? "导出内容概览" : "当前状态"}</h2>{exportOnly ? <><dl>{(Object.keys(exportLabels) as ExportCategory[]).map(key => <div key={key}><dt><FileText size={15} />{exportLabels[key]}</dt><dd>{exports.includes(key) ? data.export_counts[key] : 0} 条</dd></div>)}</dl><p>共 {selectedTotal} 条项目</p><p className={styles.info}>导出文件保留来源与版本信息，不包含原件。</p></> : <><StatusFact icon={<Database size={19} />} title="笔记使用范围" value="按当前研究或计划主动选择" note="确认笔记不会自动授权使用。" /><StatusFact icon={<FileText size={19} />} title="已选用途" value={data.authorized_contexts ? `${data.authorized_contexts} 个研究或计划` : "无"} note="可在已确认笔记中修改使用范围。" /><StatusFact icon={<Clock3 size={19} />} title="待执行操作" value={`${data.operations.filter(row => privacyActive(row.status) || row.status === "preview").length} 项`} note="任务状态与历史记录持续保存。" /></>}
          <div className={styles.recentHeading}><h3>最近操作记录</h3><button onClick={() => setHistory(true)}>查看全部 <ChevronRight size={12} /></button></div>{data.operations.length ? <ol className={styles.recent}>{data.operations.slice(0, 4).map(row => <li key={row.id}><button onClick={() => setFocused(row.id)}>{row.kind === "export" ? "导出资料" : "删除资料"} · {statusLabels[row.status]}</button><time>{dateLabel(row.updated_at)}</time></li>)}</ol> : <p className={styles.quiet}>暂无资料任务。</p>}{data.preference_history.slice(0, 2).map((entry, index) => <p className={styles.quiet} key={`${entry.at}:${index}`}>更新隐私设置<time>{dateLabel(entry.at)}</time></p>)}</section>
      </> : null}</aside>
    </div>
    {data && focused ? <OperationDialog key={focused} id={focused} ownerId={ownerId} titles={Object.fromEntries(selected.map(row => [row.id, row.title]))} onClose={() => setFocused(null)} onChanged={changed} onInvalid={failed} /> : null}
    {data && history ? <OperationHistory ownerId={ownerId} onClose={() => setHistory(false)} onSelect={id => { setHistory(false); setFocused(id); }} /> : null}
  </div></div>;
}

function Section({ number, title, subtitle, children }: { number: string; title: string; subtitle?: string; children: ReactNode }) {
  return <section className={styles.section}><span className={styles.number}>{number}</span><div className={styles.sectionBody}><header><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</header>{children}</div></section>;
}
function StatusFact({ icon, title, value, note }: { icon: ReactNode; title: string; value: string; note: string }) {
  return <div className={styles.statusFact}>{icon}<div><strong>{title}</strong><span>{value}</span><small>{note}</small></div></div>;
}
function OperationStrip({ operation: row, onOpen }: { operation: PrivacyOperation; onOpen: () => void }) {
  return <div className={styles.operationStrip} data-state={row.status}><Info size={17} /><div><strong>{row.kind === "export" ? "资料导出" : "资料删除"} · {statusLabels[row.status]}</strong><p>已完成 {row.completed} 项{row.failed ? `，${row.failed} 项未完成` : ""}{row.remaining ? `，剩余 ${row.remaining} 项` : ""}。{privacyActive(row.status) ? "可以离开后继续查看。" : ""}</p></div><button onClick={onOpen}>查看任务</button></div>;
}

export function OperationDialog({ id, ownerId, titles, onClose, onChanged, onInvalid }: { id: string; ownerId: string; titles: Record<string, string>; onClose: () => void; onChanged: () => void; onInvalid: (reason: unknown) => void }) {
  const workspace = usePersistentWorkspace<PrivacyOperation>(operationPath(id), ownerId, data => privacyActive(data.status) ? 2000 : null);
  const [acknowledgedRevision, setAcknowledgedRevision] = useState<number | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [notice, setNotice] = useState("");
  const alive = useRef(true);
  const requestAbort = useRef<AbortController | null>(null);
  useEffect(() => { alive.current = true; requestAbort.current = new AbortController(); return () => { alive.current = false; requestAbort.current?.abort(); }; }, []);
  const row = workspace.error ? null : workspace.data;
  async function command(action: "confirm" | "cancel" | "retry") {
    if (!row) return;
    try {
      const result = await workspace.mutate(`${action}:${row.revision}`, () => commandPrivacyOperation(ownerId, id, row.revision, action, requestAbort.current?.signal));
      if (result && alive.current) { setAcknowledgedRevision(null); setNotice(action === "confirm" ? "删除任务已提交，已完成的项目不能撤销。" : action === "retry" && result.kind === "erase" ? "已重新读取待处理资料，请再次核对影响。" : "任务状态已更新。"); onChanged(); }
    } catch (reason) { onInvalid(reason); }
  }
  async function download() {
    if (downloading) return;
    setDownloading(true); setNotice("");
    try {
      const output = await withPrivateOwner(ownerId, () => downloadPrivacyOperation(ownerId, id, requestAbort.current?.signal), requestAbort.current?.signal);
      if (!alive.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], { type: "application/json;charset=utf-8" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `书库资料-${id}.json`; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`已准备 ${output.records.length} 项资料并开始下载。${output.unavailable_since_preparation.length ? `其中 ${output.unavailable_since_preparation.length} 项在准备后已变化，详细原因在文件中列出。` : ""}`);
    } catch (reason) { onInvalid(reason); if (alive.current) setNotice(reason instanceof Error ? reason.message : "下载暂未完成。"); }
    finally { if (alive.current) setDownloading(false); }
  }
  return <Dialog open onRequestClose={onClose} className={styles.dialog} aria-labelledby="privacy-operation-title"><header><div><h2 id="privacy-operation-title">{row?.kind === "erase" ? "删除资料与影响" : "导出资料"}</h2><p>仅处理本次明确选择的本人资料。</p></div><button aria-label="关闭任务" onClick={onClose}><X size={18} /></button></header>
    {workspace.error ? <div className={styles.error} role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取</button></div> : null}
    {notice ? <p role="status" className={styles.feedback}>{notice}</p> : null}
    {!row ? <p role="status">正在读取任务…</p> : <><div className={styles.jobStatus}><strong>{statusLabels[row.status]}</strong><span>{dateLabel(row.updated_at)}</span></div>
      {row.status === "preview" ? <><p>将处理 {row.preview.length} 项。请核对内容与影响；资料或授权发生变化时会停止删除并要求重新预览。</p><ul className={styles.impactList}>{row.preview.map(target => <li key={target.id}><strong>{target.title || titles[target.id] || `${leafLabels[target.category]} · ${target.id.slice(0, 8)}`}</strong><p>{target.impact.message}</p>{target.current === false ? <small>这项资料已有变化；请关闭此预览，重新选择后再提交。</small> : null}{target.impact.scope_count ? <small>涉及 {target.impact.scope_count} 个笔记使用范围，将撤销对应授权。</small> : null}</li>)}</ul><label className={styles.acknowledgement}><input type="checkbox" checked={acknowledgedRevision === row.revision} onChange={event => setAcknowledgedRevision(event.target.checked ? row.revision : null)} />我已核对所选资料和影响，确认删除。账户、原始馆藏及未选择资料保留。</label></> : <><p>已完成 {row.completed} / {row.total} 项{row.failed ? `，${row.failed} 项未完成` : ""}。</p><progress max={row.total || 1} value={row.completed + row.failed} aria-label="资料任务已处理项目" /><ol className={styles.steps}><li data-current={privacyActive(row.status)}><span />{row.kind === "erase" ? "逐项复核版本与删除影响" : "复核所选资料与来源"}</li><li data-current={row.status === "completed"}><span />{row.kind === "erase" ? "清理关联授权与派生资料" : "准备 JSON 下载"}</li><li data-current={row.status === "completed"}><span />保存处理结果</li></ol>{row.error_code ? <p className={styles.error}>{failureLabels[row.error_code] || "任务未完成，请查看结果后重试。"}</p> : null}{row.results.some(result => result.status === "failed") ? <ul className={styles.failures}>{row.results.filter(result => result.status === "failed").map(result => <li key={result.id}>{leafLabels[result.category]} · {result.id.slice(0, 8)}：{failureLabels[result.error_code] || "未能完成"}</li>)}</ul> : null}</>}
      <p className={styles.info}><Info size={15} />{row.notice}</p><footer><button onClick={onClose}>稍后查看</button>{row.download_available ? <button disabled={downloading} onClick={() => void download()}><Download size={14} />{downloading ? "正在准备…" : "查看成功文件"}</button> : null}{row.status === "preview" ? <button className={styles.danger} disabled={acknowledgedRevision !== row.revision || workspace.pending || !row.preview.length} onClick={() => void command("confirm")}><Trash2 size={14} />确认删除所选资料</button> : null}{privacyActive(row.status) || row.status === "preview" ? <button disabled={workspace.pending} onClick={() => void command("cancel")}>取消此任务</button> : null}{["partial", "failed", "canceled"].includes(row.status) && row.completed < row.total ? <button className={styles.primary} disabled={workspace.pending} onClick={() => void command("retry")}>{row.kind === "erase" ? "重新预览剩余资料" : "重试未完成项"}</button> : null}</footer>
    </>}
  </Dialog>;
}

function OperationHistory({ ownerId, onClose, onSelect }: { ownerId: string; onClose: () => void; onSelect: (id: string) => void }) {
  const [page, setPage] = useState(1);
  const workspace = usePersistentWorkspace<PrivacyOperations>(`${operationPath()}?page=${page}`, ownerId, data => data.results.some(row => privacyActive(row.status)) ? 2500 : null);
  return <Dialog open onRequestClose={onClose} className={styles.dialog} aria-labelledby="privacy-history-title"><header><h2 id="privacy-history-title">资料操作历史</h2><button aria-label="关闭历史" onClick={onClose}><X size={18} /></button></header>{workspace.error ? <div className={styles.error} role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取</button></div> : null}{workspace.data ? <>{workspace.data.results.length ? workspace.data.results.map(row => <OperationStrip key={row.id} operation={row} onOpen={() => onSelect(row.id)} />) : <p className={styles.emptyList}>暂无导出或删除任务。</p>}<div className={styles.pagination}><span>共 {workspace.data.count} 项</span><button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button disabled={!workspace.data.next} onClick={() => setPage(value => value + 1)}>下一页</button></div></> : <p role="status">正在读取历史…</p>}</Dialog>;
}
