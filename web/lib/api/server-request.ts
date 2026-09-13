// This transport reads private runtime configuration and must remain server-side.
if (typeof window !== "undefined") {
  throw new Error("Server API transport cannot run in the browser.");
}

const SERVER_API =
  process.env.INTERNAL_API_URL?.replace(/\/$/, "") ??
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

export const allowDemoFallback = (
  process.env.NODE_ENV !== "production"
  && process.env.ALLOW_DEMO_FALLBACK !== "false"
);

export class ServerApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(status: number, path: string) {
    super(`API ${status}: ${path}`);
    this.name = "ServerApiError";
    this.status = status;
    this.path = path;
  }
}

export async function serverRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${SERVER_API}${path}`, {
    cache: "no-store",
    headers: {
      accept: "application/json",
      // Public deployments keep Django's HTTPS redirect enabled. Server-side
      // requests still travel over the private Docker network, so mark the
      // original scheme explicitly and avoid redirects to https://api:8000.
      "x-forwarded-proto": "https",
      ...(INTERNAL_API_TOKEN ? { "x-internal-api-token": INTERNAL_API_TOKEN } : {}),
    },
  });
  if (!response.ok) {
    throw new ServerApiError(response.status, path);
  }
  return response.json() as Promise<T>;
}
