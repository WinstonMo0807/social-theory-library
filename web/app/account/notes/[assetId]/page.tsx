import type { Metadata } from "next";
import { ReaderBookNotes } from "@/components/reader-book-notes";

export const metadata: Metadata = { title: "作品笔记" };

export default async function ReaderBookNotesPage({
  params,
}: {
  params: Promise<{ assetId: string }>;
}) {
  const { assetId } = await params;
  return <ReaderBookNotes assetId={assetId} />;
}
