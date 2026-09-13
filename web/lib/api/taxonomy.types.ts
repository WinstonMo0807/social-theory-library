// Existing public presentation contracts. Only schema-backed imports are generated.
import type { ApiWork } from "./public-catalog";

export type Discipline = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  introduction: string;
  hero_image: string;
  sort_order: number;
  theory_count: number;
  subdiscipline_count: number;
  topic_count: number;
  work_count: number;
  scholar_count: number;
};

export type Subdiscipline = {
  id: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  hero_image: string;
  discipline: Discipline;
  parent: { id: string; name: string; slug: string } | null;
  research_object: string;
  core_questions: string[];
  formation_period: string;
  research_directions: string[];
  methods: string[];
  representative_issues: string[];
  theories: { id: string; name: string; slug: string; role: string }[];
  topics: { id: string; name: string; slug: string; relation_label: string }[];
  works: ApiWork[];
  scholars: { id: string; name: string; slug: string }[];
};
