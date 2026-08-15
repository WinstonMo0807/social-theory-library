import type { Metadata } from "next";
import { TheoryRelationsAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "理论关系与审核" };

export default function Page() {
  return <TheoryRelationsAdmin />;
}
