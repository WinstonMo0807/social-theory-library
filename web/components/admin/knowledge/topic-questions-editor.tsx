"use client";

import { useEffect, useRef } from "react";
import { GripVertical, Plus, Trash2 } from "lucide-react";

export function TopicQuestionsEditor({ value, onChange }: {
  value: string[]; onChange: (next: string[]) => void; "data-editor-section"?: string;
}) {
  const rows = value.length ? value : [""];
  const root = useRef<HTMLElement>(null);
  const moving = useRef<number | null>(null);
  function move(from: number, to: number) {
    if (from === to || to < 0 || to >= rows.length) return;
    const next = [...rows];
    const [question] = next.splice(from, 1);
    next.splice(to, 0, question);
    onChange(next);
  }
  useEffect(() => {
    const select = (event: Event) => {
      const index = (event as CustomEvent<unknown>).detail;
      if (typeof index !== "number" || !Number.isInteger(index) || !root.current?.getClientRects().length) return;
      const input = root.current.querySelector<HTMLInputElement>(`input[data-topic-question-index="${index}"]`);
      if (input) { event.preventDefault(); input.focus(); }
    };
    window.addEventListener("knowledge-row-select", select);
    return () => window.removeEventListener("knowledge-row-select", select);
  }, []);
  return <section ref={root} className="topic-reference-questions" data-editor-section="questions">
    <h2>研究问题</h2>
    <p>从不同角度提出值得思考的核心问题，帮助读者进入这一主题。</p>
    <div className="topic-reference-question-list">
      {rows.map((question, index) => <article key={index} className="topic-reference-question" data-question-index={index}
        onDragOver={event => { if (moving.current !== null) event.preventDefault(); }}
        onDrop={event => { event.preventDefault(); if (moving.current !== null) move(moving.current, index); moving.current = null; }}>
        <header><button type="button" className="topic-question-grip" draggable aria-label={`移动问题 ${index + 1}`}
          onDragStart={event => { moving.current = index; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(index)); }}
          onDragEnd={() => { moving.current = null; }}
          onKeyDown={event => {
            if (event.altKey && ["ArrowUp", "ArrowDown"].includes(event.key)) {
              event.preventDefault(); move(index, index + (event.key === "ArrowUp" ? -1 : 1));
            }
          }}><GripVertical size={16} /></button><strong>问题 {index + 1}</strong>
          <button type="button" className="topic-question-remove" aria-label={`删除问题 ${index + 1}`}
            disabled={rows.length === 1 && !question} onClick={() => onChange(rows.filter((_, position) => position !== index))}>
            <Trash2 size={14} />删除</button></header>
        <div><label><span>问题标题 <b>*</b></span><input autoComplete="off" required={value.length > 0}
          data-topic-question-index={index} value={question}
          onFocus={() => window.dispatchEvent(new CustomEvent("topic-question-focus", { detail: index }))} onChange={event => {
            const next = [...rows]; next[index] = event.target.value; onChange(next);
          }} /></label>
          <label><span>问题解释 <b>*</b></span><textarea value="" readOnly disabled maxLength={300} rows={3} /></label>
          <small className="topic-question-count">0/300</small></div>
      </article>)}
    </div>
    <button type="button" className="topic-question-add" disabled={rows.length >= 3}
      onClick={() => onChange([...rows, ""])}><Plus size={15} />添加研究问题
      <span>（还可添加 {Math.max(0, 3 - rows.length)} 条）</span></button>
  </section>;
}
