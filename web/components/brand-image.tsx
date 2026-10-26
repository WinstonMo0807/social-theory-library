import { defaultSiteConfig, type SiteConfig } from "@/lib/site-config";

type BrandConfig = Pick<SiteConfig, "site_name" | "wordmark_lines">;

export function hasCustomBrand(config: BrandConfig) {
  return config.site_name !== defaultSiteConfig.site_name
    || config.wordmark_lines.join(" ") !== defaultSiteConfig.wordmark_lines.join(" ");
}

// Keep the PDF artwork unchanged until an editor explicitly changes its wording.
export function BrandImage({ config = defaultSiteConfig, src, width, height, textOnly = false, alt = config.site_name }: {
  config?: BrandConfig; src: string; width?: number; height?: number; textOnly?: boolean; alt?: string;
}) {
  if (!hasCustomBrand(config)) return <img src={src} width={width} height={height} alt={alt} />;
  const displayWidth = width ?? 203;
  const displayHeight = height ?? 32;
  const canvasWidth = displayWidth / displayHeight * 100;
  const textX = textOnly ? 0 : 142;
  const textWidth = Math.max(40, canvasWidth - textX);
  const english = config.wordmark_lines.join(" ");
  const fontSize = (text: string, maximum: number) => Math.min(maximum,
    textWidth / Math.max(1, Array.from(text).reduce((sum, character) => sum + (character.charCodeAt(0) > 255 ? 1 : .72), 0)));
  return <svg className="brand-configured" xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${canvasWidth} 100`}
    width={displayWidth} height={displayHeight} role={alt ? "img" : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}
    style={{ display: "block", width: "100%", height: "auto", maxWidth: displayWidth }}>
    {alt ? <title>{alt}</title> : null}
    {!textOnly ? <image href="/brand/stl-mark-final-r2.svg" width="130" height="100" /> : null}
    <text x={textX} y="41" fontFamily="'Times New Roman', 'Noto Serif', serif" fontSize={fontSize(english, 34)} fontWeight="700" fill="#10283e">{english}</text>
    <text x={textX} y="84" fontFamily="'Songti SC', SimSun, 'Noto Serif CJK SC', serif" fontSize={fontSize(config.site_name, 37)} fontWeight="700" fill="#10283e">{config.site_name}</text>
  </svg>;
}
