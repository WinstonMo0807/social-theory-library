"""Response-only contracts for existing public catalog/reader producers.

These describe their actual dictionaries; they do not add routes or change
visibility. Flexible historical geometry and provenance remain explicit JSON.
"""
from rest_framework import serializers

from catalog.models import Page


class PublicEntityLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField(allow_blank=True)
    slug = serializers.CharField(allow_blank=True)


class PublicClassificationLinkSerializer(PublicEntityLinkSerializer):
    is_primary = serializers.BooleanField()


class PublicJournalContentSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True, required=False)
    article_work_id = serializers.UUIDField(allow_null=True, required=False)
    title = serializers.CharField()
    author_display = serializers.CharField(allow_blank=True)
    page_range = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    article_href = serializers.CharField(allow_blank=True)


class PublicPersonSnapshotSerializer(serializers.Serializer):
    # Older snapshots may contain only identity and a display name.
    id = serializers.UUIDField(allow_null=True)
    preferred_name = serializers.CharField(allow_blank=True)
    original_name = serializers.CharField(required=False, allow_blank=True)
    aliases = serializers.ListField(child=serializers.CharField(), required=False)
    authority_status = serializers.CharField(required=False)
    birth_year = serializers.IntegerField(required=False, allow_null=True)
    death_year = serializers.IntegerField(required=False, allow_null=True)
    biography = serializers.CharField(required=False, allow_blank=True)
    portrait = serializers.CharField(required=False, allow_blank=True)
    portrait_media = serializers.JSONField(required=False, allow_null=True, help_text="Historical snapshot media is retained as JSON.")
    scholar_slug = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PublicContributionSnapshotSerializer(serializers.Serializer):
    role = serializers.CharField()
    order = serializers.IntegerField()
    person = PublicPersonSnapshotSerializer()


class PublicOutlineItemSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    file_page_index = serializers.IntegerField(required=False)
    printed_label = serializers.CharField(allow_blank=True)
    chapter_title = serializers.CharField(allow_blank=True)


class PublicTheoryAssociationNodeSerializer(PublicEntityLinkSerializer):
    id = serializers.UUIDField()
    foreign_name = serializers.CharField(allow_blank=True)
    type = serializers.CharField()


class PublicTheoryAssociationEvidenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    page_number = serializers.IntegerField()
    page_end = serializers.IntegerField(allow_null=True)
    printed_page_label = serializers.CharField(allow_blank=True)
    quote = serializers.CharField(allow_blank=True)
    reader_href = serializers.CharField()


class PublicTheoryAssociationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    node = PublicTheoryAssociationNodeSerializer()
    role = serializers.CharField()
    role_label = serializers.CharField()
    strength = serializers.CharField()
    evidence = PublicTheoryAssociationEvidenceSerializer(many=True)


class ReaderRelatedLinkSerializer(serializers.Serializer):
    name = serializers.CharField(allow_blank=True)
    slug = serializers.CharField(allow_blank=True)


class ReaderRelatedScholarSerializer(ReaderRelatedLinkSerializer):
    slug = serializers.CharField(allow_null=True, allow_blank=True)
    years = serializers.CharField(allow_blank=True)


class ReaderManifestBaseSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    page_count = serializers.IntegerField()
    publication_status = serializers.CharField()
    ocr_status = serializers.CharField()
    semantic_index_status = serializers.CharField()
    page_label_status = serializers.CharField()
    reader_rendition_policy = serializers.CharField()
    outline = PublicOutlineItemSerializer(many=True)
    related_scholars = ReaderRelatedScholarSerializer(many=True)
    related_theories = ReaderRelatedLinkSerializer(many=True)
    related_topics = ReaderRelatedLinkSerializer(many=True)


class ReaderTextBlockSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order = serializers.IntegerField()
    type = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    bbox = serializers.JSONField(help_text="Existing geometric JSON, not restricted to an invented coordinate shape.")
    confidence = serializers.FloatField()


class ReaderPageContentSerializer(serializers.Serializer):
    page_id = serializers.UUIDField()
    page_index = serializers.IntegerField()
    file_page_index = serializers.IntegerField()
    printed_label = serializers.CharField(allow_blank=True)
    citation_page_label = serializers.CharField()
    label_source = serializers.CharField()
    label_confidence = serializers.FloatField()
    chapter_title = serializers.CharField(allow_blank=True)
    text_available = serializers.BooleanField()
    text_source = serializers.ChoiceField(choices=Page.TextSource.choices)
    width = serializers.FloatField()
    height = serializers.FloatField()
    text = serializers.CharField(allow_blank=True)
    blocks = ReaderTextBlockSerializer(many=True)


class ReaderAssetAccessSerializer(serializers.Serializer):
    url = serializers.CharField()
    download_url = serializers.CharField()
    original_download_url = serializers.CharField()
    download_rendition = serializers.CharField()
    source = serializers.CharField()
    expires_in = serializers.IntegerField(allow_null=True)
    supports_range = serializers.BooleanField()
    download_filename = serializers.CharField(allow_blank=True)
    edition_id = serializers.UUIDField()
    requested_asset_id = serializers.UUIDField()
    served_asset_id = serializers.UUIDField()
    source_artifact_id = serializers.UUIDField(allow_null=True)
    rendition = serializers.CharField()
    reader_rendition_policy = serializers.CharField()
    reader_fallback_reason = serializers.CharField(allow_blank=True)
    sha256 = serializers.CharField()
    page_count = serializers.IntegerField()
    ocr_status = serializers.CharField()
    ocr_text_available = serializers.BooleanField()
    page_label_status = serializers.CharField()
    semantic_index_status = serializers.CharField()
