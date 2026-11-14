"use client";

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { BrandImage } from "@/components/brand-image";
import type { SiteConfig } from "@/lib/site-config";
import type { WelcomeBook, WelcomeCopy, WelcomeDiscovery, welcomeContent } from "@/lib/welcome";
import { GrainField } from "./welcome-illustrations";
import styles from "./home-feature-story.module.css";

export type WorkflowDemoProps = {
  books: WelcomeBook[];
  brandConfig: Pick<SiteConfig, "site_name" | "wordmark_lines">;
  copy: WelcomeCopy;
  history: ReturnType<typeof welcomeContent>["texts"];
  discovery: WelcomeDiscovery;
};

const WorkflowDemo = lazy(() => import("./welcome-workflow-demo"));

export function WelcomeDemo(props: WorkflowDemoProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    let idle: number | undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      // Give the headline and its fonts priority, then prepare the nearby demo.
      if ("requestIdleCallback" in window) idle = window.requestIdleCallback(() => setReady(true), { timeout: 1000 });
      else setReady(true);
    }, { rootMargin: "160px" });
    observer.observe(node);
    return () => { observer.disconnect(); if (idle !== undefined) window.cancelIdleCallback(idle); };
  }, []);
  const placeholder = <figure className={`${styles.demo} ${styles.demoPlaceholder}`} aria-label="书库功能演示">
    <GrainField /><div className={styles.demoFrame} style={{ animation: "none" }} aria-hidden="true" />
    <div className={styles.brandPanel} aria-hidden="true"><BrandImage config={props.brandConfig} alt="" /></div>
  </figure>;
  return <div ref={ref} className={styles.demoMount}>
    {ready ? <Suspense fallback={placeholder}><WorkflowDemo {...props} /></Suspense> : placeholder}
  </div>;
}
