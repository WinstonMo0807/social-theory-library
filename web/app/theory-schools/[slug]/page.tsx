import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { LegacyTheoryPublicView } from "@/components/public/legacy-theory-public-view";
import { loadTheoryEntity } from "@/lib/api/theories.server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const entity = await loadTheoryEntity(slug, { strict: true });
  return { title: entity?.name ?? "理论流派" };
}

export default async function TheorySchoolDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { slug } = await params;
  const entity = await loadTheoryEntity(slug, { strict: true });
  if (!entity) notFound();
  if (entity.canonical_node_url?.startsWith("/theories/nodes/")) {
    const query = new URLSearchParams();
    Object.entries(await searchParams).forEach(([key, value]) => {
      for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
        query.append(key, item);
      }
    });
    redirect(`${entity.canonical_node_url}${query.size ? `?${query}` : ""}`);
  }
  return <><LegacyTheoryPublicView entity={entity} /><SiteFooter /></>;
}
