import type { PlacementPage, PlacementState } from "@/lib/api/curation-workspace.client";
import { serverRequest } from "@/lib/api/server-request";
import { PlacementList } from "./placement-list";

export async function PublishedPlacements({type,id}:{type:PlacementPage;id:string}) {
  let data: PlacementState;
  try { data = await serverRequest<PlacementState>(`/catalog/content-placements/${type}/${encodeURIComponent(id)}/`); }
  catch { return <section className="page-shell" role="status"><p>延伸阅读暂时无法读取，请稍后重新打开本页。</p></section>; }
  if (!data.configured || data.withdrawn || !data.items.some(row=>!row.concept_usage)) return null;
  // Subdiscipline already renders exact spans in its original sources section.
  const items = type === "subdiscipline" ? data.items.filter(row=>row.target.type!=="span") : data.items;
  return <PlacementList items={items} groups={data.groups}/>;
}
