import type { ComponentPropsWithoutRef } from "react";

/** A real pending state. No invented percentage or completion time. */
export function LoadingState({ children = "正在加载…", className = "", ...props }: ComponentPropsWithoutRef<"p">) {
  return <p {...props} className={`stl-loading ${className}`} role="status" aria-busy="true">
    <span className="stl-loading-mark" aria-hidden="true">
      <svg viewBox="12 17 230 154" focusable="false"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg>
      <svg viewBox="12 17 230 154" focusable="false"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg>
    </span><span className="stl-loading-copy">{children}<span className="stl-loading-track" aria-hidden="true" /></span>
  </p>;
}
