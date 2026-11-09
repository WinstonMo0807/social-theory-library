"""Compatibility import only; catalog_candidates owns all catalogue mutations."""
from catalog.services import catalog_candidates as _catalog
FieldAssistantService = _catalog.CatalogCandidateService
FieldAssistantError = _catalog.CatalogCandidateError

def __getattr__(name):
    return getattr(_catalog, name)
