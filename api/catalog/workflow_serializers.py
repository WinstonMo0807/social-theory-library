from __future__ import annotations

from rest_framework import serializers

from catalog.models import (
    Contribution,
    DocumentType,
    ReaderRenditionPolicy,
    RelationStrength,
    WorkNodeRelation,
    WorkTheoryRole,
)


class WorkflowSectionSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField(required=False)
    expected_work_updated_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class WorkSectionSerializer(WorkflowSectionSerializer):
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    title = serializers.CharField(max_length=600, required=False, allow_blank=False, trim_whitespace=True)
    subtitle = serializers.CharField(max_length=600, required=False, allow_blank=True)
    original_title = serializers.CharField(max_length=600, required=False, allow_blank=True)
    uniform_title = serializers.CharField(max_length=600, required=False, allow_blank=True)
    language = serializers.CharField(max_length=16, required=False, allow_blank=False)
    original_language = serializers.CharField(max_length=32, required=False, allow_blank=True)
    first_publication_date = serializers.DateField(required=False, allow_null=True)
    translation_of = serializers.UUIDField(required=False, allow_null=True)
    abstract = serializers.CharField(required=False, allow_blank=True)


class BibliographySectionSerializer(WorkflowSectionSerializer):
    version_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    publication_year = serializers.IntegerField(min_value=1000, max_value=2100, required=False, allow_null=True)
    publisher = serializers.CharField(max_length=300, required=False, allow_blank=True)
    publication_place = serializers.CharField(max_length=200, required=False, allow_blank=True)
    journal_title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    volume = serializers.CharField(max_length=40, required=False, allow_blank=True)
    issue = serializers.CharField(max_length=40, required=False, allow_blank=True)
    page_range = serializers.CharField(max_length=80, required=False, allow_blank=True)
    degree_institution = serializers.CharField(max_length=300, required=False, allow_blank=True)
    degree_type = serializers.CharField(max_length=120, required=False, allow_blank=True)
    report_institution = serializers.CharField(max_length=300, required=False, allow_blank=True)
    isbn = serializers.CharField(max_length=32, required=False, allow_blank=True)
    isbn10 = serializers.CharField(max_length=20, required=False, allow_blank=True)
    isbn13 = serializers.CharField(max_length=20, required=False, allow_blank=True)
    doi = serializers.CharField(max_length=255, required=False, allow_blank=True)
    series = serializers.CharField(max_length=300, required=False, allow_blank=True)
    extent = serializers.CharField(max_length=160, required=False, allow_blank=True)
    responsibility_statement = serializers.CharField(required=False, allow_blank=True)


class ContributorRowSerializer(serializers.Serializer):
    person_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=Contribution.Role.choices)
    order = serializers.IntegerField(min_value=0, required=False)


class ContributorsSectionSerializer(WorkflowSectionSerializer):
    contributors = ContributorRowSerializer(many=True, required=False, default=list)

    def validate_contributors(self, rows):
        keys = [(row["person_id"], row["role"]) for row in rows]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError("同一责任者和角色不能重复。")
        return rows


class DisciplineRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    is_primary = serializers.BooleanField(default=False)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    evidence_text = serializers.CharField(required=False, allow_blank=True, default="")


class SubdisciplineRowSerializer(DisciplineRowSerializer):
    strength = serializers.ChoiceField(choices=RelationStrength.choices, default=RelationStrength.MEDIUM)


class ClassificationSectionSerializer(WorkflowSectionSerializer):
    disciplines = DisciplineRowSerializer(many=True, required=False, default=list)
    subdisciplines = SubdisciplineRowSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field in ("disciplines", "subdisciplines"):
            rows = attrs.get(field, [])
            identifiers = [row["id"] for row in rows]
            if len(identifiers) != len(set(identifiers)):
                raise serializers.ValidationError({field: "同一分类对象不能重复。"})
            if sum(bool(row.get("is_primary")) for row in rows) > 1:
                raise serializers.ValidationError({field: "同类分类最多只能指定一个主要对象。"})
        return attrs


class TheoryRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=WorkTheoryRole.choices, default=WorkTheoryRole.MENTION)
    strength = serializers.ChoiceField(choices=RelationStrength.choices, default=RelationStrength.MEDIUM)
    is_primary = serializers.BooleanField(default=False)
    evidence_asset = serializers.UUIDField(required=False, allow_null=True)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    evidence_text = serializers.CharField(required=False, allow_blank=True, default="")


class TopicRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    is_primary = serializers.BooleanField(default=False)
    evidence_asset = serializers.UUIDField(required=False, allow_null=True)
    evidence_page = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    evidence_printed_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    evidence_text = serializers.CharField(required=False, allow_blank=True, default="")


class NodeRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=WorkNodeRelation.Role.choices)
    strength = serializers.ChoiceField(choices=RelationStrength.choices, default=RelationStrength.MEDIUM)
    is_primary = serializers.BooleanField(default=False)


class KnowledgeSectionSerializer(WorkflowSectionSerializer):
    theories = TheoryRowSerializer(many=True, required=False, default=list)
    topics = TopicRowSerializer(many=True, required=False, default=list)
    nodes = NodeRowSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field in ("theories", "topics", "nodes"):
            rows = attrs.get(field, [])
            keys = [(row["id"], row.get("role", "")) for row in rows]
            if len(keys) != len(set(keys)):
                raise serializers.ValidationError({field: "同一知识关系不能重复。"})
        return attrs


class ReaderSectionSerializer(WorkflowSectionSerializer):
    reader_rendition_policy = serializers.ChoiceField(
        choices=ReaderRenditionPolicy.choices,
        required=False,
    )


class CurationSectionSerializer(WorkflowSectionSerializer):
    skip = serializers.BooleanField(default=False)


SECTION_SERIALIZERS = {
    "work": WorkSectionSerializer,
    "bibliography": BibliographySectionSerializer,
    "contributors": ContributorsSectionSerializer,
    "classification": ClassificationSectionSerializer,
    "knowledge": KnowledgeSectionSerializer,
    "reader": ReaderSectionSerializer,
    "curation": CurationSectionSerializer,
}
