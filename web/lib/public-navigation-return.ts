"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

const KEY = "stl.navigation.public-return.v1";
const MAX_AGE = 30 * 60 * 1000;
type ReturnLocation = { href: string; y: number; at: number };
let memory: ReturnLocation | null = null;

/** This tab stores only an allowlisted public location, never account URLs. */
export function publicReturnHref(value: string): string {
  if (!value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f]/.test(value)) return "";
  try {
    const url = new URL(value, "https://library.invalid");
    let decodedPath = url.pathname;
    for (let i = 0; i < 4; i += 1) {
      const decoded = decodeURIComponent(decodedPath);
      if (decoded === decodedPath) break;
      decodedPath = decoded;
    }
    if (/[\\%?#\u0000-\u001f\u007f]/.test(decodedPath) || decodedPath.includes("//") || decodedPath.split("/").some(part => part === "." || part === "..")) return "";
    if (url.origin !== "https://library.invalid" || !/^\/(?:$|explore(?:\/|$)|works\/|theories(?:\/|$)|theory-schools(?:\/|$)|scholars(?:\/|$)|topics(?:\/|$)|recommendations(?:\/|$)|help(?:\/|$)|about$)/.test(url.pathname)) return "";
    const query = new URLSearchParams();
    for (const name of ["q", "page", "sort", "view", "tab", "section", "type", "topic", "scholar", "theory", "mode", "context", "id", "asset_id", "document_type", "language", "concept", "author", "year", "year_min", "year_max", "match", "access", "rewrite", "rewrite_disabled", "scope"]) {
      for (const val of url.searchParams.getAll(name).slice(0, 20)) {
        if (val && val.length <= 500) query.append(name, val);
      }
    }
    if (query.toString().length > 8000) return "";
    return `${url.pathname}${query.size ? `?${query}` : ""}`;
  } catch { return ""; }
}

function readLocation(): ReturnLocation | null {
  let value = memory;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) value = JSON.parse(raw) as ReturnLocation;
  } catch { /* Validate the memory fallback by the same rules. */ }
  if (value && typeof value.href === "string" && publicReturnHref(value.href) === value.href && Number.isFinite(value.y) && value.y >= 0 && value.y < 10000000
    && Number.isFinite(value.at) && Date.now() - value.at < MAX_AGE && value.at <= Date.now()) return value;
  return null;
}

export function usePublicNavigationReturn(route: string, focusRef: RefObject<HTMLButtonElement | null>) {
  const [source, setSource] = useState<ReturnLocation | null>(null);
  const [returned, setReturned] = useState(false);
  const previousRoute = useRef(route);
  const requestedReturn = useRef(false);

  useEffect(() => {
    const location = readLocation();
    const previous = previousRoute.current;
    previousRoute.current = route;
    const fromAccount = /^\/(account|login|register)(\/|\?|$)/.test(previous);
    let stopped = false, frame = 0, timer = 0;
    const restore = location && publicReturnHref(route) === location.href && (requestedReturn.current || fromAccount);
    const notify = window.setTimeout(() => { setSource(location); setReturned(false); }, 0);
    if (!restore) return () => window.clearTimeout(notify);
    requestedReturn.current = false;
    // Streaming page content can grow after navigation. Wait for sufficient
    // height without scrolling over a reader's own subsequent interaction.
    const deadline = Date.now() + 4000;
    const stop = () => { stopped = true; window.cancelAnimationFrame(frame); };
    const finish = () => {
      if (stopped) return;
      if (document.documentElement.scrollHeight - window.innerHeight >= location.y - 2 || Date.now() > deadline) {
        window.scrollTo({ top: location.y, behavior: "instant" });
        focusRef.current?.focus({ preventScroll: true });
        setReturned(true); setSource(null); memory = null;
        try { sessionStorage.removeItem(KEY); } catch { /* In-memory fallback remains disposable. */ }
        timer = window.setTimeout(() => setReturned(false), 4500);
      } else frame = window.requestAnimationFrame(finish);
    };
    frame = window.requestAnimationFrame(() => { frame = window.requestAnimationFrame(finish); });
    window.addEventListener("wheel", stop, { passive: true });
    window.addEventListener("touchstart", stop, { passive: true });
    window.addEventListener("keydown", stop);
    return () => { stopped = true; window.clearTimeout(notify); window.clearTimeout(timer); window.cancelAnimationFrame(frame);
      window.removeEventListener("wheel", stop); window.removeEventListener("touchstart", stop); window.removeEventListener("keydown", stop); };
  }, [route, focusRef]);

  function remember() {
    const href = publicReturnHref(window.location.pathname + window.location.search);
    if (!href) return;
    const value = { href, y: window.scrollY, at: Date.now() };
    memory = value; setSource(value);
    try { sessionStorage.setItem(KEY, JSON.stringify(value)); } catch { /* The current tab still retains a memory fallback. */ }
  }
  return { source, returned, remember, requestReturn: () => { requestedReturn.current = true; } };
}
