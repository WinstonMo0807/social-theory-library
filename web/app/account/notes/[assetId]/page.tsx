import type { Metadata } from "next";
import { ReaderNotebook } from "@/components/research/reader-notebook";

export const metadata: Metadata = { title: "作品笔记" };

export default async function ReaderBookNotesPage({
  params,
}: {
  params: Promise<{ assetId: string }>;
}) {
  const { assetId } = await params;
  return <ReaderNotebook assetId={assetId} />;
}
