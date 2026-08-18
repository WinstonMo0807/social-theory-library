import type { Metadata } from "next";
import { IntakeWorkspace } from "@/components/intake-workspace";

export const metadata: Metadata = { title: "上架工作台" };

export default async function IntakePage({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  return <IntakeWorkspace itemId={itemId} />;
}
