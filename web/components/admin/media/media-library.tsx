"use client";

import { useSearchParams } from "next/navigation";
import { MediaWorkspace, ObjectMediaWorkspace, type MediaObjectType } from "./media-workspace";
import { MediaLibraryCatalog } from "./media-library-catalog";

export function MediaLibrary() {
  const params = useSearchParams(), edition = params.get("edition"), slot = params.get("slot") || "cover";
  const scholar = params.get("scholar"), objectId = params.get("object_id"), objectType = params.get("object_type"), media = params.get("media");
  const validId = (value: string | null) => Boolean(value && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value));
  const invalid = [edition, scholar, objectId, media].filter(Boolean).length > 1 || [edition, scholar, objectId, media].some(value => value !== null && !validId(value));
  if (!invalid) {
    if (scholar && !objectType && slot === "cover") return <ObjectMediaWorkspace objectType="scholar_profile" objectId={scholar} />;
    if (objectId && objectType && ["knowledge_node", "reading_path", "discipline", "subdiscipline", "topic"].includes(objectType) && slot === "cover") return <ObjectMediaWorkspace objectType={objectType as MediaObjectType} objectId={objectId} />;
    if (edition && !objectType && (slot === "cover" || slot === "recommendation")) return <MediaWorkspace editionId={edition} slot={slot} />;
    if (!edition && !scholar && !objectId && !objectType && slot === "cover") return <MediaLibraryCatalog initialMediaId={media || ""} />;
  }
  return <p role="alert">媒体入口的对象或用途不明确，请返回原编辑页面重新进入。</p>;
}
