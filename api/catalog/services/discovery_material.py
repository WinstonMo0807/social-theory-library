"""Conservative diagnostic hints, not production visibility filters or gold."""
import re

MATERIAL_ROLES = {
    "body": "正文论述", "preface": "序言或导论", "afterword": "后记或译者说明", "footnote": "注释",
    "toc": "目录", "index": "书后索引", "bibliography": "参考文献",
    "publication_metadata": "版权或编目信息", "mixed": "多种材料混合", "unknown": "无法确定",
}


def publication_metadata_hint(text):
    """Flag only two explicit publishing patterns; keep all other types unknown.

    Hints are reviewed separately. In particular, an introduction, a footnote,
    a page number or an ISBN mentioned in a substantive passage is not enough.
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if re.match(r"^图书在版编目\s*[（(]\s*CIP\s*[）)]\s*数据", value, re.I):
        return {"role": "publication_metadata", "reason": "explicit_cip_header", "verified": False}
    if len(value) <= 1200 and "©" in value and re.search(r"all rights reserved\b", value, re.I):
        if re.search(r"copyright|originally published|translation", value, re.I):
            return {"role": "publication_metadata", "reason": "explicit_copyright_notice", "verified": False}
    return {"role": "unknown", "reason": "", "verified": False}


def metadata_last(rows):
    """Evaluation variant only: defer, never delete, explicitly hinted metadata."""
    evidence, deferred = [], []
    for row in rows:
        hint = publication_metadata_hint(row.get("text") or row.get("excerpt"))
        (deferred if hint["role"] == "publication_metadata" else evidence).append(row)
    return evidence + deferred
