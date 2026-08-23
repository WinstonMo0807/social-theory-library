import type { Metadata } from "next";
import { WorkflowEditor } from "@/components/admin/workflow/workflow-editor";

export const metadata: Metadata = { title: "馆藏维护" };

export default async function WorkMaintenancePage({
  params,
  searchParams,
}: {
  params: Promise<{ workId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { workId } = await params;
  const query = await searchParams;
  const rawEdition = query.edition;
  const editionId = Array.isArray(rawEdition) ? rawEdition[0] : rawEdition;
  return <WorkflowEditor mode="maintenance" workId={workId} editionId={editionId} />;
}
