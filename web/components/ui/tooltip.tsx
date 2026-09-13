"use client";

import { cloneElement, useId, useState, type ReactElement, type ReactNode } from "react";

/** Tooltip content is supplementary text, never an interactive control. */
export function Tooltip({ children, content }: { children: ReactElement<{ "aria-describedby"?: string }>; content: ReactNode }) {
  const id = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const open = (hovered || focused) && !dismissed;
  const describedBy = [children.props["aria-describedby"], id].filter(Boolean).join(" ");
  return <span className="ui-tooltip" onPointerEnter={() => { setHovered(true); setDismissed(false); }} onPointerLeave={() => setHovered(false)}
    onFocus={() => { setFocused(true); setDismissed(false); }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}
    onKeyDown={(event) => { if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setDismissed(true); } }}>
    {cloneElement(children, { "aria-describedby": describedBy })}
    <span id={id} className="ui-tooltip-content" role="tooltip" hidden={!open}>{content}</span>
  </span>;
}
