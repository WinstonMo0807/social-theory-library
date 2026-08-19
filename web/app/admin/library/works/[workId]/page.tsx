import type { Metadata } from "next";
import { WorkflowEditor } from "@/components/admin/workflow/workflow-editor";

export const metadata: Metadata = { title: "馆藏维护" };

export default async function WorkMaintenancePage({
  params,
}: {
  params: Promise<{ workId: string }>;
}) {
  const { workId } = await params;
  return <WorkflowEditor mode="maintenance" workId={workId} />;
}
