export type OutlineGeometry = { pdf_width?: number; pdf_height?: number; rotation?: number; cropbox?: number[] };
export type OutlineCandidate = {
  source: string;
  title: string;
  pdf_page?: number | null;
  printed_label?: string;
  contents_page?: number | null;
  pdf_position?: number[];
  normalized_position?: number[];
  coordinate_space?: string;
  source_locator?: OutlineNode["source_locator"];
  page_geometry?: OutlineGeometry;
  calibration_status?: string;
};
export type OutlineNode = {
  id?: string;
  parent_id?: string | null;
  title?: string;
  chapter_title: string;
  index: number;
  pdf_page?: number | null;
  printed_label: string;
  level?: number;
  position?: number;
  pdf_position?: number[];
  normalized_position?: number[];
  coordinate_space?: string;
  source_locator?: { bbox?: number[]; coordinate_space?: string; source_width?: number; source_height?: number; page_geometry?: OutlineGeometry; geometry_status?: "validated"|"unknown" };
  page_geometry?: OutlineGeometry;
  outline_revision_id?: string;
  source?: string;
  calibration_status?: string;
  contents_page?: number | null;
  candidate_sources?: OutlineCandidate[];
  candidate_sources_count?: number;
  clear_position?: boolean;
};

export type ReaderOutlineNode = OutlineNode & { id: string; title: string; level: number };

export function prepareOutline(nodes: OutlineNode[]): ReaderOutlineNode[] {
  return nodes.map((node, index) => ({ ...node, id: node.id || `legacy-${index}-${node.index}`,
    title: node.title || node.chapter_title, level: Math.max(1, node.level || 1) }));
}

export function filterOutline(nodes: ReaderOutlineNode[], query: string, collapsed: ReadonlySet<string>) {
  const byId = new Map(nodes.map(node => [node.id, node]));
  const needle = query.trim().toLocaleLowerCase();
  const matches = new Set<string>();
  if (needle) {
    for (const node of nodes) {
      if (!`${node.title} ${node.printed_label} ${node.index}`.toLocaleLowerCase().includes(needle)) continue;
      let current: ReaderOutlineNode | undefined = node;
      const visited = new Set<string>();
      while (current && !visited.has(current.id)) {
        visited.add(current.id); matches.add(current.id);
        current = current.parent_id ? byId.get(current.parent_id) : undefined;
      }
    }
  }
  return nodes.filter(node => {
    if (needle) return matches.has(node.id);
    let parent = node.parent_id;
    const visited = new Set<string>();
    while (parent && !visited.has(parent)) {
      if (collapsed.has(parent)) return false;
      visited.add(parent); parent = byId.get(parent)?.parent_id;
    }
    return true;
  });
}

/** A normalized displayed-page point, only when its coordinate space is known. */
export function outlinePosition(node: OutlineNode): [number, number] | undefined {
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const relative = node.normalized_position;
  if (relative?.length === 2 && relative.every(Number.isFinite)) return [clamp(relative[0]), clamp(relative[1])];
  const width = node.page_geometry?.pdf_width || 0;
  const height = node.page_geometry?.pdf_height || 0;
  const point = node.pdf_position;
  if (point?.length === 2 && point.every(Number.isFinite) && width > 0 && height > 0 &&
      ["displayed_pdf_crop", "pymupdf_toc"].includes(node.coordinate_space || "")) {
    return [clamp(point[0] / width), clamp(point[1] / height)];
  }
  const source = node.source_locator;
  if (source?.geometry_status === "unknown" || !source?.bbox || source.bbox.length !== 4 || !source.bbox.every(Number.isFinite) ||
      !source.source_width || !source.source_height) return undefined;
  const x = source.bbox[0] / source.source_width;
  const y = source.bbox[1] / source.source_height;
  if (source.coordinate_space === "ocr_rendered_page") return [clamp(x), clamp(y)];
  if (source.coordinate_space !== "pymupdf_unrotated") return undefined;
  const geometry = node.page_geometry || source.page_geometry;
  const crop = geometry?.cropbox;
  if (geometry?.rotation === 0) return [clamp(x), clamp(y)];
  // Older records used rotated page dimensions for unrotated text. Only the
  // known crop box can recover that space; otherwise retain a page-only jump.
  if (!crop || crop.length !== 4 || !crop.every(Number.isFinite) || crop[2] <= crop[0] || crop[3] <= crop[1]) return undefined;
  const [x0,y0,x1,y1] = [source.bbox[0]/(crop[2]-crop[0]),source.bbox[1]/(crop[3]-crop[1]),source.bbox[2]/(crop[2]-crop[0]),source.bbox[3]/(crop[3]-crop[1])];
  switch (geometry.rotation) {
    case 90: return [clamp(1 - y1), clamp(x0)];
    case 180: return [clamp(1 - x1), clamp(1 - y1)];
    case 270: return [clamp(y0), clamp(1 - x1)];
    default: return undefined;
  }
}
