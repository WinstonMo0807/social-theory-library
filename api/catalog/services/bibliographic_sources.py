"""The existing free metadata providers, shared by saved and unsaved catalogues."""
from rest_framework.exceptions import ValidationError
from catalog.contracts.identifiers import normalize_doi, normalize_isbn, valid_doi, valid_isbn


def lookup_sources(context, title, *, item=None):
    from ingestion.services.metadata import resolve_doi, resolve_isbn, search_crossref_title, search_openlibrary_title
    from ingestion.services.provider_gateway import invoke_provider, _enabled
    isbn = normalize_isbn(context.get("isbn13") or context.get("isbn10") or context.get("isbn") or "")
    doi = normalize_doi(context.get("doi") or "")
    if isbn and not valid_isbn(isbn): raise ValidationError("ISBN校验未通过，请核对后查询。")
    if doi and not valid_doi(doi): raise ValidationError("DOI格式无效，请核对后查询。")
    if doi:
        operations = [("crossref", "doi", {"doi": doi}, lambda: resolve_doi(doi))]
    elif isbn:
        operations = [("openlibrary", "isbn", {"isbn": isbn}, lambda: resolve_isbn(isbn))]
    elif title:
        language = str(context.get("language") or "zh")
        operations = [("openlibrary", "title", {"title": title, "language": language}, lambda: search_openlibrary_title(title, language=language)),
                      ("crossref", "title", {"title": title}, lambda: search_crossref_title(title))]
    else:
        raise ValidationError("请先填写题名、ISBN或DOI。")
    for provider, operation, query, resolver in operations:
        if not _enabled(provider):
            yield [], {"key": provider, "state": "disabled", "message": "来源未启用；可继续手工填写。"}
            continue
        values, warnings = invoke_provider(provider=provider, operation=f"whole_record_{operation}", query=query, resolver=resolver, upload_item=item)
        yield values, {"key": provider, "state": "failed" if warnings else "ready" if values else "no_match",
                       "message": "；".join(warnings) if warnings else "已查询免费来源。" if values else "没有匹配书目。"}
