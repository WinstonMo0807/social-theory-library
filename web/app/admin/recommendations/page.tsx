import type { Metadata } from "next";
import { RecommendationsAdmin } from "@/components/knowledge-admin";

export const metadata: Metadata = { title: "推荐管理" };
export default function Page() { return <RecommendationsAdmin />; }
