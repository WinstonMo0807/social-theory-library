"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

export function RouteTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const containerRef = useRef<HTMLDivElement>(null);
  const readerRoute = pathname.startsWith("/reader/");
  const exploreRoute = pathname === "/explore" || pathname.startsWith("/explore/");

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const container = containerRef.current;
    if (!container) return;
    const target = pathname.startsWith("/admin")
      ? container.querySelector<HTMLElement>(".admin-content")
      : readerRoute
        ? container.querySelector<HTMLElement>(".reader-document")
        : container;
    const animation = target?.animate(
      [
        { opacity: 0, transform: "translateY(8px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      {
        duration: 220,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    );
    return () => animation?.cancel();
  }, [pathname, readerRoute]);

  return (
    <div
      className={`route-content-transition ${readerRoute ? "reader-route" : ""}`}
      data-ui-scope={exploreRoute ? "explore-frozen" : "editorial-v2"}
      ref={containerRef}
    >
      {children}
    </div>
  );
}
