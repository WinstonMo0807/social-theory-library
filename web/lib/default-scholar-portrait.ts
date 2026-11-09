export const scholarPortraitBackgrounds = ["paper", "stone", "alabaster", "dark"] as const;

/** A stable, even spread across J–M, shared by normal and curated scholar cards. */
export function defaultScholarPortraitVariant(identity: string): number {
  let key = identity.trim().replace(/^\/scholars\//, "").split(/[?#]/, 1)[0].replace(/\/+$/, "");
  try { key = decodeURIComponent(key); } catch { /* A literal % is a valid fallback identity. */ }
  let hash = 2166136261;
  for (const char of key.normalize("NFC")) hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619);
  return (hash >>> 0) % scholarPortraitBackgrounds.length;
}

/** Initial typesetting works before hydration; the component also measures actual font metrics. */
export function scholarNameSize(name: string): number {
  const units = Array.from(name).reduce((sum, char) => sum + (/\s/u.test(char) ? .3 : /[\u0000-\u024f]/u.test(char) ? .55 : 1), 0);
  return units <= 4 ? 16.3 : units <= 9 ? 12.2 : units <= 16 ? 10.5 : 9.2;
}
