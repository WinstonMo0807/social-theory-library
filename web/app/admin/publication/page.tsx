import { redirect } from "next/navigation";
import { preservingAdminRedirect } from "@/lib/admin-route-context";

export default async function AdminPublicationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawItem = params.item;
  const itemId = Array.isArray(rawItem) ? rawItem[0] : rawItem;
  if (itemId) {
    redirect(preservingAdminRedirect(`/admin/intake/${encodeURIComponent(itemId)}`, params, "publication", ["item"]));
  }
  redirect(preservingAdminRedirect("/admin/review?category=publication_ready", params));
}
