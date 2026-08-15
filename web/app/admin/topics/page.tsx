import type { Metadata } from "next";
import { TaxonomyAdmin } from "@/components/admin-sections";

export const metadata: Metadata = { title: "主题管理" };

export default function TopicsAdminPage() {
  return <TaxonomyAdmin mode="topic" />;
}
