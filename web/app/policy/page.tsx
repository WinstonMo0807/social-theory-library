import type { Metadata } from "next";
import { PolicyWorkspace } from "./policy-workspace";

export const metadata: Metadata = { title: "政策库 · 研究预览", robots: { index: false, follow: false } };
export default function PolicyPage() { return <PolicyWorkspace />; }
