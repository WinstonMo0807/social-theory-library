import type { ReactNode } from "react";
import type { PublicScholarDetail, ScholarSearchParams } from "@/lib/api/scholars.types";
import { ScholarProfile } from "./scholar-profile";

export function ScholarPublicView({ data, footer, preview = false, initialSection = "overview", params = {} }: {
  data: PublicScholarDetail; footer?: ReactNode; preview?: boolean; initialSection?: string; params?: ScholarSearchParams;
}) {
  return <><ScholarProfile key={`${data.id}:${initialSection}`} data={data} preview={preview} initialSection={initialSection} params={params} />{footer}</>;
}
