// Existing public presentation contracts. Only schema-backed imports are generated.
import type { CuratedWorkClaim } from "../data";

export type PublicCuratedClaim = Omit<CuratedWorkClaim, "kind"> & {
  kind: "core_viewpoint" | "major_criticism" | "major_response" | "debate_position";
  position: "direct" | "support" | "oppose" | "qualify";
};

export type PublicCuratedClaimGroups = Record<
  "core_viewpoint" | "major_criticism" | "major_response",
  PublicCuratedClaim[]
>;

export type PublicKnowledgeNodeLink = {
  id: string;
  node_type: "theory_tradition" | "concept" | "debate" | "research_problem" | "subdiscipline";
  name: string;
  foreign_name: string;
  slug: string;
  summary: string;
  relation_label: string;
  is_representative?: boolean;
  relation_source?: "person_relation" | "published_work_relation";
};
