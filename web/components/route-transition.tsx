"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";

const NAVIGATION_TIMEOUT_MS = 10_000;

export function RouteTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const containerRef = useRef<HTMLDivElement>(null);
  const pendingAnchorRef = useRef<HTMLAnchorElement | null>(null);
  const pendingTimerRef = useRef<number | null>(null);
  const readerRoute = pathname.startsWith("/reader/");
  const exploreRoute = pathname === "/explore" || pathname.startsWith("/explore/");
  const routeKey = `${pathname}?${searchParams.toString()}`;
  // Presentation only: keep business routing and query contracts unchanged.
  const typeMode = readerRoute ? "reader" : pathname.startsWith("/admin") ? "admin"
    : pathname.startsWith("/account") || exploreRoute || ["/login", "/register", "/activate", "/reset-password", "/verify-email", "/feedback"].includes(pathname) ? "productive"
    : pathname.startsWith("/works/") || pathname.startsWith("/recommendations/") || pathname.startsWith("/help/") ? "reading" : "expressive";

  const clearPendingNavigation = useCallback(() => {
    if (pendingTimerRef.current !== null) {
      window.clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
    const anchor = pendingAnchorRef.current;
    if (anchor) {
      delete anchor.dataset.routePending;
      anchor.removeAttribute("aria-busy");
      pendingAnchorRef.current = null;
    }
    containerRef.current?.removeAttribute("aria-busy");
  }, []);

  useEffect(() => {
    const handleNavigationIntent = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      const anchor = target instanceof Element ? target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download") || anchor.getAttribute("aria-disabled") === "true") return;
      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      const current = new URL(window.location.href);
      if (destination.pathname === current.pathname && destination.search === current.search) return;

      clearPendingNavigation();
      pendingAnchorRef.current = anchor;
      anchor.dataset.routePending = "true";
      anchor.setAttribute("aria-busy", "true");
      containerRef.current?.setAttribute("aria-busy", "true");
      pendingTimerRef.current = window.setTimeout(clearPendingNavigation, NAVIGATION_TIMEOUT_MS);
    };

    document.addEventListener("click", handleNavigationIntent, true);
    return () => {
      document.removeEventListener("click", handleNavigationIntent, true);
      clearPendingNavigation();
    };
  }, [clearPendingNavigation]);

  useEffect(() => {
    clearPendingNavigation();
  }, [clearPendingNavigation, routeKey]);

  useEffect(() => {
    if (["/", "/welcome", "/home"].includes(pathname) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const container = containerRef.current;
    if (!container) return;
    const target = pathname.startsWith("/admin")
      ? container.querySelector<HTMLElement>(".admin-content")
      : readerRoute
        ? container.querySelector<HTMLElement>(".reader-document")
        : container;
    const animation = target?.animate(
      [
        { opacity: 0.6 },
        { opacity: 1 },
      ],
      {
        duration: 140,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    );
    return () => animation?.cancel();
  }, [pathname, readerRoute]);

  return (
    <div
      className={`route-content-transition ${readerRoute ? "reader-route" : ""}`}
      data-ui-scope="stl4"
      data-workbench={pathname.startsWith("/admin") || pathname.startsWith("/account") ? "elicit" : undefined}
      data-type-mode={typeMode}
      data-type-section={pathname.split("/")[1] || "welcome"}
      ref={containerRef}
    >
      {children}
    </div>
  );
}
