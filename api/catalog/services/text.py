import html
import re
import unicodedata

from ftfy import fix_text


WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
LATIN_HYPHEN_BREAK_RE = re.compile(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])")
CJK_LINE_BREAK_RE = re.compile(r"(?<=[\u3400-\u9fff，。！？；：、）】》])\s*\n\s*(?=[\u3400-\u9fff（【《])")
LATIN_LINE_BREAK_RE = re.compile(r"(?<=[A-Za-z0-9,;:])\s*\n\s*(?=[A-Za-z0-9])")
MULTI_BREAK_RE = re.compile(r"\n{3,}")
HEX_PAGE_LABEL_RE = re.compile(r"^<FEFF((?:[0-9A-Fa-f]{4})+)>$")


def normalize_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = WHITESPACE_RE.sub(" ", value)
    return value.strip().casefold()


def clean_page_label(value: str) -> str:
    """Normalize malformed PDF page labels without changing ordinary labels."""
    value = (value or "").strip().replace("\ufeff", "")
    match = HEX_PAGE_LABEL_RE.fullmatch(value)
    if not match:
        return value
    try:
        return "".join(
            chr(int(match.group(1)[index : index + 4], 16))
            for index in range(0, len(match.group(1)), 4)
        ).replace("\ufeff", "")
    except ValueError:
        return value


def clean_copied_text(value: str) -> str:
    value = fix_text(value or "")
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = LATIN_HYPHEN_BREAK_RE.sub("", value)
    value = CJK_LINE_BREAK_RE.sub("", value)
    value = LATIN_LINE_BREAK_RE.sub(" ", value)
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in value.splitlines()]
    value = "\n".join(lines)
    value = MULTI_BREAK_RE.sub("\n\n", value)
    value = re.sub(r" *([，。！？；：、]) *", r"\1", value)
    value = re.sub(r"(?<!\d) +([,.!?;:])(?!\d)", r"\1", value)
    return value.strip()


def clipboard_payload(value: str) -> dict:
    cleaned = clean_copied_text(value)
    paragraphs = [part for part in cleaned.split("\n\n") if part]
    html_value = "".join(f"<p>{html.escape(part)}</p>" for part in paragraphs)
    return {
        "text": cleaned,
        "html": html_value,
        "warnings": [],
    }


def passage_snippet(value: str, query: str, radius: int = 90) -> str:
    value = fix_text(value or "")
    folded = normalize_search_text(value)
    needle = normalize_search_text(query)
    position = folded.find(needle)
    if position < 0:
        return value[: radius * 2].strip()
    start = max(0, position - radius)
    end = min(len(value), position + len(query) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(value) else ""
    return f"{prefix}{value[start:end].strip()}{suffix}"
