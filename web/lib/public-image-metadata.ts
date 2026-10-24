import type { Metadata } from "next";
import { headers } from "next/headers";

/** Only an explicitly selected, published, same-origin rendition may be shared. */
export async function publicImageMetadata(image: string | undefined, alt: string): Promise<Metadata> {
  if (!image || !/^\/api\/catalog\/works\/[0-9a-f-]+\/(?:cover|recommendation-image)\/\?rendition=[0-9a-f-]+$/i.test(image)) {
    return { openGraph: { images: [] }, twitter: { card: "summary", images: [] } };
  }
  const requestHeaders = await headers();
  const host = requestHeaders.get("host") || "";
  const protocol = requestHeaders.get("x-forwarded-proto")?.split(",")[0].trim() || "https";
  if (!/^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::\d{1,5})?$/i.test(host) || !["http", "https"].includes(protocol)) return {};
  let url: string;
  try { url = new URL(image, `${protocol}://${host}`).href; } catch { return {}; }
  return { openGraph: { images: [{ url, alt }] }, twitter: { card: "summary_large_image", images: [{ url, alt }] } };
}
