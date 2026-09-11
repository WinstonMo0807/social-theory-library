"use client";

import { useSyncExternalStore } from "react";
import { getApiBase } from "@/lib/runtime-api";
import type { Scholar } from "@/lib/data";

const subscribe = () => () => {};
const serverApiBase = () => "/api";

/** Server HTML keeps the real same-origin public URL. A separately hosted
 * local preview uses its explicit runtime API origin after hydration. */
export function ResponsivePortraitImage({ scholar, large }: { scholar: Scholar; large: boolean }) {
  const apiBase = useSyncExternalStore(subscribe, getApiBase, serverApiBase);
  const url = (value: string) => value.startsWith("/api/") ? `${apiBase}${value.slice(4)}` : value;
  const sources = scholar.portraitSources ?? [];
  if (!scholar.portrait || !sources.length) return null;
  return <picture style={{ display: "block", width: "100%", height: "100%" }}>
    <source type="image/webp" srcSet={sources.map((row) => `${url(row.url)} ${row.width}w`).join(", ")} sizes={large ? "(max-width: 760px) 60vw, 300px" : "180px"} />
    <img src={url(scholar.portrait)} alt={scholar.portraitAlt || `${scholar.name}肖像`} width={sources[0].width} height={sources[0].height} loading={large ? "eager" : "lazy"} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
  </picture>;
}
