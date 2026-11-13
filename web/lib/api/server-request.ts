// This transport reads private runtime configuration and must remain server-side.
if (typeof window !== "undefined") {
  throw new Error("Server API transport cannot run in the browser.");
}

const SERVER_API =
  process.env.INTERNAL_API_URL?.replace(/\/$/, "") ??
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

// STL 4.0: runtime content always reflects the API, including in development.
// Fixtures remain available to isolated tests, never as a response to an outage.
export const allowDemoFallback = false;

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

export async function serverRequest<T>(path: string, options: { forwardSession?: boolean; timeoutMs?: number } = {}): Promise<T> {
  let sessionCookie = "";
  if (options.forwardSession) {
    const { cookies } = await import("next/headers");
    const name = process.env.JWT_ACCESS_COOKIE_NAME || "stl_access";
    if (!/^[A-Za-z0-9_-]+$/.test(name)) throw new Error("Invalid access cookie configuration");
    const value = (await cookies()).get(name)?.value;
    if (value && !/[;\r\n]/.test(value)) sessionCookie = `${name}=${value}`;
  }
  const response = await fetch(`${SERVER_API}${path}`, {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(options.timeoutMs ?? 45000),
    headers: {
      accept: "application/json",
      // Reader and exploration opt in. Never forward refresh cookies or browser headers.
      ...(sessionCookie ? { cookie: sessionCookie } : {}),
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
