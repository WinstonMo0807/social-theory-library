"use client";

import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { EntityPicker, type EntityValue } from "./forms/workflow-fields";
import { AdminPublicPreviewFrame } from "./admin-public-preview-frame";

export function AdminReaderPreview({kind="reader"}: {kind?:"reader"|"book"}) {
  const [works, setWorks] = useState<EntityValue[]>([]);
  const [edition, setEdition] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CollectionPage<WorkLibraryRow> | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const work = works.at(-1)?.id ?? "";
  const selected = data?.results.find((row) => row.id === edition);
  const asset = selected?.current_reader_asset;
  const publicReader = selected?.publication?.public_state === "published" && selected.publication.catalog_revision_active === true && asset?.status === "ready";

  useEffect(() => {
    const controller = new AbortController();
    if (work) void apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?view=editions&work_id=${encodeURIComponent(work)}&page=${page}`, { signal: controller.signal }, getServerSessionCredential())
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "版本读取失败"); });
    return () => controller.abort();
  }, [work, page, retry]);

  function changePage(next: number) {
    setPage(next); setData(null); setEdition(""); setError("");
  }

  return <AdminPublicPreviewFrame title={kind==="book" ? "馆藏页面预览" : "在线阅读预览"} description={kind==="book" ? "预览所选书目的已保存内容。模型建议只有在编辑确认并发布后才向读者展示。" : undefined} src={kind==="book" ? edition ? `/admin/preview/works/${encodeURIComponent(edition)}?embed=1` : null : publicReader && asset ? `/reader/${encodeURIComponent(asset.id)}` : null} emptyMessage={error ? "版本读取失败" : selected ? "此版本暂未提供公开可读的 PDF" : "选择文档后预览"}>
    <EntityPicker label="预览文档" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={works} onChange={(values) => { setWorks(values.slice(-1)); changePage(1); }} />
    {error ? <p role="alert">{error} <button type="button" onClick={() => { setError(""); setRetry((value) => value + 1); }}>重试</button></p> : null}
    {work ? <><label className="admin-v2-reader-edition"><span>出版版本</span><select aria-label="预览出版版本" value={edition} onChange={(event) => setEdition(event.target.value)} disabled={!data}><option value="">{data ? "请选择版本" : "正在读取版本…"}</option>{data?.results.map((row) => <option key={row.id} value={row.id}>{row.label || "出版信息待补"}{row.is_primary ? "（主版本）" : ""}</option>)}</select></label>{data && data.total_pages > 1 ? <nav className="admin-v2-reader-pagination" aria-label="预览版本分页"><button type="button" disabled={!data.previous} onClick={() => changePage(page - 1)}>上一页</button><span>{page} / {data.total_pages}</span><button type="button" disabled={!data.next} onClick={() => changePage(page + 1)}>下一页</button></nav> : null}</> : null}
  </AdminPublicPreviewFrame>;
}
