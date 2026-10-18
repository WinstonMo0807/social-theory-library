/** Server-proven rectangles use the rotated displayed page, independent of PDF/OCR units. */
export type ReaderGeometryBox = {
  normalized_bbox?: number[];
  geometry_status?: "validated" | "unknown";
  geometry?: Record<string, unknown>;
};

export function validatedNormalizedBox(value: ReaderGeometryBox): number[] | null {
  const box = value.normalized_bbox;
  if (value.geometry_status !== "validated" || !Array.isArray(box) || box.length !== 4 ||
      !box.every(coordinate => typeof coordinate === "number" && Number.isFinite(coordinate) && coordinate >= 0 && coordinate <= 1) ||
      box[2] <= box[0] || box[3] <= box[1]) return null;
  return box;
}

export function displayedReaderBox(value: ReaderGeometryBox, width: number, height: number) {
  const box = validatedNormalizedBox(value);
  if (!box || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return [box[0] * width, box[1] * height, box[2] * width, box[3] * height];
}

/** Personal selections already use the displayed page's source dimensions. */
export function displayedHighlightBox(value: ReaderGeometryBox & { bbox: number[]; kind?: string }, width: number, height: number, sourceWidth: number, sourceHeight: number) {
  const normalized = displayedReaderBox(value, width, height);
  if (normalized) return normalized;
  if (value.geometry_status !== undefined || value.normalized_bbox !== undefined ||
      !["highlight", "underline", "note"].includes(value.kind || "") ||
      ![width, height, sourceWidth, sourceHeight].every(size => Number.isFinite(size) && size > 0) ||
      value.bbox.length !== 4 || !value.bbox.every(Number.isFinite) ||
      value.bbox[2] <= value.bbox[0] || value.bbox[3] <= value.bbox[1]) return null;
  return [value.bbox[0] * width / sourceWidth, value.bbox[1] * height / sourceHeight,
    value.bbox[2] * width / sourceWidth, value.bbox[3] * height / sourceHeight];
}
