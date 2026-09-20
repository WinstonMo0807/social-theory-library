import { redirect } from "next/navigation";
import { preservingAdminRedirect, type AdminSearchParams } from "@/lib/admin-route-context";

export default async function NewCatalogingPage({searchParams}:{searchParams:Promise<AdminSearchParams>}) {
  redirect(preservingAdminRedirect("/admin/recommendations", await searchParams));
}
