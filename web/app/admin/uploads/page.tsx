import type { Metadata } from "next";
import { AdminUpload } from "@/components/admin-upload";
import { UploadSourceContext } from "@/components/admin/workflow/upload-source-context";
import { firstParam, type AdminSearchParams } from "@/lib/admin-route-context";

export const metadata: Metadata = { title: "批量上传" };

export default async function AdminUploadsPage({ searchParams }: { searchParams: Promise<AdminSearchParams> }) {
  const itemId = firstParam((await searchParams).item);
  return <>{itemId ? <UploadSourceContext itemId={itemId} /> : null}<AdminUpload /></>;
}
