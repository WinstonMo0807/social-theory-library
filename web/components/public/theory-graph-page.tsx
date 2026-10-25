import { SiteFooter } from "@/components/site-footer";
import { ServerApiError } from "@/lib/api/server-request";
import { loadPublicGraph } from "@/lib/api/graph.server";
import { graphParams, type GraphSearchParams, type PublicTheoryGraph } from "@/lib/api/graph.types";
import { TheoryGraphWorkspace } from "./theory-graph-workspace";

export async function TheoryGraphPage({ searchParams }: { searchParams: GraphSearchParams }) {
  const params = graphParams(searchParams);
  const rawSaved = searchParams.saved_view;
  const savedView = Array.isArray(rawSaved) ? rawSaved[0] || "" : rawSaved || "";
  let graph: PublicTheoryGraph | null = null, error = "";
  try { if (!savedView) graph = await loadPublicGraph(params); }
  catch (failure) {
    error = failure instanceof ServerApiError && [400, 404].includes(failure.status)
      ? "当前中心或筛选范围不可用，请重新选择公开条目或调整条件。"
      : "暂时无法读取实际关系，请重试。";
  }
  return <><TheoryGraphWorkspace key={`${JSON.stringify(params)}:${savedView}`} initialGraph={graph} initialParams={params} initialError={error} initialSavedView={savedView} /><SiteFooter reference="graph" /></>;
}
