import { notFound } from "next/navigation";
import { PlacementWorkspace } from "@/components/admin/curation/placement-workspace";
import type { PlacementPage } from "@/lib/api/curation-workspace.client";
const kinds = new Set(["issue","scholar","node","topic","discipline","subdiscipline","reading_path","timeline_event"]);
export default async function Page({params}:{params:Promise<{pageType:string;pageId:string}>}) {
  const {pageType,pageId}=await params;
  if(!kinds.has(pageType)||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(pageId))notFound();
  return <PlacementWorkspace pageType={pageType as PlacementPage} pageId={pageId}/>;
}
