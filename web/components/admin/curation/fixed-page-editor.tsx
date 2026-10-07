"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Search, Monitor, Smartphone } from "lucide-react";

/** An isolated viewport keeps public media queries and typography identical to the page. */
export function PreviewViewport({ children, device }: { children: ReactNode; device?: "desktop" | "mobile" }) {
  const [chosenWidth, setWidth] = useState(1120);
  const width = device ? device === "mobile" ? 390 : 1120 : chosenWidth;
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
    {!device ? <div className="fixed-preview-tools" role="group" aria-label="预览视口">
      <button type="button" aria-pressed={width === 1120} onClick={() => setWidth(1120)}>桌面 · 1120</button>
      <button type="button" aria-pressed={width === 390} onClick={() => setWidth(390)}>移动 · 390</button>
      <button type="button" aria-pressed={!fitWidth} onClick={() => setFitWidth(value => !value)}>{fitWidth ? "放大至实际大小" : "适应预览栏"}</button>
      <span>{Math.round(scale * 100)}% · 点击页面内容定位字段</span>
    </div> : null}
    <div ref={canvasRef} className="fixed-preview-canvas" data-fit-width={fitWidth}>
      <div className="fixed-preview-stage" style={{ width: width * scale, height: height * scale }}>
        <iframe ref={frameRef} title="当前输入的公开页面预览" className="fixed-preview-frame" srcDoc={'<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="fixed-preview-root" class="fixed-preview-document" data-ui-scope="editorial-v2"></div></body></html>'} style={{ width, height, transform: `scale(${scale})` }} onLoad={event => setMount(event.currentTarget.contentDocument?.getElementById("fixed-preview-root") || null)} />
      </div>
    </div>
    {mount ? createPortal(children, mount) : null}
  </>;
}

export type FixedEditorSection = { id: string; label: string; description?: string };
export function FixedPageEditor({ sections, navigationSections = sections, activeSection, onSectionChange, fields, preview, dirty, previewHref, publishedPreview, publishedHref, toolbar, previewToolbar, hideFieldHeading = false, previewFooter, fieldHeader, fieldHeading, expandIcon }: {
  sections: FixedEditorSection[]; activeSection: string; onSectionChange: (id: string) => void;
  navigationSections?: FixedEditorSection[];
  fields: ReactNode; preview: ReactNode; dirty: boolean; previewHref?: string; publishedPreview?: ReactNode; publishedHref?: string; toolbar?: ReactNode; previewToolbar?: ReactNode; hideFieldHeading?: boolean; previewFooter?: ReactNode | ((perspective:"draft" | "published") => ReactNode);
  fieldHeader?: ReactNode; fieldHeading?: string; expandIcon?: ReactNode;
}) {
  const fieldRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const fullPreviewRef = useRef<HTMLDialogElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [perspective, setPerspective] = useState<"draft" | "published">("draft");
  const canViewPublished = publishedPreview !== undefined || Boolean(publishedHref);
  const fullHref = perspective === "published" ? publishedHref : !dirty ? previewHref : undefined;
  useEffect(() => {
    previewRef.current?.querySelectorAll<HTMLElement>("[data-edit-section]").forEach(element => {
      element.dataset.editActive = String(element.dataset.editSection === activeSection);
    });
  }, [activeSection, preview]);
  function select(id: string, focus = false) {
    if (!sections.some(section => section.id === id)) return;
    onSectionChange(id);
    if (focus) window.requestAnimationFrame(() => {
      const groups = Array.from(fieldRef.current?.querySelectorAll<HTMLElement>(`[data-field-section="${CSS.escape(id)}"]`) || []);
      const controls = groups.length ? groups.flatMap(group=>Array.from(group.querySelectorAll<HTMLElement>("input,textarea,select,button"))) : Array.from(fieldRef.current?.querySelectorAll<HTMLElement>("input,textarea,select,button") || []);
      controls.find(element => !element.closest("[hidden]") && element.offsetParent !== null)?.focus();
    });
  }
  return <div className="fixed-page-editor">
    <aside className="fixed-editor-panel">{fieldHeader}<nav className="fixed-editor-sections" aria-label="编辑区域">{navigationSections.map(section => <button type="button" key={section.id} aria-current={activeSection === section.id ? "true" : undefined} onClick={() => select(section.id)}>{section.label}</button>)}</nav>
      <div className="fixed-editor-fields" ref={fieldRef}>{!hideFieldHeading ? <><h2>{fieldHeading || sections.find(section => section.id === activeSection)?.label}</h2><p>{sections.find(section => section.id === activeSection)?.description}</p></> : null}{fields}</div>{toolbar}
    </aside>
    <section className="fixed-editor-preview" aria-label="当前输入实时预览"><header><strong>读者会看到什么</strong><span>{perspective === "published" ? "当前线上内容" : dirty ? "当前输入 · 尚未保存" : "已保存内容预览"}</span></header>
      <div className="selected-preview-tools fixed-editor-preview-tools"><div role="group" aria-label="预览内容"><button type="button" aria-pressed={perspective === "draft"} onClick={() => setPerspective("draft")}>修改后</button><button type="button" aria-pressed={perspective === "published"} disabled={!canViewPublished} title={!canViewPublished ? "当前对象尚无线上预览" : undefined} onClick={() => setPerspective("published")}>当前线上</button></div><div role="group" aria-label="预览尺寸"><button type="button" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}><Monitor size={15}/>电脑</button><button type="button" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}><Smartphone size={15}/>手机</button></div><button type="button" onClick={() => {setExpanded(true);fullPreviewRef.current?.showModal();}}>{expandIcon || <Search size={17}/>}放大查看</button></div>
      {previewToolbar}
      <PreviewViewport device={device}>{perspective === "published" ? publishedPreview ?? (publishedHref ? <iframe src={publishedHref} title="当前线上页面" style={{width:"100%",height:1000,border:0}}/> : <p className="empty-state">—</p>) : <div ref={element => {
        previewRef.current = element;
        element?.querySelectorAll<HTMLElement>("[data-edit-section]").forEach(section => {
          section.dataset.editActive = String(section.dataset.editSection === activeSection);
        });
      }} data-active-section={activeSection} onClickCapture={event => {
        const target = event.target as Element;
        const row = target.closest<HTMLElement>("[data-edit-row]");
        const rowHandled = row ? !window.dispatchEvent(new CustomEvent("knowledge-row-select", { detail: Number(row.dataset.editRow), cancelable:true })) : false;
        const section = target.closest<HTMLElement>("[data-edit-section]");
        if (section && sections.some(item => item.id === section.dataset.editSection)) { event.preventDefault(); event.stopPropagation(); select(section.dataset.editSection || "", !rowHandled); }
        else if (target.closest("a,button,input,select,textarea,form")) { event.preventDefault(); event.stopPropagation(); }
      }} onSubmitCapture={event => { event.preventDefault(); event.stopPropagation(); }}>{preview}</div>}</PreviewViewport>
      {typeof previewFooter === "function" ? previewFooter(perspective) : previewFooter}
    </section>
    <dialog className="fixed-preview-dialog" ref={fullPreviewRef} onClose={() => setExpanded(false)}><header><strong>{perspective === "published" ? "当前线上内容" : dirty ? "当前输入 · 尚未保存" : "已保存内容预览"}</strong>{fullHref ? <a href={fullHref} target="_blank" rel="noopener">在新标签页打开已保存页面</a> : null}<button type="button" onClick={() => fullPreviewRef.current?.close()}>关闭预览</button></header>{expanded ? <PreviewViewport device={device}>{perspective === "published" ? publishedPreview ?? (publishedHref ? <iframe src={publishedHref} title="当前线上页面放大预览" style={{width:"100%",height:1000,border:0}}/> : null) : <div inert>{preview}</div>}</PreviewViewport> : null}</dialog>
  </div>;
}
