import type { Metadata } from "next";
import { ReadingPathWorkbench } from "@/components/admin/curation/reading-path-workbench";

export const metadata: Metadata = { title: "阅读路径管理" };

export default function Page() {
  return <ReadingPathWorkbench />;
}
