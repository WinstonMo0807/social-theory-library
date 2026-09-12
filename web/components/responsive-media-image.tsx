"use client";

import { useSyncExternalStore } from "react";
import { getApiBase } from "@/lib/runtime-api";
import type { components } from "@/lib/api/generated/schema";

const subscribe = () => () => {};
const serverApiBase = () => "/api";

export function ResponsiveMediaImage({ src, sources, alt, sizes, loading = "lazy" }: {
  src: string; sources: components["schemas"]["PublicMediaRendition"][]; alt: string; sizes: string; loading?: "eager" | "lazy";
}) {
  const apiBase = useSyncExternalStore(subscribe, getApiBase, serverApiBase);
  const url = (value: string) => value.startsWith("/api/") ? `${apiBase}${value.slice(4)}` : value;
  if (!src || !sources.length) return null;
  return <picture style={{ display: "block", width: "100%", height: "100%" }}>
    <source type="image/webp" srcSet={sources.map((row) => `${url(row.url)} ${row.width}w`).join(", ")} sizes={sizes} />
    <img src={url(src)} alt={alt} width={sources[0].width} height={sources[0].height} loading={loading} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
  </picture>;
}
