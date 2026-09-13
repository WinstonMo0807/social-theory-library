// Existing public presentation contracts. Only schema-backed imports are generated.
import type { ApiWork } from "./public-catalog";

export type RecommendationItem = {
  id: string;
  position: number;
  reason: string;
  image_override: string;
  target_type: "work" | "theory_school" | "topic" | "scholar";
  target: ApiWork | {
    id: string;
    name: string;
    slug: string;
    description: string;
    symbol?: string;
    hero_image?: string;
  };
};

export type RecommendationPlacement = {
  id: string;
  placement: string;
  title: string;
  item_count: number;
  rotation_days: number;
  enabled: boolean;
  last_generated_at: string | null;
  next_refresh_at: string | null;
  current: {
    id: string;
    starts_at: string;
    expires_at: string;
    source: "automatic" | "manual";
    items: RecommendationItem[];
  } | null;
};

export type RecommendationBundle = {
  shared_for_all_readers: boolean;
  rotation_days: number;
  placements: Record<string, RecommendationPlacement>;
};
