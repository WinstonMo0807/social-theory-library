"""Public detail reads one selected, activated Edition throughout the response."""
from uuid import UUID

from django.db.models import Q
from django.http import Http404
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalog_search_serializers import CatalogEditionSerializer, catalog_reader_access_statuses
from .media_views import PublicCoverMediaSerializer
from .models import KnowledgeNode, Topic
from .public_response_serializers import (
    PublicEntityLinkSerializer, PublicOutlineItemSerializer, PublicTheoryAssociationSerializer,
    ReaderManifestBaseSerializer,
)
from .serializers import AssetCompactSerializer, WorkCardSerializer, WorkDetailSerializer
from .services.publication_eligibility import active_catalog_snapshot, public_editions
from .services.work_detail_relations import WorkRelationsSerializer, public_work_relations


def public_detail_edition(identifier, *, work=None):
    """Draft slugs never redirect to the last published edition accidentally."""
    query = Q(active_catalog_revision__snapshot__edition__public_slug=str(identifier))
    try:
        query |= Q(pk=UUID(str(identifier)))
    except (ValueError, TypeError, AttributeError):
        pass
    queryset = public_editions()
    if work is not None:
        queryset = queryset.filter(work=work)
    # A draft may reuse another edition's old published slug. Ambiguous
    # activated identities fail closed instead of selecting an arbitrary row.
    editions = list(queryset.filter(query)[:2])
    if len(editions) != 1 or not active_catalog_snapshot(editions[0]):
        raise Http404("该版本尚未公开，或已撤回。")
    return editions[0]


def requested_work_snapshot(request, work):
    """Keep existing primary image URLs, with explicit published-version URLs."""
    identifier = request.query_params.get("edition_id")
    if identifier is not None:
        identifier = serializers.UUIDField().run_validation(identifier)
        return active_catalog_snapshot(public_detail_edition(identifier, work=work))
    edition = next((row for row in work.editions.all() if row.is_primary), None)
    return active_catalog_snapshot(edition)


class PublicWorkDetailSerializer(WorkDetailSerializer):
    relations = serializers.SerializerMethodField()

    class Meta(WorkDetailSerializer.Meta):
        fields = WorkDetailSerializer.Meta.fields + ("relations",)

    def _public_catalog(self, obj):
        edition = self.context.get("selected_edition")
        if edition is None or edition.work_id != obj.pk:
            raise Http404("未找到所选的公开版本。")
        if not hasattr(self, "_selected_snapshot"):
            self._selected_snapshot = active_catalog_snapshot(edition)
        if not self._selected_snapshot:
            raise Http404("该版本尚未公开，或已撤回。")
        return edition, self._selected_snapshot

    @extend_schema_field(CatalogEditionSerializer(allow_null=True))
    def get_edition(self, obj):
        if not hasattr(self, "_selected_edition_data"):
            self._selected_edition_data = CatalogEditionSerializer(self._public_edition(obj), context=self.context).data
        return self._selected_edition_data

    @extend_schema_field(CatalogEditionSerializer(many=True))
    def get_editions(self, obj):
        editions = public_editions().filter(work=obj).order_by("-is_primary", "-published_at", "id")
        return CatalogEditionSerializer(editions, many=True, context=self.context).data

    @extend_schema_field(PublicOutlineItemSerializer(many=True))
    def get_outline(self, obj):
        from .services.document_outline import public_outline

        edition = self._public_edition(obj)
        if not self.get_edition(obj)["readable_asset"]:
            return []
        return public_outline(edition.active_catalog_revision.reader_asset,
                              access_statuses=catalog_reader_access_statuses(self.context.get("request")))

    @extend_schema_field(PublicTheoryAssociationSerializer(many=True))
    def get_theory_associations(self, obj):
        # The public detail remains public even when an administrator is signed
        # in. Private evidence belongs to the separate administration preview.
        public_context = {**self.context, "request": None}
        return WorkDetailSerializer(context=public_context).get_theory_associations(obj)

    @extend_schema_field(WorkRelationsSerializer)
    def get_relations(self, obj):
        return public_work_relations(obj, self._public_edition(obj), context=self.context)

    @extend_schema_field(PublicCoverMediaSerializer(allow_null=True))
    def get_cover_media(self, obj):
        return self._public_image_media(obj)

    @extend_schema_field(PublicCoverMediaSerializer(allow_null=True))
    def get_recommendation_media(self, obj):
        return self._public_image_media(obj, recommendation=True)

    def get_cover(self, obj) -> str:
        values = self._public_snapshot(obj).get("work") or {}
        media = self.get_cover_media(obj)
        if not media and not values.get("cover"):
            return ""
        return self._image_url(obj, "public-work-cover", rendition=media.get("primary_rendition_id") if media else None)

    def get_recommendation_image(self, obj) -> str:
        values = self._public_snapshot(obj).get("work") or {}
        media = self.get_recommendation_media(obj)
        if not media and not (values.get("recommendation_image") or values.get("cover")):
            return ""
        return self._image_url(obj, "public-work-recommendation-image", rendition=media.get("primary_rendition_id") if media else None)

    def to_representation(self, instance):
        values = self._public_snapshot(instance).get("work") or {}
        # Historical omissions remain empty. Never fill them from editable Work
        # fields, which may already contain the next unpublished revision.
        data = {key: values.get(key, "") for key in WorkCardSerializer.Meta.fields}
        data.update(id=str(instance.pk), first_publication_date=values.get("first_publication_date"),
                    translation_of=values.get("translation_of_id"))
        for field in (
            "cover", "cover_media", "recommendation_image", "recommendation_media",
            "edition", "editions", "outline", "theories", "topics", "disciplines",
            "subdisciplines", "theory_associations", "curated_claims", "relations",
        ):
            if field in self.fields:
                data[field] = getattr(self, f"get_{field}")(instance)
        return {key: value for key, value in data.items() if key in self.fields}


class PublicReaderWorkSerializer(PublicWorkDetailSerializer):
    """The requested PDF and its bibliography share one activated edition."""

    class Meta(PublicWorkDetailSerializer.Meta):
        fields = WorkCardSerializer.Meta.fields + ("editions",)

    @extend_schema_field(CatalogEditionSerializer(allow_null=True))
    def get_edition(self, obj):
        data = dict(super().get_edition(obj))
        asset = self.context.get("reader_asset")
        edition, snapshot = self._public_catalog(obj)
        # The manifest view has already applied the current caller's access
        # rule. This exception only describes that exact authorized asset;
        # the version picker still uses the public CatalogEdition contract.
        if (
            asset is not None and asset.edition_id == edition.pk
            and edition.active_catalog_revision.reader_asset_id == asset.pk
            and str((snapshot.get("document") or {}).get("asset_id")) == str(asset.pk)
        ):
            data.update(readable_asset=AssetCompactSerializer(asset).data,
                        availability="readable", access_state="readable")
        return data

    @extend_schema_field(PublicEntityLinkSerializer(many=True))
    def get_theories(self, obj):
        rows = super().get_theories(obj)
        current = {str(row.pk): row for row in KnowledgeNode.objects.filter(
            pk__in=[row["id"] for row in rows], status="published", node_type="theory_tradition",
        )}
        return [{"id": row["id"], "name": current[row["id"]].canonical_name_zh,
                 "slug": current[row["id"]].slug} for row in rows if row["id"] in current]

    @extend_schema_field(PublicEntityLinkSerializer(many=True))
    def get_topics(self, obj):
        rows = super().get_topics(obj)
        current = {str(row.pk): row for row in Topic.objects.filter(
            pk__in=[row["id"] for row in rows], editorial_status="published",
        )}
        return [{"id": row["id"], "name": current[row["id"]].name,
                 "slug": current[row["id"]].slug} for row in rows if row["id"] in current]


class PublicReaderManifestSerializer(ReaderManifestBaseSerializer):
    work = PublicReaderWorkSerializer()
