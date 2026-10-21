import { serverRequest } from "./server-request";
import { graphFilterKeys, type GraphParams, type PublicTheoryGraph } from "./graph.types";

export function loadPublicGraph(params: GraphParams): Promise<PublicTheoryGraph> {
  const query = new URLSearchParams();
  for (const key of graphFilterKeys) if (params[key]) query.set(key, params[key]);
  return serverRequest<PublicTheoryGraph>(`/catalog/theory-system/graph/${query.size ? `?${query}` : ""}`, { forwardSession: true });
}
