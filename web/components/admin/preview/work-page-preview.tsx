"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { ActionButton, AsyncStatus } from "@/components/action-feedback";
import { WorkDetailView } from "@/components/work-detail-view";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { Work } from "@/lib/data";
import type { ApiWork } from "@/lib/api/public-catalog";
import { useSearchParams } from "next/navigation";
import { safeAdminHref } from "@/lib/admin-route-context";

type PreviewPayload = {
  preview_mode: true;
  publication_state: string;
  editorial_revision: {
    id: string;
    revision: number;
    changed_fields: string[];
    has_conflict: boolean;
  } | null;
  public_url: string;
  pdf_preview_url: string;
  return_url: string;
  work: ApiWork;
};

const coverStyles: Work["cover"][] = ["dark", "paper", "cream", "line"];

function adaptPreviewWork(value: ApiWork): Work {
  const authors = value.edition?.contributors.filter((row) => row.role === "author") ?? [];
  return {
    id: value.edition?.readable_asset?.id ?? value.id,
    workId: value.id,
    editionId: value.edition?.id,
    slug: value.edition?.public_slug || value.id,
    title: value.title,
    subtitle: value.subtitle || undefined,
    originalTitle: value.original_title || undefined,
    originalLanguage: value.original_language,
    firstPublicationDate: value.first_publication_date,
    version: value.edition ? { ...value.edition, language: value.language || "", availability: value.edition.readable_asset ? "readable" : "metadata" } : undefined,
    versions: value.editions,
    author: authors.map((row) => row.person.preferred_name).join("、") || "作者待确认",
    year: String(value.edition?.publication_year ?? "出版年不详"),
    kind: ({ book: "图书", journal_article: "期刊论文", journal_issue: "整期期刊", thesis: "学位论文", report: "研究报告" } satisfies Record<ApiWork["document_type"], Work["kind"]>)[value.document_type],
    school: value.theories[0]?.name ?? value.topics[0]?.name ?? "社会理论",
    summary: value.abstract || "简介待编辑。",
    cover: coverStyles[0],
    coverImage: normalizePublicResourceUrl(value.cover || value.recommendation_image || "") || undefined,
    coverSources: (value.cover ? value.cover_media : value.recommendation_media)?.renditions.map((row) => ({ ...row, url: normalizePublicResourceUrl(row.url) })),
    coverAlt: (value.cover ? value.cover_media : value.recommendation_media)?.alt_text || undefined,
    pages: value.edition?.readable_asset?.page_count ?? 0,
    language: value.language,
    authors: authors.map((row) => ({ name: row.person.preferred_name, slug: row.person.scholar_slug })),
    theories: value.theories,
    topics: value.topics,
    theoryAssociations: value.theory_associations ?? [],
    curatedClaims: value.curated_claims,
    outline: value.outline ?? [],
  };
}

export function AdminWorkPagePreview({
  editionId,
  footer,
}: {
  editionId: string;
  footer: ReactNode;
}) {
  const routeParams = useSearchParams();
  const user = useAdminSession(), owner = user ? String(user.id) : "";
  const version = routeParams.get("version") || "", fingerprint = routeParams.get("fingerprint") || "", frame = routeParams.get("frame") === "1";
  const [payload, setPayload] = useState<PreviewPayload | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRevision = useRef(0);
  const lifetime = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setPayload(null);
    setMessage("");
    try {
      if (frame && (!/^[0-9a-f]{64}$/.test(version) || !/^[0-9a-f]{64}$/.test(fingerprint))) throw Error("请从发布前检查重新打开当前版本预览。");
      const signal = AbortSignal.any([lifetime.current!.signal, AbortSignal.timeout(30000)]);
      const query = version || fingerprint ? `?${new URLSearchParams({version, fingerprint})}` : "";
      const result = await withPrivateOwner(owner, () => apiRequest<PreviewPayload>(
        `/catalog/admin/page-preview/editions/${editionId}/${query}`, {signal, headers:{"X-Editor-Owner":owner}}, getServerSessionCredential()), signal);
      if (result.work.edition?.id !== editionId) throw Error("预览与选定版本不一致，请返回检查。");
      if (requestRevision.current === revision) setPayload(result);
    } catch (reason) {
      if (requestRevision.current === revision) {
        setMessage(reason instanceof Error ? reason.message : "管理员页面预览加载失败。");
      }
    } finally {
      if (requestRevision.current === revision) setLoading(false);
    }
  }, [editionId, owner, version, fingerprint, frame]);

  useEffect(() => {
    if (!owner) return;
    const controller = new AbortController(); lifetime.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => {controller.abort();requestRevision.current += 1;setPayload(null);setMessage("账户已变化，请重新打开预览。");setLoading(false);});
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => {
      controller.abort(); unsubscribe();
      window.clearTimeout(timer);
      requestRevision.current += 1;
    };
  }, [load, owner]);

  useEffect(() => {
    if (frame && !loading) window.parent.postMessage({type:"stl:publication-preview",editionId,version,fingerprint,ok:Boolean(payload)&&!message},window.location.origin);
  }, [frame, loading, payload, message, editionId, version, fingerprint]);

  const work = useMemo(() => payload ? adaptPreviewWork(payload.work) : null, [payload]);
  if (!work || !payload) {
    return (
      <div className="admin-page admin-page-preview-state">
        <AsyncStatus
          state={loading ? "pending" : "error"}
          message={loading ? "正在生成管理员页面预览……" : message || "预览不可用。"}
          assertive={!loading}
        />
        {!loading ? (
          <ActionButton className="button secondary" onClick={() => void load()}>
            <RefreshCw size={15} />重试
          </ActionButton>
        ) : null}
      </div>
    );
  }
  return (
    <WorkDetailView
      work={work}
      footer={footer}
      preview={{
        publicationState: payload.publication_state,
        pdfPreviewUrl: normalizePublicResourceUrl(payload.pdf_preview_url),
        returnHref: safeAdminHref(routeParams.get("return_to"), payload.return_url),
        draftRevision: payload.editorial_revision
          ? {
              revision: payload.editorial_revision.revision,
              changedFields: payload.editorial_revision.changed_fields,
              hasConflict: payload.editorial_revision.has_conflict,
            }
          : null,
      }}
    />
  );
}
