import { redirect } from "next/navigation";
import { preservingAdminRedirect, type AdminSearchParams } from "@/lib/admin-route-context";

export default async function CandidateReviewPage({ searchParams }: { searchParams: Promise<AdminSearchParams> }) {
  redirect(preservingAdminRedirect("/admin/knowledge", await searchParams));
}
