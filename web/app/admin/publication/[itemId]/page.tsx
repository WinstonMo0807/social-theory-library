import { redirect } from "next/navigation";
import { preservingAdminRedirect, type AdminSearchParams } from "@/lib/admin-route-context";

export default async function LegacyPublicationItemPage({
  params,
  searchParams,
}: {
  params: Promise<{ itemId: string }>;
  searchParams: Promise<AdminSearchParams>;
}) {
  const { itemId } = await params;
  redirect(preservingAdminRedirect(`/admin/intake/${encodeURIComponent(itemId)}`, await searchParams, "publication"));
}
