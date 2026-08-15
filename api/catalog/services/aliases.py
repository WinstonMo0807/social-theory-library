import re
import unicodedata

from pypinyin import Style, lazy_pinyin
from unidecode import unidecode


CJK_RE = re.compile(r"[\u3400-\u9fff]")


def search_aliases(*values: str) -> list[str]:
    aliases: list[str] = []
    for raw in values:
        value = " ".join((raw or "").split()).strip()
        if not value:
            continue
        folded = unicodedata.normalize("NFKC", value).casefold()
        aliases.extend([folded, unidecode(folded).casefold()])
        if CJK_RE.search(value):
            full = "".join(lazy_pinyin(value, errors="ignore")).casefold()
            initials = "".join(lazy_pinyin(value, style=Style.FIRST_LETTER, errors="ignore")).casefold()
            spaced = " ".join(lazy_pinyin(value, errors="ignore")).casefold()
            aliases.extend([full, initials, spaced])
    return list(dict.fromkeys(alias for alias in aliases if alias))
