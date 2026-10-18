import type { Metadata } from "next";
import { WorkFilesWorkspace } from "@/components/admin/library/work-files-workspace";

export const metadata: Metadata = { title: "版本与文件管理" };

export default async function WorkFilesPage({ params }: { params: Promise<{ workId: string }> }) {
  const { workId } = await params;
  return <WorkFilesWorkspace workId={workId} />;
}
