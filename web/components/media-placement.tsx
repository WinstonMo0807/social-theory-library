import type { ReactNode } from "react";
import { mediaAllows, type MediaDisplayUse } from "@/lib/media-usage";
import styles from "./media-placement.module.css";

/** SVG images cannot contain the HTML fallback wrappers used by cards. */
export function mediaGraphicClass(uses: readonly MediaDisplayUse[] | undefined, placement: "detail" | "list" = "list") {
  const desktop = mediaAllows(uses, placement), mobile = mediaAllows(uses, "mobile");
  return desktop && mobile ? "" : desktop ? styles.graphicDesktop : mobile ? styles.graphicMobile : styles.graphicHidden;
}

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
