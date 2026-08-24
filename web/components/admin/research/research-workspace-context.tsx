"use client";

import { createContext, useContext } from "react";
import type { WorkflowCandidate, WorkflowDrafts } from "../workflow/workflow-types";
import type { DirtyFields } from "../workflow/workflow-state";

export type ResearchWorkspaceContextValue = {
  mode: "intake" | "maintenance";
  itemId?: string;
  workId?: string;
  editionId?: string;
  draftSessionId: string;
  token: string | null;
  canRun: boolean;
  draftData: WorkflowDrafts;
  changedFields: DirtyFields;
  onCandidateApply?: (candidate: WorkflowCandidate) => boolean;
  onCandidateDecision?: (candidate: WorkflowCandidate, action: string) => Promise<boolean> | boolean;
  onUpdated?: () => Promise<void> | void;
  onMessage?: (message: string) => void;
};

export const ResearchWorkspaceContext = createContext<ResearchWorkspaceContextValue | null>(null);

export function useResearchWorkspace() {
  return useContext(ResearchWorkspaceContext);
}
