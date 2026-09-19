import { publicationPresentation, publicationPublicHref, type CatalogPublication } from "@/lib/api/admin-collections";

/** Passive upload-card result: UploadItem.status is never public eligibility. */
export function UploadPublicationResult({ editionId, publication }: { editionId: string | null; publication?: CatalogPublication }) {
  if (!editionId) return <div data-upload-publication="unbound"><dt>公开结果</dt><dd>尚未建立出版版本，上传来源和处理记录仍保留。</dd></div>;
  const state = publicationPresentation(publication);
  const href = publicationPublicHref(publication);
  return <div data-upload-publication={publication?.public_state || "unknown"}><dt>公开结果</dt><dd><strong className={`status-${state.tone}`}>{state.label}</strong>{publication?.detail ? <small>{publication.detail}</small> : <small>请在当前版本工作页重新读取公开条件；上传处理完成不等于已公开。</small>}{href ? <a href={href} target="_blank" rel="noreferrer">核验当前公开页面</a> : null}</dd></div>;
}
