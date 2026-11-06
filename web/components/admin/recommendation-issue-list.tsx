"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { FileText, Plus, Search } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { adminListHref } from "@/lib/admin-route-context";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { IssuePage } from "@/lib/api/recommendation-issues.types";
import type { components } from "@/lib/api/generated/schema";
import { RecommendationsAdmin } from "@/components/knowledge-admin";
import { Dialog } from "@/components/ui/dialog";
import { RecycleControl } from "./recycle-control";
import { PrivateMediaImage } from "./media/media-crop";
import { useCatalogCommand } from "./workflow/use-intake-command";
import styles from "./article-directory.module.css";

const scopes = [["all", "全部文章"], ["unassigned", "未归组"], ["mine", "我创建的"], ["draft", "待发布修改"], ["published", "已公开"], ["scheduled", "已排期"]];
const kinds = { article: "策划文章", research: "研究论文", exhibition: "原文展览" };
const date = (value?: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚未安排";
const createPath = "/catalog/admin/recommendation-issues/create/";
type ProposalPreview = components["schemas"]["IssueProposalPreview"];
type Creation = { title: string; kind: keyof typeof kinds; proposal?: { id: string; expected_revision: number; preview_hash: string } };
type Receipt = { owner_id: string; request_id: string; state: "applied" | "cancelled"; next_url: string; issue_id: string | null; available: boolean };
type Directory = IssuePage & { page: number; pages: number };

export function RecommendationIssueList({ initialTab = "issues" }: { initialTab?: "issues" | "placements" }) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0), params = useSearchParams();
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <ArticleDirectory key={`${user.id}:${epoch}:${initialTab}:${params.get("proposal") || ""}`} owner={String(user.id)} home={initialTab === "placements"} canEdit={hasAdminCapability(user, "can_edit_metadata")} canReview={hasAdminCapability(user, "can_review_candidate")} /> : <p role="status">正在核对编辑账户…</p>;
}

function ArticleDirectory({ owner, home, canEdit, canReview }: { owner: string; home: boolean; canEdit: boolean; canReview: boolean }) {
  const params = useSearchParams(), router = useRouter(), pathname = usePathname();
  const proposalId = !home ? params.get("proposal") || "" : "";
  const validProposal = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(proposalId);
  const scope = scopes.some(([key]) => key === params.get("scope")) ? params.get("scope")! : "all";
  const query = params.get("q") || "", page = params.get("page") || "1";
  const load = useCallback((url: string, signal: AbortSignal) => apiRequest<Directory>(url, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const resource = usePersistentWorkspace<Directory>(home ? "" : `/catalog/admin/recommendation-issues/?${new URLSearchParams({ q: query, page, scope })}`, owner, undefined, load);
  const loadProposal = useCallback((url: string, signal: AbortSignal) => apiRequest<ProposalPreview>(url, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const proposalResource = usePersistentWorkspace<ProposalPreview>(validProposal && canEdit && canReview ? `/catalog/admin/recommendation-issues/proposals/${proposalId}/` : "", owner, undefined, loadProposal);
  const proposal = proposalResource.error ? null : proposalResource.data;
  const data = resource.data, selectedId = params.get("article") || data?.results[0]?.id;
  const selected = data?.results.find(row => row.id === selectedId);
  const [open, setOpen] = useState(false), [title, setTitle] = useState(""), [kind, setKind] = useState<Creation["kind"]>("article"), [message, setMessage] = useState("");
  const [confirmedHash, setConfirmedHash] = useState("");
  const command = useCatalogCommand<Creation, Receipt>(owner, createPath, `stl-article-create:${owner}`, row => row.available ? Boolean(row.issue_id && row.next_url === `/admin/recommendations/issues/${row.issue_id}`) : row.available === false && row.issue_id === null && row.next_url === "");
  const locked = !canEdit || !command.ready || command.busy || Boolean(command.recovery);
  const proposalLocked = Boolean(proposalId && (!validProposal || !canReview || !proposal || proposal.already_created || proposal.review_state === "declined"));
  useUnsavedForm(Boolean(title.trim() || command.recovery), false);
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, params.toString(), values));
  function accept(result: Receipt | null) {
    if (!result) return;
    if (result.state === "cancelled") { setMessage("尚未执行的新建请求已停止，标题仍保留。"); return; }
    if (!result.available) { setTitle(""); setOpen(false); setMessage("原文章已创建，但目前已回收或不在当前项目可见范围。请联系项目负责人核对，勿重复创建同一文章。"); resource.reload(); return; }
    setTitle(""); setOpen(false); router.push(result.next_url);
  }
  function close() { if (!command.busy) setOpen(false); }
  function search(event: FormEvent<HTMLFormElement>) { event.preventDefault(); change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() || null, page: 1, article: null }); }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked || proposalLocked || proposalId && (!proposal || confirmedHash !== proposal.preview_hash)) return;
    void command.send({ title: title.trim(), kind, ...(proposalId && proposal ? { proposal: { id: proposalId, expected_revision: proposal.expected_revision, preview_hash: proposal.preview_hash } } : {}) }).then(accept);
  }
  return <main className={styles.page}>
    <nav className={styles.breadcrumb} aria-label="当前位置"><Link href="/admin/recommendations">策划项目与文章管理</Link><span>› {home ? "首页推荐编排" : "文章目录与归档"}</span></nav>
    <header className={styles.heading}><div><h1>{home ? "首页推荐编排" : "文章目录与归档"}</h1><p>{home ? "维护首页学者、主题和阅读内容的选择与顺序。" : "从现有文章继续编辑，保留项目归属、公开版本和历史记录。"}</p></div><div className={styles.actions}><Link href="/admin/recommendations">返回策划项目</Link>{home ? <Link href="/home" target="_blank" rel="noopener noreferrer">查看当前公开首页</Link> : canEdit ? <button className={styles.primary} disabled={locked || proposalLocked} onClick={() => setOpen(true)}><Plus size={15} />{proposalId ? "按提案建立草稿" : "新建文章"}</button> : null}</div></header>
    <nav className={styles.tabs} aria-label="内容管理范围"><Link aria-current={!home ? "page" : undefined} href="/admin/recommendations?view=legacy">文章目录</Link><Link aria-current={home ? "page" : undefined} href="/admin/recommendations?view=home">首页编排</Link></nav>
    {message || command.error ? <p className={styles.notice} role={command.error ? "alert" : "status"}>{command.error || message}</p> : null}
    {command.recovery ? <aside className={styles.notice}><p>上次新建结果尚未确认。先查询原请求，避免重复创建；停止时若文章已创建，会返回原文章。</p><div className={styles.actions}><button disabled={command.busy} onClick={() => void command.lookup().then(accept)}>查询原文章</button>{command.canRetry ? <button disabled={command.busy} onClick={() => void command.send().then(accept)}>重试原请求</button> : null}<button disabled={command.busy} onClick={() => void command.lookup(true).then(accept)}>停止尚未执行的请求</button></div></aside> : null}
    {proposalId ? <section className={styles.proposal} aria-labelledby="proposal-scope-title"><div className={styles.actions}><h2 id="proposal-scope-title">策划提案接手范围</h2>{validProposal ? <Link href={`/account/sharing/${proposalId}`}>返回原提案评阅</Link> : null}<Link href="/admin/recommendations?view=legacy">退出提案接手</Link></div>
      {!validProposal ? <p role="alert">提案地址不完整，请从原分享记录重新进入。</p> : !canReview || !canEdit ? <p role="alert">接手提案需要策划审核和文章编辑权限。</p> : proposalResource.error ? <p role="alert">{proposalResource.error}<button disabled={command.busy} onClick={proposalResource.reload}>重新核对提案</button></p> : !proposal ? <p role="status">正在核对提案授权和公开版本…</p> : <>
        <p>本次所选 {proposal.selected_material_count} 项材料对应 {proposal.materials.length} 个公开版本；同版本的重复引用只列一次。草稿会加入下列书目，文章标题由编辑另行填写。</p>
        {proposal.materials.length ? <ol className={styles.proposalItems}>{proposal.materials.map(item => <li key={item.edition_id}><Link href={item.href} target="_blank" rel="noopener noreferrer">{item.title}</Link><span>{item.authors.join("、") || "署名待补"}{item.version_note ? ` · ${item.version_note}` : ""}</span></li>)}</ol> : <p>提案没有选择公开书目，可建立空白文章草稿，继续在原提案中讨论选题。</p>}
        <p className={styles.muted}>保留在原提案中，不写入文章：{proposal.excluded.join("、")}。提案撤回、到期或原内容变化后停止交付；已选入草稿的公开书目由原文章编辑和发布流程管理。</p>
        {proposal.already_created ? proposal.issue_id && proposal.next_url === `/admin/recommendations/issues/${proposal.issue_id}` ? <Link className={styles.primary} href={proposal.next_url}>继续已有文章草稿</Link> : <p role="status">此提案已经建立文章，目前已回收或不在你的项目可见范围。请联系项目负责人核对，不会重复建立。</p> : proposal.review_state === "declined" ? <p role="status">提案目前为未采用，请先返回原提案恢复策划讨论状态。</p> : <p className={styles.muted}>只建立未公开草稿。后续发布仍需完整预览与发布检查。</p>}
        <button disabled={command.busy} onClick={() => { setConfirmedHash(""); proposalResource.reload(); }}>重新核对入编范围</button>
      </>}
    </section> : null}
    {home ? <div className={styles.home}><RecommendationsAdmin embedded /></div> : <>
      <nav className={styles.filters} aria-label="文章范围">{scopes.map(([key, label]) => <button key={key} aria-pressed={scope === key} onClick={() => change({ scope: key, page: 1, article: null })}>{label}</button>)}</nav>
      {resource.error ? <p className={styles.notice} role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}
      <div className={styles.columns}><section className={styles.directory} aria-label="文章目录"><form className={styles.search} onSubmit={search}><Search size={16} /><input key={query} name="q" defaultValue={query} maxLength={200} placeholder="搜索文章标题…" aria-label="搜索文章标题" /><button>查找</button></form>
        {resource.loading ? <p role="status">正在读取可见文章…</p> : null}
        {data ? <><p className={styles.muted}>{data.count} 篇符合条件的文章</p><div className={styles.cards}>{data.results.map(row => <button key={row.id} aria-pressed={selectedId === row.id} onClick={() => change({ article: row.id })}><span><strong>{row.title}</strong><small>{row.introduction || "尚未填写简介"}</small><em>{row.is_public ? "已公开" : "未公开"}{row.has_unpublished_changes ? " · 有待发布修改" : ""}</em><small>{row.project_title || "未归组文章"}</small></span><span className={styles.cover}>{row.cover_url ? <PrivateMediaImage owner={owner} path={row.cover_url} alt="文章封面" /> : <FileText size={26} />}</span></button>)}</div>{!data.count ? <p className={styles.empty}>当前范围没有文章，可调整筛选或新建文章。</p> : null}<nav className={styles.pagination} aria-label="文章分页"><button disabled={data.page <= 1 || resource.loading} onClick={() => change({ page: data.page - 1, article: null })}>上一页</button><span>{data.page}/{data.pages}</span><button disabled={data.page >= data.pages || resource.loading} onClick={() => change({ page: data.page + 1, article: null })}>下一页</button></nav></> : null}
      </section><section className={styles.inspector} aria-label="所选文章">{selected ? <><div className={styles.articleTop}><span>{kinds[selected.article_metadata?.kind || "article"]}</span><span>{selected.is_public ? "已公开" : "未公开"}</span>{selected.has_unpublished_changes ? <span>草稿待发布</span> : null}</div><h2>{selected.title}</h2><p className={styles.introduction}>{selected.introduction || "尚未填写文章简介。"}</p><dl className={styles.facts}><div><dt>所属项目</dt><dd>{selected.project_id ? <Link href={`/admin/recommendations?project=${selected.project_id}`}>{selected.project_title || "查看项目"}</Link> : "未归组，可在项目中加入已有文章"}</dd></div><div><dt>公开署名</dt><dd>{selected.public_byline || "尚未署名"}</dd></div><div><dt>最近保存</dt><dd>{selected.saved_at ? date(selected.saved_at) : "尚未记录"}{selected.saved_by ? ` · ${selected.saved_by}` : ""}</dd></div><div><dt>展示日期</dt><dd>{date(selected.display_from)}</dd></div><div><dt>已保存内容</dt><dd>{selected.body_blocks.length} 个正文区块 · {selected.items.length} 项附录材料</dd></div></dl>{selected.project_archived ? <p className={styles.notice}>所属项目已归档，恢复项目后才能继续修改；公开状态单独管理。</p> : null}<div className={styles.actions}><Link className={styles.primary} href={`/admin/recommendations/issues/${selected.id}`}>{canEdit && !selected.project_archived ? "继续编辑文章" : "查看文章与历史"}</Link><Link href={`/admin/recommendations/issues/${selected.id}/preview`}>预览与发布检查</Link>{selected.is_public ? <Link href={`/recommendations/${selected.slug}`} target="_blank" rel="noopener noreferrer">查看当前公开版</Link> : null}</div><p className={styles.muted}>正文草稿、公开版本和排期分别保留。项目中的团队权限仍适用于这里的文章。</p>{canEdit ? <div className={styles.recycle}><RecycleControl kind="recommendation-issue" id={selected.id} name={selected.title} disabled={Boolean(selected.project_archived)} onDeleted={resource.reload} /></div> : null}</> : <div className={styles.empty}><FileText size={32} /><h2>选择文章继续工作</h2><p>从目录中选择一篇文章，查看保存状态、项目归属和发布入口。</p></div>}</section></div>
      {data ? <details className={styles.schedule}><summary>当前公开推荐与已确认排期</summary><p>{data.current ? <Link href={`/recommendations/${data.current.slug}`}>当前公开推荐：{data.current.title}</Link> : "尚无生效的本期推荐。"}</p>{data.upcoming?.length ? <ul>{data.upcoming.map(row => <li key={row.id}><Link href={`/admin/recommendations/issues/${row.id}`}>{row.title}</Link><span> · {date(row.display_from)}</span></li>)}</ul> : <p>暂无已确认的后续排期。</p>}<p className={styles.muted}>后续修改不会自动替换已确认的排期修订。首页学者与主题名单可从“首页编排”维护。</p></details> : null}
    </>}
    <Dialog open={open} onRequestClose={close} className={styles.dialog} aria-labelledby="article-create-title"><h2 id="article-create-title">{proposalId ? "从提案建立文章草稿" : "新建文章"}</h2><p>先建立独立草稿，之后可加入已有策划项目。</p><form onSubmit={create} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }}><label>文章标题<input autoFocus required maxLength={600} value={title} disabled={Boolean(command.recovery) || command.busy} onChange={event => setTitle(event.target.value)} /></label><label>内容类型<select value={kind} disabled={Boolean(command.recovery) || command.busy} onChange={event => setKind(event.target.value as Creation["kind"])}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>{proposalId ? <><p>只加入本次核对的 {proposal?.materials.length ?? 0} 个公开书目版本。私人问题、笔记、材料摘录和附言留在原提案中评阅。</p><label className={styles.proposalConfirm}><input type="checkbox" disabled={locked || proposalLocked} checked={Boolean(proposal && confirmedHash === proposal.preview_hash)} onChange={event => setConfirmedHash(event.target.checked && proposal ? proposal.preview_hash : "")} />我已核对入编范围，建立未公开草稿</label>{proposalLocked ? <p role="alert">提案范围或状态已变化，请返回页面重新核对。</p> : null}</> : null}{command.error ? <p role="alert">{command.error}</p> : null}{command.recovery ? <p>请关闭此弹层，从页面上的原请求入口核对结果。</p> : null}<div className={styles.actions}><button type="button" disabled={command.busy} onClick={close}>返回并保留填写</button><button className={styles.primary} disabled={locked || proposalLocked || !title.trim() || Boolean(proposalId && confirmedHash !== proposal?.preview_hash)}>{command.busy ? "正在建立…" : "建立草稿并编辑"}</button></div></form></Dialog>
  </main>;
}
