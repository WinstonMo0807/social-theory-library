import type { Metadata } from "next";
import { ScholarsAdmin } from "@/components/admin-sections";

export const metadata: Metadata = { title: "编辑学者" };

export default async function ScholarEditorPage({
  params,
}: {
  params: Promise<{ scholarId: string }>;
}) {
  const { scholarId } = await params;
  return <ScholarsAdmin scholarId={scholarId} />;
}
