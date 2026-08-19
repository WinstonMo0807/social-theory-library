import { PublicationDesk } from "@/components/publication-desk";
import { redirect } from "next/navigation";

export default async function AdminPublicationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawItem = params.item;
  const itemId = Array.isArray(rawItem) ? rawItem[0] : rawItem;
  if (itemId) {
    redirect(`/admin/intake/${encodeURIComponent(itemId)}#publication`);
  }
  return <PublicationDesk />;
}
