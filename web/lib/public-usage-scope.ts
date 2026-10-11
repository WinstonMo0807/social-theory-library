const publicRoots = new Set([
  "explore", "works", "reader", "scholars", "theories", "theory-schools",
  "subdisciplines", "topics", "recommendations", "concepts", "about",
]);

export function publicUsageScope(pathname: string): string | null {
  if (pathname === "/") return "home";
  if (!pathname.startsWith("/")) return null;
  const root = pathname.split("/")[1];
  return publicRoots.has(root) ? root : null;
}
