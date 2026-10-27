import { defaultSiteConfig, type SiteConfig } from "@/lib/site-config";

type BrandConfig = Pick<SiteConfig, "site_name" | "wordmark_lines">;

export function hasCustomBrand(config: BrandConfig) {
  return config.site_name !== defaultSiteConfig.site_name
    || config.wordmark_lines.join(" ") !== defaultSiteConfig.wordmark_lines.join(" ");
}

// The user's 2026-10-27 reference supersedes the PDF's varying logo lockups.
// One vector emblem and live bilingual type, without stretched image lettering.
export function BrandImage({ config = defaultSiteConfig, alt = config.site_name }: {
  config?: BrandConfig; alt?: string;
}) {
  const english = config.wordmark_lines.join(" ");
  return <span className="brand-identity" role={alt ? "img" : undefined} aria-label={alt || undefined}
    aria-hidden={alt ? undefined : true} data-custom-brand={hasCustomBrand(config) || undefined}>
    <svg className="brand-identity-symbol" viewBox="12 17 230 154" aria-hidden="true" focusable="false">
      <use href="/brand/stl-symbol-20261027.svg#mark" />
    </svg>
    <span className="brand-identity-words" aria-hidden="true">
      <span className="brand-identity-en">{english === defaultSiteConfig.wordmark_lines.join(" ") ? "Social Theory Library" : english}</span>
      <span className="brand-identity-cn">{config.site_name}</span>
    </span>
  </span>;
}
