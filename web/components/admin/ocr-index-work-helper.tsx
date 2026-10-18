import Link from "next/link";
import { AlertTriangle, ArrowRight, CheckCircle2, FileSearch } from "lucide-react";

export type ProcessingAttentionItem = {
  id: string;
  title: string;
  source_filename: string;
  processing_url: string;
  ocr: {
    status: string;
    label: string;
    detail: string;
    detected_pages?: number;
    scheduled_pages?: number;
  };
  index: {
    status: string;
    label: string;
    detail: string;
    semantic_status?: string;
    viewpoint_status?: string;
  };
};

export type ProcessingAttentionData = {
  total: number;
  ocr_count: number;
  index_count: number;
  items: ProcessingAttentionItem[];
};

type Props = {
  data?: ProcessingAttentionData;
};

function Stage({ kind, label, detail, attention }: { kind: "ocr" | "index"; label: string; detail: string; attention: boolean }) {
  return (
    <div className={`admin-v307-processing-stage ${attention ? "is-attention" : "is-ready"}`}>
      {attention ? <AlertTriangle size={15} aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />}
      <div>
        <strong>{kind === "ocr" ? "OCR" : "观点索引"} · {label}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

export function OcrIndexWorkHelper({ data }: Props) {
  if (!data) return null;

  return (
    <section className="admin-panel admin-v307-processing-helper" aria-labelledby="processing-helper-title">
      <header>
        <div>
          <p className="admin-v307-section-kicker">处理中心提醒</p>
          <h2 id="processing-helper-title">OCR 与索引</h2>
          <p>先处理这里列出的馆藏，完成后才能稳定进入全文和观点检索。</p>
        </div>
        <Link href="/admin/processing?surface=documents" className="admin-v307-processing-helper-link">打开处理中心 <ArrowRight size={14} /></Link>
      </header>
      <div className="admin-v307-processing-helper-summary" aria-label="待处理数量">
        <span><strong>{data.ocr_count}</strong> 项 OCR 待处理</span>
        <span><strong>{data.index_count}</strong> 项索引待处理</span>
      </div>
      {data.items.length ? (
        <div className="admin-v307-processing-helper-list">
          {data.items.map((item) => (
            <article className="admin-v307-processing-helper-item" key={item.id}>
              <div className="admin-v307-processing-helper-title">
                <FileSearch size={18} aria-hidden="true" />
                <div><strong>{item.title || "未命名馆藏"}</strong><small>{item.source_filename || "文件名待识别"}</small></div>
              </div>
              <div className="admin-v307-processing-stages">
                <Stage kind="ocr" label={item.ocr.label} detail={item.ocr.detail} attention={item.ocr.status !== "succeeded" && item.ocr.status !== "not_required" && item.ocr.status !== "disabled"} />
                <Stage kind="index" label={item.index.label} detail={item.index.detail} attention={item.index.status !== "ready"} />
              </div>
              <Link className="button secondary admin-v307-processing-helper-action" href={item.processing_url}>处理 <ArrowRight size={13} /></Link>
            </article>
          ))}
        </div>
      ) : (
        <p className="admin-v307-processing-helper-empty"><CheckCircle2 size={16} />当前没有需要 OCR 或索引修复的馆藏。</p>
      )}
    </section>
  );
}
