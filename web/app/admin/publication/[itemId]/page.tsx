import { PublicationReviewEntry } from "@/components/admin/workflow/publication-review-entry";
import { firstParam, safeAdminHref, type AdminSearchParams } from "@/lib/admin-route-context";

export default async function PublicationItemPage({
  params,
  searchParams,
}: {
  params: Promise<{ itemId: string }>;
  searchParams: Promise<AdminSearchParams>;
}) {
  const [{itemId},query]=await Promise.all([params,searchParams]);
  return <PublicationReviewEntry key={`${itemId}:${firstParam(query.object)}`} itemId={itemId} objectKind={firstParam(query.object,"upload")} view={firstParam(query.view)==="history"?"desk":"review"} backHref={safeAdminHref(firstParam(query.return_to),"/admin/publication")} />;
}
