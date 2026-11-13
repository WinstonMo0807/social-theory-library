"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { ArrowLeft, BookOpen, ChevronDown, CircleAlert, Download, Pencil, Plus, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { MediaPlacement } from "@/components/media-placement";
import { normalizePublicResourceUrl } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { exportResearchRecord, saveResearchComparison, updateResearchProject, type ComparisonCell, type ProjectData, type ResolvedEvidence } from "@/lib/api/research.client";
import { comparisonCellColumn, comparisonColumns, type ComparisonColumn } from "@/lib/api/research-comparison";
import { researchEvidenceKey, researchReaderHref } from "@/lib/api/research-evidence";
import { useResearchProject } from "./use-research-project";
import { ResearchComparisonDrafts, ResearchComparisonGenerate } from "./research-comparison-draft";
import { ResearchComparisonTranslations } from "./research-comparison-translations";
import { ResearchComparisonActivity, ResearchComparisonSearch, type ComparisonSearchTarget } from "./research-comparison-search";

type Editor = { dimension: string; column: ComparisonColumn; original: string | null; note: string; ids: string[]; initialNote: string; initialIds: string[]; revision: number; modelCandidate?: boolean };
const cellIdentity = (cell: ComparisonCell) => JSON.stringify([cell.dimension, cell.column_id || "", cell.author || "", cell.reference_ids || [], cell.note || ""]);
const evidenceLabels = { selected: "原文证据", partial: "部分来源待核对", unavailable: "来源待核对", missing: "尚未选入证据" };

export function ResearchSessionCompare({ id }: { id: string }) {
  const workspace = useResearchProject(id, true);
  if (workspace.error || ["forbidden", "temporary_error"].includes(workspace.session.status)) return <Frame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>证据比较暂时不可用</h2><p>{workspace.error || workspace.session.message}</p><button onClick={workspace.refresh}><RefreshCw size={15} />重新读取</button></div></Frame>;
  if (!workspace.record) return <Frame><div className="stl4-research-state" role="status"><LoadingState>正在读取证据比较……</LoadingState></div></Frame>;
  return <Comparison key={`${workspace.session.user?.id}:${id}`} workspace={workspace} />;
}

function Comparison({ workspace }: { workspace: ReturnType<typeof useResearchProject> }) {
  const { record, pending, run, refresh, notice, actionError } = workspace;
  const [searchTarget, setSearchTarget] = useState<ComparisonSearchTarget | null>(null);
  const [generationDimension, setGenerationDimension] = useState("");
  const [dimensionOpen, setDimensionOpen] = useState(false);
  const [dimension, setDimension] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [filter, setFilter] = useState("");
  const [matrixLayout,setMatrixLayout]=useState<"overview"|"dimension">("overview");
  const [tab, setTab] = useState("matrix");
  const [noteDraft, setNoteDraft] = useState<{ text: string; initialText: string; revision: number } | null>(null);
  const [discard, setDiscard] = useState<"cell" | "notes" | "dimension" | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const cellDirty = Boolean(editor && (editor.note !== editor.initialNote || JSON.stringify(editor.ids) !== JSON.stringify(editor.initialIds)));
  const notesDirty = Boolean(noteDraft && noteDraft.text !== noteDraft.initialText);
  useUnsavedForm([cellDirty, notesDirty, dimension], [false, false, ""]);
  function closeEditor(target: "cell" | "notes" | "dimension") {
    if (pending) return;
    if (target === "cell" ? cellDirty : target === "notes" ? notesDirty : Boolean(dimension.trim())) { setDiscard(target); return; }
    discardEditor(target);
  }
  function discardEditor(target: "cell" | "notes" | "dimension") {
    if (pending) return;
    if (target === "cell") setEditor(null);
    else if (target === "notes") setNoteDraft(null);
    else { setDimensionOpen(false); setDimension(""); }
    setDiscard(null);
  }
  if (!record) return null;
  const dimensions = record.data.comparison?.dimensions || [];
  const cells = record.data.comparison?.cells || [];
  const selections = record.data.selections || [];
  const columns = comparisonColumns(selections, cells);
  const references = new Map(selections.map((ref) => [researchEvidenceKey(ref), ref]));
  const activeDimension = dimensions.includes(filter) ? filter : dimensions[0] || "";
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
    setEditor({ dimension: name, column, original: cell ? cellIdentity(cell) : null, note: cell?.note || "", ids: cell?.reference_ids || [], initialNote: cell?.note || "", initialIds: [...(cell?.reference_ids || [])], revision: record.revision });
  }
  async function saveCell(event: FormEvent) {
    event.preventDefault();
    if (!record || !editor || !dimensions.includes(editor.dimension)) return;
    const previous = originalIndex >= 0 ? cells[originalIndex] : null;
    const columnId = previous?.column_id || (!editor.column.id.startsWith("retained:") ? editor.column.id : undefined);
    const cell: ComparisonCell = { dimension: editor.dimension, ...(columnId ? { column_id: columnId } : {}), author: previous?.author || editor.column.authors || "", reference_ids: editor.ids, note: editor.note.trim() };
    if (originalIndex < 0 && cells.some(saved => saved.dimension === cell.dimension && saved.column_id === cell.column_id && saved.note === cell.note && JSON.stringify([...(saved.reference_ids || [])].sort()) === JSON.stringify([...editor.ids].sort()))) {
      setEditor(null); return;
    }
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
    }, "已导出研究、来源信息和比较记录。");
  }
  function entriesFor(column: ComparisonColumn,name=activeDimension) { return cells.filter(cell=>cell.dimension===name&&comparisonCellColumn(cell,columns)===column.id); }
  function columnEvidence(column: ComparisonColumn, sourceOnly=false,name=activeDimension) {
    const ids=[...new Set(entriesFor(column,name).flatMap(cell=>cell.reference_ids||[]))];
    return ids.length?ids.map(key=>sourceOnly?<SourceLocation key={key} reference={references.get(key)}/>:<Evidence key={key} reference={references.get(key)} showLink={false}/>):<p className="stl4-comparison-gap">本维度尚未选入原文依据，可从选材区核对后补充。</p>;
  }
  function columnNotes(column: ComparisonColumn,name=activeDimension) {
    const entries=entriesFor(column,name);
    return <>{entries.map((cell,index)=><div className="stl4-comparison-entry" key={index}><p className="stl4-comparison-note">{cell.note||"尚未写下判断。"}</p><p className="stl4-comparison-evidence-status">{evidenceLabels[cell.evidence_status||(cell.reference_ids?.length?"selected":"missing")]}</p><button type="button" disabled={pending} onClick={()=>editCell(name,column,cell)}><Pencil size={12}/>编辑笔记与证据</button></div>)}{!entries.length?<p className="stl4-comparison-gap">尚未填写本人判断。</p>:null}{column.references.length?<button type="button" className="stl4-comparison-add" disabled={pending||cells.length>=200} onClick={()=>editCell(name,column)}><Plus size={12}/>{entries.length?"补充一条笔记":"填写比较与依据"}</button>:null}</>;
  }
  return <Frame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href={`/account/research/${record.id}`}>持续研究</Link><span>/</span><strong>证据比较</strong></nav>
    <header className="stl4-research-heading"><h1>选材比较与证据矩阵</h1><span className="stl4-research-privacy">仅本人可见</span></header>
    <section className="stl4-research-workspace stl4-research-compare-surface" data-matrix-layout={matrixLayout}>
      <div className="stl4-research-compare-head"><div><p className="stl4-research-kicker">当前研究</p><h2>{record.data.title || record.data.question || "未命名研究"}</h2></div><Link href={`/account/research/${record.id}`}><ArrowLeft size={14} />返回工作区</Link></div>
      <div className="stl4-comparison-layout"><aside className="stl4-comparison-selected" aria-label="当前选材">
        <header><h2>已选文献 / 段落 <small>{columns.filter(column=>column.references.length).length}</small></h2><Link href={`/account/research/${record.id}`}>管理</Link></header>
        {columns.filter(column=>column.references.length).map((column,index)=><details data-disclosure="collection" key={column.id} open={index===0}><summary><span className="stl4-comparison-index">{index+1}</span><ColumnHeading column={column}/><ChevronDown size={14}/></summary><div className="stl4-comparison-selected-evidence">{column.references.map(reference=><Evidence key={researchEvidenceKey(reference)} reference={reference}/>)}</div></details>)}
        {!selections.length?<p>尚未选入文献或原文段落。</p>:null}<Link className="stl4-research-secondary" href={`/account/research/${record.id}`}><Plus size={14}/>添加文献或段落</Link>
      </aside><div className="stl4-comparison-content">
      <div className="stl4-comparison-tabs" role="tablist" aria-label="比较资料视图" onKeyDown={(event) => { const names = ["matrix", "sources", "draft", "gaps", "notes"]; const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0; if (!offset && event.key !== "Home" && event.key !== "End") return; event.preventDefault(); const next = event.key === "Home" ? names[0] : event.key === "End" ? names.at(-1)! : names[(names.indexOf(tab) + offset + names.length) % names.length]; setTab(next); document.getElementById(`comparison-tab-${next}`)?.focus(); }}>{[["matrix", "比较视图"], ["sources", `已选文献（${columns.filter((column) => column.references.length).length}）`], ["draft", "比较草稿"], ["gaps", `证据缺口（${gaps.length}）`], ["notes", "我的笔记"]].map(([value, label]) => <button key={value} id={`comparison-tab-${value}`} role="tab" tabIndex={tab === value ? 0 : -1} aria-selected={tab === value} aria-controls={`comparison-panel-${value}`} onClick={() => setTab(value)}>{label}</button>)}</div>
      <div className="stl4-research-compare-toolbar"><div className="stl4-comparison-layout-choice" aria-label="比较视图布局"><button type="button" aria-pressed={matrixLayout==="overview"} onClick={()=>setMatrixLayout("overview")}>全部维度矩阵</button><button type="button" aria-pressed={matrixLayout==="dimension"} onClick={()=>setMatrixLayout("dimension")}>单维度对照</button></div><label>比较维度<select data-stl-select value={activeDimension} disabled={!dimensions.length} onChange={(event) => setFilter(event.target.value)}>{!dimensions.length?<option value="">尚未设置</option>:null}{dimensions.map((name) => <option key={name}>{name}</option>)}</select></label><div><button type="button" disabled={pending || dimensions.length >= 20} onClick={() => setDimensionOpen(true)}><Plus size={14} />添加维度</button><button type="button" disabled={pending || record.archived} onClick={() => setSearchTarget({ dimension: activeDimension })}>扩展寻找新证据</button><button type="button" disabled={pending || record.archived || !activeDimension || !selections.some(ref=>ref.source_status==="available")} onClick={()=>setGenerationDimension(activeDimension)}>生成比较草稿</button><button disabled={pending} onClick={() => void exportComparison()}><Download size={14} />导出</button><button disabled={pending} onClick={refresh}><RefreshCw size={14} />刷新</button></div></div>
      {notice ? <p className="stl4-research-action-message" role="status">{notice}</p> : null}{actionError ? <p className="stl4-research-action-message is-error" role="alert">{actionError}</p> : null}
      <ResearchComparisonActivity workspace={workspace}/>
      <div id={`comparison-panel-${tab}`} role="tabpanel" aria-labelledby={`comparison-tab-${tab}`}>
      {tab === "matrix" ? dimensions.length && columns.length ? <>
        <nav className="stl4-comparison-dimensions" aria-label="比较维度">{dimensions.map((name,index)=><button type="button" key={name} aria-pressed={activeDimension===name} onClick={()=>setFilter(name)}><small>{String(index+1).padStart(2,"0")}</small>{name}</button>)}</nav>
        {matrixLayout==="overview"?<div className="stl4-research-matrix stl4-comparison-desktop stl4-comparison-overview" tabIndex={0} role="region" aria-label="全部维度证据矩阵"><table><caption className="sr-only">将各文献的比较判断和原文按维度并列</caption><thead><tr><th scope="col">比较维度</th>{columns.map(column=><th scope="col" key={column.id}><ColumnHeading column={column}/></th>)}</tr></thead><tbody>{dimensions.map(name=><tr key={name}><th scope="row"><button type="button" onClick={()=>{setFilter(name);setMatrixLayout("dimension");}}>{name}</button></th>{columns.map(column=><td key={column.id}>{columnNotes(column,name)}{columnEvidence(column,false,name)}</td>)}</tr>)}</tbody></table></div>:null}
        <div className="stl4-research-matrix stl4-comparison-desktop stl4-comparison-single" tabIndex={0} role="region" aria-label="可横向滚动的单维度证据比较"><table><caption className="sr-only">{activeDimension}：按文献版本分别核对原文、来源和本人判断</caption><thead><tr><th scope="col"><small>比较维度</small><strong>{activeDimension}</strong></th>{columns.map(column=><th scope="col" key={column.id}><ColumnHeading column={column}/></th>)}</tr></thead><tbody>
          <tr><th scope="row">作者原话<small>已明确选入本维度的段落</small></th>{columns.map(column=><td key={column.id}>{columnEvidence(column)}</td>)}</tr>
          <tr><th scope="row">来源信息</th>{columns.map(column=><td key={column.id}>{columnEvidence(column,true)}</td>)}</tr>
          <tr><th scope="row">比较笔记<small>我的理解与判断</small></th>{columns.map(column=><td key={column.id}>{columnNotes(column)}</td>)}</tr>
        </tbody></table></div>
        <div className="stl4-comparison-mobile"><header><small>当前比较维度</small><h2>{activeDimension}</h2></header>{columns.map((column,index)=><details data-disclosure="collection" key={`${activeDimension}:${column.id}`} open={index===0}><summary><ColumnHeading column={column}/><ChevronDown size={16}/></summary><section><h3>作者原话</h3>{columnEvidence(column)}<h3>来源信息</h3>{columnEvidence(column,true)}<h3>比较笔记 · 我的理解</h3>{columnNotes(column)}</section></details>)}</div>
      </> : <div className="stl4-research-empty"><h2>{!columns.length ? "先选择需要比较的材料" : "建立第一个比较维度"}</h2><p>{!columns.length ? "先将原文加入研究，再按文献并列比较。" : "填写与你的问题有关的比较角度。原文证据由你逐格选择，空缺会保留。"}</p>{!columns.length ? <Link className="stl4-research-secondary" href={`/account/research/${record.id}`}>返回工作区选材</Link> : <button className="stl4-research-secondary" onClick={() => setDimensionOpen(true)}><Plus size={14} />添加维度</button>}</div> : null}
      {tab === "sources" ? <div className="stl4-comparison-text-view">{columns.filter((column) => column.references.length).map((column) => <article key={column.id}><h3>{column.title}</h3><p>{column.authors}</p>{column.references.map((ref) => <Evidence key={researchEvidenceKey(ref)} reference={ref} />)}</article>)}{!selections.length ? <p>还没有选材。请回到研究工作区选择原文。</p> : null}</div> : null}
      {tab === "draft" ? <><ResearchComparisonDrafts workspace={workspace} dimension={activeDimension} onReview={(name,candidate)=>{const column=columns.find(row=>row.id===candidate.column_id);if(column)setEditor({dimension:name,column,original:null,note:candidate.note,ids:candidate.reference_ids,initialNote:"",initialIds:[],revision:record.revision,modelCandidate:true});}}/><div className="stl4-comparison-text-view"><p>下列内容来自你逐格保存的比较笔记，原文依据仍可逐条核对。</p>{cells.filter((cell) => cell.note?.trim()).map((cell, index) => <article key={index}><h3>{cell.dimension} · {columns.find((column) => column.id === comparisonCellColumn(cell, columns))?.title}</h3><p className="stl4-comparison-note">{cell.note}</p>{cell.reference_ids?.map((refId) => <Evidence key={refId} reference={references.get(refId)} />)}</article>)}{!cells.some((cell) => cell.note?.trim()) ? <p>尚未保存比较笔记。可以从比较视图开始填写。</p> : null}</div></> : null}
      {tab === "gaps" ? <div className="stl4-comparison-text-view">{gaps.map((gap) => <article key={`${gap.dimension}:${gap.column.id}`}><h3>{gap.dimension} · {gap.column.title}</h3><p>当前没有可核对的已选原文。可以从该文献的选材中补入证据，或回到研究工作区继续查找。</p>{gap.column.references.length ? <button className="stl4-research-secondary" disabled={pending} onClick={() => editCell(gap.dimension, gap.column)}>补充证据</button> : null}<button type="button" className="stl4-research-secondary" disabled={pending || record.archived} onClick={() => setSearchTarget({ dimension: gap.dimension, columnId: gap.column.id, title: gap.column.title })}>扩展寻找新证据</button></article>)}{!gaps.length ? <p>{dimensions.length && columns.length ? "当前比较格均有可读取的原文依据。观点是否成立仍需你核对全文。" : "建立比较维度并加入选材后，这里会列出尚缺依据的位置。"}</p> : null}</div> : null}
      {tab === "notes" ? <div className="stl4-comparison-text-view"><h3>我的研究笔记</h3><p className="stl4-comparison-note">{record.data.notes || "还没有保存研究笔记。"}</p><button className="stl4-research-secondary" disabled={pending} onClick={() => setNoteDraft({ text: record.data.notes || "", initialText: record.data.notes || "", revision: record.revision })}><Pencil size={13} />编辑笔记</button></div> : null}
      </div>
      </div></div>
    </section>
    <Dialog open={!!noteDraft} onRequestClose={() => closeEditor("notes")} className="stl4-research-dialog" aria-labelledby="comparison-project-notes-title">{noteDraft ? <form onSubmit={(event) => { event.preventDefault(); void run(() => updateResearchProject(record.id, { expected_revision: noteDraft.revision, notes: noteDraft.text }), "研究笔记已保存。").then((ok) => { if (ok) setNoteDraft(null); }); }}><h2 id="comparison-project-notes-title">我的研究笔记</h2><label htmlFor="comparison-project-notes">记录比较后的判断、疑问与下一步</label><textarea id="comparison-project-notes" rows={10} maxLength={20000} value={noteDraft.text} onChange={(event) => setNoteDraft({ ...noteDraft, text: event.target.value })} />{actionError ? <p role="alert">{actionError}</p> : null}{noteDraft.revision !== record.revision ? <div><p>资料已有更新。最新已保存笔记如下，请核对后决定是否使用当前输入替换。</p><p className="stl4-comparison-note">{record.data.notes || "尚无已保存笔记"}</p><button type="button" onClick={() => setNoteDraft({ ...noteDraft, revision: record.revision })}>已核对，保留当前输入</button></div> : null}<footer><button type="button" disabled={pending} onClick={() => closeEditor("notes")}>取消编辑</button><button type="button" disabled={pending} onClick={refresh}>读取最新状态</button><button type="submit" disabled={pending || noteDraft.revision !== record.revision}>保存笔记</button></footer></form> : null}</Dialog>
    <Dialog open={dimensionOpen} onRequestClose={() => closeEditor("dimension")} className="stl4-research-dialog" aria-labelledby="comparison-dimension-title"><form onSubmit={(event) => void addDimension(event)}><h2 id="comparison-dimension-title">添加比较维度</h2><label htmlFor="comparison-dimension-name">你希望比较哪个方面？</label><input id="comparison-dimension-name" value={dimension} onChange={(event) => setDimension(event.target.value)} maxLength={120} required placeholder="例如：概念界定、解释机制、适用范围" /><p>每个维度中的材料与笔记都由你确定。</p>{dimensions.includes(dimension.trim()) ? <p role="alert">这个维度已经存在。</p> : null}{actionError ? <p role="alert">{actionError}</p> : null}<footer><button type="button" disabled={pending} onClick={() => closeEditor("dimension")}>返回</button><button type="submit" disabled={pending || !validDimension}>保存维度</button></footer></form></Dialog>
    <Dialog open={!!editor} onRequestClose={() => closeEditor("cell")} className="stl4-research-dialog stl4-comparison-editor" aria-labelledby="comparison-editor-title">{editor && editorColumn ? <form onSubmit={(event) => void saveCell(event)}><h2 id="comparison-editor-title">{editor.dimension}</h2><p>{editorColumn.title} · {editorColumn.authors}</p><fieldset><legend>作为依据的原文</legend>{editorColumn.references.map((ref, index) => { const key = researchEvidenceKey(ref); return <label className="stl4-comparison-source" key={key}><input type="checkbox" checked={editor.ids.includes(key)} disabled={pending || ref.source_status !== "available" && !editor.ids.includes(key)} onChange={(event) => setEditor({ ...editor, ids: event.target.checked ? [...editor.ids, key] : editor.ids.filter((item) => item !== key) })} /><span><strong>材料 {index + 1}{ref.pdf_page ? ` · PDF 第 ${ref.pdf_page} 页` : ""}</strong><span>{ref.source_status === "available" ? ref.quote || ref.text || "打开原文核对" : "来源暂不可用，原引用记录保留"}</span>{researchReaderHref(ref) ? <Link href={researchReaderHref(ref)} target="_blank" rel="noreferrer">查看原文</Link> : null}</span></label>; })}{editor.ids.filter((key) => !editorColumn.references.some((ref) => researchEvidenceKey(ref) === key)).map((key) => <p key={key}>已保留一条历史引用，当前选材中不可用。</p>)}{!editor.ids.length ? <p>尚未选入原文；保存后会显示证据缺口。</p> : null}</fieldset>{editor.modelCandidate?<p role="status">下面是模型生成的待核对草稿。请逐条核对所选原文并编辑后再保存；将新增一条本人确认的比较笔记，已有笔记保留。</p>:null}<label htmlFor="comparison-note">我的比较笔记</label><textarea id="comparison-note" value={editor.note} onChange={(event) => setEditor({ ...editor, note: event.target.value })} maxLength={8000} rows={6} placeholder="写下你对这一维度的理解，并区分证据与仍待核对的问题。" />{record.revision !== editor.revision ? <p role="status">研究资料已有更新。当前原文可用性已重新读取，编辑内容仍保留。{concurrentChange ? "原笔记也有变动，本次将另存一条，保留双方内容。" : ""}</p> : null}{!dimensions.includes(editor.dimension) ? <p role="alert">这个维度已被移除。请复制保留笔记，再回到矩阵选择新的维度。</p> : null}{actionError ? <p role="alert">{actionError} <button type="button" disabled={pending} onClick={refresh}>读取最新状态，保留当前输入</button></p> : null}<footer><button type="button" disabled={pending} onClick={() => closeEditor("cell")}>取消编辑</button><button type="submit" disabled={pending || !dimensions.includes(editor.dimension) || originalIndex < 0 && cells.length >= 200}>{pending ? "正在保存……" : concurrentChange ? "另存为一条比较笔记" : "保存笔记与证据"}</button></footer></form> : null}</Dialog>
    {generationDimension ? <ResearchComparisonGenerate workspace={workspace} dimension={generationDimension} onClose={()=>{setGenerationDimension("");setTab("draft");}}/> : null}
    {searchTarget ? <ResearchComparisonSearch workspace={workspace} target={searchTarget} onClose={() => setSearchTarget(null)}/> : null}
    <ConfirmDialog open={discard!==null} title="放弃尚未保存的填写？" description="当前修改尚未保存。已保存的研究、原文引用和比较笔记会保留。" confirmLabel="放弃本次填写" cancelLabel="继续编辑" pending={pending} onCancel={()=>setDiscard(null)} onConfirm={()=>{if(discard)discardEditor(discard);}} />
  </Frame>;
}
function Evidence({ reference, showLink = true }: { reference?: ResolvedEvidence; showLink?: boolean }) {
  if (!reference || reference.source_status !== "available") return <p className="stl4-comparison-unavailable">来源暂不可用，原引用记录保留。</p>;
  const href = researchReaderHref(reference);
  return <blockquote><p>{reference.quote || reference.text || "打开原文核对。"}</p><footer>{href && showLink ? <Link href={href} target="_blank" rel="noreferrer">查看原文 · {locationLabel(reference)}</Link> : locationLabel(reference)}</footer></blockquote>;
}
function locationLabel(reference:ResolvedEvidence) {
  const anchors=reference.anchors?.length?reference.anchors:[reference];
  const pages=[...new Set(anchors.map(row=>row.pdf_page).filter((page):page is number=>typeof page==="number"&&Number.isInteger(page)&&page>0))];
  const labels=[...new Set(reference.printed_labels?.length?reference.printed_labels:anchors.map(row=>row.printed_label).filter(Boolean))];
  return [labels.length?`书内页码 ${labels.join("、")}`:"",pages.length?`PDF 第 ${pages.join("、")} 页`:""].filter(Boolean).join(" · ")||"原文定位待核对";
}
function ColumnHeading({column}:{column:ComparisonColumn}) {
  const reference=column.references.find(row=>row.source_status==="available"),url=reference?.cover_url?normalizePublicResourceUrl(reference.cover_url):"";
  const [failed,setFailed]=useState("");
  const fallback=<span className="stl4-comparison-cover" role="img" aria-label={url?"封面暂不可用或本位置不展示":"暂无可用封面"}><BookOpen size={24} strokeWidth={1}/></span>;
  return <span className="stl4-comparison-document">{url&&failed!==url?<MediaPlacement uses={reference?.cover_media?.display_uses} fallback={fallback}><img src={url} alt="" className="stl4-comparison-cover" loading="lazy" onError={()=>setFailed(url)}/></MediaPlacement>:fallback}<span><strong>{column.title}</strong><small>{column.authors||"作者信息待补充"}{reference?.publication_year!=null?` · ${reference.publication_year}`:""}</small><small>{column.references.length?`${column.references.length} 条选材`:"保留的历史比较"}</small></span></span>;
}
function SourceLocation({reference}:{reference?:ResolvedEvidence}) {
  const [translations,setTranslations]=useState(false);
  if(!reference||reference.source_status!=="available")return <p className="stl4-comparison-unavailable">来源暂不可用，原引用保留。</p>;
  const href=researchReaderHref(reference);
  return <div className="stl4-comparison-location">{reference.citation?<p>{reference.citation}</p>:null}<small>{locationLabel(reference)}</small>{href?<Link href={href} target="_blank" rel="noreferrer">打开原文{(reference.anchors?.length||0)>1?"（起始位置）":""} →</Link>:<p>原文定位待核对</p>}<button type="button" onClick={()=>setTranslations(true)}>译本与版本差异</button>{translations?<ResearchComparisonTranslations reference={reference} onClose={()=>setTranslations(false)}/>:null}</div>;
}
function Frame({ children }: { children: ReactNode }) { return <div className="stl4-research-page stl4-comparison-page"><div className="stl4-research-detail-shell">{children}</div></div>; }
