import type { ComponentPropsWithoutRef, ReactNode } from "react";

/** Error content remains visible and is never converted into an empty result. */
export function ErrorState({ children, ...props }: ComponentPropsWithoutRef<"p">) {
  return <p {...props} role="alert">{children}</p>;
}

/** A text placeholder announces real loading without inventing item counts. */
export function Skeleton({ children, ...props }: ComponentPropsWithoutRef<"p"> & { children: ReactNode }) {
  return <p {...props} role="status" aria-busy="true">{children}</p>;
}
