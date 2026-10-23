import type { ReactNode } from "react";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import { ReadingPathWorkspace } from "./reading-path-workspace";

export function ReadingPathPublicView({ path, footer, preview = false, initialCopy = false, initialRevision = "", initialPlanId = "", initialTab = "route", previewStageId = "", initialStage = "" }: {
  path: PublicReadingPath; footer: ReactNode; preview?: boolean; initialCopy?: boolean; initialRevision?: string; initialPlanId?: string; initialTab?: string; previewStageId?: string; initialStage?: string;
}) {
  return <><ReadingPathWorkspace key={`${path.id}:${path.revision.token}:${initialPlanId}:${initialTab}:${initialStage}`} path={path} preview={preview} initialCopy={initialCopy} initialRevision={initialRevision} initialPlanId={initialPlanId} initialTab={initialTab} previewStageId={previewStageId} initialStage={initialStage} />{footer}</>;
}
