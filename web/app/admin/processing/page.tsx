import type { Metadata } from "next";
import { ProcessingCenter } from "@/components/processing-center";

export const metadata: Metadata = { title: "处理中心" };

export default function ProcessingPage() {
  return <ProcessingCenter />;
}
