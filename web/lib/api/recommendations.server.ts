// Server-side public API domain. Browser components use pure adapters and type-only imports.
import type { Work, Scholar } from "../data";
import { adaptRecommendationWork } from "../public-data-adapters";
import { loadScholar } from "./people.server";
import type { ApiWork } from "./public-catalog";
import type { RecommendationBundle } from "./recommendations.types";
import { serverRequest, allowDemoFallback } from "./server-request";

export async function loadRecommendations(): Promise<RecommendationBundle> {
  try {
    return await serverRequest<RecommendationBundle>("/catalog/recommendations/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { shared_for_all_readers: true, rotation_days: 3, placements: {} };
  }
}

export function recommendationWorks(bundle: RecommendationBundle, placement: string): Work[] {
  return (bundle.placements[placement]?.current?.items ?? [])
    .filter((item) => item.target_type === "work")
    .map((item, index) => adaptRecommendationWork(item.target as ApiWork, index));
}

export function recommendationSlugs(
  bundle: RecommendationBundle,
  placement: string,
  targetType: "theory_school" | "topic" | "scholar",
): string[] {
  const seen = new Set<string>();
  return (bundle.placements[placement]?.current?.items ?? []).flatMap((item) => {
    if (item.target_type !== targetType || !("slug" in item.target)) return [];
    const slug = String(item.target.slug || "").trim();
    if (!slug || seen.has(slug)) return [];
    seen.add(slug);
    return [slug];
  });
}

export async function loadRecommendedScholars(
  bundle: RecommendationBundle,
  limit = 4,
): Promise<Scholar[]> {
  const itemBySlug = new Map(
    (bundle.placements.home_scholars?.current?.items ?? []).flatMap((item) => (
      item.target_type === "scholar" && "slug" in item.target
        ? [[String(item.target.slug), item] as const]
        : []
    )),
  );
  const items = recommendationSlugs(bundle, "home_scholars", "scholar")
    .slice(0, Math.max(0, limit))
    .flatMap((slug) => itemBySlug.has(slug) ? [itemBySlug.get(slug)!] : []);
  const loaded = await Promise.all(items.map(async (item) => {
    const target = item.target as {
      slug: string;
    };
    try {
      const detail = await loadScholar(target.slug);
      if (detail) return detail.scholar;
    } catch {
      // A missing public detail must not become a visible recommendation with a broken link.
    }
    return null;
  }));
  const seen = new Set<string>();
  return loaded.filter((scholar): scholar is Scholar => {
    if (!scholar) return false;
    if (!scholar.slug || seen.has(scholar.slug)) return false;
    seen.add(scholar.slug);
    return true;
  });
}
