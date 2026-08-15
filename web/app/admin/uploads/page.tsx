import type { Metadata } from "next";
import { AdminUpload } from "@/components/admin-upload";

export const metadata: Metadata = { title: "批量上传" };

export default function AdminUploadsPage() {
  return <AdminUpload />;
}
