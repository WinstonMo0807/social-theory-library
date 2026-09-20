import type { Metadata } from "next";
import { DisciplinesAdmin } from "@/components/knowledge-admin";

export const metadata: Metadata = { title: "学科管理" };
export default function Page() { return <DisciplinesAdmin />; }
