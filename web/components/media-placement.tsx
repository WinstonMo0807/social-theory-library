import type { ReactNode } from "react";
import { mediaAllows, type MediaDisplayUse } from "@/lib/media-usage";
import styles from "./media-placement.module.css";

/** CSS applies the saved mobile choice before hydration, including without JS. */
export function MediaPlacement({ uses, placement = "list", children, fallback = null }: {
  uses?: readonly MediaDisplayUse[]; placement?: "detail" | "list"; children: ReactNode; fallback?: ReactNode;
}) {
  const desktop = mediaAllows(uses, placement), mobile = mediaAllows(uses, "mobile");
  if (desktop && mobile) return children;
  if (!desktop && !mobile) return fallback;
  return <><div className={`${styles.contents} ${desktop ? styles.desktop : styles.mobile}`}>{children}</div>
    <div className={`${styles.contents} ${desktop ? styles.mobile : styles.desktop}`}>{fallback}</div></>;
}
