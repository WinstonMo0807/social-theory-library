"use client";

import { WorkflowEditor } from "./admin/workflow/workflow-editor";

/** Canonical intake entry retained for existing imports and external links. */
export function IntakeWorkspace({ itemId }: { itemId: string }) {
  return <WorkflowEditor mode="intake" itemId={itemId} />;
}
