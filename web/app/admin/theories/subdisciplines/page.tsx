import type { Metadata } from "next";
import { SubdisciplinesAdmin } from "@/components/knowledge-admin";

export const metadata: Metadata = { title: "子学科管理" };
export default function Page() { return <SubdisciplinesAdmin />; }
