/** Server-proven rectangles use the rotated displayed page, independent of PDF/OCR units. */
export type ReaderGeometryBox = {
  normalized_bbox?: number[];
  geometry_status?: "validated" | "unknown";
  geometry?: Record<string, unknown>;
};

/** A temporary viewer rotation relative to the server's displayed-page frame. */
export type ReaderRotation = 0 | 90 | 180 | 270;

export function rotateReaderPoint(point: [number, number], rotation: ReaderRotation): [number, number] {
  const [x, y] = point;
  switch (rotation) {
    case 90: return [1 - y, x];
    case 180: return [1 - x, 1 - y];
    case 270: return [y, 1 - x];
    default: return [x, y];
  }
}

export function rotateReaderBox(box: number[], rotation: ReaderRotation): number[] {
  const first = rotateReaderPoint([box[0], box[1]], rotation);
  const last = rotateReaderPoint([box[2], box[3]], rotation);
  return [Math.min(first[0], last[0]), Math.min(first[1], last[1]),
    Math.max(first[0], last[0]), Math.max(first[1], last[1])];
}

/** Browser selection rectangles return to the original annotation frame. */
export function readerSelectionSourceBox(
  displayedBox: number[], displayedWidth: number, displayedHeight: number,
  sourceWidth: number, sourceHeight: number, rotation: ReaderRotation,
): number[] | null {
  if (![displayedWidth, displayedHeight, sourceWidth, sourceHeight].every(value => Number.isFinite(value) && value > 0)
    || displayedBox.length !== 4 || !displayedBox.every(Number.isFinite)) return null;
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const normalized = displayedBox.map((value, index) => clamp(value / (index % 2 ? displayedHeight : displayedWidth)));
  if (normalized[2] <= normalized[0] || normalized[3] <= normalized[1]) return null;
  const original = rotateReaderBox(normalized, ((360 - rotation) % 360) as ReaderRotation);
  return original.map((value, index) => value * (index % 2 ? sourceHeight : sourceWidth));
}

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
