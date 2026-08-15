import type { Metadata } from "next";
import { TheoryNodesAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "理论节点管理" };

export default function Page() {
  return <TheoryNodesAdmin />;
}
