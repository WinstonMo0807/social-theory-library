import type { Metadata } from "next";
import { ReadingPathsAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "阅读路径管理" };

export default function Page() {
  return <ReadingPathsAdmin />;
}
