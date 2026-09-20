"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** An isolated viewport keeps public media queries and typography identical to the page. */
function PreviewViewport({ children }: { children: ReactNode }) {
  const [width, setWidth] = useState(1120);
  const [fitWidth, setFitWidth] = useState(true);
  const [availableWidth, setAvailableWidth] = useState(0);
  const [height, setHeight] = useState(800);
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => setAvailableWidth(canvas.clientWidth));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!mount) return;
    const frameDocument = frameRef.current?.contentDocument;
    if (!frameDocument) return;
    const copyStyles = () => {
      frameDocument.head.querySelectorAll("[data-preview-stylesheet]").forEach(element => element.remove());
      document.head.querySelectorAll<HTMLLinkElement | HTMLStyleElement>('link[rel="stylesheet"],style').forEach(source => {
        const clone = source.cloneNode(true) as HTMLLinkElement | HTMLStyleElement;
        clone.dataset.previewStylesheet = "true";
        if (source instanceof HTMLLinkElement) (clone as HTMLLinkElement).href = source.href;
        frameDocument.head.appendChild(clone);
      });
      frameDocument.documentElement.className = document.documentElement.className;
      frameDocument.documentElement.lang = document.documentElement.lang || "zh-CN";
    };
    copyStyles();
    const styles = new MutationObserver(copyStyles);
    styles.observe(document.head, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["href", "media", "disabled"] });
    const content = new ResizeObserver(() => setHeight(Math.max(320, Math.ceil(mount.scrollHeight))));
    content.observe(mount);
    return () => { styles.disconnect(); content.disconnect(); };
  }, [mount]);

  const scale = fitWidth && availableWidth ? Math.min(1, availableWidth / width) : 1;
  return <>
    <div className="fixed-preview-tools" role="group" aria-label="预览视口">
      <button type="button" aria-pressed={width === 1120} onClick={() => setWidth(1120)}>桌面 · 1120</button>
      <button type="button" aria-pressed={width === 390} onClick={() => setWidth(390)}>移动 · 390</button>
      <button type="button" aria-pressed={!fitWidth} onClick={() => setFitWidth(value => !value)}>{fitWidth ? "放大至实际大小" : "适应预览栏"}</button>
      <span>{Math.round(scale * 100)}% · 点击页面内容定位字段</span>
    </div>
    <div ref={canvasRef} className="fixed-preview-canvas">
      <div className="fixed-preview-stage" style={{ width: width * scale, height: height * scale }}>
        <iframe ref={frameRef} title="当前输入的公开页面预览" className="fixed-preview-frame" srcDoc={'<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="fixed-preview-root" class="fixed-preview-document" data-ui-scope="editorial-v2"></div></body></html>'} style={{ width, height, transform: `scale(${scale})` }} onLoad={event => setMount(event.currentTarget.contentDocument?.getElementById("fixed-preview-root") || null)} />
      </div>
    </div>
    {mount ? createPortal(children, mount) : null}
  </>;
}

export type FixedEditorSection = { id: string; label: string; description?: string };
export function FixedPageEditor({ sections, activeSection, onSectionChange, fields, preview, dirty, previewHref, toolbar }: {
  sections: FixedEditorSection[]; activeSection: string; onSectionChange: (id: string) => void;
  fields: ReactNode; preview: ReactNode; dirty: boolean; previewHref?: string; toolbar?: ReactNode;
}) {
  const fieldRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    previewRef.current?.querySelectorAll<HTMLElement>("[data-edit-section]").forEach(element => {
      element.dataset.editActive = String(element.dataset.editSection === activeSection);
    });
  }, [activeSection, preview]);
  function select(id: string, focus = false) {
    if (!sections.some(section => section.id === id)) return;
    onSectionChange(id);
    if (focus) window.requestAnimationFrame(() => { Array.from(fieldRef.current?.querySelectorAll<HTMLElement>("input,textarea,select,button") || []).find(element => !element.closest("[hidden]") && element.offsetParent !== null)?.focus(); });
  }
  return <div className="fixed-page-editor">
    <aside className="fixed-editor-panel"><nav className="fixed-editor-sections" aria-label="编辑区域">{sections.map(section => <button type="button" key={section.id} aria-current={activeSection === section.id ? "true" : undefined} onClick={() => select(section.id)}>{section.label}</button>)}</nav>
      <div className="fixed-editor-fields" ref={fieldRef}><h2>{sections.find(section => section.id === activeSection)?.label}</h2><p>{sections.find(section => section.id === activeSection)?.description}</p>{fields}</div>{toolbar}
    </aside>
    <section className="fixed-editor-preview" aria-label="当前输入实时预览"><header><strong>实时预览</strong><span>{dirty ? "有未保存修改 · 仅当前浏览器可见" : "已保存草稿 · 尚不代表公开"}</span>{previewHref ? dirty ? <span>保存后可打开完整预览</span> : <a href={previewHref} target="_blank" rel="noopener">完整预览 ↗</a> : null}</header>
      <PreviewViewport><div ref={element => {
        previewRef.current = element;
        element?.querySelectorAll<HTMLElement>("[data-edit-section]").forEach(section => {
          section.dataset.editActive = String(section.dataset.editSection === activeSection);
        });
      }} data-active-section={activeSection} onClickCapture={event => {
        const target = event.target as Element;
        const row = target.closest<HTMLElement>("[data-edit-row]");
        if (row) window.dispatchEvent(new CustomEvent("knowledge-row-select", { detail: Number(row.dataset.editRow) }));
        const section = target.closest<HTMLElement>("[data-edit-section]");
        if (section && sections.some(item => item.id === section.dataset.editSection)) { event.preventDefault(); event.stopPropagation(); select(section.dataset.editSection || "", true); }
        else if (target.closest("a,button,input,select,textarea,form")) { event.preventDefault(); event.stopPropagation(); }
      }} onSubmitCapture={event => { event.preventDefault(); event.stopPropagation(); }}>{preview}</div></PreviewViewport>
    </section>
  </div>;
}
