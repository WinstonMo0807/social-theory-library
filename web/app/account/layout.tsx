import { RouteStyles } from "./route-styles";
import type { ReactNode } from "react";

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <div data-stl-page-layout="account"><RouteStyles />{children}</div>;
}
