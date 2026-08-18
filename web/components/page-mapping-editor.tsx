"use client";

import { Check, ExternalLink, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type MappingPage = {
  id: string;
  file_page_index: number;
  printed_page_label: string;
  source: string;
  confidence: number;
  is_manual: boolean;
  is_anchor: boolean;
  reader_url: string;
};

type MappingPayload = {
  asset_id: string;
  edition_id: string;
  title: string;
  status: string;
  page_count: number;
  pagination: { page: number; page_size: number; total: number };
  segments: {
    id: string;
    start_file_page_index: number;
    end_file_page_index: number | null;
    start_label: string;
    style: string;
    source: string;
    confidence: number;
  }[];
  pages: MappingPage[];
};

export function PageMappingEditor({ assetId, onMessage }: { assetId: string; onMessage: (message: string) => void }) {
  const [data, setData] = useState<MappingPayload | null>(null);
  const [pending, setPending] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [segment, setSegment] = useState({ start: "1", end: "", label: "1", style: "arabic" });
  const [pageNumber, setPageNumber] = useState(1);

  const load = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    setPending(true);
    try {
      const payload = await apiRequest<MappingPayload>(`/catalog/admin/assets/${assetId}/page-mapping/?page=${pageNumber}&page_size=50`, {}, token);
      setData(payload);
      setDrafts(Object.fromEntries(payload.pages.map((page) => [page.file_page_index, page.printed_page_label])));
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "页码映射读取失败。");
    } finally {
      setPending(false);
    }
  }, [assetId, onMessage, pageNumber]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function action(body: Record<string, unknown>, success: string) {
    const token = getServerSessionCredential();
    if (!token) return;
    setPending(true);
    try {
      await apiRequest(`/catalog/admin/assets/${assetId}/page-mapping/`, {
        method: "POST",
        body: JSON.stringify(body),
      }, token);
      onMessage(success);
      await load();
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "页码操作失败。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="page-mapping-editor">
      <header>
        <div><h3>引用页码映射</h3><p>阅读定位使用 PDF 页序，引用输出使用书页上印刷的页码。</p></div>
        <span>{data?.status === "ready" ? "已确认" : "待校对"}</span>
      </header>
      <div className="page-mapping-actions">
        <button type="button" onClick={() => void action({ action: "analyze" }, "页码已按人工映射、PDF PageLabels、OCR 连续性和回退顺序重新分析。") } disabled={pending}><RefreshCw size={14} />重新分析</button>
        <button type="button" onClick={() => void action({ action: "confirm" }, "页码映射已经确认，引用生成器将使用当前标签。") } disabled={pending}><Check size={14} />确认当前映射</button>
      </div>
      <section className="page-segment-editor">
        <label><span>PDF 起始页</span><input type="number" min="1" value={segment.start} onChange={(event) => setSegment({ ...segment, start: event.target.value })} /></label>
        <label><span>PDF 结束页</span><input type="number" min="1" value={segment.end} onChange={(event) => setSegment({ ...segment, end: event.target.value })} placeholder="留空到下一段" /></label>
        <label><span>起始印刷页码</span><input value={segment.label} onChange={(event) => setSegment({ ...segment, label: event.target.value })} /></label>
        <label><span>编号样式</span><select value={segment.style} onChange={(event) => setSegment({ ...segment, style: event.target.value })}><option value="arabic">阿拉伯数字</option><option value="roman_lower">小写罗马数字</option><option value="roman_upper">大写罗马数字</option><option value="custom">自定义标签</option><option value="none">无页码</option></select></label>
        <button type="button" disabled={pending} onClick={() => void action({
          action: "create_segment",
          start_file_page_index: Number(segment.start),
          end_file_page_index: segment.end ? Number(segment.end) : null,
          start_label: segment.label,
          style: segment.style,
        }, "页码分段已经保存并应用。") }><Save size={14} />保存分段</button>
      </section>
      {data?.segments.length ? <div className="page-segment-list">{data.segments.map((item) => <p key={item.id}><strong>PDF {item.start_file_page_index}{item.end_file_page_index ? ` 至 ${item.end_file_page_index}` : " 起"}</strong><span>{item.start_label || "无页码"} · {item.style}</span></p>)}</div> : null}
      {data ? <nav className="page-mapping-pagination" aria-label="页码校对分页"><button type="button" disabled={pending || data.pagination.page <= 1} onClick={() => setPageNumber((value) => Math.max(1, value - 1))}>上一组</button><span>PDF 第 {(data.pagination.page - 1) * data.pagination.page_size + 1} 至 {Math.min(data.pagination.page * data.pagination.page_size, data.pagination.total)} 页，共 {data.pagination.total} 页</span><button type="button" disabled={pending || data.pagination.page * data.pagination.page_size >= data.pagination.total} onClick={() => setPageNumber((value) => value + 1)}>下一组</button></nav> : null}
      <div className="admin-table-scroll page-mapping-table"><table><thead><tr><th>PDF 页</th><th>印刷页码</th><th>来源</th><th>置信度</th><th>操作</th></tr></thead><tbody>
        {data?.pages.map((page) => <tr key={page.id}><td>第 {page.file_page_index} 页</td><td><input aria-label={`PDF 第 ${page.file_page_index} 页的印刷页码`} value={drafts[page.file_page_index] ?? ""} onChange={(event) => setDrafts({ ...drafts, [page.file_page_index]: event.target.value })} /></td><td>{page.is_manual ? "人工" : ({ pdf_page_labels: "PDF PageLabels", embedded_text: "PDF 页眉页脚", ocr: "OCR", sequence: "连续页码推算", file_index: "尚未识别" }[page.source] ?? page.source)}</td><td>{Math.round(page.confidence * 100)}%</td><td><button type="button" disabled={pending} onClick={() => void action({ action: "set_page", file_page_index: page.file_page_index, printed_page_label: drafts[page.file_page_index] ?? "", is_anchor: true }, `PDF 第 ${page.file_page_index} 页的引用页码已保存。`)}><Save size={13} />保存锚点</button><a href={page.reader_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />定位</a></td></tr>)}
        {!data?.pages.length ? <tr><td colSpan={5}>{pending ? "正在读取页码……" : "尚无逐页数据。"}</td></tr> : null}
      </tbody></table></div>
      {data && data.pagination.total > data.pages.length ? <p className="admin-help">逐页校对按 50 页分页。已知连续段可用上方锚点规则一次生成，之后仍可修改单页。</p> : null}
    </div>
  );
}
