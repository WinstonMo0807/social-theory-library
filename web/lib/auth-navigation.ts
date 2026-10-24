/** Only local page destinations; reject browser URL normalization escapes. */
export function safeAuthDestination(value: string | null | undefined, fallback = "/account") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return fallback;
  try {
    const url = new URL(value, "https://stl.invalid");
    const path = decodeURIComponent(url.pathname);
    if (url.origin !== "https://stl.invalid" || path.startsWith("//") || /[\\\u0000-\u0020]/.test(path) || /^\/(login|register|reset-password|verify-email|activate)(\/|$)/.test(path)) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch { return fallback; }
}

export function authPageHref(mode: "login" | "register" | "reset", next: string) {
  return `/${mode === "reset" ? "reset-password" : mode}?${new URLSearchParams({ next: safeAuthDestination(next) })}`;
}
