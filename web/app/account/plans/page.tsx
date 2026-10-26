import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReadingPlans } from "@/components/research/reading-plans";
export const metadata: Metadata = { title: "阅读计划" };
export default function PlansPage() { return <><ReadingPlans /><SiteFooter reference="reading-plan" /></>; }
