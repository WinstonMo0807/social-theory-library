import type { ComponentPropsWithRef } from "react";

export type InspectorProps = ComponentPropsWithRef<"aside"> & { "aria-label": string };

/** The persistent inspection surface is non-modal and does not trap focus. */
export function Inspector(props: InspectorProps) {
  return <aside {...props} />;
}
