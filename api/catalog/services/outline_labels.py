"""Read existing page-label observations; never infer a whole-book offset."""
from collections import defaultdict
import re
import unicodedata


LABEL_TOKEN = r"(?:[A-Za-z]{1,8}[-－]?\d{1,5}|\d{1,5}|[ivxlcdmIVXLCDM]{1,12})"
PRINTED_LABEL = rf"{LABEL_TOKEN}(?:\s*[-–—－]\s*{LABEL_TOKEN})?"
LABEL_ONLY = re.compile(rf"^{PRINTED_LABEL}$")
LABEL_RANGE = re.compile(rf"^(?P<start>{LABEL_TOKEN})\s*[-–—－]\s*(?P<end>{LABEL_TOKEN})$")


def label_key(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s*[-–—－]\s*", "-", value)


class OutlineLabels:
    def __init__(self, pages, mapping):
        mapping = mapping if isinstance(mapping, dict) else {}
        prior = {}
        duplicated = set()
        for row in mapping.get("pages", []):
            if not isinstance(row, dict) or type(row.get("pdf_page")) is not int:
                continue
            page = row["pdf_page"]
            if page in prior:
                duplicated.add(page)
            prior[page] = row
        self.by_label = defaultdict(dict)
        actual = {page["index"] for page in pages}
        for page in pages:
            number, printed = page["index"], page["printed_label"]
            row = prior.get(number, {})
            labels = row.get("labels")
            # Applied mapping metadata must still agree with the actual Page.
            # A literal legacy '10–11' alone does not prove a two-page spread.
            if (number in duplicated or not isinstance(labels, list) or not 1 <= len(labels) <= 2
                    or any(not isinstance(label, str) or not label.strip() for label in labels)
                    or "–".join(labels) != printed):
                labels = [printed] if printed else []
            observation = {"pdf_page": number, "label_segment": page.get("label_segment", ""),
                           "printed_labels": labels, "spread": len(labels) == 2}
            for label in [printed, *labels]:
                if key := label_key(label):
                    self.by_label[key][number] = observation
        self.missing = {label_key(row.get("label")) for row in mapping.get("missing", [])
                        if isinstance(row, dict) and type(row.get("after_pdf_page")) is int
                        and row["after_pdf_page"] in actual and row.get("label")}

    def observations(self, label):
        direct = self.by_label.get(label_key(label))
        if direct:
            return list(direct.values())
        match = LABEL_RANGE.fullmatch(str(label).strip())
        if not match:
            return []
        starts = self.by_label.get(label_key(match["start"]), {})
        ends = self.by_label.get(label_key(match["end"]), {})
        result = []
        for start in starts.values():
            # A range requires real endpoints within the same known segment.
            # Multiple possible ends, reversed pages and absent segments are
            # deliberately not resolved by picking the nearest/first number.
            possible = [end for end in ends.values() if end["pdf_page"] >= start["pdf_page"] and
                        (end["pdf_page"] == start["pdf_page"] or
                         start["label_segment"] and end["label_segment"] == start["label_segment"])]
            if len(possible) == 1:
                result.append({**start, "range_end_pdf_page": possible[0]["pdf_page"]})
        return result

    def has_missing_label(self, label):
        if label_key(label) in self.missing:
            return True
        match = LABEL_RANGE.fullmatch(str(label).strip())
        return bool(match and any(label_key(match[key]) in self.missing for key in ("start", "end")))
