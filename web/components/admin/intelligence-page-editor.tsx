"use client";

import { useEffect, useRef, useState } from "react";
import { Pencil } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { KnowledgePageContent, type KnowledgePageData, type KnowledgeBlock } from "@/components/public/knowledge-page-content";
import { IssueTextEditor } from "./curation/issue-text-editor";
import styles from "./intelligence-workspace.module.css";

type Patch = { title?: string; scope?: string; page_id?: string; block_id?: string; operation?: string; reason?: string; human_protected?: boolean; human_edited?: boolean; block?: Partial<KnowledgeBlock> };

export function IntelligencePageEditor({ patch, title, version, applied, onBlock, onHumanReview, onMetadata, anchors = [] }: {
  onMetadata?: (value: { title?: string; scope?: string }) => void;
  patch: Patch; title: string; version: number; applied: boolean; onBlock: (block: Partial<KnowledgeBlock>) => void; onHumanReview?: (confirmed: boolean) => void; anchors?: KnowledgePageData["anchors"];
}) {
  const [current, setCurrent] = useState<KnowledgePageData | null>(null);
  const [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  const [perspective, setPerspective] = useState<"current" | "proposed">("proposed");
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setCurrent(null); setError("");
    if (patch.page_id) void apiRequest<KnowledgePageData>(`/knowledge/pages/${patch.page_id}/?preview=1`, {
      cache: "no-store", signal: controller.signal,
    }, getServerSessionCredential()).then(setCurrent).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [patch.page_id, version, attempt]);

  const key = patch.block_id || "proposed-block";
  const blocks = current?.blocks || [];
  const metadataEdit = patch.operation === "metadata";
  const proposed = applied || metadataEdit ? blocks : patch.operation === "delete" ? blocks.filter(b => b.id !== key)
    : patch.operation === "replace" ? blocks.map(b => b.id === key ? { ...b, ...patch.block, id: key } : b)
    : [...blocks, { ...patch.block, id: key, text: patch.block?.text || "" }];
  const missingTarget = !metadataEdit && !applied && patch.operation !== "add" && !!current && !blocks.some(b => b.id === key);
  const shown = perspective === "current" ? blocks : proposed;
  const loading = !!patch.page_id && !current && !error;
  const focusField = () => { field.current?.querySelector<HTMLElement>('[contenteditable="true"]')?.focus(); field.current?.scrollIntoView({ behavior: "instant", block: "nearest" }); };

  return <div className={styles.pageEditor}>
    <div className={styles.editorFields}>
      <div className={styles.fieldHeading}><h4>{metadataEdit ? "标题与范围" : patch.operation === "delete" ? "删除区块" : patch.operation === "replace" ? "修改区块" : "新增区块"}</h4><span>{applied ? "已保存" : "审核后保存为草稿"}</span></div>
      {patch.reason && <p className={styles.reason}>{patch.reason}</p>}
      {metadataEdit ? <><label>标题<input disabled={applied} value={patch.title || ""} maxLength={600} onChange={e => onMetadata?.({ title: e.target.value })} /></label><label>编纂范围<textarea disabled={applied} value={patch.scope || ""} maxLength={6000} onChange={e => onMetadata?.({ scope: e.target.value })} /></label></> : patch.operation === "delete" ? <p>确认并保存后，将移除此区块。其他区块保持原样。</p> : <div ref={field}><IssueTextEditor label="区块正文" block={{ ...patch.block, type: patch.block?.type || "analysis", text: patch.block?.text || "", references: undefined }} disabled={applied} onChange={value => onBlock({ ...patch.block, ...value, references: patch.block?.references })} maxLength={6000} /></div>}
      {patch.human_protected && !applied && <label className={styles.notice}><span>此处包含受保护的人工正文。</span><span><input type="checkbox" checked={!!patch.human_edited} onChange={e => onHumanReview?.(e.target.checked)} /> 已对照当前内容与原文，允许本次局部修改</span></label>}
    </div>
    <section className={styles.livePreview} aria-label="知识页实时预览">
      <div className={styles.previewToolbar}><h4>展示效果</h4><div className={styles.segmented} aria-label="预览版本">
        <button type="button" aria-pressed={perspective === "current"} onClick={() => setPerspective("current")}>当前内容</button>
        <button type="button" aria-pressed={perspective === "proposed"} onClick={() => setPerspective("proposed")}>{applied ? "已保存内容" : "修改后"}</button>
      </div></div>
      <div className={styles.destination}>{current?.title || title} / 知识导读</div>
      {error ? <div role="alert" className={styles.error}>当前页面读取失败：{error}<button type="button" onClick={() => setAttempt(v => v + 1)}>重试</button></div>
        : loading ? <p role="status" className={styles.previewState}>正在读取当前页面…</p>
        : missingTarget ? <p role="alert" className={styles.error}>目标区块已不存在，请刷新审核内容后处理冲突。</p>
        : <div className={styles.previewPaper} data-ui-scope="stl4" data-type-mode="expressive">
          {!metadataEdit && <h3>{current?.title || title}</h3>}
          {metadataEdit && <header><h2>{perspective === "current" ? current?.title : patch.title}</h2><p>{perspective === "current" ? current?.scope : patch.scope}</p></header>}
          <KnowledgePageContent page={{ blocks: shown, assertions: current?.assertions || [], anchors: [...(current?.anchors || []), ...anchors] }} renderBlock={(block, content) =>
            block.id === key && !applied && perspective === "proposed" && patch.operation !== "delete"
              ? <div key={block.id} className={styles.activeBlock} role="button" tabIndex={0} aria-label="返回编辑这个区块"
                  onClick={focusField} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focusField(); } }}>
                  <span className={styles.blockMarker}><Pencil size={13} />本次{patch.operation === "replace" ? "修改" : "新增"}</span>{content}
                </div> : content} />
          {!shown.length && <p className={styles.previewState}>{perspective === "current" ? "此处尚无知识导读正文。" : "此项修改后，知识导读没有正文区块。"}</p>}
        </div>}
      <p id="intelligence-preview-description" className={styles.previewCaption}>{applied ? "显示当前保存版本的正文。" : "正文随输入实时变化，标记区块可点击返回编辑。"}{!patch.page_id && "此处仅预览本次区块。"}来源在原文区核对，公开展示以发布结果为准。</p>
    </section>
  </div>;
}
