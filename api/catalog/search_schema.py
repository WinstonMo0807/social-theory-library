"""Document the existing search endpoint's three response shapes without changing it."""
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.utils import extend_schema
from rest_framework import serializers

from .catalog_search_serializers import CatalogCounts, CatalogFacets, CatalogPagination, CatalogSearchOutput
from .serializers import ScholarProfileSerializer, TheorySchoolSerializer, TopicSerializer, WorkCardSerializer
from .services.scoped_search import SearchContext, SearchVisibility


class GlobalSearchQuery(serializers.Serializer):
    # No shared defaults: the catalog, scoped and legacy branches apply different ones.
    q = serializers.CharField(required=False, allow_blank=True, help_text="Catalog and explicit context searches accept at most 500 characters; catalog also limits whitespace-separated terms to 20.")
    context = serializers.ChoiceField(choices=list(SearchContext), required=False, help_text="scope=catalog accepts global only. Other non-global contexts return the scoped envelope. Omitting context uses the deprecated legacy global response.")
    scope = serializers.CharField(required=False, help_text="catalog selects the snapshot-backed catalog response. Legacy global uses all by default, or book, article, thesis, report, scholar, topic, theory, fulltext to select pagination totals.")
    envelope = serializers.CharField(required=False, help_text="With an explicit global context, the literal value 1 selects the scoped envelope. Ignored for scope=catalog.")
    visibility = serializers.ChoiceField(choices=list(SearchVisibility), required=False, help_text="Scoped envelope only. admin is honored only for authorized staff or admin/editor/reviewer accounts; otherwise public is used.")
    page = serializers.IntegerField(required=False, min_value=1, help_text="Defaults to 1. Catalog rejects values over 100000; legacy/scoped branches normalize invalid values.")
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50, help_text="Catalog defaults to 24. Legacy defaults to 8 for scope=all, otherwise 24. Scoped envelope uses this only when limit is absent.")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, help_text="Scoped envelope page limit, default 24. Ignored by catalog and legacy global.")
    sort = serializers.ChoiceField(choices=["relevance", "newest", "year"], required=False, help_text="Catalog and legacy global only; defaults to relevance.")
    match = serializers.ListField(child=serializers.ChoiceField(choices=["title", "author", "keyword", "abstract", "fulltext"]), required=False, min_length=1, max_length=5, help_text="Catalog only. Repeat the parameter for multiple values. Defaults to title, author, keyword, abstract.")
    document_type = serializers.ListField(child=serializers.CharField(), required=False)
    author = serializers.ListField(child=serializers.CharField(), required=False)
    language = serializers.ListField(child=serializers.CharField(), required=False)
    theory = serializers.ListField(child=serializers.CharField(), required=False)
    topic = serializers.ListField(child=serializers.CharField(), required=False)
    concept = serializers.ListField(child=serializers.CharField(), required=False)
    tag = serializers.ListField(child=serializers.CharField(), required=False, help_text="Legacy global only.")
    access = serializers.ListField(child=serializers.CharField(), required=False, help_text="Catalog: readable or metadata. Legacy global: online or download.")
    year = serializers.ListField(child=serializers.CharField(), required=False, help_text="Catalog/legacy year buckets: before-1900, 1900-1949, 1950-1999, 2000-2009, 2010-2019, 2020-now.")
    year_min = serializers.IntegerField(required=False, min_value=1, max_value=9999, help_text="Catalog only; inclusive lower bound.")
    year_max = serializers.IntegerField(required=False, min_value=1, max_value=9999, help_text="Catalog only; inclusive upper bound, not less than year_min.")
    discipline = serializers.CharField(required=False, help_text="Scoped subdisciplines, theories, topics or reading_paths only.")
    type = serializers.CharField(required=False, help_text="Scoped theories node type; takes precedence over node_type.")
    node_type = serializers.CharField(required=False, help_text="Scoped theories only, when type is absent.")


class LegacyGlobalFacets(CatalogFacets):
    year_histogram = None


class LegacyGlobalPassage(serializers.Serializer):
    id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    edition_slug = serializers.CharField(allow_blank=True)
    asset_id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    page_index = serializers.IntegerField()
    printed_label = serializers.CharField(allow_blank=True)
    snippet = serializers.CharField(allow_blank=True)
    bbox = serializers.JSONField()
    query = serializers.CharField(allow_blank=True)


class LegacySearchScholar(ScholarProfileSerializer):
    # These legacy computed fields lack annotations on their runtime serializers.
    # Preserve their object/array shapes instead of generating misleading strings.
    works = WorkCardSerializer(many=True, read_only=True)
    curated = serializers.DictField(read_only=True)
    curated_claims = serializers.DictField(child=serializers.ListField(child=serializers.DictField()), read_only=True)
    knowledge_nodes = serializers.ListField(child=serializers.DictField(), read_only=True)


class LegacySearchTopic(TopicSerializer):
    disciplines = serializers.ListField(child=serializers.DictField(), read_only=True)
    subdisciplines = serializers.ListField(child=serializers.DictField(), read_only=True)
    linked_theories = serializers.ListField(child=serializers.DictField(), read_only=True)
    knowledge_nodes = serializers.ListField(child=serializers.DictField(), read_only=True)
    curated = serializers.DictField(read_only=True)
    curated_claims = serializers.DictField(child=serializers.ListField(child=serializers.DictField()), read_only=True)


class LegacySearchTheory(TheorySchoolSerializer):
    disciplines = serializers.ListField(child=serializers.DictField(), read_only=True)
    subdisciplines = serializers.ListField(child=serializers.DictField(), read_only=True)
    hierarchy = serializers.DictField(child=serializers.ListField(child=serializers.DictField()), read_only=True)
    relations = serializers.ListField(child=serializers.DictField(), read_only=True)
    timeline = serializers.ListField(child=serializers.DictField(), read_only=True)
    scholar_count = serializers.IntegerField(read_only=True)
    curated = serializers.DictField(read_only=True)


class LegacyGlobalSearchOutput(serializers.Serializer):
    context = serializers.ChoiceField(choices=[SearchContext.GLOBAL])
    query = serializers.CharField(allow_blank=True)
    counts = CatalogCounts()
    facets = LegacyGlobalFacets()
    pagination = CatalogPagination()
    works = WorkCardSerializer(many=True)
    scholars = LegacySearchScholar(many=True)
    topics = LegacySearchTopic(many=True)
    theories = LegacySearchTheory(many=True)
    passages = LegacyGlobalPassage(many=True)


class ScopedSearchPagination(serializers.Serializer):
    page = serializers.IntegerField()
    limit = serializers.IntegerField()
    total = serializers.IntegerField()
    total_pages = serializers.IntegerField()


class ScopedSearchMatch(serializers.Serializer):
    type = serializers.ChoiceField(choices=["exact", "verified_alias", "prefix", "text", "browse"])
    query = serializers.CharField(allow_blank=True)
    highlights = serializers.ListField(child=serializers.CharField())


class ScopedSearchResult(serializers.Serializer):
    context = serializers.ChoiceField(choices=[item for item in SearchContext if item != SearchContext.GLOBAL])
    entity_type = serializers.CharField()
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    url = serializers.CharField(allow_blank=True)
    match = ScopedSearchMatch()
    metadata = serializers.DictField()


class ScopedSearchGroup(serializers.Serializer):
    context = serializers.ChoiceField(choices=[item for item in SearchContext if item != SearchContext.GLOBAL])
    label = serializers.CharField()
    backend = serializers.ChoiceField(choices=["database"])
    count = serializers.IntegerField()
    results = ScopedSearchResult(many=True)
    pagination = ScopedSearchPagination(required=False, help_text="Present only for a non-global scoped search.")


class ScopedSearchOutput(serializers.Serializer):
    implementation_version = serializers.CharField()
    context = serializers.ChoiceField(choices=list(SearchContext))
    visibility = serializers.ChoiceField(choices=list(SearchVisibility))
    query = serializers.CharField(allow_blank=True)
    groups = ScopedSearchGroup(many=True)
    total = serializers.IntegerField()
    pagination = ScopedSearchPagination()
    latency_ms = serializers.FloatField()


class GlobalSearchOutput(serializers.Serializer):
    """Schema marker; responses are built by the existing search implementations."""


class GlobalSearchOutputExtension(OpenApiSerializerExtension):
    target_class = GlobalSearchOutput

    def map_serializer(self, auto_schema, direction):
        # Catalog extends legacy fields, so oneOf would incorrectly reject it.
        return {"anyOf": [auto_schema.resolve_serializer(serializer(), direction).ref
                          for serializer in (CatalogSearchOutput, LegacyGlobalSearchOutput, ScopedSearchOutput)]}


global_search_schema = extend_schema(
    parameters=[GlobalSearchQuery],
    responses={200: GlobalSearchOutput},
    description=(
        "This endpoint preserves three response branches. scope=catalog (context omitted or global) "
        "returns CatalogSearchOutput. Other explicit non-global contexts, or context=global&envelope=1, "
        "return ScopedSearchOutput. Remaining requests return LegacyGlobalSearchOutput; omitting context "
        "also emits Deprecation and Warning headers. Catalog filters use repeated query parameters, "
        "AND across fields and OR within a field, on the same activated public edition. "
        "Parameter defaults and validation differ by branch; see each parameter description."
    ),
)
