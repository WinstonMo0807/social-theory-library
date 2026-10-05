"use client";

import { Monitor, Smartphone } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export function AdminPublicPreviewFrame({
  title,
  description,
  src,
  emptyMessage = "选择内容后预览",
  children,
}: {
  title: string;
  description?: string;
  src?: string | null;
  emptyMessage?: string;
  children?: ReactNode;
}) {
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [availableWidth, setAvailableWidth] = useState(600);
  const viewport = useRef<HTMLDivElement>(null);
  const width = device === "desktop" ? 1280 : 390;
  const scale = Math.min(1, availableWidth / width);

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setAvailableWidth(Math.max(1, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <aside className="admin-v2-public-preview admin-panel" aria-label="读者会看到什么">
      <header>
        <div><p className="eyebrow">读者会看到什么</p><h2>{title}</h2></div>
        <div className="admin-v2-preview-actions">
          <div className="admin-v2-preview-devices" role="group" aria-label="预览设备">
            <button type="button" aria-label="电脑预览" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}><Monitor size={16} /><span>电脑</span></button>
            <button type="button" aria-label="手机预览" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}><Smartphone size={16} /><span>手机</span></button>
          </div>
          {src ? <a href={src} target="_blank" rel="noreferrer">放大查看 ↗</a> : <span className="admin-v2-preview-enlarge-disabled">放大查看 ↗</span>}
        </div>
      </header>
      {description ? <p>{description}</p> : null}
      {children ? <div className="admin-v2-preview-controls">{children}</div> : null}
      <div className="admin-v2-preview-viewport" ref={viewport} data-device={device}>
        {src ? <div className="admin-v2-preview-page" style={{ width: width * scale, height: 670 }}><iframe src={src} title={`${title}（${device === "desktop" ? "电脑" : "手机"}）`} loading="lazy" style={{ width, height: 670 / scale, transform: `scale(${scale})` }} /></div> : <p className="admin-v2-preview-empty">{emptyMessage}</p>}
      </div>
    </aside>
  );
}
