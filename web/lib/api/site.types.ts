// Existing public presentation contracts. Only schema-backed imports are generated.
export type AboutPageBlock = {
  id: string;
  key: string;
  block_type: "intro" | "stat" | "feature" | "process" | "principle" | "notice" | "action" | "footer";
  title: string;
  body: string;
  icon: string;
  action_label: string;
  action_href: string;
  sort_order: number;
  visible: boolean;
  configuration: Record<string, unknown>;
};

export type SiteStats = {
  documents: number;
  scholars: number;
  knowledge_objects: number;
  last_updated: string | null;
  last_updated_label: string;
  version: string;
};
