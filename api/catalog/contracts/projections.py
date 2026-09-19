"""Single declarative field-to-projection contract, free of ORM imports."""

ALL_PROJECTIONS = ("query_lexicon","fulltext","semantic","claim_index","knowledge_graph","timeline","recommendation","reading_path_support","public")

FIELD_PROJECTION_DEPENDENCIES: dict[str, dict[str, tuple[str, ...]]] = {
    "knowledge_node": {"image_selection": ("public",)},
    "reading_path": {"image_selection": ("public",)},
    "scholar_profile": {"portrait_selection": ("public",)},
    "work": {
        "cover": ("public",),
        "cover_rendition": ("public",),
        "recommendation_image": ("public",),
        "recommendation_rendition": ("public",),
        "title": (
            "query_lexicon",
            "fulltext",
            "recommendation",
            "public",
        ),
        "subtitle": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "original_title": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "uniform_title": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "document_type": ("fulltext", "public"),
        "language": ("fulltext", "public"),
        "abstract": ("fulltext", "public"),
        "contributors": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "classification": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "knowledge": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "curation": (
            "claim_index",
            "knowledge_graph",
            "recommendation",
            "public",
        ),
    },
    "edition": {
        # Catalog publication is coordinated from Edition so one publication
        # revision cannot enqueue duplicate whole-book jobs for Work and
        # Edition.  Work-owned fields therefore have explicit Edition aliases.
        "catalog_publish": ALL_PROJECTIONS,
        "catalog_withdraw": ALL_PROJECTIONS,
        # A primary selection changes which existing Edition serves the Work
        # listing and its derived consumers; it never triggers a global index.
        "is_primary": ALL_PROJECTIONS,
        "cover": ("public",),
        "cover_rendition": ("public",),
        "recommendation_image": ("public",),
        "recommendation_rendition": ("public",),
        "title": (
            "query_lexicon",
            "fulltext",
            "recommendation",
            "public",
        ),
        "subtitle": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "original_title": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "uniform_title": (
            "query_lexicon",
            "fulltext",
            "public",
        ),
        "document_type": ("fulltext", "public"),
        "language": ("fulltext", "public"),
        "abstract": ("fulltext", "public"),
        "authors": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "translators": (
            "fulltext",
            "knowledge_graph",
            "public",
        ),
        "disciplines": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "subdisciplines": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "topics": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "theories": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "reading_path_support",
            "public",
        ),
        "curation": (
            "claim_index",
            "knowledge_graph",
            "recommendation",
            "public",
        ),
        "version_label": ("fulltext", "public"),
        "publication_date": ("fulltext", "public"),
        "publication_year": (
            "fulltext",
            "recommendation",
            "public",
        ),
        "publisher": ("fulltext", "public"),
        "journal_contents": ("fulltext", "public"),
        "publisher_authority": ("fulltext", "public"),
        "publication_place": ("fulltext", "public"),
        "isbn": ("fulltext", "public"),
        "isbn10": ("fulltext", "public"),
        "isbn13": ("fulltext", "public"),
        "doi": ("fulltext", "public"),
        "contributors": (
            "fulltext",
            "knowledge_graph",
            "recommendation",
            "public",
        ),
        "metadata_ready": ("fulltext", "public"),
        "fulltext_ready": (
            "fulltext",
            "semantic",
            "claim_index",
            "public",
        ),
        "asset": (
            "fulltext",
            "semantic",
            "claim_index",
            "public",
        ),
        "document_revision": (
            "fulltext",
            "semantic",
            "claim_index",
            "public",
        ),
    },
}

# Catalog aliases share the same exact runtime mapping; unknown fields retain
# the coordinator's explicit object-level fallback.
EXTRA_METADATA_FIELDS = frozenset(("original_language", "first_publication_date", "translation_of", "series", "extent", "journal_title", "volume", "issue", "page_range", "degree_institution", "degree_type", "report_institution", "recommendation_image"))
SEMANTIC_METADATA_FIELDS = frozenset(("title", "subtitle", "original_title", "uniform_title", "document_type", "language", "authors", "translators", "contributors", "publication_year", "topics", "theories", "disciplines", "subdisciplines", "classification", "knowledge"))

def field_projection_impact(object_type, field_name):
    field_name = field_name.split(".", 1)[0]
    projections = FIELD_PROJECTION_DEPENDENCIES.get(object_type, {}).get(field_name)
    if projections is None and object_type == "work":
        projections = FIELD_PROJECTION_DEPENDENCIES["edition"].get(field_name)
    if projections is None and object_type in {"work", "edition"} and field_name in EXTRA_METADATA_FIELDS:
        projections = ("fulltext", "public")
    if projections is None:
        return None
    selected = set(projections)
    if object_type in {"work", "edition"} and field_name in SEMANTIC_METADATA_FIELDS:
        selected.update(("semantic", "claim_index"))
    return tuple(value for value in ALL_PROJECTIONS if value in selected)


def catalog_contract_projection_impact(name, domain, section):
    aliases = {"publisher_authority_id": "publisher_authority", "reader_asset": "asset", "file": "asset", "ocr_text": "document_revision", "page_labels": "document_revision"}
    key = aliases.get(name, name)
    if domain == "contribution":
        key = "contributors"
    elif section in {"classification", "knowledge"}:
        key = section
    return field_projection_impact("edition", key) or field_projection_impact("work", key) or ("fulltext", "public")
