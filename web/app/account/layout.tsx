import { RouteStyles } from "./route-styles";
import type { ReactNode } from "react";
import { ReaderWorkspace } from "@/components/research/reader-workspace";

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <div data-stl-page-layout="account"><RouteStyles /><ReaderWorkspace>{children}</ReaderWorkspace></div>;
}
