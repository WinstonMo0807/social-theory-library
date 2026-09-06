from catalog.contracts.fields import FIELD_CONTRACTS
from catalog.contracts.identifiers import normalize_doi, normalize_isbn, valid_doi, valid_isbn


def normalize_integer(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("布尔值不是年份。")
    return int(str(value).strip())


NORMALIZERS = {"identity": lambda value: value, "trim": lambda value: str(value or "").strip(),
               "isbn": normalize_isbn, "doi": normalize_doi, "integer": normalize_integer}
VALIDATORS = {
    "none": lambda value: True,
    "isbn10": lambda value: valid_isbn(value, 10),
    "isbn13": lambda value: valid_isbn(value, 13),
    "isbn": valid_isbn,
    "doi": valid_doi,
    "document_type": lambda value: value in {"book", "journal_article", "journal_issue", "thesis", "report"},
    "publication_mode": lambda value: value in {"document", "bibliographic"},
    "publication_year": lambda value: value in {None, ""} or (isinstance(value, int) and 1000 <= value <= 2100),
}


def normalize_field(name, value):
    return NORMALIZERS[FIELD_CONTRACTS[name].normalizer](value)


def field_error(name, value):
    contract = FIELD_CONTRACTS.get(name)
    if contract is None:
        return None
    try:
        valid = VALIDATORS[contract.validator](normalize_field(name, value))
    except (TypeError, ValueError):
        valid = False
    if valid:
        return None
    return {"code": f"catalog.invalid_{contract.validator}", "field": name, "severity": "blocking",
            "message": f"{contract.label}格式或校验值无效，请核对原书。", "details": {}}
