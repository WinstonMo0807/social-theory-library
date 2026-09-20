import { redirect } from "next/navigation";
import { preservingAdminRedirect, type AdminSearchParams } from "@/lib/admin-route-context";
export default async function Page({searchParams}:{searchParams:Promise<AdminSearchParams>}) {
  redirect(preservingAdminRedirect("/admin/processing/health/candidates", await searchParams));
}
