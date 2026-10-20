"""Typed public subdiscipline additions without changing catalog identities."""
from rest_framework import serializers


class SubdisciplineDisciplineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()


class SubdisciplineWorksPaginationSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    total_pages = serializers.IntegerField(min_value=1)


class SubdisciplineLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    href = serializers.CharField()


class SubdisciplineCanonicalTargetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    href = serializers.CharField()


class SubdisciplineLegacyIdentitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    role = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)


class SubdisciplineTheorySerializer(SubdisciplineLegacyIdentitySerializer):
    kind = serializers.CharField()
    node_type = serializers.CharField(allow_null=True)
    href = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    canonical_target = SubdisciplineCanonicalTargetSerializer(allow_null=True)
    legacy_identities = SubdisciplineLegacyIdentitySerializer(many=True)


class SubdisciplineTopicSerializer(SubdisciplineLinkSerializer):
    relation_label = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    hero_image = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)


class SubdisciplineScholarSerializer(SubdisciplineLinkSerializer):
    person_id = serializers.UUIDField()
    source_label = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    confidence = serializers.FloatField()
    approved = serializers.BooleanField()
    portrait_url = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    relation_label = serializers.CharField(allow_blank=True)
    source_href = serializers.CharField(allow_null=True)


class SubdisciplineQuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_null=True)
    source = serializers.CharField(allow_blank=True)


class SubdisciplineSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_kind = serializers.CharField()
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    edition_label = serializers.CharField(allow_blank=True)
    quote = serializers.CharField()
    pdf_page = serializers.IntegerField(min_value=1)
    printed_page_label = serializers.CharField(allow_blank=True)
    reader_href = serializers.CharField()


class SubdisciplineWorkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    document_type = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)
    author = serializers.CharField(allow_blank=True)
    year = serializers.IntegerField(allow_null=True)
    publisher = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    edition_id = serializers.UUIDField()
    catalog_revision_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField(allow_null=True)
    source_status = serializers.CharField()
    asset_id = serializers.UUIDField(allow_null=True)
    reader_href = serializers.CharField(allow_null=True)
    detail_href = serializers.CharField()
    relation_label = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    evidence = SubdisciplineSourceSerializer(allow_null=True)


class SubdisciplineReadingPathSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    href = serializers.CharField()
    introduction = serializers.CharField(allow_blank=True)
    relation_label = serializers.CharField()
