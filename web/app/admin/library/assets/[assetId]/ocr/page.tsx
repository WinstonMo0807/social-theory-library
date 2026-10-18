import type { Metadata } from "next";
import { OCRWorkspaceView } from "@/components/admin/library/ocr-workspace";

export const metadata: Metadata = { title: "文字识别与质检" };
export default async function OCRPage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return <OCRWorkspaceView assetId={assetId} />;
}
