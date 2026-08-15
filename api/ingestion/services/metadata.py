from dataclasses import dataclass, field
import re
from pathlib import Path
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

import fitz
import httpx
from django.conf import settings

from catalog.models import DocumentType
from ingestion.services.metadata_scoring import AI_SOURCE_RE, calibrate_candidate, ranked_candidates


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
ISBN_RE = re.compile(r"\b(?:97[89][-\s]?)?\d(?:[-\s]?\d){8,12}[0-9X]\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
TRADITIONAL_MARKERS = set("學國體會義論與為書東後這個們來時說無現專業術經濟社會發展關係")


@dataclass
class Candidate:
    field_name: str
    value: object
    source: str
    confidence: float
    evidence: dict = field(default_factory=dict)


class ProviderCandidates(list):
    """List-compatible provider result retaining the provider response for audit/cache."""

    def __init__(
        self,
        values=(),
        *,
        raw_response=None,
        external_id: str = "",
        provider_version: str = "v1",
    ):
        super().__init__(values)
        self.raw_response = raw_response if raw_response is not None else {}
        self.external_id = external_id
        self.provider_version = provider_version


def _clean_pdf_metadata(value: str) -> str:
    value = (value or "").strip()
    if value.lower() in {"untitled", "microsoft word", "扫描全能王"}:
        return ""
    return value


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        line = " ".join(line.split()).strip()
        if 4 <= len(line) <= 240 and not line.isdigit():
            return line
    return ""


def _split_authors(value: str) -> list[str]:
    if not value:
        return []
    chunks = re.split(r"[;,；，、]|\s+and\s+", value)
    return [chunk.strip() for chunk in chunks if 1 < len(chunk.strip()) < 120]


def detect_document_type(first_text: str, metadata: dict) -> tuple[str, float]:
    sample = f"{metadata.get('subject', '')}\n{first_text[:5000]}".casefold()
    if any(token in sample for token in ("学位论文", "博士论文", "硕士论文", "dissertation", "thesis submitted")):
        return DocumentType.THESIS, 0.94
    if any(token in sample for token in ("research report", "研究报告", "课题报告", "policy report")):
        return DocumentType.REPORT, 0.9
    if DOI_RE.search(sample) or (
        any(token in sample for token in ("abstract", "摘要"))
        and any(token in sample for token in ("keywords", "关键词"))
    ):
        return DocumentType.JOURNAL_ARTICLE, 0.84
    return DocumentType.BOOK, 0.72


def _language_candidate(text: str) -> tuple[str, float]:
    sample = text[:20000]
    latin_count = sum(character.isascii() and character.isalpha() for character in sample)
    cjk_count = sum("\u3400" <= character <= "\u9fff" for character in sample)
    if latin_count > max(120, cjk_count * 2):
        return "en", 0.88
    traditional_count = sum(character in TRADITIONAL_MARKERS for character in sample)
    if traditional_count >= max(5, round(cjk_count * 0.015)):
        return "zh-TW", 0.76
    return "zh-CN", 0.74


def _line_candidates(text: str) -> list[str]:
    return [
        " ".join(line.split()).strip()
        for line in text.splitlines()
        if " ".join(line.split()).strip()
    ]


def extract_text_candidates(
    text: str,
    *,
    source: str = "first_pages",
    metadata: dict | None = None,
) -> list[Candidate]:
    metadata = metadata or {}
    candidates: list[Candidate] = []
    visible_title = _first_meaningful_line(text)
    if visible_title:
        candidates.append(Candidate("title", visible_title, source, 0.68, {"page": 1}))

    years = [int(match.group(0)) for match in YEAR_RE.finditer(text[:12000])]
    if years:
        candidates.append(
            Candidate(
                "publication_year",
                max(years),
                source,
                0.62,
                {"page_range": [1, 5]},
            )
        )

    document_type, confidence = detect_document_type(text, metadata)
    candidates.append(Candidate("document_type", document_type, source, confidence))
    language, language_confidence = _language_candidate(text)
    candidates.append(Candidate("language", language, source, language_confidence))

    doi_match = DOI_RE.search(text)
    if doi_match:
        candidates.append(
            Candidate(
                "doi",
                doi_match.group(0).rstrip(".,;)"),
                source,
                0.93,
                {"page_range": [1, 5]},
            )
        )

    isbn_match = ISBN_RE.search(text)
    if isbn_match:
        value = re.sub(r"[-\s]", "", isbn_match.group(0)).upper()
        candidates.append(
            Candidate("isbn", value, source, 0.9, {"page_range": [1, 5]})
        )

    lines = _line_candidates(text[:16000])
    author_patterns = (
        re.compile(r"^(?:作者|著者|编著|編著|主编|主編)\s*[:：]?\s*(.{2,120})$"),
        re.compile(r"^(.{2,80})\s+(?:著|编著|編著|主编|主編)$"),
        re.compile(r"^(?:by|authors?)\s*[:：]?\s*(.{3,160})$", re.IGNORECASE),
    )
    for line_index, line in enumerate(lines[:40]):
        for pattern in author_patterns:
            match = pattern.match(line)
            if not match:
                continue
            authors = _split_authors(match.group(1))
            if authors:
                candidates.append(
                    Candidate(
                        "authors",
                        authors,
                        source,
                        0.78,
                        {"page": 1, "line": line_index + 1},
                    )
                )
                break
        if any(candidate.field_name == "authors" for candidate in candidates):
            break

    for line_index, line in enumerate(lines[:80]):
        folded = line.casefold()
        if (
            ("出版社" in line or re.search(r"\b(?:university\s+)?press\b", folded))
            and len(line) <= 180
        ):
            candidates.append(
                Candidate(
                    "publisher",
                    line.strip("，,。.; "),
                    source,
                    0.72,
                    {"page": 1, "line": line_index + 1},
                )
            )
            break

    abstract_match = re.search(
        r"(?:摘要|abstract)\s*[:：]?\s*(.{80,5000}?)(?=\n\s*(?:关键词|關鍵詞|keywords?)\s*[:：]?)",
        text[:20000],
        re.IGNORECASE | re.DOTALL,
    )
    if abstract_match:
        abstract = " ".join(abstract_match.group(1).split())
        candidates.append(Candidate("abstract", abstract, source, 0.78, {"page_range": [1, 5]}))

    if document_type == DocumentType.THESIS:
        degree = next(
            (
                label
                for label in ("博士学位论文", "博士論文", "硕士学位论文", "碩士論文", "doctoral dissertation", "master's thesis")
                if label.casefold() in text[:12000].casefold()
            ),
            "",
        )
        if degree:
            candidates.append(Candidate("degree_type", degree, source, 0.82, {"page_range": [1, 5]}))
        institution = next(
            (
                line
                for line in lines[:80]
                if len(line) <= 120
                and (
                    line.endswith(("大学", "大學", "学院", "學院"))
                    or "university" in line.casefold()
                )
            ),
            "",
        )
        if institution:
            candidates.append(
                Candidate("degree_institution", institution, source, 0.76, {"page_range": [1, 5]})
            )

    if document_type == DocumentType.REPORT:
        institution = next(
            (
                line
                for line in lines[:80]
                if 3 <= len(line) <= 140
                and line.endswith(("研究院", "研究所", "研究中心", "委员会", "委員會", "中心"))
            ),
            "",
        )
        if institution:
            candidates.append(
                Candidate("report_institution", institution, source, 0.72, {"page_range": [1, 5]})
            )
    return candidates


def extract_local_candidates(path: str | Path) -> tuple[list[Candidate], str]:
    with fitz.open(str(path)) as document:
        metadata = document.metadata or {}
        first_text = "\n".join(
            document[index].get_text("text")
            for index in range(min(5, document.page_count))
        )
    candidates: list[Candidate] = []

    title = _clean_pdf_metadata(metadata.get("title", ""))
    if title:
        candidates.append(Candidate("title", title, "pdf_metadata", 0.78, {"key": "title"}))
    authors = _split_authors(_clean_pdf_metadata(metadata.get("author", "")))
    if authors:
        candidates.append(Candidate("authors", authors, "pdf_metadata", 0.78, {"key": "author"}))

    candidates.extend(
        extract_text_candidates(
            first_text,
            source="first_pages",
            metadata=metadata,
        )
    )
    return candidates, first_text


def resolve_doi(doi: str) -> list[Candidate]:
    user_agent = "SocialTheoryLibrary/2.6.1 (metadata resolution"
    if settings.CROSSREF_MAILTO:
        user_agent = f"{user_agent}; mailto:{settings.CROSSREF_MAILTO}"
    user_agent = f"{user_agent})"
    response = httpx.get(
        f"https://api.crossref.org/works/{doi}",
        headers={"User-Agent": user_agent},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    raw_response = response.json()
    message = raw_response["message"]
    candidates = []
    if message.get("title"):
        candidates.append(Candidate("title", message["title"][0], "crossref", 0.98, {"doi": doi}))
    authors = [
        " ".join(filter(None, (author.get("given"), author.get("family"))))
        for author in message.get("author", [])
    ]
    if authors:
        candidates.append(Candidate("authors", authors, "crossref", 0.98, {"doi": doi}))
    issued = message.get("issued", {}).get("date-parts", [[]])
    if issued and issued[0]:
        candidates.append(Candidate("publication_year", issued[0][0], "crossref", 0.98, {"doi": doi}))
    if message.get("container-title"):
        candidates.append(Candidate("journal_title", message["container-title"][0], "crossref", 0.97, {"doi": doi}))
    if message.get("volume"):
        candidates.append(Candidate("volume", message["volume"], "crossref", 0.97, {"doi": doi}))
    if message.get("issue"):
        candidates.append(Candidate("issue", message["issue"], "crossref", 0.97, {"doi": doi}))
    if message.get("page"):
        candidates.append(Candidate("page_range", message["page"], "crossref", 0.97, {"doi": doi}))
    return ProviderCandidates(
        candidates,
        raw_response=raw_response,
        external_id=doi,
        provider_version="crossref-rest-v1",
    )


def resolve_isbn(isbn: str) -> list[Candidate]:
    response = httpx.get(
        f"https://openlibrary.org/isbn/{isbn}.json",
        headers={"User-Agent": "SocialTheoryLibrary/2.6.1 metadata-candidate-service"},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    candidates = []
    if data.get("title"):
        candidates.append(Candidate("title", data["title"], "openlibrary", 0.92, {"isbn": isbn}))
    if data.get("publish_date"):
        year_match = YEAR_RE.search(data["publish_date"])
        if year_match:
            candidates.append(Candidate("publication_year", int(year_match.group()), "openlibrary", 0.9, {"isbn": isbn}))
    if data.get("publishers"):
        candidates.append(Candidate("publisher", data["publishers"][0], "openlibrary", 0.9, {"isbn": isbn}))
    if data.get("publish_places"):
        for order, place in enumerate(data["publish_places"][:8]):
            candidates.append(
                Candidate(
                    "publication_place",
                    place,
                    "openlibrary",
                    0.93 if order == 0 else 0.9,
                    {"isbn": isbn, "edition_key": data.get("key", ""), "order": order},
                )
            )
    search_response = httpx.get(
        "https://openlibrary.org/search.json",
        params={
            "isbn": isbn,
            "fields": "title,author_name,first_publish_year,publisher,publish_place,edition_key",
            "limit": 1,
        },
        headers={"User-Agent": "SocialTheoryLibrary/2.6.1 metadata-candidate-service"},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    search_response.raise_for_status()
    records = search_response.json().get("docs", [])
    if records:
        record = records[0]
        if record.get("author_name"):
            candidates.append(
                Candidate(
                    "authors",
                    record["author_name"],
                    "openlibrary_search",
                    0.93,
                    {"isbn": isbn},
                )
            )
        for order, place in enumerate(record.get("publish_place") or []):
            candidates.append(
                Candidate(
                    "publication_place",
                    place,
                    "openlibrary_search",
                    0.88,
                    {"isbn": isbn, "edition_key": (record.get("edition_key") or [""])[0], "order": order},
                )
            )
    return ProviderCandidates(
        candidates,
        raw_response={"edition": data, "search": search_response.json()},
        external_id=isbn,
        provider_version="open-library-v1",
    )


def search_crossref_title(title: str, *, limit: int = 3) -> list[Candidate]:
    user_agent = "SocialTheoryLibrary/2.6.1 (administrator metadata suggestions"
    if settings.CROSSREF_MAILTO:
        user_agent = f"{user_agent}; mailto:{settings.CROSSREF_MAILTO}"
    user_agent = f"{user_agent})"
    response = httpx.get(
        "https://api.crossref.org/works",
        params={
            "query.title": title,
            "rows": max(1, min(limit, 5)),
            "select": "DOI,title,author,published,container-title,volume,issue,page,publisher,type",
        },
        headers={"User-Agent": user_agent},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    raw_response = response.json()
    candidates: list[Candidate] = []
    for rank, record in enumerate(raw_response.get("message", {}).get("items", []), start=1):
        confidence = max(0.68, 0.86 - (rank - 1) * 0.07)
        doi = str(record.get("DOI") or "").strip()
        evidence = {
            "query": title,
            "rank": rank,
            "record_url": f"https://doi.org/{quote(doi, safe='/()')}" if doi else "",
            "match_type": "title_search",
        }
        if record.get("title"):
            candidates.append(Candidate("title", record["title"][0], "crossref_title", confidence, evidence))
        authors = [
            " ".join(filter(None, (author.get("given"), author.get("family"))))
            for author in record.get("author", [])
        ]
        authors = [author for author in authors if author]
        if authors:
            candidates.append(Candidate("authors", authors, "crossref_title", confidence, evidence))
        issued = record.get("published", {}).get("date-parts", [[]])
        if issued and issued[0]:
            candidates.append(Candidate("publication_year", issued[0][0], "crossref_title", confidence, evidence))
        if record.get("container-title"):
            candidates.append(Candidate("journal_title", record["container-title"][0], "crossref_title", confidence, evidence))
        for source_name, field_name in (("publisher", "publisher"), ("volume", "volume"), ("issue", "issue"), ("page", "page_range"), ("DOI", "doi")):
            if record.get(source_name):
                candidates.append(Candidate(field_name, record[source_name], "crossref_title", confidence, evidence))
    return ProviderCandidates(
        candidates,
        raw_response=raw_response,
        provider_version="crossref-rest-v1",
    )


def search_openlibrary_title(title: str, *, language: str = "zh", limit: int = 3) -> list[Candidate]:
    response = httpx.get(
        "https://openlibrary.org/search.json",
        params={
            "title": title,
            "lang": "zh" if language.startswith("zh") else "en",
            "fields": "key,title,author_name,first_publish_year,publisher,publish_place,isbn,edition_key,language",
            "limit": max(1, min(limit, 5)),
        },
        headers={"User-Agent": "SocialTheoryLibrary/2.6.1 metadata-candidate-service"},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    raw_response = response.json()
    candidates: list[Candidate] = []
    for rank, record in enumerate(raw_response.get("docs", []), start=1):
        confidence, match_type = _title_match_confidence(
            title,
            str(record.get("title") or ""),
            rank,
        )
        languages = [str(value).casefold() for value in (record.get("language") or [])]
        preferred = "chi" if language.startswith("zh") else "eng" if language.startswith("en") else ""
        if preferred and preferred in languages:
            confidence = round(min(0.94, confidence + 0.02), 3)
        work_key = str(record.get("key") or "").strip()
        evidence = {
            "query": title,
            "rank": rank,
            "record_url": f"https://openlibrary.org{work_key}" if work_key.startswith("/") else "",
            "match_type": match_type,
            "record_languages": languages[:8],
        }
        if record.get("title"):
            candidates.append(Candidate("title", record["title"], "openlibrary_title", confidence, evidence))
        if record.get("author_name"):
            candidates.append(Candidate("authors", record["author_name"], "openlibrary_title", confidence, evidence))
        if record.get("first_publish_year"):
            candidates.append(Candidate("publication_year", record["first_publish_year"], "openlibrary_title", confidence, evidence))
        if record.get("publisher"):
            candidates.append(Candidate("publisher", record["publisher"][0], "openlibrary_title", confidence, evidence))
        if record.get("publish_place"):
            candidates.append(Candidate("publication_place", record["publish_place"][0], "openlibrary_title", confidence, evidence))
        if record.get("isbn"):
            candidates.append(Candidate("isbn", record["isbn"][0], "openlibrary_title", confidence, evidence))
    return ProviderCandidates(
        candidates,
        raw_response=raw_response,
        provider_version="open-library-search-v1",
    )


def _normalized_bibliographic_text(value: str) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


def _title_match_confidence(query: str, result: str, rank: int) -> tuple[float, str]:
    query_key = _normalized_bibliographic_text(query)
    result_key = _normalized_bibliographic_text(result)
    if query_key and result_key == query_key:
        return max(0.78, 0.9 - (rank - 1) * 0.03), "normalized_exact_title"
    if query_key and result_key and (query_key in result_key or result_key in query_key):
        return max(0.7, 0.82 - (rank - 1) * 0.04), "normalized_contained_title"
    return max(0.58, 0.72 - (rank - 1) * 0.05), "provider_rank"


def _google_books_records(query: str, *, language: str = "", limit: int = 3) -> list[dict]:
    params = {
        "q": query,
        "printType": "books",
        "projection": "lite",
        "maxResults": max(1, min(limit, 10)),
    }
    if language.startswith("zh"):
        params["langRestrict"] = "zh"
    elif language.startswith("en"):
        params["langRestrict"] = "en"
    if settings.GOOGLE_BOOKS_API_KEY:
        params["key"] = settings.GOOGLE_BOOKS_API_KEY
    response = httpx.get(
        "https://www.googleapis.com/books/v1/volumes",
        params=params,
        headers={"User-Agent": "SocialTheoryLibrary/2.6.1 (administrator metadata suggestions)"},
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return list(response.json().get("items") or [])


def _google_books_candidates(
    records: list[dict],
    *,
    query: str,
    title_query: str = "",
    exact_identifier: str = "",
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for rank, record in enumerate(records, start=1):
        info = record.get("volumeInfo") or {}
        record_title = str(info.get("title") or "").strip()
        if exact_identifier:
            confidence, match_type = 0.94, "exact_isbn_query"
        else:
            confidence, match_type = _title_match_confidence(title_query, record_title, rank)
        volume_id = str(record.get("id") or "").strip()
        evidence = {
            "query": query,
            "rank": rank,
            "record_url": f"https://books.google.com/books?id={quote(volume_id)}" if volume_id else "",
            "volume_id": volume_id,
            "match_type": match_type,
            "record_language": info.get("language", ""),
        }
        if record_title:
            candidates.append(Candidate("title", record_title, "google_books", confidence, evidence))
        authors = [str(author).strip() for author in (info.get("authors") or []) if str(author).strip()]
        if authors:
            candidates.append(Candidate("authors", authors, "google_books", confidence, evidence))
        if info.get("publisher"):
            candidates.append(Candidate("publisher", str(info["publisher"]), "google_books", confidence, evidence))
        year_match = YEAR_RE.search(str(info.get("publishedDate") or ""))
        if year_match:
            candidates.append(Candidate("publication_year", int(year_match.group()), "google_books", confidence, evidence))
        identifiers = info.get("industryIdentifiers") or []
        isbn_values = [
            re.sub(r"[-\s]", "", str(identifier.get("identifier") or "")).upper()
            for identifier in identifiers
            if str(identifier.get("type") or "").startswith("ISBN_")
        ]
        if isbn_values:
            preferred = next((value for value in isbn_values if len(value) == 13), isbn_values[0])
            candidates.append(Candidate("isbn", preferred, "google_books", confidence, evidence))
    return candidates


def resolve_google_books_isbn(isbn: str, *, language: str = "") -> list[Candidate]:
    normalized = re.sub(r"[-\s]", "", isbn).upper()
    query = f"isbn:{normalized}"
    raw_response = _google_books_records(query, language=language, limit=3)
    return ProviderCandidates(
        _google_books_candidates(
            raw_response,
            query=query,
            exact_identifier=normalized,
        ),
        raw_response={"items": raw_response},
        external_id=normalized,
        provider_version="google-books-v1",
    )


def search_google_books_title(title: str, *, language: str = "", limit: int = 3) -> list[Candidate]:
    query = f'intitle:"{title}"'
    raw_response = _google_books_records(query, language=language, limit=limit)
    return ProviderCandidates(
        _google_books_candidates(
            raw_response,
            query=query,
            title_query=title,
        ),
        raw_response={"items": raw_response},
        provider_version="google-books-v1",
    )


def _openalex_headers() -> dict[str, str]:
    headers = {"User-Agent": "SocialTheoryLibrary/2.6.1 (administrator metadata suggestions)"}
    if getattr(settings, "OPENALEX_API_KEY", ""):
        headers["api_key"] = settings.OPENALEX_API_KEY
    return headers


def _openalex_candidates(
    records: list[dict],
    *,
    query: str,
    exact_doi: str = "",
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for rank, record in enumerate(records, start=1):
        title = str(record.get("title") or record.get("display_name") or "").strip()
        if exact_doi:
            confidence, match_type = 0.95, "exact_doi_query"
        else:
            confidence, match_type = _title_match_confidence(query, title, rank)
        openalex_id = str(record.get("id") or "").rstrip("/").split("/")[-1]
        evidence = {
            "query": query,
            "rank": rank,
            "record_url": f"https://openalex.org/{quote(openalex_id)}" if openalex_id else "",
            "openalex_id": openalex_id,
            "match_type": match_type,
            "record_type": record.get("type", ""),
            "record_language": record.get("language", ""),
        }
        if title:
            candidates.append(Candidate("title", title, "openalex", confidence, evidence))
        authors = [
            str((authorship.get("author") or {}).get("display_name") or "").strip()
            for authorship in (record.get("authorships") or [])
            if isinstance(authorship, dict)
        ]
        authors = [author for author in authors if author]
        if authors:
            candidates.append(Candidate("authors", authors, "openalex", confidence, evidence))
        if record.get("publication_year"):
            candidates.append(
                Candidate("publication_year", record["publication_year"], "openalex", confidence, evidence)
            )
        primary_location = record.get("primary_location") or {}
        source = primary_location.get("source") or {} if isinstance(primary_location, dict) else {}
        journal_title = str(source.get("display_name") or "").strip() if isinstance(source, dict) else ""
        if journal_title:
            candidates.append(Candidate("journal_title", journal_title, "openalex", confidence, evidence))
        biblio = record.get("biblio") or {}
        if isinstance(biblio, dict):
            for source_name, field_name in (("volume", "volume"), ("issue", "issue")):
                if biblio.get(source_name):
                    candidates.append(Candidate(field_name, biblio[source_name], "openalex", confidence, evidence))
            first_page = str(biblio.get("first_page") or "").strip()
            last_page = str(biblio.get("last_page") or "").strip()
            if first_page:
                page_range = first_page if not last_page or last_page == first_page else f"{first_page}-{last_page}"
                candidates.append(Candidate("page_range", page_range, "openalex", confidence, evidence))
        doi = str(record.get("doi") or "").strip()
        if doi:
            normalized_doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
            candidates.append(Candidate("doi", normalized_doi, "openalex", confidence, evidence))
    return candidates


def resolve_openalex_doi(doi: str) -> list[Candidate]:
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    response = httpx.get(
        "https://api.openalex.org/works",
        params={
            "filter": f"doi:https://doi.org/{normalized}",
            "per-page": 1,
            "select": "id,doi,title,display_name,publication_year,authorships,primary_location,type,biblio,language",
        },
        headers=_openalex_headers(),
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    raw_response = response.json()
    records = list(raw_response.get("results") or [])
    return ProviderCandidates(
        _openalex_candidates(records, query=normalized, exact_doi=normalized),
        raw_response=raw_response,
        external_id=normalized,
        provider_version="openalex-rest-v1",
    )


def search_openalex_title(title: str, *, limit: int = 3) -> list[Candidate]:
    response = httpx.get(
        "https://api.openalex.org/works",
        params={
            "search": title,
            "per-page": max(1, min(limit, 5)),
            "select": "id,doi,title,display_name,publication_year,authorships,primary_location,type,biblio,language",
        },
        headers=_openalex_headers(),
        timeout=settings.METADATA_PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    raw_response = response.json()
    records = list(raw_response.get("results") or [])
    return ProviderCandidates(
        _openalex_candidates(records, query=title),
        raw_response=raw_response,
        provider_version="openalex-rest-v1",
    )


def authority_verification_links(*, title: str, isbn: str = "", doi: str = "", document_type: str = "") -> list[dict]:
    query = isbn or doi or title
    links = [
        {
            "label": "国家图书馆馆藏目录",
            "url": "https://www.nlc.cn/web/select.html",
            "query": query,
            "language": "zh-CN",
            "purpose": "核对中文图书题名、责任者、出版者与版本信息",
            "automated": False,
        },
        {
            "label": "全国馆社共荐优质书目",
            "url": "https://goodbook.nlc.cn/",
            "query": isbn or title,
            "language": "zh-CN",
            "purpose": "按书名、ISBN、作者或出版者核对中文新书书目",
            "automated": False,
        },
    ]
    if document_type == DocumentType.JOURNAL_ARTICLE:
        links.append(
            {
                "label": "中国知网",
                "url": "https://www.cnki.net/",
                "query": doi or title,
                "language": "zh-CN",
                "purpose": "人工核对中文期刊论文的刊名、年卷期与页码",
                "automated": False,
            }
        )
    if doi:
        links.append(
            {
                "label": "DOI 解析记录",
                "url": f"https://doi.org/{quote(doi, safe='/()')}",
                "query": doi,
                "language": "en",
                "purpose": "核对 DOI 对应的出版记录",
                "automated": True,
            }
        )
    elif title:
        links.append(
            {
                "label": "Open Library 题名检索",
                "url": f"https://openlibrary.org/search?{urlencode({'title': title})}",
                "query": title,
                "language": "en",
                "purpose": "补充外文图书和译本候选",
                "automated": True,
            }
        )
    return links


def refresh_remote_candidates(edition) -> tuple[list[Candidate], list[str]]:
    """Resolve exact identifiers first, then use a conservative title search."""

    candidates: list[Candidate] = []
    warnings: list[str] = []
    if edition.doi:
        try:
            candidates.extend(resolve_doi(edition.doi))
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            warnings.append(f"Crossref DOI 核对失败：{str(exc)[:300]}")
    elif edition.isbn:
        try:
            candidates.extend(resolve_isbn(edition.isbn))
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            warnings.append(f"Open Library ISBN 核对失败：{str(exc)[:300]}")
        try:
            candidates.extend(
                resolve_google_books_isbn(
                    edition.isbn,
                    language=edition.work.language,
                )
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            warnings.append(f"Google Books ISBN 核对失败：{str(exc)[:300]}")

    title = edition.work.title.strip()
    if title and not candidates:
        if edition.work.document_type == DocumentType.JOURNAL_ARTICLE:
            try:
                candidates.extend(search_crossref_title(title))
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                warnings.append(f"Crossref 题名检索失败：{str(exc)[:300]}")
        else:
            providers = (
                (
                    "Open Library",
                    lambda: search_openlibrary_title(
                        title,
                        language=edition.work.language,
                    ),
                ),
                (
                    "Google Books",
                    lambda: search_google_books_title(
                        title,
                        language=edition.work.language,
                    ),
                ),
            )
            for provider, resolver in providers:
                try:
                    candidates.extend(resolver())
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    warnings.append(f"{provider} 题名检索失败：{str(exc)[:300]}")
    return candidates, warnings


def _element_text(element) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split()).strip()


def resolve_grobid(path: str | Path) -> list[Candidate]:
    base_url = settings.GROBID_SERVICE_URL.rstrip("/")
    if not base_url:
        return []
    with Path(path).open("rb") as handle:
        response = httpx.post(
            f"{base_url}/api/processHeaderDocument",
            files={"input": (Path(path).name, handle, "application/pdf")},
            data={"consolidateHeader": "0"},
            headers={"Accept": "application/xml"},
            timeout=min(120, settings.METADATA_PROVIDER_TIMEOUT_SECONDS * 4),
        )
    if response.status_code == 204:
        return []
    response.raise_for_status()
    if len(response.content) > 5 * 1024 * 1024:
        raise ValueError("GROBID 头部响应超过安全大小。")
    root = ElementTree.fromstring(response.content)
    evidence = {"endpoint": "processHeaderDocument"}
    candidates = []

    title = _element_text(root.find(".//{*}titleStmt/{*}title"))
    if title:
        candidates.append(Candidate("title", title, "grobid", 0.91, evidence))

    authors = []
    for author in root.findall(".//{*}titleStmt/{*}author"):
        name = _element_text(author.find(".//{*}persName")) or _element_text(author)
        if name and name not in authors:
            authors.append(name)
    if authors:
        candidates.append(Candidate("authors", authors, "grobid", 0.9, evidence))

    abstract = _element_text(root.find(".//{*}profileDesc/{*}abstract"))
    if abstract:
        candidates.append(Candidate("abstract", abstract, "grobid", 0.86, evidence))

    journal_title = _element_text(root.find(".//{*}sourceDesc//{*}title[@level='j']"))
    if journal_title:
        candidates.append(Candidate("journal_title", journal_title, "grobid", 0.9, evidence))

    for date in root.findall(".//{*}sourceDesc//{*}date"):
        value = date.attrib.get("when") or _element_text(date)
        match = YEAR_RE.search(value)
        if match:
            candidates.append(Candidate("publication_year", int(match.group()), "grobid", 0.88, evidence))
            break

    for identifier in root.findall(".//{*}idno"):
        identifier_type = identifier.attrib.get("type", "").casefold()
        value = _element_text(identifier)
        if identifier_type == "doi" and value:
            candidates.append(Candidate("doi", value, "grobid", 0.95, evidence))
            break

    scope_fields = {"volume": "volume", "issue": "issue", "page": "page_range", "pp": "page_range"}
    for scope in root.findall(".//{*}sourceDesc//{*}biblScope"):
        field_name = scope_fields.get(scope.attrib.get("unit", "").casefold())
        value = _element_text(scope) or scope.attrib.get("from", "")
        if field_name and value:
            if field_name == "page_range" and scope.attrib.get("to"):
                value = f"{scope.attrib.get('from', value)}-{scope.attrib['to']}"
            candidates.append(Candidate(field_name, value, "grobid", 0.88, evidence))

    if title and (authors or journal_title):
        candidates.append(
            Candidate(
                "document_type",
                DocumentType.JOURNAL_ARTICLE,
                "grobid",
                0.92,
                evidence,
            )
        )
    return ProviderCandidates(
        candidates,
        raw_response={"tei_xml": response.text},
        provider_version="grobid-process-header-v1",
    )


def enrich_candidates(candidates: list[Candidate], path: str | Path | None = None) -> list[Candidate]:
    enriched = list(candidates)
    doi = next((candidate.value for candidate in candidates if candidate.field_name == "doi"), None)
    isbn = next((candidate.value for candidate in candidates if candidate.field_name == "isbn"), None)
    try:
        if doi:
            enriched.extend(resolve_doi(str(doi)))
        elif isbn:
            enriched.extend(resolve_isbn(str(isbn)))
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    document_type = next(
        (
            candidate.value
            for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True)
            if candidate.field_name == "document_type"
        ),
        None,
    )
    if path and settings.GROBID_SERVICE_URL and document_type == DocumentType.JOURNAL_ARTICLE:
        try:
            enriched.extend(resolve_grobid(path))
        except (httpx.HTTPError, ElementTree.ParseError, KeyError, ValueError):
            pass
    return enriched


def select_best(candidates: list[Candidate]) -> dict:
    selected: dict[str, Candidate] = {}
    selected_scores: dict[str, float] = {}
    for candidate, calibrated in ranked_candidates(candidates):
        # AI proposals stay in MetadataCandidate until a human explicitly
        # accepts them. They never become draft catalog fields implicitly.
        if AI_SOURCE_RE.search(candidate.source):
            continue
        existing = selected.get(candidate.field_name)
        if existing is None or calibrated.score > selected_scores[candidate.field_name]:
            selected[candidate.field_name] = candidate
            selected_scores[candidate.field_name] = calibrated.score
    return {field_name: candidate.value for field_name, candidate in selected.items()}


def overall_confidence(candidates: list[Candidate], selected: dict) -> float:
    required = ["title", "authors", "document_type", "publication_year"]
    confidences = []
    for field_name in required:
        matching = [
            calibrate_candidate(candidate, candidates).score
            for candidate in candidates
            if candidate.field_name == field_name and candidate.value == selected.get(field_name)
        ]
        confidences.append(max(matching) if matching else 0)
    return sum(confidences) / len(confidences)
