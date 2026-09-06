"""Identifier syntax checks, never a claim that a record exists externally.

ISBN checksum: International ISBN Agency User's Manual, appendix 1.
DOI syntax/case handling: DOI Foundation Handbook, DOI Namespace.
"""
import re
import unicodedata
from urllib.parse import unquote, urlsplit


def normalize_isbn(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    text = re.sub(r"^ISBN(?:-1[03])?\s*:?\s*", "", text)
    return re.sub(r"[\s\-‐‑–—]", "", text)


def valid_isbn(value, length=None):
    isbn = normalize_isbn(value)
    if not isbn:
        return True
    if length is not None and len(isbn) != length:
        return False
    if re.fullmatch(r"[0-9]{9}[0-9X]", isbn):
        digits = [int(value) if value != "X" else 10 for value in isbn]
        return sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0
    if re.fullmatch(r"97[89][0-9]{10}", isbn):
        return sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(isbn)) % 10 == 0
    return False


def isbn13_from_10(value):
    isbn = normalize_isbn(value)
    if len(isbn) != 10 or not valid_isbn(isbn, 10):
        raise ValueError("无效 ISBN-10。")
    prefix = "978" + isbn[:9]
    check = (-sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(prefix))) % 10
    return prefix + str(check)


def normalize_doi(value):
    text = str(value or "").strip()
    if text.lower().startswith(("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/")):
        text = unquote(urlsplit(text).path.lstrip("/"))
    elif text.lower().startswith("doi:"):
        text = text[4:].strip()
    return text.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def valid_doi(value):
    text = normalize_doi(value)
    return not text or (len(text) <= 255 and re.fullmatch(r"10\.[0-9]+(?:\.[0-9]+)*/\S+", text) is not None
                        and not any(unicodedata.category(char).startswith("C") for char in text))
