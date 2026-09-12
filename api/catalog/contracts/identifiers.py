"""Identifier syntax checks, never a claim that a record exists externally.

ISBN checksum: International ISBN Agency User's Manual, appendix 1.
DOI syntax/case handling: DOI Foundation Handbook, DOI Namespace.
"""
from copy import deepcopy
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit, urlunsplit


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


# These rules establish syntax and display only, not identity or registration.
# Sources: https://www.issn.org/faq/what-is-an-issn/
# https://www.loc.gov/issn/basics/basics-checkdigit.html
# https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
# https://viaf.org/viaf/data
# https://help.openalex.org/data/
# https://www.wikidata.org/wiki/Help:Items
# https://help.oclc.org/Metadata_Services/WorldShare_Collection_Manager/Data_sync_collections/Prepare_your_data/30035_field_and_OCLC_control_numbers
IDENTIFIER_SCHEMES = frozenset({"isbn", "isbn10", "isbn13", "doi", "issn", "url", "oclc", "openalex", "viaf", "wikidata", "orcid"})
SCHEME_ALIASES = {"isbn-10": "isbn10", "isbn_10": "isbn10", "isbn-13": "isbn13", "isbn_13": "isbn13", "doi_url": "doi", "ocn": "oclc", "ocolc": "oclc"}
OPENALEX_NAMESPACES = {"works": "W", "authors": "A", "sources": "S", "institutions": "I", "publishers": "P", "funders": "F", "awards": "G", "topics": "T", "concepts": "C", "keywords": "K"}
UNIQUENESS_POLICY = "scheme_and_normalized_value; local_duplicates_require_human_resolution"


def canonical_identifier_scheme(scheme):
    name = str(scheme).strip().casefold()
    canonical = SCHEME_ALIASES.get(name, name)
    return canonical if canonical in IDENTIFIER_SCHEMES else scheme


def _identifier_text(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("标识符必须是文本或数字。")
    text = str(value).strip()
    if not text or len(text) > 500 or any(unicodedata.category(char).startswith("C") for char in text):
        raise ValueError("标识符为空、过长或包含控制字符。")
    return text


def _registry_value(text, hosts, path_pattern):
    if "://" not in text:
        return text
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or parts.hostname not in hosts or parts.username or parts.password or parts.port or parts.query or parts.fragment:
        raise ValueError("标识符网址不属于对应登记机构。")
    matched = re.fullmatch(path_pattern, unquote(parts.path))
    if not matched:
        raise ValueError("标识符网址路径无效。")
    return matched.group(1)


def normalize_issn(value):
    text = _identifier_text(value)
    text = _registry_value(text, {"portal.issn.org"}, r"/resource/ISSN/([^/]+)/?")
    text = re.sub(r"^(?:urn:issn:|issn\s*:?)\s*", "", text, flags=re.I)
    compact = re.sub(r"[\s\-‐‑–—]", "", text).upper()
    if not re.fullmatch(r"[0-9]{7}[0-9X]", compact):
        raise ValueError("ISSN 必须是八位，末位可以是 X。")
    total = sum(int(char) * weight for char, weight in zip(compact[:7], range(8, 1, -1)))
    if (total + (10 if compact[-1] == "X" else int(compact[-1]))) % 11:
        raise ValueError("ISSN 校验位错误。")
    return compact[:4] + "-" + compact[4:]


def normalize_orcid(value):
    text = _registry_value(_identifier_text(value), {"orcid.org", "www.orcid.org"}, r"/([^/]+)/?")
    text = re.sub(r"^orcid\s*:?\s*", "", text, flags=re.I)
    compact = re.sub(r"[\s-]", "", text).upper()
    if not re.fullmatch(r"[0-9]{15}[0-9X]", compact):
        raise ValueError("ORCID 必须保留全部十六位，末位可以是 X。")
    total = 0
    for char in compact[:15]:
        total = (total + int(char)) * 2
    check = (12 - total % 11) % 11
    if compact[-1] != ("X" if check == 10 else str(check)):
        raise ValueError("ORCID 校验位错误。")
    return "-".join(compact[index:index + 4] for index in range(0, 16, 4))


def normalize_identifier(scheme, value):
    """Normalize one explicit input; unknown schemes and raw JSON stay opaque."""
    scheme = canonical_identifier_scheme(scheme)
    if scheme not in IDENTIFIER_SCHEMES:
        return deepcopy(value)
    text = _identifier_text(value)
    if scheme in {"isbn", "isbn10", "isbn13"}:
        text = normalize_isbn(text)
        if not valid_isbn(text, {"isbn10": 10, "isbn13": 13}.get(scheme)):
            raise ValueError("ISBN 格式或校验位错误。")
    elif scheme == "doi":
        text = normalize_doi(text)
        if not valid_doi(text):
            raise ValueError("DOI 格式无效。")
    elif scheme == "issn":
        return normalize_issn(text)
    elif scheme == "orcid":
        return normalize_orcid(text)
    elif scheme == "viaf":
        text = _registry_value(text, {"viaf.org", "www.viaf.org"}, r"/(?:[a-z]{2}/)?viaf/([0-9]+)/?")
        text = re.sub(r"^viaf\s*:\s*", "", text, flags=re.I)
        if not re.fullmatch(r"[0-9]+", text) or not int(text):
            raise ValueError("VIAF 必须是正数编号。")
    elif scheme == "wikidata":
        text = _registry_value(text, {"wikidata.org", "www.wikidata.org"}, r"/(?:wiki|entity)/([^/]+)/?")
        text = re.sub(r"^(?:wikidata|wd)\s*:\s*", "", text, flags=re.I).upper()
        if not re.fullmatch(r"Q[1-9][0-9]*", text):
            raise ValueError("Wikidata 人物或知识条目标识符必须是 Q 编号。")
    elif scheme == "oclc":
        text = _registry_value(text, {"worldcat.org", "www.worldcat.org", "search.worldcat.org"}, r"/(?:oclc|title)/([0-9]+)/?")
        text = re.sub(r"^(?:\(OCoLC\)|oclc\s*:\s*)", "", text, flags=re.I)
        text = re.sub(r"^(?:ocm|ocn|on)", "", text, flags=re.I).strip()
        if not re.fullmatch(r"[0-9]+", text) or not int(text):
            raise ValueError("OCLC 必须是正数编号。")
        text = str(int(text))
    elif scheme == "openalex":
        text = _registry_value(text, {"openalex.org", "www.openalex.org"}, r"/([^?#]+?)/?")
        text = re.sub(r"^openalex\s*:\s*", "", text, flags=re.I)
        if "/" in text:
            namespace, key = text.split("/", 1)
            namespace = namespace.casefold()
            if namespace in {"domains", "fields", "subfields", "sdgs"} and re.fullmatch(r"[1-9][0-9]*", key):
                return f"{namespace}/{key}"
            if namespace == "keywords" and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", key):
                return f"keywords/{key}"
            if namespace not in OPENALEX_NAMESPACES or not key.upper().startswith(OPENALEX_NAMESPACES[namespace]):
                raise ValueError("OpenAlex 编号与实体类型不一致。")
            text = key
        text = text.upper()
        if not re.fullmatch(r"[WASIPFGTCK][1-9][0-9]*", text):
            raise ValueError("OpenAlex 编号格式无效。")
    elif scheme == "url":
        from django.core.exceptions import ValidationError
        from django.core.validators import URLValidator
        try:
            URLValidator(schemes=["http", "https"])(text)
            parts = urlsplit(text)
            if parts.username or parts.password:
                raise ValueError("标识符网址不能含登录凭据。")
            text = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, parts.fragment))
        except ValidationError as error:
            raise ValueError("网址必须是有效的 HTTP 或 HTTPS 地址。") from error
    return _identifier_text(text)


def describe_identifier(scheme, value, *, source=None):
    canonical = canonical_identifier_scheme(scheme)
    known = canonical in IDENTIFIER_SCHEMES
    record = {"scheme": scheme, "canonical_scheme": canonical, "value": deepcopy(value),
              "normalized_value": None, "display_value": value if isinstance(value, str) else str(value),
              "uri": None, "status": "unrecognized", "source": deepcopy(source) if source else {"kind": "unrecorded"},
              "externally_verified": False, "uniqueness_policy": UNIQUENESS_POLICY if known else "opaque; preserve_existing_keys_and_values"}
    if not known:
        return record
    try:
        normalized = normalize_identifier(canonical, value)
    except (ValueError, TypeError):
        record["status"] = "invalid"
        return record
    record.update(normalized_value=normalized, display_value=normalized, status="syntax_valid")
    templates = {"doi": "https://doi.org/{}", "issn": "https://portal.issn.org/resource/ISSN/{}",
                 "orcid": "https://orcid.org/{}", "viaf": "https://viaf.org/viaf/{}",
                 "wikidata": "https://www.wikidata.org/entity/{}", "oclc": "https://www.worldcat.org/oclc/{}",
                 "openalex": "https://openalex.org/{}", "isbn": "urn:isbn:{}", "isbn10": "urn:isbn:{}", "isbn13": "urn:isbn:{}"}
    record["uri"] = normalized if canonical == "url" else templates[canonical].format(quote(normalized, safe="/"))
    if canonical == "orcid":
        record["display_value"] = record["uri"]
    return record


def describe_external_identifiers(values, *, source=None):
    return [describe_identifier(scheme, value, source=source) for scheme, value in values.items()] if isinstance(values, dict) else []


def validate_external_identifiers(values, *, previous=None):
    """Validate changed known values, without rewriting historical JSON."""
    if not isinstance(values, dict):
        raise ValueError("external_ids 必须是对象。")
    previous = previous if isinstance(previous, dict) else {}
    seen = {}
    for scheme, value in values.items():
        canonical = canonical_identifier_scheme(scheme)
        unchanged = scheme in previous and type(previous[scheme]) is type(value) and previous[scheme] == value
        if canonical not in IDENTIFIER_SCHEMES:
            continue
        try:
            normalized = normalize_identifier(canonical, value)
        except (TypeError, ValueError):
            if unchanged:
                continue
            raise ValueError(f"{canonical} 标识符格式或校验位无效。") from None
        if canonical in seen and seen[canonical][0] != normalized and not (unchanged and seen[canonical][1]):
            raise ValueError(f"{canonical} 存在不同写法的冲突值，请人工核对。")
        seen[canonical] = (normalized, unchanged)
    return deepcopy(values)


def validate_model_external_identifiers(instance):
    """Used by model/form clean; does not clean data on reads or migrations."""
    from django.core.exceptions import ValidationError
    previous = None
    if not instance._state.adding:
        previous = type(instance).objects.filter(pk=instance.pk).values_list("external_ids", flat=True).first()
    try:
        validate_external_identifiers(instance.external_ids, previous=previous)
    except ValueError as error:
        raise ValidationError({"external_ids": str(error)}) from error
