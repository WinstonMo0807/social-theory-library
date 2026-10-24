export const mediaDisplayUses = ["detail", "list", "mobile", "share"] as const;
export type MediaDisplayUse = (typeof mediaDisplayUses)[number];
export const defaultMediaDisplayUses: MediaDisplayUse[] = ["detail", "list", "mobile"];

export function mediaAllows(uses: readonly MediaDisplayUse[] | undefined, use: MediaDisplayUse) {
  return (uses ?? defaultMediaDisplayUses).includes(use);
}
