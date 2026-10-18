"""Expose confirmed spread labels without interpreting arbitrary range strings."""
from catalog.services.text import clean_page_label


def structured_page_labels(page):
    label = clean_page_label(page.printed_label)
    stored = ((page.asset.validation_details or {}).get("page_mapping") or {}).get("pages", [])
    row = next((row for row in stored if row.get("pdf_page") == page.index), {})
    labels = row.get("labels")
    if not (isinstance(labels, list) and 1 <= len(labels) <= 2 and all(isinstance(v, str) and v for v in labels)
            and clean_page_label("–".join(labels)) == label):
        labels = [label] if label else []
    return {"printed_labels": labels, "printed_label_precision": "spread" if len(labels) == 2 else "page" if labels else "unknown"}


def claimed_page_status(references, claimed_label):
    if not claimed_label:
        return "not_specified"
    anchors = [anchor for ref in references if ref.get("source_status") == "available"
               for anchor in ref.get("anchors", [ref])]
    # Text found on a two-page scan is not evidence of which printed half contains it.
    return "matched" if any(anchor.get("printed_label_precision") != "spread" and
        anchor.get("printed_label") == claimed_label for anchor in anchors) else "needs_review"
