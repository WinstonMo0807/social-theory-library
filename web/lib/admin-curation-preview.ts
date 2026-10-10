import { safeAdminHref } from "./admin-route-context";

/** Evidence drafts belong to the owner in the canonical editor route. */
export function evidenceCurationPreviewHref(editHref: string): string {
  const href = safeAdminHref(editHref, "");
  if (!href) return "";
  const url = new URL(href, "https://admin.invalid");
  const match = /^\/admin\/(topics|scholars|theories)\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(url.pathname);
  if (!match || url.searchParams.get("section") !== "passages") return "";
  const type = { topics: "topic", scholars: "scholar", theories: "node" }[match[1].toLowerCase()];
  return `/admin/preview/evidence/${type}/${match[2]}`;
}
