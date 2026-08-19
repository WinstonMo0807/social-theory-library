import { redirect } from "next/navigation";

export default async function LegacyPublicationItemPage({
  params,
}: {
  params: Promise<{ itemId: string }>;
}) {
  const { itemId } = await params;
  redirect(`/admin/intake/${encodeURIComponent(itemId)}#publication`);
}
