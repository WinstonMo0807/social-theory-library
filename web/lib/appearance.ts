export type ThemeChoice = "light" | "dark" | "system";
export type Appearance = {
  theme: ThemeChoice;
  text_size: "standard" | "comfortable" | "large";
  font_family: "sans" | "serif";
};
export const defaultAppearance: Appearance = { theme: "light", text_size: "standard", font_family: "sans" };
export const appearanceKeys = { theme: "library_theme", text_size: "library_text_size", font_family: "library_font_family" } as const;

export function validAppearance(value: unknown): Partial<Appearance> {
  if (!value || typeof value !== "object") return {};
  const data = value as Record<string, unknown>;
  return {
    ...(["light", "dark", "system"].includes(String(data.theme)) ? { theme: data.theme as Appearance["theme"] } : {}),
    ...(["standard", "comfortable", "large"].includes(String(data.text_size)) ? { text_size: data.text_size as Appearance["text_size"] } : {}),
    ...(["sans", "serif"].includes(String(data.font_family)) ? { font_family: data.font_family as Appearance["font_family"] } : {}),
  };
}
export function readAppearance(): Appearance {
  try {
    return { ...defaultAppearance, ...validAppearance(Object.fromEntries(Object.entries(appearanceKeys).map(([field, key]) => [field, localStorage.getItem(key)]))) };
  } catch { return defaultAppearance; }
}
export function applyAppearance(value: Appearance) {
  const dark = value.theme === "dark" || (value.theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  root.dataset.theme = dark ? "dark" : "light";
  root.dataset.themeChoice = value.theme;
  root.dataset.textSize = value.text_size;
  root.dataset.fontFamily = value.font_family;
  return dark;
}
export function storeAppearance(value: Appearance) {
  try {
    for (const [field, key] of Object.entries(appearanceKeys)) localStorage.setItem(key, value[field as keyof Appearance]);
    return true;
  } catch { return false; }
}
