"use client";

import Link from "next/link";
import { useSyncExternalStore, type ComponentProps } from "react";

const query = "(min-width: 900px) and (pointer: fine)";
function subscribe(callback: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
const snapshot = () => window.matchMedia(query).matches;
const serverSnapshot = () => false;

/** Lists preserve their current query and scroll; mobile follows the same link in place. */
export function CollectionLink(props: ComponentProps<typeof Link>) {
  const desktop = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  return <Link {...props} target={desktop ? "_blank" : undefined} rel={desktop ? "noopener" : undefined} title={desktop ? `${props.title || "打开馆藏"}（新标签页）` : props.title} />;
}
