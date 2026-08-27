import type { Metadata } from "next";
import { TheoryNodesAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "理论传统" };

export default function Page() {
  return <TheoryNodesAdmin />;
}
