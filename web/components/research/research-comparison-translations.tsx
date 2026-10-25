"use client";

import Link from "next/link";
import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { useParallelResource } from "@/components/reader/use-parallel-resource";
import type { ParallelVersions } from "@/lib/api/parallel-reader.client";
import { parallelEvidenceHref, parallelSourceMatches } from "@/lib/api/parallel-navigation";
import type { ResolvedEvidence } from "@/lib/api/research.client";

export function ResearchComparisonTranslations({ reference, onClose }: { reference: ResolvedEvidence; onClose: () => void }) {
  const first = reference.anchors?.[0] || reference;
  const resource = useParallelResource<ParallelVersions>(reference.source_status === "available" && first.asset_id ? `/catalog/parallel/versions/?asset_id=${encodeURIComponent(first.asset_id)}` : "");
  const [edition, setEdition] = useState("");
  const source = resource.data?.versions.find(row => row.asset_id === first.asset_id);
  const available = reference.source_status === "available" && parallelSourceMatches(source, first.asset_id || "", first.document_revision_id || "");
  const versions = resource.data?.versions.filter(row => row.asset_id !== first.asset_id || !row.asset_id) || [];
  const target = versions.find(row => row.edition_id === edition);
  const href = available && target?.state === "available" ? parallelEvidenceHref(reference, target) : "";
  return <Dialog open onRequestClose={onClose} className="stl4-research-dialog stl4-comparison-translations" aria-labelledby="comparison-translations-title">
    <h2 id="comparison-translations-title">原文与译本差异</h2>
    <p>{reference.title || "所选文献"} · PDF 第 {first.pdf_page || "—"} 页{(reference.anchors?.length || 0) > 1 ? "（跨页引用的起始位置）" : ""}</p>
    {resource.loading ? <p role="status">正在读取已关联的出版版本……</p> : resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p> : !available ? <p role="alert">原引用的文件或文字修订已变化，暂不能继续此处对照。原选材和笔记仍保留，请回到选材重新核对来源。</p> : <>
      <blockquote>{reference.quote || reference.text || "请打开原文核对所选内容。"}</blockquote>
      <label htmlFor="comparison-translation-version">选择需要对照的译本或版本</label>
      <select id="comparison-translation-version" value={edition} onChange={event => setEdition(event.target.value)}><option value="">请选择一个版本</option>{versions.map(row => <option key={row.edition_id} value={row.edition_id}>{row.title} · {row.language || "语言待补"} · {row.publication_year || "年份待补"} · {row.version_label || "版本信息待补"}{row.state === "metadata_only" ? "（暂无正文）" : ""}</option>)}</select>
      {target ? <p>{target.authors.join("、")} {target.notice}</p> : null}
      {!versions.length ? <p>当前没有已公开关联的其他版本。可以提交版本建议，不会根据同名书目猜测译本。</p> : null}
      {resource.data?.truncated ? <p>版本关系较多，此处仅显示当前返回的范围；可提交需要补充的版本建议。</p> : null}
      <p>在并读页中分别定位原文和译文，再明确确认对应关系。不同版本的页码不自动等同，术语差异和判断保存到你本人的对齐笔记。</p>
    </>}
    <footer><button type="button" onClick={onClose}>返回比较</button><Link href="/feedback?category=content" target="_blank" rel="noreferrer">提交版本建议</Link>{href ? <Link className="stl4-research-secondary" href={href} target="_blank" rel="noreferrer">查看译本对照 →</Link> : null}</footer>
  </Dialog>;
}
