import type { Metadata } from "next";
import { headers } from "next/headers";
import type { components } from "./api/generated/schema";
import { mediaAllows, publicShareImagePath } from "./media-usage";

export async function publicMediaMetadata(media: components["schemas"]["PublicCoverMedia"] | null | undefined, title: string) {
  return publicImageMetadata(media && mediaAllows(media.display_uses, "share") ? media.renditions.at(-1)?.url : undefined, media?.alt_text || title);
}

/** Only an explicitly selected, published, same-origin rendition may be shared. */
export async function publicImageMetadata(image: string | undefined, alt: string): Promise<Metadata> {
  const path = publicShareImagePath(image);
  if (!path) {
    return { openGraph: { images: [] }, twitter: { card: "summary", images: [] } };
  }
  const requestHeaders = await headers();
  const host = requestHeaders.get("host") || "";
  const protocol = requestHeaders.get("x-forwarded-proto")?.split(",")[0].trim() || "https";
  if (!/^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::\d{1,5})?$/i.test(host) || !["http", "https"].includes(protocol)) return {};
  let url: string;
  try { url = new URL(path, `${protocol}://${host}`).href; } catch { return {}; }
  return { openGraph: { images: [{ url, alt }] }, twitter: { card: "summary_large_image", images: [{ url, alt }] } };
}
