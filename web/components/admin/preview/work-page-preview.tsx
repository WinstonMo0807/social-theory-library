"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { ActionButton, AsyncStatus } from "@/components/action-feedback";
import { WorkDetailView } from "@/components/work-detail-view";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { Work } from "@/lib/data";
import type { ApiWork } from "@/lib/server-api";

type PreviewPayload = {
  preview_mode: true;
  publication_state: string;
  public_url: string;
  pdf_preview_url: string;
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
    originalTitle: value.subtitle || undefined,
    author: authors.map((row) => row.person.preferred_name).join("、") || "责任者待补",
    year: String(value.edition?.publication_year ?? "出版年不详"),
    kind: ({ book: "图书", journal_article: "期刊论文", thesis: "学位论文", report: "研究报告" } satisfies Record<ApiWork["document_type"], Work["kind"]>)[value.document_type],
    school: value.theories[0]?.name ?? value.topics[0]?.name ?? "社会理论",
    summary: value.abstract || "本馆已收录全文，简介待编辑。",
    cover: coverStyles[0],
    coverImage: normalizePublicResourceUrl(value.cover || value.recommendation_image || "") || undefined,
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
  const [payload, setPayload] = useState<PreviewPayload | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRevision = useRef(0);

  const load = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setMessage("");
    try {
      const result = await apiRequest<PreviewPayload>(
        `/catalog/admin/page-preview/editions/${editionId}/`,
        {},
        getServerSessionCredential(),
      );
      if (requestRevision.current === revision) setPayload(result);
    } catch (reason) {
      if (requestRevision.current === revision) {
        setMessage(reason instanceof Error ? reason.message : "管理员页面预览加载失败。");
      }
    } finally {
      if (requestRevision.current === revision) setLoading(false);
    }
  }, [editionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRevision.current += 1;
    };
  }, [load]);

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
      }}
    />
  );
}
