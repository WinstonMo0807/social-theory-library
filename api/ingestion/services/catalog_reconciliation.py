from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from django.db.models import Prefetch, Q

from catalog.models import Contribution, Edition, Work


def normalize_identifier(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalize_isbn(value: object) -> str:
    return "".join(character for character in normalize_identifier(value).upper() if character.isdigit() or character == "X")


def normalize_doi(value: object) -> str:
    value = normalize_identifier(value).casefold()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.strip().rstrip(".")


def normalize_title(value: object) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in value if character.isalnum())


def normalize_name(value: object) -> str:
    return normalize_title(value)


@dataclass(frozen=True, slots=True)
class CatalogMatch:
    mode: str
    work: Work | None = None
    edition: Edition | None = None
    confidence: float = 0
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    @property
    def is_strong(self) -> bool:
        return self.mode in {"existing_edition", "existing_work"}


def _identifier_editions(selected: dict) -> list[Edition]:
    isbn_raw = normalize_identifier(selected.get("isbn"))
    isbn = normalize_isbn(isbn_raw)
    doi_raw = normalize_identifier(selected.get("doi"))
    doi = normalize_doi(doi_raw)
    query = Q(pk__isnull=True)
    if isbn:
        query |= Q(isbn__iexact=isbn_raw) | Q(isbn__iexact=isbn)
        if len(isbn) == 10:
            query |= Q(isbn10__iexact=isbn)
        elif len(isbn) == 13:
            query |= Q(isbn13__iexact=isbn)
    if doi:
        query |= Q(doi__iexact=doi) | Q(doi__iexact=doi_raw)
        query |= Q(doi__iexact=f"https://doi.org/{doi}")
    if not isbn and not doi:
        return []
    rows = list(Edition.objects.filter(query).select_related("work")[:10])
    matches = []
    for edition in rows:
        isbn_matches = bool(isbn) and isbn in {
            normalize_isbn(edition.isbn),
            normalize_isbn(edition.isbn10),
            normalize_isbn(edition.isbn13),
        }
        doi_matches = bool(doi) and doi == normalize_doi(edition.doi)
        if isbn_matches or doi_matches:
            matches.append(edition)
    return matches


def _work_candidates(selected: dict) -> list[Work]:
    title = str(selected.get("title") or "").strip()
    title_key = normalize_title(title)
    if not title_key:
        return []
    document_type = str(selected.get("document_type") or "").strip()
    query = Work.objects.all()
    if document_type:
        query = query.filter(document_type=document_type)
    author_prefetch = Prefetch(
        "editions__contributions",
        queryset=Contribution.objects.filter(approved=True).select_related("person"),
        to_attr="approved_contributions_for_match",
    )
    possible = query.filter(
        Q(normalized_title__iexact=title.casefold())
        | Q(title__iexact=title)
        | Q(uniform_title__iexact=title)
        | Q(original_title__iexact=title)
    ).prefetch_related(author_prefetch)[:20]
    return [
        work
        for work in possible
        if title_key
        in {
            normalize_title(work.title),
            normalize_title(work.uniform_title),
            normalize_title(work.original_title),
        }
    ]


def _work_author_keys(work: Work) -> set[str]:
    keys: set[str] = set()
    for edition in work.editions.all():
        for contribution in getattr(edition, "approved_contributions_for_match", []):
            person = contribution.person
            for value in [person.preferred_name, person.original_name, *(person.aliases or [])]:
                key = normalize_name(value)
                if key:
                    keys.add(key)
    return keys


def find_catalog_match(selected: dict) -> CatalogMatch:
    identifier_matches = _identifier_editions(selected)
    if len(identifier_matches) == 1:
        edition = identifier_matches[0]
        reasons = []
        if normalize_isbn(selected.get("isbn")):
            reasons.append("ISBN 与馆内版本完全一致")
        if normalize_doi(selected.get("doi")):
            reasons.append("DOI 与馆内版本完全一致")
        return CatalogMatch(
            mode="existing_edition",
            work=edition.work,
            edition=edition,
            confidence=1,
            reasons=tuple(reasons),
        )
    if len(identifier_matches) > 1:
        return CatalogMatch(
            mode="ambiguous",
            confidence=0,
            conflicts=("同一强标识符对应多个馆内版本，需要人工处理",),
        )

    works = _work_candidates(selected)
    author_keys = {
        normalize_name(value)
        for value in selected.get("authors", [])
        if normalize_name(value)
    }
    if author_keys:
        supported = [work for work in works if author_keys.intersection(_work_author_keys(work))]
        if len(supported) == 1:
            return CatalogMatch(
                mode="existing_work",
                work=supported[0],
                confidence=0.96,
                reasons=("规范题名、文献类型与已确认责任者一致",),
            )
        if len(supported) > 1:
            return CatalogMatch(
                mode="ambiguous",
                confidence=0,
                conflicts=("题名与责任者仍对应多个馆内作品，需要人工选择",),
            )
    if works:
        return CatalogMatch(
            mode="ambiguous",
            confidence=0,
            conflicts=("馆内存在同题名作品，但缺少足以自动合并的强标识符或责任者证据",),
        )
    return CatalogMatch(mode="new")
