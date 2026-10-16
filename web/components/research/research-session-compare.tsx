"use client";

import Link from "next/link";
import { ArrowLeft, CircleAlert, Download, LoaderCircle, Pencil, Plus, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Dialog } from "@/components/ui/dialog";
import { exportResearchRecord, saveResearchComparison, updateResearchProject, type ComparisonCell, type ProjectData, type ResolvedEvidence } from "@/lib/api/research.client";
import { comparisonCellColumn, comparisonColumns, type ComparisonColumn } from "@/lib/api/research-comparison";
import { researchEvidenceKey, researchReaderHref } from "@/lib/api/research-evidence";
import { useResearchProject } from "./use-research-project";
import { ResearchCenterNav } from "./research-center-nav";

type Editor = { dimension: string; column: ComparisonColumn; original: string | null; note: string; ids: string[]; revision: number };
const cellIdentity = (cell: ComparisonCell) => JSON.stringify([cell.dimension, cell.column_id || "", cell.author || "", cell.reference_ids || [], cell.note || ""]);
const evidenceLabels = { selected: "原文证据", partial: "部分来源待核对", unavailable: "来源待核对", missing: "尚未选入证据" };

export function ResearchSessionCompare({ id }: { id: string }) {
  const workspace = useResearchProject(id);
  if (workspace.error || ["forbidden", "temporary_error"].includes(workspace.session.status)) return <Frame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>证据比较暂时不可用</h2><p>{workspace.error || workspace.session.message}</p><button onClick={workspace.refresh}><RefreshCw size={15} />重新读取</button></div></Frame>;
  if (!workspace.record) return <Frame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取证据比较……</p></div></Frame>;
  return <Comparison key={`${workspace.session.user?.id}:${id}`} workspace={workspace} />;
}

function Comparison({ workspace }: { workspace: ReturnType<typeof useResearchProject> }) {
  const { record, pending, run, refresh, notice, actionError } = workspace;
  const [dimensionOpen, setDimensionOpen] = useState(false);
  const [dimension, setDimension] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState("matrix");
  const [noteDraft, setNoteDraft] = useState<{ text: string; revision: number } | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!editor && !noteDraft) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [editor, noteDraft]);
  if (!record) return null;
  const dimensions = record.data.comparison?.dimensions || [];
  const cells = record.data.comparison?.cells || [];
  const selections = record.data.selections || [];
  const columns = comparisonColumns(selections, cells);
  const references = new Map(selections.map((ref) => [researchEvidenceKey(ref), ref]));
  const displayedDimensions = filter ? dimensions.filter((name) => name === filter) : dimensions;
  const editorColumn = editor ? columns.find((column) => column.id === editor.column.id) || { ...editor.column, references: [] } : null;
  const originalIndex = editor?.original ? cells.findIndex((cell) => cellIdentity(cell) === editor.original) : -1;
  const concurrentChange = !!editor?.original && originalIndex < 0;
  const validDimension = !!dimension.trim() && !dimensions.includes(dimension.trim()) && dimensions.length < 20;
  const gaps = dimensions.flatMap((name) => columns.filter((column) => !cells.some((cell) => cell.dimension === name && comparisonCellColumn(cell, columns) === column.id && cell.reference_ids?.some((refId) => references.get(refId)?.source_status === "available"))).map((column) => ({ dimension: name, column })));

  async function addDimension(event: FormEvent) {
    event.preventDefault();
    if (!record || !validDimension) return;
    const ok = await run(() => saveResearchComparison(record.id, { expected_revision: record.revision, dimensions: [...dimensions, dimension.trim()], cells }), "比较维度已保存。");
    if (ok) { setDimensionOpen(false); setDimension(""); }
  }
  function editCell(name: string, column: ComparisonColumn, cell?: ComparisonCell) {
    if (!record) return;
    setEditor({ dimension: name, column, original: cell ? cellIdentity(cell) : null, note: cell?.note || "", ids: cell?.reference_ids || [], revision: record.revision });
  }
  async function saveCell(event: FormEvent) {
    event.preventDefault();
    if (!record || !editor || !dimensions.includes(editor.dimension)) return;
    const previous = originalIndex >= 0 ? cells[originalIndex] : null;
    const columnId = previous?.column_id || (!editor.column.id.startsWith("retained:") ? editor.column.id : undefined);
    const cell: ComparisonCell = { dimension: editor.dimension, ...(columnId ? { column_id: columnId } : {}), author: previous?.author || editor.column.authors || "", reference_ids: editor.ids, note: editor.note.trim() };
    const next = [...cells];
    if (originalIndex >= 0) next[originalIndex] = cell; else next.push(cell);
    const ok = await run(() => saveResearchComparison(record.id, { expected_revision: record.revision, dimensions, cells: next }), concurrentChange ? "已另存比较笔记，同时保留其他位置的修改。" : "比较笔记已保存。你的判断与原文证据分别保留。");
    if (ok) setEditor(null);
  }
  async function exportComparison() {
    if (!record) return;
    await run(async () => {
      const payload = await exportResearchRecord<ProjectData>("research-projects", record.id);
      if (!alive.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `research-${record.id}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "已导出当前已保存的研究、证据身份与比较记录。");
  }
  return <Frame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href={`/account/research/${record.id}`}>持续研究</Link><span>/</span><strong>证据比较</strong></nav>
    <header className="stl4-research-heading"><h1>选材比较与证据矩阵</h1><p>沿研究维度并列核对文献，保留原文依据与自己的判断。</p><span className="stl4-research-privacy">仅本人可见</span></header>
    <section className="stl4-research-workspace stl4-research-compare-surface"><ResearchCenterNav active="research" />
      <div className="stl4-research-compare-head"><div><p className="stl4-research-kicker">当前研究</p><h2>{record.data.title || record.data.question || "未命名研究"}</h2></div><Link href={`/account/research/${record.id}`}><ArrowLeft size={14} />返回工作区</Link></div>
      <div className="stl4-comparison-tabs" role="tablist" aria-label="比较资料视图" onKeyDown={(event) => { const names = ["matrix", "sources", "draft", "gaps", "notes"]; const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0; if (!offset && event.key !== "Home" && event.key !== "End") return; event.preventDefault(); const next = event.key === "Home" ? names[0] : event.key === "End" ? names.at(-1)! : names[(names.indexOf(tab) + offset + names.length) % names.length]; setTab(next); document.getElementById(`comparison-tab-${next}`)?.focus(); }}>{[["matrix", "比较视图"], ["sources", `已选文献（${columns.filter((column) => column.references.length).length}）`], ["draft", "比较草稿"], ["gaps", `证据缺口（${gaps.length}）`], ["notes", "我的笔记"]].map(([value, label]) => <button key={value} id={`comparison-tab-${value}`} role="tab" tabIndex={tab === value ? 0 : -1} aria-selected={tab === value} aria-controls={`comparison-panel-${value}`} onClick={() => setTab(value)}>{label}</button>)}</div>
      <div className="stl4-research-compare-toolbar"><label>比较维度<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">全部维度</option>{dimensions.map((name) => <option key={name}>{name}</option>)}</select></label><div><button type="button" disabled={pending || dimensions.length >= 20} onClick={() => setDimensionOpen(true)}><Plus size={14} />添加维度</button><button disabled={pending} onClick={() => void exportComparison()}><Download size={14} />导出</button><button disabled={pending} onClick={refresh}><RefreshCw size={14} />刷新</button></div></div>
      {notice ? <p className="stl4-research-action-message" role="status">{notice}</p> : null}{actionError ? <p className="stl4-research-action-message is-error" role="alert">{actionError}</p> : null}
      <div id={`comparison-panel-${tab}`} role="tabpanel" aria-labelledby={`comparison-tab-${tab}`}>
      {tab === "matrix" ? dimensions.length && columns.length ? <div className="stl4-research-matrix" tabIndex={0} role="region" aria-label="可横向滚动的证据比较矩阵"><table><caption className="sr-only">行是研究维度，列是当前选材的文献版本</caption><thead><tr><th scope="col">研究维度</th>{columns.map((column) => <th scope="col" key={column.id}><strong>{column.title}</strong><small>{column.authors || "作者信息待补充"}</small><span>{column.references.length} 条选材</span></th>)}</tr></thead><tbody>{displayedDimensions.map((name) => <tr key={name}><th scope="row">{name}</th>{columns.map((column) => {
        const entries = cells.filter((cell) => cell.dimension === name && comparisonCellColumn(cell, columns) === column.id);
        return <td key={column.id} data-document={column.title}>{entries.map((cell, index) => <div className="stl4-comparison-entry" key={index}><p className="stl4-comparison-label">我的比较笔记</p><p className="stl4-comparison-note">{cell.note || "尚未写下判断。"}</p><p className="stl4-comparison-evidence-status">{evidenceLabels[cell.evidence_status || (cell.reference_ids?.length ? "selected" : "missing")]}</p>{(cell.reference_ids || []).map((refId) => <Evidence key={refId} reference={references.get(refId)} />)}<button type="button" disabled={pending} onClick={() => editCell(name, column, cell)}><Pencil size={12} />编辑笔记与证据</button></div>)}{!entries.length ? <div className="stl4-comparison-gap"><p>尚未选入本维度的证据</p><small>留下问题或判断，再从该文献的选材中补入原文。</small></div> : null}{column.references.length ? <button type="button" className="stl4-comparison-add" disabled={pending || cells.length >= 200} onClick={() => editCell(name, column)}><Plus size={12} />{entries.length ? "补充一条笔记" : "填写比较"}</button> : null}</td>;
      })}</tr>)}</tbody></table></div> : <div className="stl4-research-empty"><h2>{!columns.length ? "先选择需要比较的材料" : "建立第一个比较维度"}</h2><p>{!columns.length ? "在研究工作区加入真实文献片段后，即可按文献并列核对。" : "填写与你的问题有关的比较角度。原文证据由你逐格选择，空缺会保留。"}</p>{!columns.length ? <Link className="stl4-research-secondary" href={`/account/research/${record.id}`}>返回工作区选材</Link> : <button className="stl4-research-secondary" onClick={() => setDimensionOpen(true)}><Plus size={14} />添加维度</button>}</div> : null}
      {tab === "sources" ? <div className="stl4-comparison-text-view">{columns.filter((column) => column.references.length).map((column) => <article key={column.id}><h3>{column.title}</h3><p>{column.authors}</p>{column.references.map((ref) => <Evidence key={researchEvidenceKey(ref)} reference={ref} />)}</article>)}{!selections.length ? <p>还没有选材。请回到研究工作区选择原文。</p> : null}</div> : null}
      {tab === "draft" ? <div className="stl4-comparison-text-view"><p>下列内容来自你逐格保存的比较笔记，原文依据仍可逐条核对。</p>{cells.filter((cell) => cell.note?.trim()).map((cell, index) => <article key={index}><h3>{cell.dimension} · {columns.find((column) => column.id === comparisonCellColumn(cell, columns))?.title}</h3><p className="stl4-comparison-note">{cell.note}</p>{cell.reference_ids?.map((refId) => <Evidence key={refId} reference={references.get(refId)} />)}</article>)}{!cells.some((cell) => cell.note?.trim()) ? <p>尚未保存比较笔记。可以从比较视图开始填写。</p> : null}</div> : null}
      {tab === "gaps" ? <div className="stl4-comparison-text-view">{gaps.map((gap) => <article key={`${gap.dimension}:${gap.column.id}`}><h3>{gap.dimension} · {gap.column.title}</h3><p>当前没有可核对的已选原文。可以从该文献的选材中补入证据，或回到研究工作区继续查找。</p>{gap.column.references.length ? <button className="stl4-research-secondary" onClick={() => editCell(gap.dimension, gap.column)}>补充证据</button> : null}</article>)}{!gaps.length ? <p>{dimensions.length && columns.length ? "当前比较格均有可读取的原文依据。观点是否成立仍需你核对全文。" : "建立比较维度并加入选材后，这里会列出尚缺依据的位置。"}</p> : null}</div> : null}
      {tab === "notes" ? <div className="stl4-comparison-text-view"><h3>我的研究笔记</h3><p className="stl4-comparison-note">{record.data.notes || "还没有保存研究笔记。"}</p><button className="stl4-research-secondary" disabled={pending} onClick={() => setNoteDraft({ text: record.data.notes || "", revision: record.revision })}><Pencil size={13} />编辑笔记</button></div> : null}
      </div>
    </section>
    <Dialog open={!!noteDraft} onRequestClose={() => { if (!pending) setNoteDraft(null); }} className="stl4-research-dialog" aria-labelledby="comparison-project-notes-title">{noteDraft ? <form onSubmit={(event) => { event.preventDefault(); void run(() => updateResearchProject(record.id, { expected_revision: noteDraft.revision, notes: noteDraft.text }), "研究笔记已保存。").then((ok) => { if (ok) setNoteDraft(null); }); }}><h2 id="comparison-project-notes-title">我的研究笔记</h2><label htmlFor="comparison-project-notes">记录比较后的判断、疑问与下一步</label><textarea id="comparison-project-notes" rows={10} maxLength={20000} value={noteDraft.text} onChange={(event) => setNoteDraft({ ...noteDraft, text: event.target.value })} />{actionError ? <p role="alert">{actionError}</p> : null}{noteDraft.revision !== record.revision ? <div><p>资料已有更新。最新已保存笔记如下，请核对后决定是否使用当前输入替换。</p><p className="stl4-comparison-note">{record.data.notes || "尚无已保存笔记"}</p><button type="button" onClick={() => setNoteDraft({ ...noteDraft, revision: record.revision })}>已核对，保留当前输入</button></div> : null}<footer><button type="button" disabled={pending} onClick={() => setNoteDraft(null)}>取消编辑</button><button type="button" disabled={pending} onClick={refresh}>读取最新状态</button><button type="submit" disabled={pending || noteDraft.revision !== record.revision}>保存笔记</button></footer></form> : null}</Dialog>
    <Dialog open={dimensionOpen} onRequestClose={() => { if (!pending) setDimensionOpen(false); }} className="stl4-research-dialog" aria-labelledby="comparison-dimension-title"><form onSubmit={(event) => void addDimension(event)}><h2 id="comparison-dimension-title">添加比较维度</h2><label htmlFor="comparison-dimension-name">你希望比较哪个方面？</label><input id="comparison-dimension-name" value={dimension} onChange={(event) => setDimension(event.target.value)} maxLength={120} required placeholder="例如：概念界定、解释机制、适用范围" /><p>每个维度中的材料与笔记都由你确定。</p>{dimensions.includes(dimension.trim()) ? <p role="alert">这个维度已经存在。</p> : null}{actionError ? <p role="alert">{actionError}</p> : null}<footer><button type="button" disabled={pending} onClick={() => setDimensionOpen(false)}>返回</button><button type="submit" disabled={pending || !validDimension}>保存维度</button></footer></form></Dialog>
    <Dialog open={!!editor} onRequestClose={() => { if (!pending) setEditor(null); }} className="stl4-research-dialog stl4-comparison-editor" aria-labelledby="comparison-editor-title">{editor && editorColumn ? <form onSubmit={(event) => void saveCell(event)}><h2 id="comparison-editor-title">{editor.dimension}</h2><p>{editorColumn.title} · {editorColumn.authors}</p><fieldset><legend>作为依据的原文</legend>{editorColumn.references.map((ref, index) => { const key = researchEvidenceKey(ref); return <label className="stl4-comparison-source" key={key}><input type="checkbox" checked={editor.ids.includes(key)} disabled={pending || ref.source_status !== "available" && !editor.ids.includes(key)} onChange={(event) => setEditor({ ...editor, ids: event.target.checked ? [...editor.ids, key] : editor.ids.filter((item) => item !== key) })} /><span><strong>材料 {index + 1}{ref.pdf_page ? ` · PDF 第 ${ref.pdf_page} 页` : ""}</strong><span>{ref.source_status === "available" ? ref.quote || ref.text || "打开原文核对" : "来源暂不可用，保留原有引用身份"}</span>{researchReaderHref(ref) ? <Link href={researchReaderHref(ref)} target="_blank" rel="noreferrer">查看原文</Link> : null}</span></label>; })}{editor.ids.filter((key) => !editorColumn.references.some((ref) => researchEvidenceKey(ref) === key)).map((key) => <p key={key}>已保留一条历史引用，当前选材中不可用。</p>)}{!editor.ids.length ? <p>尚未选入原文；保存后会显示证据缺口。</p> : null}</fieldset><label htmlFor="comparison-note">我的比较笔记</label><textarea id="comparison-note" value={editor.note} onChange={(event) => setEditor({ ...editor, note: event.target.value })} maxLength={8000} rows={6} placeholder="写下你对这一维度的理解，并区分证据与仍待核对的问题。" />{record.revision !== editor.revision ? <p role="status">研究资料已有更新。当前原文可用性已重新读取，编辑内容仍保留。{concurrentChange ? "原笔记也有变动，本次将另存一条，保留双方内容。" : ""}</p> : null}{!dimensions.includes(editor.dimension) ? <p role="alert">这个维度已被移除。请复制保留笔记，再回到矩阵选择新的维度。</p> : null}{actionError ? <p role="alert">{actionError} <button type="button" disabled={pending} onClick={refresh}>读取最新状态，保留当前输入</button></p> : null}<footer><button type="button" disabled={pending} onClick={() => setEditor(null)}>取消编辑</button><button type="submit" disabled={pending || !dimensions.includes(editor.dimension) || originalIndex < 0 && cells.length >= 200}>{pending ? "正在保存……" : concurrentChange ? "另存为一条比较笔记" : "保存笔记与证据"}</button></footer></form> : null}</Dialog>
  </Frame>;
}
function Evidence({ reference }: { reference?: ResolvedEvidence }) {
  if (!reference || reference.source_status !== "available") return <p className="stl4-comparison-unavailable">来源暂不可用，原引用身份仍保留。</p>;
  const href = researchReaderHref(reference);
  return <blockquote><p>{reference.quote || reference.text || "打开原文核对。"}</p><footer>{href ? <Link href={href}>查看原文{reference.pdf_page ? ` · PDF 第 ${reference.pdf_page} 页` : ""}</Link> : "原文定位待核对"}</footer></blockquote>;
}
function Frame({ children }: { children: ReactNode }) { return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div></div>; }
