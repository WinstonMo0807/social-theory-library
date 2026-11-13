export const brandLoadingVariants = ["l5", "l6", "l7"] as const;
export type BrandLoadingVariant = typeof brandLoadingVariants[number];

export function pickBrandLoadingVariant(random = Math.random()): BrandLoadingVariant {
  return brandLoadingVariants[Math.min(2, Math.max(0, Math.floor(random * 3)))];
}
