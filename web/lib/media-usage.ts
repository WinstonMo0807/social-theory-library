export const mediaDisplayUses = ["detail", "list", "mobile", "share"] as const;
export type MediaDisplayUse = (typeof mediaDisplayUses)[number];
export const defaultMediaDisplayUses: MediaDisplayUse[] = ["detail", "list", "mobile"];

export function mediaAllows(uses: readonly MediaDisplayUse[] | undefined, use: MediaDisplayUse) {
  return (uses ?? defaultMediaDisplayUses).includes(use);
}

/** Preserve version-qualified public URLs; reject private files and unknown parameters. */
export function publicShareImagePath(image: string | undefined): string | null {
  if (!image?.startsWith("/api/catalog/")) return null;
  const value = new URL(image, "https://same-origin.invalid");
  if (value.hash || value.origin !== "https://same-origin.invalid") return null;
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  const validId = new RegExp(`^${uuid}$`, "i");
  const work = new RegExp(`^/api/catalog/works/${uuid}/(?:cover|recommendation-image)/$`, "i").test(value.pathname);
  const object = new RegExp(`^/api/catalog/(?:people/${uuid}/portrait|knowledge-media/(?:knowledge_node|reading_path|discipline|subdiscipline|topic)/${uuid}/file)/$`, "i").test(value.pathname);
  if (!work && !object) return null;
  if (!validId.test(value.searchParams.get("rendition") || "") || value.searchParams.getAll("rendition").length !== 1) return null;
  for (const [key, item] of value.searchParams) {
    if (key === "rendition") continue;
    if (key !== "edition_id" || !work || !validId.test(item) || value.searchParams.getAll(key).length !== 1) return null;
  }
  return value.pathname + value.search;
}
