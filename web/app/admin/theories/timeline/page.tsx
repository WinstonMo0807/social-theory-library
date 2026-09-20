import type { Metadata } from "next";
import { NormalizedTimelineAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "理论时间轴管理" };
export default function Page() { return <NormalizedTimelineAdmin />; }
