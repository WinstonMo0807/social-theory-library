"use client";

import Link from "next/link";
import { ChevronDown, FileText } from "lucide-react";
import type { CatalogSearchWork } from "@/lib/api/catalog-search.client";
import { adaptApiWork } from "@/lib/public-data-adapters";
import { BookCover } from "./ui";
import { SaveWorkButton } from "./save-work-button";
import { AssetDownloadButton } from "./asset-download-button";
import { AddWorkToListButton } from "./add-work-to-list-button";
import { SharedCitationButton } from "./shared-citation-overlay";

const languages: Record<string, string> = { "zh-CN": "中文", "zh-TW": "繁体中文", zh: "中文", en: "英文", fr: "法文", de: "德文", ja: "日文" };

export function CatalogResultCard({ row }: { row: CatalogSearchWork }) {
  const work = adaptApiWork(row);
  const editions = row.editions ?? (row.edition ? [row.edition] : []);
  const edition = row.edition;
  const anyReadable = editions.some(version => version.readable_asset);
  const authors = edition?.contributors.filter(person => person.role === "author").map(person => person.person.preferred_name) ?? [];
  const translators = edition?.contributors.filter(person => person.role === "translator").map(person => person.person.preferred_name) ?? [];
  const journal = [edition?.journal_title, edition?.publication_year ? `${edition.publication_year} 年` : null, edition?.volume ? `第 ${edition.volume} 卷` : null, edition?.issue ? `第 ${edition.issue} 期` : null, edition?.page_range].filter(Boolean).join(" · ");
  const publication = [edition?.publication_year, edition?.publisher, languages[row.language ?? ""] || row.language].filter(Boolean).join(" · ");
  return <article className="stl4-catalog-result">
    <div className="stl4-catalog-result-main">
      <Link href={`/works/${work.slug}`} className="stl4-catalog-cover" aria-label={`查看${row.title}`}><BookCover work={work} size="small" /></Link>
      <div className="stl4-catalog-result-copy">
        <p className="stl4-catalog-result-tags"><span>{work.kind}</span>{editions.length > 1 ? <span>作品整合 · {editions.length} 个版本</span> : null}</p>
        <h3><Link href={`/works/${work.slug}`}>{row.title}</Link></h3>
        <p>{authors.length ? `${authors.join("、")} 著` : "作者信息待补充"}{translators.length ? ` · ${translators.join("、")} 译` : ""}</p>
        <p>{row.document_type === "journal_article" ? journal : publication}</p>
        {row.abstract ? <details className="stl4-catalog-abstract"><summary><span>{row.abstract}</span></summary><p>{row.abstract}</p></details> : null}
        <span className={`stl4-catalog-availability ${anyReadable ? "is-readable" : ""}`}>{anyReadable ? "可在线阅读" : "仅书目信息"}</span>
      </div>
      <aside className="stl4-catalog-publication" aria-label="出版信息">
        <p className="stl4-catalog-publication-label">{row.document_type === "journal_article" ? "发表信息" : "出版信息"}</p>
        {editions.length > 1 ? <div className="stl4-catalog-version-previews">{editions.slice(0, 2).map(version => <div key={version.id}>
          <span>{[version.version_label, version.publisher, version.publication_year].filter(Boolean).join(" · ") || "版本信息待补充"}</span>
          {version.readable_asset ? <div><Link href={`/reader/${version.readable_asset.id}`}><FileText size={13} />阅读</Link><AssetDownloadButton assetId={version.readable_asset.id} /></div> : <small>仅书目信息</small>}
        </div>)}</div> : <p>{row.document_type === "journal_article" ? journal : publication || "出版信息待补充"}</p>}
        <div className="stl4-catalog-result-actions">
        {editions.length < 2 && edition?.readable_asset ? <><Link className="stl4-catalog-read" href={`/reader/${edition.readable_asset.id}`}>在线阅读</Link><AssetDownloadButton assetId={edition.readable_asset.id} /></> : null}
        <SaveWorkButton workId={row.id} /><AddWorkToListButton workId={row.id} title={row.title} />
        {edition ? <SharedCitationButton editionId={edition.id}>引用</SharedCitationButton> : null}
        </div>
      </aside>
    </div>
    {editions.length > 1 ? <details className="stl4-catalog-versions">
      <summary><strong>可查看的版本（{editions.length}）</strong><ChevronDown size={16} /></summary>
      <div className="stl4-catalog-version-table" role="table" aria-label={`${row.title}的出版版本`}>
        <div role="row" className="stl4-catalog-version-head"><span role="columnheader">版本信息</span><span role="columnheader">语言</span><span role="columnheader">格式</span><span role="columnheader">可用性</span><span role="columnheader">操作</span></div>
        {editions.map(version => {
          const language = "language" in version && typeof version.language === "string" ? version.language : row.language ?? "";
          const credits = version.contributors.filter(person => person.role === "translator").map(person => person.person.preferred_name).join("、");
          const matched = row.matched_edition_ids?.includes(version.id);
          return <div role="row" className={`stl4-catalog-version-row${matched ? " is-matched" : ""}`} key={version.id}>
            <div role="cell"><Link href={`/works/${version.public_slug || version.id}`}>{[version.publication_year, version.publisher, version.version_label].filter(Boolean).join(" · ") || "版本书目信息待补充"}</Link>{credits ? <small>{credits} 译</small> : null}{matched ? <small className="stl4-catalog-version-match">符合当前条件</small> : null}</div>
            <span role="cell">{languages[language] || language || "未标注"}</span>
            <span role="cell">{version.readable_asset ? <><FileText size={12} /> PDF</> : "—"}</span>
            <span role="cell">{version.readable_asset ? "可在线阅读 / 下载" : "仅书目信息"}</span>
            <div role="cell" className="stl4-catalog-version-actions">{version.readable_asset ? <><Link className="stl4-catalog-read" href={`/reader/${version.readable_asset.id}`}>阅读</Link><AssetDownloadButton assetId={version.readable_asset.id} /></> : <Link href={`/works/${version.public_slug || version.id}`}>查看书目</Link>}</div>
          </div>;
        })}
      </div>
      <Link className="stl4-catalog-version-detail" href={`/works/${work.slug}`}>查看作品详情 →</Link>
    </details> : <div className="stl4-catalog-single-actions"><Link href={`/works/${work.slug}`}>查看书目</Link>{work.readerHref ? <Link href={work.readerHref}>在线阅读 →</Link> : null}</div>}
  </article>;
}
