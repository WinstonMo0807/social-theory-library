import type { Metadata } from "next";
import { AboutAdmin } from "@/components/knowledge-admin";

export const metadata: Metadata = { title: "关于书库管理" };
export default function Page() { return <AboutAdmin />; }
