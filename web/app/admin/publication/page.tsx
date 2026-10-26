import { PublicationDesk } from "@/components/publication-desk";
import { redirect } from "next/navigation";
import { preservingAdminRedirect } from "@/lib/admin-route-context";

export default async function AdminPublicationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  if(params.site==="1")redirect(preservingAdminRedirect("/admin/about?panel=history",params,undefined,["site","panel"]));
  const rawItem = params.item;
  const itemId = Array.isArray(rawItem) ? rawItem[0] : rawItem;
  if (itemId) {
    redirect(preservingAdminRedirect(`/admin/intake/${encodeURIComponent(itemId)}`, params, "publication", ["item"]));
  }
  return <PublicationDesk/>;
}
