import manifest from './performance-assets.json';

export const preferencesBootstrapSource = `/assets/performance/preferences-${manifest.preferencesSha256.slice(0,16)}.js`;

/** Only known public static art has variants. Authenticated/revocable API media keeps its original URL. */
export function editorialImageSources(src: string, sizes = '100vw') {
  const entry = (manifest.images as Record<string,{sha256:string;width:number;height:number;widths:number[]}>)[src];
  if (!entry) return {};
  return {
    srcSet: [...entry.widths.map(width => `/assets/performance/editorial-${entry.sha256.slice(0,16)}-${width}.webp ${width}w`), `${src} ${entry.width}w`].join(', '),
    sizes,
  };
}
