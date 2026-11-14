export const brandLoadingVariants = ["l5", "l6", "j", "k"] as const;
export type BrandLoadingVariant = typeof brandLoadingVariants[number];

export function pickBrandLoadingVariant(random = Math.random()): BrandLoadingVariant {
  return brandLoadingVariants[Math.min(brandLoadingVariants.length - 1, Math.max(0, Math.floor(random * brandLoadingVariants.length)))];
}
