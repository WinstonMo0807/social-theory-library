"use client";

import { MediaPlacement } from "./media-placement";
import { ResponsiveMediaImage } from "./responsive-media-image";
import type { Scholar } from "@/lib/data";

/** Server HTML keeps the real same-origin public URL. A separately hosted
 * local preview uses its explicit runtime API origin after hydration. */
export function ResponsivePortraitImage({ scholar, large }: { scholar: Scholar; large: boolean }) {
  const sources = scholar.portraitSources ?? [];
  if (!scholar.portrait || !sources.length) return null;
  return <MediaPlacement uses={scholar.portraitDisplayUses} placement={large?"detail":"list"} fallback={<span>{scholar.name.slice(0,1)}</span>}><ResponsiveMediaImage src={scholar.portrait} sources={sources} alt={scholar.portraitAlt || `${scholar.name}肖像`} sizes={large ? "(max-width: 760px) 60vw, 420px" : "(max-width: 760px) 45vw, (min-width: 1600px) 16vw, 320px"} fit="contain" loading={large ? "eager" : "lazy"} /></MediaPlacement>;
}
