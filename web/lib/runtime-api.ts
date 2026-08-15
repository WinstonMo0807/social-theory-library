export type RuntimeApiConfig = {
  apiBase?: string;
};

export type BrowserLocationLike = {
  protocol: string;
  hostname: string;
  port: string;
  origin: string;
};

declare global {
  interface Window {
    __SOCIAL_THEORY_LIBRARY_CONFIG__?: RuntimeApiConfig;
  }
}

function cleanApiBase(value?: string | null) {
  const cleaned = value?.trim().replace(/\/+$/, "") ?? "";
  if (!cleaned) return "";
  if (cleaned === "/api" || /^https?:\/\/[^\s]+\/api$/i.test(cleaned)) {
    return cleaned;
  }
  return "";
}

/**
 * Keep the browser independent from a build-time IP address.
 *
 * Production and LAN traffic both enter through the edge proxy.  The proxy
 * owns ports 3000, 18080 and 18082 and forwards /api internally.  Keeping API
 * calls on the same origin is also required for the HttpOnly login cookie.
 * A developer who intentionally runs Next.js without the edge proxy can set
 * window.__SOCIAL_THEORY_LIBRARY_CONFIG__.apiBase explicitly.
 */
export function inferBrowserApiBase(location: BrowserLocationLike) {
  void location;
  return "/api";
}

export function resolveBrowserApiBase(
  location: BrowserLocationLike,
  runtimeConfig?: RuntimeApiConfig | null,
) {
  return cleanApiBase(runtimeConfig?.apiBase) || inferBrowserApiBase(location);
}

export function getApiBase() {
  if (typeof window === "undefined") return "/api";
  return resolveBrowserApiBase(
    window.location,
    window.__SOCIAL_THEORY_LIBRARY_CONFIG__,
  );
}

export function apiEndpoint(path: string) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBase()}${normalized}`;
}

export function normalizePublicResourceUrl(value: string) {
  if (!value || typeof window === "undefined") return value;
  if (value.startsWith("/api/")) return `${getApiBase()}${value.slice(4)}`;
  if (!/^https?:\/\//i.test(value)) return value;

  try {
    const parsed = new URL(value);
    const isLoopback = ["localhost", "127.0.0.1", "::1", "api"].includes(parsed.hostname);
    const apiIndex = parsed.pathname.indexOf("/api/");
    if (isLoopback && apiIndex >= 0 && !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname)) {
      return `${getApiBase()}${parsed.pathname.slice(apiIndex + 4)}${parsed.search}${parsed.hash}`;
    }
  } catch {
    return value;
  }
  return value;
}
