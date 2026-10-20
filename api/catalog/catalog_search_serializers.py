"""Catalog-only public search contracts. Values come from activated snapshots."""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import Asset
from .serializers import AssetCompactSerializer, EditionCompactSerializer, WorkCardSerializer
from .services.publication_eligibility import active_catalog_snapshot


class CatalogSearchQuery(serializers.Serializer):
    q = serializers.CharField(max_length=500, allow_blank=True, default="")
    match = serializers.ListField(child=serializers.ChoiceField(choices=["title", "author", "keyword", "abstract", "fulltext"]), min_length=1, max_length=5, default=["title", "author", "keyword", "abstract"])
    document_type = serializers.ListField(child=serializers.ChoiceField(choices=["book", "journal_article", "journal_issue", "article", "thesis", "report"]), max_length=10, default=list)
    author = serializers.ListField(child=serializers.CharField(max_length=180), max_length=30, default=list)
    language = serializers.ListField(child=serializers.CharField(max_length=32), max_length=30, default=list)
    theory = serializers.ListField(child=serializers.CharField(max_length=180), max_length=30, default=list)
    topic = serializers.ListField(child=serializers.CharField(max_length=180), max_length=30, default=list)
    concept = serializers.ListField(child=serializers.CharField(max_length=180), max_length=30, default=list)
    access = serializers.ListField(child=serializers.ChoiceField(choices=["readable", "metadata"]), max_length=2, default=list)
    year = serializers.ListField(child=serializers.ChoiceField(choices=["before-1900", "1900-1949", "1950-1999", "2000-2009", "2010-2019", "2020-now"]), max_length=6, default=list)
    year_min = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    year_max = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    sort = serializers.ChoiceField(choices=["relevance", "newest", "year"], default="relevance")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, default=24)

    def validate(self, data):
        if data.get("year_min", 1) > data.get("year_max", 9999):
            raise serializers.ValidationError({"year_max": "截止年份不能早于起始年份。"})
        if len(data["q"].split()) > 20:
            raise serializers.ValidationError({"q": "检索词过多，请缩短为 20 项以内。"})
        return data


class CatalogEditionSerializer(EditionCompactSerializer):
    language = serializers.CharField(read_only=True)
    availability = serializers.CharField(read_only=True)

    class Meta(EditionCompactSerializer.Meta):
        fields = EditionCompactSerializer.Meta.fields + ("language", "availability")

    def to_representation(self, instance):
        snapshot = active_catalog_snapshot(instance)
        values = snapshot.get("edition") or {}
        # Absent historical fields stay blank; current editorial values are not a fallback.
        data = {key: values.get(key, "") for key in self.Meta.fields}
        data.update(id=str(instance.pk), publication_year=values.get("publication_year"),
            publication_date=values.get("publication_date"), publisher_authority=values.get("publisher_authority_id"),
            public_slug=values.get("public_slug"), language=(snapshot.get("work") or {}).get("language", ""),
            edition_statement=values.get("version_label", ""), publisher_verbatim=values.get("publisher", ""),
            publication_place_verbatim=values.get("publication_place", ""), journal_contents=[], contributors=[], readable_asset=None)
        if snapshot:
            data["contributors"] = self.get_contributors(instance)
            data["journal_contents"] = self.get_journal_contents(instance)
            asset = instance.active_catalog_revision.reader_asset
            if asset and asset.edition_id == instance.pk and asset.kind == Asset.Kind.NORMALIZED and asset.status == Asset.Status.READY and asset.validation_status == Asset.ValidationStatus.VALID and asset.file and asset.access_status in {Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT} and str(asset.pk) == str((snapshot.get("document") or {}).get("asset_id")):
                data["readable_asset"] = AssetCompactSerializer(asset).data
        data["availability"] = "readable" if data["readable_asset"] else "metadata"
        return data


class CatalogWorkSerializer(WorkCardSerializer):
    editions = serializers.SerializerMethodField()
    matched_edition_ids = serializers.SerializerMethodField()

    class Meta(WorkCardSerializer.Meta):
        fields = WorkCardSerializer.Meta.fields + ("editions", "matched_edition_ids")

    @extend_schema_field(CatalogEditionSerializer(many=True))
    def get_editions(self, obj):
        return CatalogEditionSerializer(obj.editions.all(), many=True, context=self.context).data

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_matched_edition_ids(self, obj):
        return self.context["matched_editions"].get(obj.pk, [])

    @extend_schema_field(CatalogEditionSerializer(allow_null=True))
    def get_edition(self, obj):
        edition = self._public_edition(obj)
        return CatalogEditionSerializer(edition, context=self.context).data if edition else None

    def to_representation(self, instance):
        snapshot = self._public_snapshot(instance)
        values = snapshot.get("work") or {}
        data = {key: values.get(key, "") for key in WorkCardSerializer.Meta.fields}
        data.update(id=str(instance.pk), first_publication_date=values.get("first_publication_date"),
            translation_of=values.get("translation_of_id"), edition=self.get_edition(instance),
            editions=self.get_editions(instance), matched_edition_ids=self.get_matched_edition_ids(instance),
            cover=self.get_cover(instance) if snapshot else "", cover_media=self.get_cover_media(instance) if snapshot else None,
            recommendation_image=self.get_recommendation_image(instance) if snapshot else "",
            recommendation_media=self.get_recommendation_media(instance) if snapshot else None,
            theories=self.get_theories(instance) if snapshot else [], topics=self.get_topics(instance) if snapshot else [],
            disciplines=self.get_disciplines(instance) if snapshot else [], subdisciplines=self.get_subdisciplines(instance) if snapshot else [])
        return data


class CatalogFacet(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class CatalogYearCount(serializers.Serializer):
    year = serializers.IntegerField()
    count = serializers.IntegerField()


class CatalogFacets(serializers.Serializer):
    document_types = CatalogFacet(many=True)
    authors = CatalogFacet(many=True)
    years = CatalogFacet(many=True)
    languages = CatalogFacet(many=True)
    access = CatalogFacet(many=True)
    theories = CatalogFacet(many=True)
    topics = CatalogFacet(many=True)
    concepts = CatalogFacet(many=True)
    year_histogram = CatalogYearCount(many=True)


class CatalogCounts(serializers.Serializer):
    works = serializers.IntegerField()
    books = serializers.IntegerField()
    articles = serializers.IntegerField()
    theses = serializers.IntegerField()
    reports = serializers.IntegerField()
    scholars = serializers.IntegerField()
    topics = serializers.IntegerField()
    theories = serializers.IntegerField()
    passages = serializers.IntegerField()


class CatalogPagination(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total = serializers.IntegerField()
    total_pages = serializers.IntegerField()


class CatalogSearchOutput(serializers.Serializer):
    context = serializers.ChoiceField(choices=["global"])
    query = serializers.CharField(allow_blank=True)
    scope = serializers.ChoiceField(choices=["catalog"])
    counts = CatalogCounts()
    works = CatalogWorkSerializer(many=True)
    facets = CatalogFacets()
    pagination = CatalogPagination()
    scholars = serializers.ListField()
    topics = serializers.ListField()
    theories = serializers.ListField()
    passages = serializers.ListField()
