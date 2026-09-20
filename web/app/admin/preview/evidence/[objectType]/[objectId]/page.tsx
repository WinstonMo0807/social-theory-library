import { notFound } from "next/navigation";
import { EvidenceCurationEditor } from "@/components/admin/curation/evidence-curation-editor";
import type { EvidenceCurationType } from "@/lib/api/evidence-curation.types";

export const metadata = { title: "原文策展私有预览", robots: { index: false, follow: false } };
export default async function EvidencePreviewPage({ params }: { params: Promise<{ objectType: string; objectId: string }> }) {
  const { objectType, objectId } = await params;
  if (!["topic", "scholar", "node"].includes(objectType)) notFound();
  return <EvidenceCurationEditor key={`${objectType}:${objectId}`} objectType={objectType as EvidenceCurationType} objectId={objectId} fullPreview />;
}
