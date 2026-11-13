import type { ReactNode } from "react";
import "@/styles/features/center-layout.css";

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <div data-stl-page-layout="account">{children}</div>;
}
