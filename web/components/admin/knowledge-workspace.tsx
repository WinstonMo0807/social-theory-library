"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, Plus, PanelRightOpen, Search } from "lucide-react";
import { apiStreamRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { confirmAction } from "@/lib/ui-dialog";
import type { IssueBlock } from "@/lib/api/recommendation-issues.types";
import { IssueTextEditor } from "./curation/issue-text-editor";
import { KnowledgePageContent, type KnowledgePageData, type KnowledgeBlock } from "@/components/public/knowledge-page-content";
import { EvidencePanel, KnowledgeNavigation, knowledgeCall, type LibrarySource, type SourceLocator } from "./knowledge-workbench";
import { KnowledgeAssertionEditor, type EditableAssertion } from "./knowledge-assertion-editor";
import { AcademicRelations } from "./academic-relations";
import { KnowledgeSearch } from "./knowledge-search";
import s from "./knowledge-workbench.module.css";

type Ref = { type: string; id: string; edition_id?: string };
type Block = KnowledgeBlock & { type: IssueBlock["type"]; text: string; style?: "paragraph" | "heading"; heading_level?: 1 | 2 | 3; human_edited?: boolean };
type PageRow = { id: string; title: string; kind: string; status: string; has_draft: boolean; changed_blocks: number; work_id?: string; updated_at: string };
type Workspace = KnowledgePageData & { metadata_hash: string; kind: string; work_id?: string; entity_id?: string; public_url?: string; blocks: Block[]; block_hashes: Record<string, string>;
  dependencies: { block_id: string; source_type: string; source_id: string; stale: boolean }[]; references: (Ref & { title: string; locator?: SourceLocator; unavailable?: boolean })[];
  backlinks: { page_id: string; title: string; block_id: string }[]; revisions: { id: string; revision: number; status: string; created_at: string }[];
  assertion_hashes: Record<string, string>; pending_changesets: { id: string; origin: string; status: string }[] };
const kinds: Record<string, string> = { work: "作品", person: "人物", concept: "概念", school: "理论流派", tradition: "理论传统", theory_school: "理论流派", topic: "主题", discipline: "学科", special: "专题" };
const date = (value: string) => new Date(value).toLocaleString("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function KnowledgeWorkspace() {
  const query = useSearchParams();
  if (query.get("search") === "1") return <KnowledgeSearch />;
  return query.get("relations") === "1" ? <><KnowledgeNavigation active="pages" /><AcademicRelations /></> : <PageWorkspace />;
}

function PageWorkspace() {
  const query = useSearchParams(), router = useRouter(), pageId = query.get("page") || "", work = query.get("work_id") || "", incomingAnchor = query.get("anchor") || "";
  const [directory, setDirectory] = useState<{ pages: PageRow[]; count: number } | null>(null), [filter, setFilter] = useState(""), [search, setSearch] = useState(""), [state, setState] = useState(""), [kind, setKind] = useState(""), [offset, setOffset] = useState(0);
  const [data, setData] = useState<Workspace | null>(null), [blocks, setBlocks] = useState<Block[]>([]), [selected, setSelected] = useState(""), [perspective, setPerspective] = useState("proposed");
  const [sources, setSources] = useState<LibrarySource[]>([]), [revision, setRevision] = useState(query.get("revision") || ""), [availableAnchor, setAvailableAnchor] = useState<SourceLocator | null>(null);
  const [locator, setLocator] = useState<SourceLocator | null>(null), [evidenceOpen, setEvidenceOpen] = useState(false), [reason, setReason] = useState("");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [notice, setNotice] = useState(""), [attempt, setAttempt] = useState(0), [submitted, setSubmitted] = useState("");
  const [entityQuery, setEntityQuery] = useState(""), [entities, setEntities] = useState<{ id: string; label: string; kind: string; definition?: string }[]>([]);
  const [metadata, setMetadata] = useState({ title: "", scope: "" });
  const [newAssertion, setNewAssertion] = useState(query.get("new_assertion") === "1");
  const request = useRef<{ signature: string; id: string } | null>(null), editor = useRef<HTMLDivElement>(null);
  const source = sources.find(v => v.revision_id === revision), current = blocks.find(v => v.id === selected);
  const baseline = { blocks: data?.blocks || [], title: data?.title || "", scope: data?.scope || "" };
  const dirty = useUnsavedForm(submitted ? baseline : { blocks, ...metadata }, baseline);
  useEffect(() => {
    const c = new AbortController(); setError("");
    if (pageId) {
      setData(null); setSubmitted("");
      void knowledgeCall<Workspace>(`/knowledge/pages/${pageId}/workspace/`, undefined, c.signal).then(r => { setData(r); setMetadata({ title: r.title || "", scope: r.scope || "" }); setBlocks(r.blocks); setSelected(r.blocks.find(b => b.references?.some(ref => ref.type === "assertion" && ref.id === query.get("assertion")))?.id || r.blocks[0]?.id || ""); }).catch(e => { if (!c.signal.aborted) setError(e.message); });
    } else {
      if (data) { setData(null); setMetadata({ title: "", scope: "" }); setBlocks([]); setSelected(""); setSubmitted(""); }
      setDirectory(null);
      void knowledgeCall<{ pages: PageRow[]; count: number }>(`/knowledge/workspace/?q=${encodeURIComponent(search)}&state=${state}&kind=${kind}&offset=${offset}`, undefined, c.signal).then(setDirectory).catch(e => { if (!c.signal.aborted) setError(e.message); });
    }
    return () => c.abort();
  }, [pageId, search, state, kind, offset, attempt]);
  useEffect(() => {
    const c = new AbortController();
    void knowledgeCall<{ sources: LibrarySource[] }>(`/search/sources/${work || data?.work_id ? `?work_id=${work || data?.work_id}` : ""}`, undefined, c.signal)
      .then(r => { setSources(r.sources); setRevision(old => old || (work || data?.work_id ? r.sources[0]?.revision_id : "") || ""); }).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [work, data?.work_id]);
  useEffect(() => {
    setAvailableAnchor(null); if (!incomingAnchor) return; const c = new AbortController();
    void knowledgeCall<SourceLocator>(`/knowledge/anchors/${incomingAnchor}/?preview=1`, undefined, c.signal).then(r => { setAvailableAnchor(r); setLocator(r); setRevision(r.document_revision_id); }).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [incomingAnchor]);
  async function action(fn: () => Promise<void>) { setBusy(true); setError(""); setNotice(""); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "操作未完成，请重试。"); } finally { setBusy(false); } }
  function update(patch: Partial<Block>) { setSubmitted(""); setBlocks(old => old.map(v => v.id === selected ? { ...v, ...patch } : v)); }
  function addBlock() {
    const id = createRequestKey(); setSubmitted(""); setBlocks(old => [...old, { id, type: "analysis", style: "paragraph", text: "", references: availableAnchor ? [{ type: "anchor", id: availableAnchor.anchor_id }] : source ? [{ type: "work", id: source.work_id, edition_id: source.edition_id }] : [] }]); setSelected(id);
  }
  function addReference(ref: Ref) { if (current) update({ references: [...(current.references || []).filter(v => v.id !== ref.id || v.type !== ref.type), ref] }); }
  async function openIdentity(body: { work_id?: string; entity_id?: string }) { await action(async () => { const r = await knowledgeCall<{ id: string }>("/knowledge/workspace/", body); router.push(`/admin/knowledge?page=${r.id}${revision ? `&revision=${revision}` : ""}`); }); }
  async function openSpecial() {
    await action(async () => {
      const signature = JSON.stringify(metadata);
      if (request.current?.signature !== signature) request.current = { signature, id: createRequestKey() };
      const r = await knowledgeCall<{ id: string }>("/knowledge/workspace/", { ...metadata, request_id: request.current.id });
      router.push(`/admin/knowledge?page=${r.id}`);
    });
  }
  async function submit() {
    if (!data) return;
    const original = new Map(data.blocks.map(v => [v.id, v])), after = new Set(blocks.map(v => v.id));
    const patches: Record<string, unknown>[] = blocks.filter(b => JSON.stringify(b) !== JSON.stringify(original.get(b.id))).map(b => ({ operation: original.has(b.id) ? "replace" : "add", block_id: b.id, base_hash: data.block_hashes[b.id], block: b, reason: reason || "人工编纂知识页" }));
    for (const block of data.blocks) if (!after.has(block.id)) patches.push({ operation: "delete", block_id: block.id, base_hash: data.block_hashes[block.id], reason: reason || "人工移除区块" });
    if (metadata.title !== data.title || metadata.scope !== (data.scope || "")) patches.push({ operation: "metadata", block_id: pageId,
      base_hash: data.metadata_hash, ...metadata, reason: reason || "人工修改知识页标题与范围" });
    if (!patches.length) return;
    await action(async () => {
      const signature = JSON.stringify({ revision, patches }); if (request.current?.signature !== signature) request.current = { signature, id: createRequestKey() };
      const result = await knowledgeCall<{ id: string }>(`/knowledge/pages/${pageId}/workspace/`, { document_revision_id: revision, patches, request_id: request.current.id });
      setSubmitted(result.id); setNotice("修改已进入审核队列，尚未改变公开页面。请继续核对来源、保存已审核草稿并发布。");
    });
  }
  async function publish() {
    if (!data?.revision_id || dirty || !await confirmAction(`发布《${data.title}》当前已保存的知识页修订？此操作也会发布该页引用且已审核保存的陈述。${data.publication_scope?.withdrawals?.length ? `同时撤回 ${data.publication_scope.withdrawals.length} 条陈述。` : ""}${data.publication_scope?.entities.length ? `同时发布已审核的新身份：${data.publication_scope.entities.map(v => v.label).join("、")}。` : ""}`, { title: "发布知识页", confirmLabel: "发布当前修订" })) return;
    await action(async () => { await knowledgeCall(`/knowledge/pages/${pageId}/`, { revision_id: data.revision_id }); setAttempt(v => v + 1); setNotice("当前知识页已发布。"); });
  }
  async function exportMarkdown() {
    await action(async () => {
      const response = await apiStreamRequest(`/knowledge/pages/${pageId}/export/?preview=1`, { cache: "no-store" }, getServerSessionCredential());
      if (!response.ok) throw new Error(`导出未完成（${response.status}），请重新读取当前修订。`);
      const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
      link.href = url; link.download = `knowledge-${pageId}.md`; link.click(); URL.revokeObjectURL(url);
    });
  }
  const references = [...(data?.references || []), ...(availableAnchor && !data?.references.some(v => v.id === availableAnchor.anchor_id) ? [{ type: "anchor", id: availableAnchor.anchor_id, title: `原文 · PDF ${availableAnchor.segments.map(v => v.page_number).join("、")}`, locator: availableAnchor }] : [])];
  return <div className={s.workbench}>
    <header className={s.heading}><div><h1>{data?.title || "知识编纂"}</h1><p>{data ? `${kinds[data.kind] || data.kind}知识页 · ${data.status === "published" ? "已发布" : "草稿"}` : "让文献中的观点成为有来源、可修订的知识页面。"}</p></div>{data?.public_url && <Link className={s.buttonLink} target="_blank" href={data.public_url}>公开展示位置 <ArrowUpRight size={15} /></Link>}</header>
    <KnowledgeNavigation active="pages" workId={data?.work_id || work} revisionId={revision} /><div className={s.toolbar}><Link href="/admin/knowledge?relations=1">管理学术陈述与关系</Link><Link href="/admin/knowledge?search=1">检索已发布知识</Link></div>
    {error && <div className={s.error} role="alert">{error} <button onClick={() => setAttempt(v => v + 1)}>重新读取</button></div>}
    {notice && <div className={s.notice} role="status">{notice}{submitted && <p><Link href={`/admin/intelligence?changeset=${submitted}&work_id=${source?.work_id || ""}`}>进入审核与发布 →</Link></p>}</div>}
    {!pageId ? <>
      <form className={s.toolbar} onSubmit={e => { e.preventDefault(); setSearch(filter); setOffset(0); }}><label>查找知识页<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="作品、人物、概念或主题" /></label><select aria-label="知识页类型" value={kind} onChange={e => { setKind(e.target.value); setOffset(0); }}><option value="">全部类型</option>{Object.entries(kinds).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select><select aria-label="知识页状态" value={state} onChange={e => { setState(e.target.value); setOffset(0); }}><option value="">全部状态</option><option value="draft">草稿</option><option value="published">已发布</option><option value="stale">来源有更新</option></select><button><Search size={16} />查找</button></form>
      <div className={s.tableWrap}><table className={s.table}><thead><tr><th>知识页</th><th>类型</th><th>编辑状态</th><th>来源变化</th><th>最近编辑</th></tr></thead><tbody>{directory?.pages.map(p => <tr key={p.id}><td><Link href={`/admin/knowledge?page=${p.id}`}>{p.title}</Link></td><td data-label="类型">{kinds[p.kind] || p.kind}</td><td data-label="编辑状态">{p.status === "published" ? "已发布" : "草稿"}{p.has_draft ? " · 有编辑稿" : ""}</td><td data-label="来源变化">{p.changed_blocks ? `${p.changed_blocks} 处待核对` : "无已记录变化"}</td><td data-label="最近编辑">{date(p.updated_at)}</td></tr>)}</tbody></table></div>
      {directory ? !directory.count && <p className={s.empty}>没有符合筛选的知识页。可以从下方作品或实体开始编纂。</p> : !error && <p className={s.empty} role="status">正在读取知识页…</p>}
      {!!directory?.count && <div className={s.toolbar}><button disabled={!offset} onClick={() => setOffset(v => Math.max(0, v - 30))}>上一页</button><span>{offset + 1}—{Math.min(offset + 30, directory.count)} / {directory.count}</span><button disabled={offset + 30 >= directory.count} onClick={() => setOffset(v => v + 30)}>下一页</button></div>}
      <section className={s.preview}><h2>开始编纂</h2><div className={s.toolbar}><label>从馆藏版本选择<select value={revision} onChange={e => setRevision(e.target.value)}><option value="">选择作品</option>{sources.map(v => <option key={v.revision_id} value={v.revision_id}>{v.title} · {v.edition_label || `修订 ${v.revision_number}`}</option>)}</select></label><button disabled={busy || !source} onClick={() => source && void openIdentity({ work_id: source.work_id })}>打开作品知识页</button></div>
        <form className={s.toolbar} onSubmit={e => { e.preventDefault(); void action(async () => setEntities((await knowledgeCall<{ entities: typeof entities }>(`/knowledge/entities/?preview=1&q=${encodeURIComponent(entityQuery)}`)).entities)); }}><label>从规范身份选择<input value={entityQuery} onChange={e => setEntityQuery(e.target.value)} placeholder="人物、概念或其他实体" required /></label><button disabled={busy}>查找身份</button></form>
        {entities.map(v => <button className={s.result} key={v.id} onClick={() => void openIdentity({ entity_id: v.id })}><span>{kinds[v.kind] || v.kind}</span><strong>{v.label}</strong><span>{v.definition || "打开该身份的知识页"}</span></button>)}
        <details data-disclosure="collection"><summary>创建跨著作专题</summary><form className={s.editor} onSubmit={e => { e.preventDefault(); void openSpecial(); }}>
          <label>专题标题<input required maxLength={600} value={metadata.title} onChange={e => setMetadata(v => ({ ...v, title: e.target.value }))} /></label>
          <label>编纂范围<textarea required maxLength={6000} value={metadata.scope} onChange={e => setMetadata(v => ({ ...v, scope: e.target.value }))} placeholder="说明问题、纳入的作品与边界" /></label>
          <button className={s.primary} disabled={busy}>创建专题草稿</button></form></details>
      </section>
    </> : !data ? !error && <p role="status" className={s.empty}>正在读取正文、来源与修订…</p> : <>
      <div className={s.toolbar}><Link href="/admin/knowledge"><ArrowLeft size={15} />全部知识页</Link><button className={s.primary} disabled={busy || !dirty} onClick={() => void submit()}>提交修改并审核</button><button disabled={busy || dirty || data.status === "published" || !data.revision_id} onClick={() => void publish()}>发布已保存稿</button><button disabled={busy || dirty || !data.revision_id} onClick={() => void exportMarkdown()}>导出 Markdown</button><button className={s.mobileOnly} onClick={() => setEvidenceOpen(true)}><PanelRightOpen size={16} />核对证据</button></div>
      <details data-disclosure="collection"><summary>编辑标题与编纂范围</summary><div className={s.editor}>
        <label>知识页标题<input maxLength={600} value={metadata.title} onChange={e => { setSubmitted(""); setMetadata(v => ({ ...v, title: e.target.value })); }} /></label>
        <label>编纂范围<textarea maxLength={6000} value={metadata.scope} onChange={e => { setSubmitted(""); setMetadata(v => ({ ...v, scope: e.target.value })); }} /></label>
        <div className={s.preview} aria-label="页面信息预览"><h2>{metadata.title}</h2><p>{metadata.scope}</p></div>
      </div></details>
      <div className={s.workspace}>
        <aside className={s.rail}><h2>页面区块</h2>{blocks.map((b, i) => <button key={b.id} aria-current={selected === b.id} onClick={() => setSelected(b.id)}>{i + 1}. {b.text.slice(0, 42) || "未填写正文"}<small>{b.human_edited ? "人工编辑" : "来源编纂"}{data.dependencies.some(d => d.block_id === b.id && d.stale) ? " · 来源有更新" : ""}</small></button>)}<button onClick={addBlock}><Plus size={15} />新增区块</button>
          {!!data.pending_changesets.length && <><h2>待审核修改</h2>{data.pending_changesets.map(v => <Link key={v.id} href={`/admin/intelligence?changeset=${v.id}`}>{v.origin === "human" ? "人工编纂" : "编纂建议"} →</Link>)}</>}
        </aside>
        <main className={s.main}>
          <div className={s.toolbar}><button onClick={() => setNewAssertion(v => !v)}>{newAssertion ? "收起陈述编辑" : "新增学术陈述"}</button></div>
          {newAssertion && <KnowledgeAssertionEditor key={`new-${data.id}`} pageId={data.id} title={data.title || ""} subjectEntity={data.entity_id} subjectWork={data.work_id} anchor={availableAnchor || undefined} />}
          {data.assertions.filter(a => current?.references?.some(r => r.type === "assertion" && r.id === a.id)).map(a => <KnowledgeAssertionEditor key={a.id} pageId={data.id} title={data.title || ""} initial={a as EditableAssertion} baseHash={data.assertion_hashes[a.id]} />)}
          {current ? <div ref={editor}><div className={s.sectionBar}><h2>编辑区块</h2><button onClick={() => { setSubmitted(""); setBlocks(old => old.filter(v => v.id !== current.id)); setSelected(""); }}>移除区块</button></div>
            {current.type === "analysis" && <label>展示方式<select value={current.style || "paragraph"} onChange={e => update({ style: e.target.value as "paragraph" | "heading", heading_level: e.target.value === "heading" ? 1 : undefined })}><option value="paragraph">解释正文</option><option value="heading">章节标题</option></select></label>}
            {!current.references?.some(r => r.type === "assertion") && <IssueTextEditor key={current.id} block={{ ...current, references: undefined }} label="区块正文" onChange={patch => update(patch as Partial<Block>)} maxLength={6000} />}
            {current.type === "analysis" && <><h3>本区块的依据</h3><ul className={s.sourceRefs}>{(current.references || []).map(ref => <li key={`${ref.type}:${ref.id}`}><span>{references.find(v => v.id === ref.id)?.title || (ref.type === "work" ? sources.find(v => v.work_id === ref.id && (!ref.edition_id || v.edition_id === ref.edition_id))?.title : undefined) || `${ref.type} · ${ref.id.slice(0, 8)}`}</span><button onClick={() => update({ references: current.references?.filter(v => v !== ref) })}>移出依据</button></li>)}</ul>
              {references.map(ref => <div key={`${ref.type}:${ref.id}`} className={s.toolbar}><span className={s.muted}>{ref.title}</span>{ref.locator && <button onClick={() => { setLocator(ref.locator!); setEvidenceOpen(true); }}>核验原文</button>}<button disabled={current.references?.some(v => v.id === ref.id && v.type === ref.type)} onClick={() => addReference({ type: ref.type, id: ref.id, ...(ref.edition_id ? { edition_id: ref.edition_id } : {}) })}>用作依据</button></div>)}
              <Link target="_blank" href={`/admin/sources?revision=${revision}&page=${pageId}`}>在原文工作区选取更多证据 <ArrowUpRight size={14} /></Link>
            </>}
          </div> : <p className={s.empty}>选择左侧区块开始编辑，或新增一个有来源的解释区块。</p>}
          <section className={s.preview} aria-label="知识页实时预览"><div className={s.sectionBar}><h3>展示效果</h3><div className={s.segmented}><button aria-pressed={perspective === "current"} onClick={() => setPerspective("current")}>当前内容</button><button aria-pressed={perspective === "proposed"} onClick={() => setPerspective("proposed")}>修改后</button></div></div>
            <p className={s.muted}>{data.kind === "work" ? "作品页 / 研究资料 / 知识导读" : `${kinds[data.kind] || data.kind}详情 / 知识导读`}</p>
            <KnowledgePageContent page={{ ...data, anchors: [...(data.anchors || []), ...(availableAnchor ? [{ anchor_id: availableAnchor.anchor_id, locator: availableAnchor }] : [])], blocks: perspective === "current" ? data.blocks : blocks }} renderBlock={(block, content) => <div key={block.id} className={block.id === selected ? s.selectedBlock : undefined} role="button" tabIndex={0} aria-label="编辑此区块" onClick={() => { setSelected(block.id); editor.current?.scrollIntoView({ behavior: "instant", block: "nearest" }); }} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(block.id); } }}>{content}</div>} />
          </section>
          <div className={s.toolbar}><label>本次依据的正文修订<select value={revision} onChange={e => setRevision(e.target.value)}><option value="">人工编纂（无指定正文修订）</option>{sources.map(v => <option key={v.revision_id} value={v.revision_id}>{v.title} · 修订 {v.revision_number}</option>)}</select></label></div>
          <label>修改说明<input value={reason} onChange={e => setReason(e.target.value)} placeholder="说明这次增补或修改的依据" /></label>
          {data.publication_scope?.withdrawals?.map(v => <p key={v.id} className={s.notice}>将撤回：{v.text} · {v.reason}</p>)}
          {!!data.publication_scope?.entities.length && <p className={s.notice}>本次发布还包含已审核的新身份：{data.publication_scope.entities.map(v => v.label).join("、")}。</p>}
          <details><summary>引用关系与修订</summary>{data.backlinks.map(v => <p key={`${v.page_id}:${v.block_id}`}><Link href={`/admin/knowledge?page=${v.page_id}`}>{v.title}</Link> 引用了此页</p>)}{!data.backlinks.length && <p className={s.muted}>尚无其他知识页引用此页。</p>}{data.dependencies.filter(v => v.stale).map((v, i) => <p key={i} className={s.notice}>区块 {blocks.findIndex(b => b.id === v.block_id) + 1} 的 {v.source_type} 来源有变化，请核对后更新。</p>)}{data.revisions.map(v => <p className={s.muted} key={v.id}>修订 {v.revision} · {v.status === "published" ? "已发布" : "草稿"} · {date(v.created_at)}</p>)}</details>
        </main>
        <EvidencePanel source={source} locator={locator} open={evidenceOpen} onClose={() => setEvidenceOpen(false)} />
      </div>
    </>}
  </div>;
}
