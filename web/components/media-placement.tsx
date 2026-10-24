import { Children, cloneElement, Fragment, isValidElement, type ReactNode } from "react";
import { mediaAllows, type MediaDisplayUse } from "@/lib/media-usage";
import styles from "./media-placement.module.css";

/** SVG images cannot contain the HTML fallback wrappers used by cards. */
export function mediaGraphicClass(uses: readonly MediaDisplayUse[] | undefined, placement: "detail" | "list" = "list") {
  const desktop = mediaAllows(uses, placement), mobile = mediaAllows(uses, "mobile");
  return desktop && mobile ? "" : desktop ? styles.graphicDesktop : mobile ? styles.graphicMobile : styles.graphicHidden;
}

function placed(nodes: ReactNode, className: string): ReactNode {
  return Children.map(nodes, node => {
    if (!isValidElement<{ className?: string; children?: ReactNode }>(node))
      return node == null ? null : <span className={`${styles.contents} ${className}`}>{node}</span>;
    if (node.type === Fragment) return placed(node.props.children, className);
    // Images and icons used here forward className to their root DOM element.
    // Keep direct-child sizing selectors and button contents intact.
    return cloneElement(node, { className: [node.props.className, className].filter(Boolean).join(" ") });
  });
}

/** CSS applies the saved mobile choice before hydration, including without JS. */
export function MediaPlacement({ uses, placement = "list", children, fallback = null }: {
  uses?: readonly MediaDisplayUse[]; placement?: "detail" | "list"; children: ReactNode; fallback?: ReactNode;
}) {
  const desktop = mediaAllows(uses, placement), mobile = mediaAllows(uses, "mobile");
  if (desktop && mobile) return children;
  if (!desktop && !mobile) return fallback;
  return <>{placed(children, desktop ? styles.desktop : styles.mobile)}
    {placed(fallback, desktop ? styles.mobile : styles.desktop)}</>;
}
