"""Conservative native PDF heading observations, never confirmed bookmarks."""
from collections import Counter
import math


def styled_headings(blocks):
    """Use character-weighted body size; do not treat a larger font as truth."""
    sizes, lines = Counter(), []
    for block in blocks:
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if str(span.get("text", "")).strip()]
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            box = line.get("bbox", ())
            if not text or len(box) != 4 or not all(type(v) in {float, int} and math.isfinite(v) for v in box):
                continue
            valid = [span for span in spans if type(span.get("size")) in {float, int} and math.isfinite(span["size"]) and span["size"] > 0]
            if not valid or len(valid) != len(spans):
                continue
            for span in valid:
                sizes[round(span["size"], 1)] += len(str(span["text"]).strip())
            lines.append((text, list(box), min(span["size"] for span in valid), line.get("dir", (1, 0))))
    if not sizes or sum(sizes.values()) < 160:
        return []  # A cover or sparse page cannot establish a reliable body size.
    body = sizes.most_common(1)[0][0]
    return [{"text": text, "bbox": box, "font_size": size, "body_font_size": body,
             "direction": list(direction) if isinstance(direction, (tuple, list)) else [],
             "basis": "larger_than_page_body"}
            for text, box, size, direction in lines
            if 2 <= len(text) <= 180 and size >= body * 1.25 and not text.isdecimal()]
