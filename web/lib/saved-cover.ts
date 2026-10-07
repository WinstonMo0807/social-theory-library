import { apiBlob } from "./api";

let pending: Promise<unknown> = Promise.resolve();

/** Pace visible list thumbnails below the shared API rate limit; cancelled rows do no work. */
export function loadSavedCover(url: string, token: string | null, signal: AbortSignal) {
  const request = pending.then(async () => {
    signal.throwIfAborted();
    try {
      return await apiBlob(url.replace(/^\/api(?=\/)/, ""), token);
    } finally {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  });
  pending = request.catch(() => undefined);
  return request;
}
