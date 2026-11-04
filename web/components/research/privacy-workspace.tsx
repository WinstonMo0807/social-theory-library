"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BookOpen, ChevronRight, Clock3, Database, Download, FileText, Globe2, Info, LockKeyhole, RefreshCw, Settings, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { commandPrivacyOperation, operationPath, privacyActive, privacyPath, privacyTargetKey, savePrivacyPreferences,
  type EraseCategory, type ExportCategory, type PrivacyItem, type PrivacyItems, type PrivacyOperation, type PrivacyOperations, type PrivacySummary, type RetentionKey } from "@/lib/api/privacy.client";
import { canExportFolder, downloadPrivacyFiles, type PrivacyExportFormat } from "@/lib/api/privacy-export.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { PrivacyRequestRecovery, usePrivacyPreparation } from "./privacy-request-recovery";
import { ReaderMobileNav } from "./reader-mobile-nav";
import styles from "./privacy.module.css";

const coreRetention: RetentionKey[] = ["reading_history","search_history","personal_notes","followed_topics"];
const coreExports: ExportCategory[] = ["research","notes","plans","audits"];
const coreErase: EraseCategory[] = ["reading_history", "search_history", "personal_notes", "reading_plans"];
const eraseDisplay: Partial<Record<EraseCategory, string>> = { personal_notes: "个人笔记", reading_plans: "研究计划" };
const retentionDisplay: Partial<Record<RetentionKey,[string,string]>> = {reading_history:["阅读历史","我阅读过的书籍与文章"],search_history:["搜索记录","我使用的关键词与筛选条件"],personal_notes:["个人笔记","我添加的笔记与标注"],followed_topics:["关注的主题","我收藏的主题"]};
const exportDisplay: Partial<Record<ExportCategory,[string,string]>> = {research:["研究资料","收藏的文献、书籍与条目（含来源与版本）"],notes:["笔记内容","个人笔记与标注（含创建时间）"],plans:["研究计划","我创建的研究计划与阅读清单"],audits:["引用报告","我生成的引用报告（含来源与版本）"]};
const retentionLabels: Record<RetentionKey, string> = { reading_history: "阅读历史", search_history: "搜索记录", personal_notes: "笔记、摘录与书签", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", saved_knowledge: "知识条目、图谱视图与私人书单" };
const retentionCopy: Record<RetentionKey, string> = { reading_history: "保存以后阅读的位置记录，阅读进度单独保留。", search_history: "仅在开启后保存新的检索词与筛选条件。", personal_notes: "允许新建阅读笔记、书签、个人认识与私人并读对齐（含术语笔记）。已有内容仍可编辑；研究工作台中主动保存的笔记单独保留。", followed_topics: "允许新增主题收藏，已有收藏不会自动删除；主题档案更新关注单独管理。", source_follows: "允许关注公开来源、学者与主题档案，并保存后续正式更新。关闭后停止记录更新，已有记录仍保留。", saved_knowledge: "允许收藏理论、概念与争论，以及保存私人图谱范围、布局和文章书单。关闭后不新增，已有记录仍可取消或删除。" };
const exportLabels: Record<ExportCategory, string> = { collaboration: "小组、分享与站内通知", article_comments: "文章评论", research: "研究资料", notes: "笔记内容", plans: "阅读计划与公共跟读", audits: "引文报告", source_follows: "来源、学者与主题关注", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
const exportCopy: Record<ExportCategory, string> = { collaboration: "本人小组关系、邀请、明确分享范围和站内通知，不导出链接或邀请凭证", article_comments: "本人明确提交的评论、公开署名及审核状态，包含已公开与未公开内容", research: "研究问题、选材、轮次及研究笔记、选材备注、比较与回放笔记（含来源与版本）", notes: "阅读笔记、书签、已保存认识与私人并读对齐及术语笔记；工作台研究笔记请勾选研究资料", plans: "本人创建或另存的阅读计划、公共路径收藏及跟读进度与笔记", audits: "引文报告与本人来源信息（不含原件）", source_follows: "本人来源、学者与主题关注及站内状态历史（不含原文）", saved_knowledge: "本人收藏的作品、理论与概念入口，以及私人图谱名称、范围和布局，以及私人书单与作品顺序；不含来源正文或候选关系。" };
const eraseLabels: Record<EraseCategory, string> = { collaboration: "小组、分享与站内通知", article_comments: "文章评论", reading_history: "阅读历史", search_history: "搜索记录", personal_notes: "笔记、摘录与书签", reading_plans: "阅读计划与公共跟读", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
const leafLabels: Record<string, string> = { reader_groups: "本人小组", group_memberships: "小组成员关系", group_invitations: "小组邀请", reader_shares: "分享与提案", share_notices: "站内通知", saved_items: "作品收藏", article_comments: "文章评论", reading_history: "阅读历史", search_history: "搜索记录", bookmarks: "页面书签", annotations: "阅读笔记", memories: "个人认识", parallel_alignments: "私人并读对齐与术语笔记", plans: "阅读计划与公共跟读", followed_topics: "收藏的主题", source_follows: "来源、学者与主题关注", research: "研究资料", audits: "引文报告", citation_sources: "本人来源信息", graph_views: "私人图谱视图", reading_lists: "私人书单", saved_knowledge: "作品收藏、知识条目、图谱与书单" };
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
  const search = useSearchParams(), statusView = search?.get("view") === "status";
  const summary = usePersistentWorkspace<PrivacySummary>(privacyPath, ownerId, poll);
  const [category, setCategory] = useState<EraseCategory>("reading_history");
  const [page, setPage] = useState(1);
  const items = usePersistentWorkspace<PrivacyItems>(`${privacyPath}items/?category=${category}&page=${page}`, ownerId);
  const [selected, setSelected] = useState<PrivacyItem[]>([]);
  const [format, setFormat] = useState<PrivacyExportFormat>("zip");
  const [exports, setExports] = useState<ExportCategory[]>(["research", "notes"]);
  const [draft, setDraft] = useState<{ revision: number; retention: Record<RetentionKey, boolean> } | null>(null);
  const [mobileTab, setMobileTab] = useState(exportOnly ? "export" : "settings");
  const [focused, setFocused] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [notice, setNotice] = useState("");
  const [invalid, setInvalid] = useState(false);
  const preparation = usePrivacyPreparation(ownerId, `stl-reader-material-request:${ownerId}`);
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
    const input = kind === "export" ? { kind, categories: exports } as const : { kind, targets: targets.map(({ category: leaf, id, revision, preference_revision }) => ({ category: leaf, id, revision, preference_revision })) } as const;
    setNotice("");
    const id = await preparation.prepare(input);
    if (id) { setFocused(id); summary.reload(); }
  }

  const exportOverview = data ? <><dl>{[...coreExports, ...(Object.keys(exportLabels) as ExportCategory[]).filter(key => !coreExports.includes(key) && exports.includes(key))].map(key => <div key={key}><dt><FileText size={15} />{exportLabels[key]}</dt><dd>{exports.includes(key) ? data.export_counts[key] : 0} 条</dd></div>)}</dl><p>共 {selectedTotal} 条项目</p><p className={styles.info}>导出文件保留来源与版本信息，不包含原件。</p></> : null;
  const eraseCategoryButton = (key: EraseCategory) => <button key={key} aria-label={`${eraseLabels[key]} ${data?.erase_counts[key] ?? 0}`} title={eraseLabels[key]} aria-pressed={category === key} onClick={() => { setCategory(key); setPage(1); setSelected([]); }}>{eraseDisplay[key] || eraseLabels[key]}<span>{data?.erase_counts[key]}</span></button>;

  function changed() { summary.reload(); items.reload(); setSelected([]); }
  if (invalid) return <div className={styles.page}><div className={styles.empty} role="alert"><p>登录账户暂时无法确认，私人内容已收起。</p><button onClick={() => window.location.reload()}>重新验证账户</button></div></div>;
  return <div className={styles.page} data-status-view={statusView||undefined} data-export-view={exportOnly||undefined}><div className={styles.shell}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/account">读者中心</Link><ChevronRight size={12} /><Link href="/account/settings/privacy">隐私与资料</Link>{exportOnly ? <><ChevronRight size={12} /><span>导出与删除</span></> : null}<span className={styles.private}><LockKeyhole size={12} />仅本人可见</span></nav>
    <header className={styles.heading}><h1>{statusView ? "隐私、记忆偏好与资料导出" : exportOnly ? "导出与删除资料" : "隐私与资料"}</h1>{statusView?<Link href="/account/settings/privacy">返回隐私设置 →</Link>:null}</header>
    <nav className={styles.mobileTabs} aria-label="隐私资料分区">{[["settings", "隐私设置"], ["export", "导出资料"], ["erase", "删除资料"]].map(([key, label]) => <button key={key} aria-current={mobileTab === key ? "page" : undefined} onClick={() => { setMobileTab(key); document.getElementById(`privacy-${key}`)?.scrollIntoView({block:"start"}); }}>{label}</button>)}</nav>
    <div className={styles.layout}>
      <aside className={styles.sidebar}><nav aria-label="账户设置"><Link className={!exportOnly ? styles.active : ""} href="/account/settings/privacy"><LockKeyhole size={15} />隐私与资料</Link><Link href="/account?section=settings"><Settings size={15} />账号设置</Link><Link href="/account?section=settings"><BookOpen size={15} />阅读偏好</Link><Link href="/account/confirmed-notes"><FileText size={15} />研究与笔记</Link><Link className={exportOnly ? styles.active : ""} href="/account/settings/privacy/export"><Download size={15} />导出与下载</Link><button onClick={() => setHistory(true)}><Clock3 size={15} />历史记录</button></nav><div className={styles.help}><strong>需要帮助？</strong><p>导出保留可用来源信息。删除前可逐项查看影响。</p><Link href="/help/account#site-privacy">隐私政策 <ChevronRight size={12}/></Link><a href="#privacy-notices">资料导出说明 <ChevronRight size={12} /></a><Link href="/help">常见问题 <ChevronRight size={12}/></Link></div></aside>
      <div className={styles.main} data-mobile-tab={mobileTab}>
        {summary.error ? <div className={styles.error} role="alert">{summary.error}<button onClick={summary.reload}><RefreshCw size={14} />重新读取</button></div> : null}
        {notice ? <p className={styles.feedback} role="status">{notice}</p> : null}
        <PrivacyRequestRecovery preparation={preparation} className={styles.feedback} onOpen={id => { setFocused(id); summary.reload(); }} />
        {!data ? <div className={styles.empty} role="status">{summary.loading ? "正在读取本人隐私设置…" : "当前资料尚未读取，请重试。"}</div> : <>
          {!exportOnly || mobileTab === "settings" ? <div className={styles.settingsSections} id="privacy-settings">
            <Section number="01" title={statusView?"隐私范围概览":"笔记使用范围"}><div className={styles.scope}><p><Link href="/account/confirmed-notes" title="选择笔记与使用范围">仅在你主动选定的研究或阅读计划中使用已确认的笔记。</Link></p><p>默认关闭；取消使用不会删除原笔记。</p></div>
              <div className={styles.overview}><div><FileText size={21} /><span>本人主动确认的笔记</span><strong>{data.confirmed_notes} 条</strong><p>仅在你主动选择的研究或阅读计划中使用。</p></div><div><BookOpen size={21} /><span>当前研究 / 计划授权范围</span><strong>{data.authorized_contexts} 个</strong><p>已明确选定的研究与阅读计划。</p></div><div><Globe2 size={21} /><span>全局自动使用</span><strong>默认关闭</strong><p>不会自动将你的笔记用于任何新研究或阅读计划。</p></div></div>
            </Section>
            <Section number="02" title="保留哪些记录" ><div className={styles.retention}>{coreRetention.map(key => <label key={key}><input type="checkbox" checked={(draft?.retention || data.retention)[key]} onChange={event => setDraft(current => ({ revision: current?.revision ?? data.revision, retention: { ...(current?.retention || data.retention), [key]: event.target.checked } }))} /><span><strong title={retentionCopy[key]}>{retentionDisplay[key]?.[0]||retentionLabels[key]}</strong><small>{retentionDisplay[key]?.[1]||retentionCopy[key]}</small></span></label>)}</div><details className={styles.moreOptions}><summary>其他记录类型</summary><div className={styles.retention}>{(Object.keys(retentionLabels) as RetentionKey[]).filter(key=>!coreRetention.includes(key)).map(key => <label key={key}><input type="checkbox" checked={(draft?.retention || data.retention)[key]} onChange={event => setDraft(current => ({ revision: current?.revision ?? data.revision, retention: { ...(current?.retention || data.retention), [key]: event.target.checked } }))} /><span><strong>{retentionLabels[key]}</strong><small>{retentionCopy[key]}</small></span></label>)}</div></details><p className={styles.info}><Info size={15} />你可以随时调整这些设置。</p>{draft ? <div className={styles.actions}><button onClick={() => setDraft(null)}>取消修改</button><button className={styles.primary} disabled={summary.pending} onClick={() => void savePreferences()}>保存设置</button></div> : null}</Section>
          </div> : null}
          {statusView?<Section number="02" title="任务状态与操作" ><div className={styles.taskCards}>{data.operations.slice(0,4).map(row=><PrivacyTaskCard key={row.id} row={row} onOpen={()=>setFocused(row.id)}/>)}{!data.operations.length?<article><FileText size={34}/><h3>{Object.values(data.export_counts).some(count=>count>0)?"暂无资料任务":"无可导出内容"}</h3><p>{Object.values(data.export_counts).some(count=>count>0)?"选择需要导出的资料后，可以在这里继续查看处理结果。":"所选内容暂时没有可导出的条目。创建研究、笔记或阅读计划后，可在导出资料中选择。"}</p><Link href="/account/settings/privacy/export">查看导出资料 →</Link></article>:null}</div><button onClick={()=>setHistory(true)}>查看全部任务历史</button></Section>:null}
          <div className={styles.exportSection} id="privacy-export">
            <Section number={exportOnly ? "01" : "03"} title="导出资料" subtitle="选择要导出的内容类型，保留来源与版本信息，不默认包含原件。"><div className={styles.exportOptions}>{coreExports.map(key => <label key={key} data-selected={exports.includes(key)}><input type="checkbox" checked={exports.includes(key)} onChange={event => setExports(current => event.target.checked ? [...current, key] : current.filter(value => value !== key))} /><span><strong title={exportCopy[key]}>{exportDisplay[key]?.[0]||exportLabels[key]}</strong><small>{exportDisplay[key]?.[1]||exportCopy[key]}</small></span></label>)}</div><details className={styles.moreOptions}><summary>其他资料类型</summary><div className={styles.exportOptions}>{(Object.keys(exportLabels) as ExportCategory[]).filter(key=>!coreExports.includes(key)).map(key => <label key={key} data-selected={exports.includes(key)}><input type="checkbox" checked={exports.includes(key)} onChange={event => setExports(current => event.target.checked ? [...current, key] : current.filter(value => value !== key))} /><span><strong>{exportLabels[key]}</strong><small>{exportCopy[key]}</small></span></label>)}</div></details><p className={styles.info}><Info size={15} />只导出本人选择的资料。取消勾选不会删除内容。</p><ExportFormatChoice value={format} onChange={setFormat} disabled={preparation.busy} /><div className={styles.actions}><span>来源、版本与失败清单随文件保留</span><button className={styles.primary} disabled={summary.pending || preparation.locked || selectedTotal === 0 || selectedTotal > data.max_operation_items} onClick={() => void prepare("export")}><Download size={15} />准备导出</button></div>{selectedTotal === 0 ? <div className={styles.emptyExport}><FileText size={22} /><strong>无可导出内容</strong><p>所选类别暂时没有资料。可以重新选择，或先创建研究、笔记与阅读计划。</p></div> : selectedTotal > data.max_operation_items ? <p className={styles.error}>所选 {selectedTotal} 项超过单次 {data.max_operation_items} 项限制，请分类型或在相应工作台逐项导出。</p> : null}
              {data.operations.filter(row => row.kind === "export").slice(0, 2).map(row => <OperationStrip key={row.id} operation={row} onOpen={() => setFocused(row.id)} />)}
            </Section>
            {exportOnly ? <section className={styles.mobileExportOverview} aria-label="导出内容概览"><h2>导出内容概览</h2>{exportOverview}</section> : null}
          </div>
          <div className={styles.eraseSection} id="privacy-erase">
            <Section number={exportOnly ? "02" : "04"} title="删除资料" subtitle="先预览影响，再明确确认。这里的操作不会删除公开馆藏或你的账户。"><div className={styles.categoryTabs} aria-label="删除资料分类">{coreErase.map(eraseCategoryButton)}</div><details className={styles.moreOptions}><summary>{coreErase.includes(category) ? "其他资料类型" : `其他资料类型 · ${eraseLabels[category]}`}</summary><div className={styles.categoryTabs} aria-label="其他删除资料分类">{(Object.keys(eraseLabels) as EraseCategory[]).filter(key => !coreErase.includes(key)).map(eraseCategoryButton)}</div></details>
              {category === "personal_notes" ? <p className={styles.info}><Info size={15} /><span>这里仅清理所选阅读笔记、书签、个人认识和私人并读记录。研究工作台中的笔记、选材备注与比较仍保留，可到<Link href="/account/research">我的研究</Link>管理。</span></p> : null}
              {items.error ? <div className={styles.error} role="alert">{items.error}<button onClick={items.reload}>重新读取</button></div> : null}
              {items.loading ? <p role="status">正在读取资料…</p> : items.data ? rows.length ? <div className={styles.tableWrap}><table><thead><tr><th><input type="checkbox" aria-label="选择本页资料" checked={Boolean(rows.length) && rows.every(row => selected.some(value => privacyTargetKey(value) === privacyTargetKey(row)))} onChange={event => setSelected(event.target.checked ? rows : [])} /></th><th>内容</th><th>来源 / 版本</th><th>更新时间</th><th>操作</th></tr></thead><tbody>{rows.map(row => <tr key={privacyTargetKey(row)}><td><input type="checkbox" aria-label={`选择：${row.title}`} checked={selected.some(value => privacyTargetKey(value) === privacyTargetKey(row))} onChange={event => setSelected(current => event.target.checked ? [...current, row] : current.filter(value => privacyTargetKey(value) !== privacyTargetKey(row)))} /></td><td><div className={styles.itemTitle}>{row.source.cover_url ? <MediaPlacement uses={row.source.cover_media?.display_uses} fallback={<FileText size={24} />}><img src={row.source.cover_url} alt="" /></MediaPlacement> : <FileText size={24} />}<span><strong>{row.title}</strong><small>{leafLabels[row.category]}</small></span></div></td><td>{row.source.title || "本人资料"}{row.source.edition ? <small>{row.source.edition}</small> : null}</td><td><time dateTime={row.updated_at}>{dateLabel(row.updated_at)}</time></td><td>{row.category === "saved_knowledge" && row.source.path?.startsWith("/theories/nodes/") ? <Link href={row.source.path}>打开条目</Link> : null}{row.category === "graph_views" && row.source.path?.startsWith("/theories/graph?saved_view=") ? <Link href={row.source.path}>恢复图谱</Link> : null}<button disabled={summary.pending || preparation.locked} onClick={() => void prepare("erase", [row])}>预览影响</button></td></tr>)}</tbody></table></div> : <div className={styles.emptyList}><FileText size={22} /><p>暂无{eraseLabels[category]}。</p>{category === "search_history" && !data.retention.search_history ? <small>搜索记录默认不保存，开启后才会记录新的检索。</small> : null}</div> : null}
              <div className={styles.pagination}><span>共 {items.data?.count ?? "—"} 项</span><button disabled={page === 1} onClick={() => { setPage(value => value - 1); setSelected([]); }}>上一页</button><span>第 {page} 页</span><button disabled={!items.data || page * items.data.page_size >= items.data.count} onClick={() => { setPage(value => value + 1); setSelected([]); }}>下一页</button></div><div className={styles.selection}><span>已选择 {selected.length} 项资料</span><button disabled={!selected.length} onClick={() => setSelected([])}>取消选择</button><button className={styles.danger} disabled={!selected.length || summary.pending || preparation.locked || !items.data} onClick={() => void prepare("erase")}><Trash2 size={14} />提交删除预览</button></div>
              {data.operations.filter(row => row.kind === "erase" && privacyActive(row.status)).map(row => <OperationStrip key={row.id} operation={row} onOpen={() => setFocused(row.id)} />)}
            </Section>
          </div>
          <section className={styles.notices} id="privacy-notices"><h2>注意事项</h2><div><p><Database size={18} /><span><strong>保留来源信息</strong>下载时重新核对来源资格；失效来源保留身份信息，不提供旧原文。</span></p><p><ShieldCheck size={18} /><span><strong>不删除公开馆藏</strong>只处理本人选择的记录。笔记与独立认识的关系会在预览中说明。</span></p><p><Clock3 size={18} /><span><strong>历史记录参考</strong>删除结果保留对象标识与操作状态，不复制已删除正文。备份按既有保留期清理。</span></p></div></section>
        </>}
      </div>
      <aside className={styles.statusSidebar}>{data ? <>
        <section><h2>{exportOnly ? "导出内容概览" : "当前状态"}</h2>{exportOnly ? exportOverview : <><StatusFact icon={<Database size={19} />} title="笔记使用范围" value="按当前研究或计划主动选择" note="用于研究或计划时需另行选择。" /><StatusFact icon={<FileText size={19} />} title="已选用途" value={data.authorized_contexts ? `${data.authorized_contexts} 个研究或计划` : "无"} note="可在已确认笔记中修改使用范围。" /><StatusFact icon={<Clock3 size={19} />} title="待执行操作" value={`${data.operations.filter(row => privacyActive(row.status) || row.status === "preview").length} 项`} note="任务状态与历史记录持续保存。" /></>}
          <Link className={styles.taskViewLink} href="/account/settings/privacy?view=status">任务状态与操作 →</Link><div className={styles.recentHeading}><h3>最近操作记录</h3><button onClick={() => setHistory(true)}>查看全部 <ChevronRight size={12} /></button></div>{data.operations.length ? <ol className={styles.recent}>{data.operations.slice(0, 4).map(row => <li key={row.id}><button onClick={() => setFocused(row.id)}>{row.kind === "export" ? "导出资料" : "删除资料"} · {statusLabels[row.status]}</button><time>{dateLabel(row.updated_at)}</time></li>)}</ol> : <p className={styles.quiet}>暂无资料任务。</p>}{data.preference_history.slice(0, 2).map((entry, index) => <p className={styles.quiet} key={`${entry.at}:${index}`}>更新隐私设置<time>{dateLabel(entry.at)}</time></p>)}</section>
      </> : null}</aside>
    </div>
    {data && focused ? <OperationDialog key={focused} id={focused} ownerId={ownerId} initialFormat={format} onClose={() => setFocused(null)} onChanged={changed} onInvalid={failed} /> : null}
    {data && history ? <OperationHistory ownerId={ownerId} onClose={() => setHistory(false)} onSelect={id => { setHistory(false); setFocused(id); }} /> : null}
    {!exportOnly ? <ReaderMobileNav variant="privacy" /> : null}
  </div></div>;
}

function Section({ number, title, subtitle, children }: { number: string; title: string; subtitle?: string; children: ReactNode }) {
  return <section className={styles.section}><span className={styles.number}>{number}</span><div className={styles.sectionBody}><header><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</header>{children}</div></section>;
}
function StatusFact({ icon, title, value, note }: { icon: ReactNode; title: string; value: string; note: string }) {
  return <div className={styles.statusFact}>{icon}<div><strong>{title}</strong><span>{value}</span><small>{note}</small></div></div>;
}
function PrivacyTaskCard({ row, onOpen }: { row: PrivacyOperation; onOpen: () => void }) {
  const active=privacyActive(row.status);
  return <article data-state={row.status}><header>{active?<span className={styles.taskRing} aria-hidden/>:<FileText size={34}/>}<h3>{row.kind==="erase"?"删除派生资料":"导出资料"} · {statusLabels[row.status]}</h3></header><strong>{active?"可离开后恢复查看":row.status==="preview"?"等待本人确认影响":`已完成 ${row.completed} 项${row.failed?`，${row.failed} 项未完成`:""}`}</strong><p>{row.notice || (active?"正在处理本次明确选择的资料。你可以离开此页面，稍后回来查看进度。":"可查看处理结果、成功文件及未完成项目。")}</p>{row.total>0?<><progress value={row.completed+row.failed} max={row.total} aria-label="已处理项目"/><small>成功 {row.completed} · 未完成 {row.failed} · 剩余 {row.remaining}</small></>:null}<time dateTime={row.updated_at}>{dateLabel(row.updated_at)}</time><button onClick={onOpen}>{row.status==="preview"?"核对资料与影响":active?"查看进度与可用操作":"查看结果与可用操作"}</button></article>;
}

function OperationStrip({ operation: row, onOpen }: { operation: PrivacyOperation; onOpen: () => void }) {
  return <div className={styles.operationStrip} data-state={row.status}><Info size={17} /><div><strong>{row.kind === "export" ? "资料导出" : "资料删除"} · {statusLabels[row.status]}</strong><p>已完成 {row.completed} 项{row.failed ? `，${row.failed} 项未完成` : ""}{row.remaining ? `，剩余 ${row.remaining} 项` : ""}。{privacyActive(row.status) ? "可以离开后继续查看。" : ""}</p></div><button onClick={onOpen}>查看任务</button></div>;
}

export function OperationDialog({ id, ownerId, onClose, onChanged, onInvalid, initialFormat = "zip" }: { id: string; ownerId: string; initialFormat?: PrivacyExportFormat; onClose: () => void; onChanged: () => void; onInvalid: (reason: unknown) => void }) {
  const workspace = usePersistentWorkspace<PrivacyOperation>(operationPath(id), ownerId, data => privacyActive(data.status) ? 2000 : null);
  const [acknowledgedRevision, setAcknowledgedRevision] = useState<number | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [format, setFormat] = useState<PrivacyExportFormat>(initialFormat);
  const downloadLock = useRef(false);
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
    const controller = requestAbort.current;
    if (downloadLock.current || !controller || controller.signal.aborted) return;
    downloadLock.current = true; setDownloading(true); setNotice("");
    try {
      const message = await downloadPrivacyFiles(ownerId, id, format, controller.signal);
      if (alive.current) setNotice(message);
    } catch (reason) { onInvalid(reason); if (alive.current) setNotice(reason instanceof Error ? reason.message : "下载暂未完成，原任务仍保留。"); }
    finally { downloadLock.current = false; if (alive.current) setDownloading(false); }
  }

  return <Dialog open onRequestClose={onClose} className={styles.dialog} aria-labelledby="privacy-operation-title"><header><div><h2 id="privacy-operation-title">{row?.kind === "erase" ? "删除资料与影响" : "导出资料"}</h2><p>仅处理本次明确选择的本人资料。</p></div><button aria-label="关闭任务" onClick={onClose}><X size={18} /></button></header>
    {workspace.error ? <div className={styles.error} role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取</button></div> : null}
    {notice ? <p role="status" className={styles.feedback}>{notice}</p> : null}
    {!row ? <p role="status">正在读取任务…</p> : <><div className={styles.jobStatus}><strong>{statusLabels[row.status]}</strong><span>{dateLabel(row.updated_at)}</span></div>
      {row.status === "preview" ? <><p>将处理 {row.preview.length} 项。请核对内容与影响；资料或授权发生变化时会停止删除并要求重新预览。</p><ul className={styles.impactList}>{row.preview.map(target => <li key={`${target.category}:${target.id}`}><strong>{target.title || `${leafLabels[target.category]} · ${target.id.slice(0, 8)}`}</strong><p>{target.impact.message}</p>{target.current === false ? <small>这项资料已有变化；请关闭此预览，重新选择后再提交。</small> : null}{target.impact.scope_count ? <small>涉及 {target.impact.scope_count} 个笔记使用范围，将撤销对应授权。</small> : null}</li>)}</ul><label className={styles.acknowledgement}><input type="checkbox" checked={acknowledgedRevision === row.revision} onChange={event => setAcknowledgedRevision(event.target.checked ? row.revision : null)} />我已核对所选资料和影响，确认删除。账户、原始馆藏及未选择资料保留。</label></> : <><p>已完成 {row.completed} / {row.total} 项{row.failed ? `，${row.failed} 项未完成` : ""}。</p><progress max={row.total || 1} value={row.completed + row.failed} aria-label="资料任务已处理项目" /><ol className={styles.steps}><li data-current={privacyActive(row.status)}><span />{row.kind === "erase" ? "逐项复核版本与删除影响" : "复核所选资料与来源"}</li><li data-current={row.status === "completed"}><span />{row.kind === "erase" ? "清理关联授权与派生资料" : "准备资料与下载清单"}</li><li data-current={row.status === "completed"}><span />保存处理结果</li></ol>{row.error_code ? <p className={styles.error}>{failureLabels[row.error_code] || "任务未完成，请查看结果后重试。"}</p> : null}{row.results.some(result => result.status === "failed") ? <ul className={styles.failures}>{row.results.filter(result => result.status === "failed").map(result => <li key={`${result.category}:${result.id}`}>{leafLabels[result.category]} · {result.id.slice(0, 8)}：{failureLabels[result.error_code] || "未能完成"}</li>)}</ul> : null}</>}
      {row.kind === "export" ? <ExportFormatChoice value={format} onChange={setFormat} disabled={downloading} /> : null}
      <p className={styles.info}><Info size={15} />{row.notice}</p><footer><button onClick={onClose}>稍后查看</button>{row.download_available ? <button disabled={downloading} onClick={() => void download()}><Download size={14} />{downloading ? "正在准备…" : "查看成功文件"}</button> : null}{row.status === "preview" ? <button className={styles.danger} disabled={acknowledgedRevision !== row.revision || workspace.pending || !row.preview.length || row.preview.some(target => target.current === false)} onClick={() => void command("confirm")}><Trash2 size={14} />确认删除所选资料</button> : null}{privacyActive(row.status) || row.status === "preview" ? <button disabled={workspace.pending} onClick={() => void command("cancel")}>取消此任务</button> : null}{["partial", "failed", "canceled"].includes(row.status) && row.completed < row.total ? <button className={styles.primary} disabled={workspace.pending} onClick={() => void command("retry")}>{row.kind === "erase" ? "重新预览剩余资料" : "重试未完成项"}</button> : null}</footer>
    </>}
  </Dialog>;
}

function OperationHistory({ ownerId, onClose, onSelect }: { ownerId: string; onClose: () => void; onSelect: (id: string) => void }) {
  const [page, setPage] = useState(1);
  const workspace = usePersistentWorkspace<PrivacyOperations>(`${operationPath()}?page=${page}`, ownerId, data => data.results.some(row => privacyActive(row.status)) ? 2500 : null);
  return <Dialog open onRequestClose={onClose} className={styles.dialog} aria-labelledby="privacy-history-title"><header><h2 id="privacy-history-title">资料操作历史</h2><button aria-label="关闭历史" onClick={onClose}><X size={18} /></button></header>{workspace.error ? <div className={styles.error} role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取</button></div> : null}{workspace.data ? <>{workspace.data.results.length ? workspace.data.results.map(row => <OperationStrip key={row.id} operation={row} onOpen={() => onSelect(row.id)} />) : <p className={styles.emptyList}>暂无导出或删除任务。</p>}<div className={styles.pagination}><span>共 {workspace.data.count} 项</span><button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button disabled={!workspace.data.next} onClick={() => setPage(value => value + 1)}>下一页</button></div></> : <p role="status">正在读取历史…</p>}</Dialog>;
}

function ExportFormatChoice({ value, onChange, disabled }: { value: PrivacyExportFormat; onChange: (format: PrivacyExportFormat) => void; disabled: boolean }) {
  const fieldId = useId();
  const [folderSupported, setFolderSupported] = useState(false);
  useEffect(() => { queueMicrotask(() => setFolderSupported(canExportFolder())); }, []);
  return <fieldset className={styles.formats} disabled={disabled}><legend>输出格式</legend>
    {([["zip", "ZIP 压缩包（推荐）"], ["folder", "单独文件夹"], ["csv", "CSV（便于进一步处理）"], ["json", "JSON"]] as const).map(([key, label]) => <label key={key}><input type="radio" name={fieldId} checked={value === key} disabled={key === "folder" && !folderSupported} onChange={() => onChange(key)} />{label}</label>)}
    {!folderSupported ? <small>当前浏览器或连接不支持直接选择文件夹；ZIP 解压后保留同样的分类目录。</small> : value === "folder" ? <small>下载时选择保存位置，每次创建新目录。部分保存会保留已写文件并提示，不覆盖已有资料。</small> : null}
  </fieldset>;
}
