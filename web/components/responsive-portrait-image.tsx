"use client";

import { ResponsiveMediaImage } from "./responsive-media-image";
import type { Scholar } from "@/lib/data";

/** Server HTML keeps the real same-origin public URL. A separately hosted
 * local preview uses its explicit runtime API origin after hydration. */
export function ResponsivePortraitImage({ scholar, large }: { scholar: Scholar; large: boolean }) {
  const sources = scholar.portraitSources ?? [];
  if (!scholar.portrait || !sources.length) return null;
  return <ResponsiveMediaImage src={scholar.portrait} sources={sources} alt={scholar.portraitAlt || `${scholar.name}肖像`} sizes={large ? "(max-width: 760px) 60vw, 300px" : "180px"} loading={large ? "eager" : "lazy"} />;
}
