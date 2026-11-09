"""Knowledge identities and immutable, revision-scoped source material.

Existing bibliography and typed authority tables remain authoritative. Wiki
drafts/publication use EditorialRevision; there is no second revision body.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import UUIDTimeStampedModel


class ImmutableSourceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("已保存的原文快照不可覆盖，请创建新修订。")

    def delete(self):
        raise ValidationError("可引用的历史原文不可删除。")


class ImmutableSource(UUIDTimeStampedModel):
    objects = ImmutableSourceQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("已保存的原文快照不可覆盖。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("可引用的历史原文不可删除。")


class RevisionPage(ImmutableSource):
    document_revision = models.ForeignKey("catalog.DocumentRevision", on_delete=models.PROTECT, related_name="page_snapshots")
    page_number = models.PositiveIntegerField()
    printed_label = models.CharField(max_length=40, blank=True)
    text = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    text_source = models.CharField(max_length=16)
    geometry = models.JSONField(default=dict)
    blocks = models.JSONField(default=list)

    class Meta:
        ordering = ["page_number"]
        constraints = [models.UniqueConstraint(fields=["document_revision", "page_number"], name="knowledge_revision_page_unique"),
                       models.CheckConstraint(condition=models.Q(page_number__gte=1), name="knowledge_page_one_based")]


class DocumentStructure(ImmutableSource):
    document_revision = models.ForeignKey("catalog.DocumentRevision", on_delete=models.PROTECT, related_name="structures")
    outline_revision = models.ForeignKey("catalog.DocumentOutlineRevision", null=True, on_delete=models.PROTECT)
    parser = models.CharField(max_length=80)
    parser_version = models.CharField(max_length=80)
    input_hash = models.CharField(max_length=64)
    coverage = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document_revision", "input_hash"], name="knowledge_structure_input_unique")]


class DocumentNode(ImmutableSource):
    class Kind(models.TextChoices):
        DOCUMENT = "document", "文献"
        PART = "part", "部"
        CHAPTER = "chapter", "章"
        SECTION = "section", "节"
        PARAGRAPH = "paragraph", "段落"
        PREFACE = "preface", "前言"
        APPENDIX = "appendix", "附录"
        FOOTNOTE = "footnote", "脚注"
        TABLE = "table", "表格"
        REFERENCES = "references", "参考文献"
        UNRESOLVED = "unresolved", "未确认结构"

    structure = models.ForeignKey(DocumentStructure, on_delete=models.PROTECT, related_name="nodes")
    document_revision = models.ForeignKey("catalog.DocumentRevision", on_delete=models.PROTECT, related_name="nodes")
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT, related_name="children")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=600, blank=True)
    content_hash = models.CharField(max_length=64)
    source = models.JSONField(default=dict)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["structure", "order"], name="knowledge_node_order_unique")]


class DocumentNodeSegment(ImmutableSource):
    node = models.ForeignKey(DocumentNode, on_delete=models.PROTECT, related_name="segments")
    page = models.ForeignKey(RevisionPage, on_delete=models.PROTECT, related_name="node_segments")
    order = models.PositiveIntegerField()
    start = models.PositiveIntegerField()
    end = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["node", "order"], name="knowledge_node_segment_unique"),
                       models.CheckConstraint(condition=models.Q(end__gt=models.F("start")), name="knowledge_node_segment_range")]


class DocumentNodeReference(ImmutableSource):
    source = models.ForeignKey(DocumentNode, on_delete=models.PROTECT, related_name="outgoing_references")
    target = models.ForeignKey(DocumentNode, on_delete=models.PROTECT, related_name="incoming_references")
    kind = models.CharField(max_length=32, default="footnote")
    label = models.CharField(max_length=80, blank=True)
    provenance = models.JSONField(default=dict)


class EvidenceAnchor(ImmutableSource):
    document_revision = models.ForeignKey("catalog.DocumentRevision", on_delete=models.PROTECT, related_name="anchors")
    content_hash = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64, unique=True)
    validation = models.CharField(max_length=32, default="verified_text")


class EvidenceSegment(ImmutableSource):
    anchor = models.ForeignKey(EvidenceAnchor, on_delete=models.PROTECT, related_name="segments")
    page = models.ForeignKey(RevisionPage, on_delete=models.PROTECT, related_name="evidence_segments")
    node = models.ForeignKey(DocumentNode, null=True, on_delete=models.PROTECT, related_name="evidence_segments")
    # One immutable text source. exact/prefix/suffix are derived from this range.
    order = models.PositiveIntegerField()
    start = models.PositiveIntegerField()
    end = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    geometry = models.JSONField(default=dict)
    precision = models.CharField(max_length=24, default="text_range")

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["anchor", "order"], name="knowledge_anchor_segment_unique"),
                       models.CheckConstraint(condition=models.Q(end__gt=models.F("start")), name="knowledge_anchor_segment_range")]


class Entity(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        PERSON = "person", "人物"
        TRADITION = "tradition", "理论传统"
        SCHOOL = "school", "理论流派"
        CONCEPT = "concept", "概念"
        DEBATE = "debate", "争论"
        QUESTION = "question", "研究问题"
        TOPIC = "topic", "主题"
        DISCIPLINE = "discipline", "学科"
        ORGANIZATION = "organization", "组织"
        EVENT = "event", "事件"
        OBJECT = "research_object", "研究对象"

    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True)
    label = models.CharField(max_length=600)
    definition = models.TextField(blank=True)
    context = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="draft", db_index=True)
    person = models.OneToOneField("catalog.Person", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    node = models.OneToOneField("catalog.KnowledgeNode", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    topic = models.OneToOneField("catalog.Topic", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    discipline = models.OneToOneField("catalog.Discipline", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    subdiscipline = models.OneToOneField("catalog.Subdiscipline", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    theory_school = models.OneToOneField("catalog.TheorySchool", null=True, blank=True, on_delete=models.PROTECT, related_name="entity")
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="merged_identities")


class EntityAlias(UUIDTimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="aliases")
    text = models.CharField(max_length=600, db_index=True)
    language = models.CharField(max_length=32, blank=True)
    script = models.CharField(max_length=32, blank=True)
    source = models.JSONField(default=dict)
    review_status = models.CharField(max_length=24, default="pending")


class EntityIdentifier(UUIDTimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="identifiers")
    namespace = models.CharField(max_length=80)
    value = models.CharField(max_length=600)
    source = models.JSONField(default=dict)
    review_status = models.CharField(max_length=24, default="pending")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["entity", "namespace", "value"], name="knowledge_entity_identifier_unique")]
        indexes = [models.Index(fields=["namespace", "value"])]


class Assertion(UUIDTimeStampedModel):
    text = models.TextField()
    category = models.CharField(max_length=40, default="proposition")
    predicate = models.CharField(max_length=80, blank=True)
    direction = models.CharField(max_length=20, default="directed")
    expression = models.CharField(max_length=32, default="author_claim")
    conditions = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="draft", db_index=True)
    source_quality = models.CharField(max_length=40, default="unverified")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    origin = models.JSONField(default=dict)


class AssertionParticipant(UUIDTimeStampedModel):
    assertion = models.ForeignKey(Assertion, on_delete=models.PROTECT, related_name="participants")
    role = models.CharField(max_length=32)
    entity = models.ForeignKey(Entity, null=True, on_delete=models.PROTECT, related_name="assertion_participations")
    work = models.ForeignKey("catalog.Work", null=True, on_delete=models.PROTECT, related_name="assertion_participations")
    edition = models.ForeignKey("catalog.Edition", null=True, on_delete=models.PROTECT, related_name="assertion_participations")

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            models.Q(entity__isnull=False, work__isnull=True, edition__isnull=True)
            | models.Q(entity__isnull=True, work__isnull=False, edition__isnull=True)
            | models.Q(entity__isnull=True, work__isnull=True, edition__isnull=False)), name="knowledge_participant_one_identity")]


class AssertionSource(UUIDTimeStampedModel):
    assertion = models.ForeignKey(Assertion, on_delete=models.PROTECT, related_name="sources")
    work = models.ForeignKey("catalog.Work", on_delete=models.PROTECT)
    edition = models.ForeignKey("catalog.Edition", null=True, on_delete=models.PROTECT)
    document_revision = models.ForeignKey("catalog.DocumentRevision", null=True, on_delete=models.PROTECT)
    node = models.ForeignKey(DocumentNode, null=True, on_delete=models.PROTECT)
    attribution = models.ForeignKey(Entity, null=True, on_delete=models.PROTECT)
    expression = models.CharField(max_length=32, default="author_claim")
    provenance = models.JSONField(default=dict)


class AssertionEvidence(UUIDTimeStampedModel):
    assertion = models.ForeignKey(Assertion, on_delete=models.PROTECT, related_name="evidence")
    anchor = models.ForeignKey(EvidenceAnchor, on_delete=models.PROTECT, related_name="assertion_links")
    stance = models.CharField(max_length=24, choices=[(s, s) for s in ("supports", "opposes", "qualifies", "context")])
    note = models.TextField(blank=True)


class KnowledgePage(UUIDTimeStampedModel):
    work = models.OneToOneField("catalog.Work", null=True, blank=True, on_delete=models.PROTECT, related_name="knowledge_page")
    entity = models.OneToOneField(Entity, null=True, blank=True, on_delete=models.PROTECT, related_name="knowledge_page")
    slug = models.SlugField(max_length=240, allow_unicode=True, unique=True)
    title = models.CharField(max_length=600)
    scope = models.TextField(blank=True)
    # Published materialization only; drafts reside exclusively in EditorialRevision.
    body_blocks = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, default="draft")
    legacy_target_type = models.CharField(max_length=32, blank=True)
    legacy_target_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(work__isnull=False, entity__isnull=False), name="knowledge_page_one_subject")]


class KnowledgeLegacyMapping(UUIDTimeStampedModel):
    """Deterministic old-ID resolver; never fabricates a historical revision."""
    source_type = models.CharField(max_length=80)
    source_id = models.UUIDField()
    target_type = models.CharField(max_length=40)
    target_id = models.UUIDField(null=True)
    quality = models.CharField(max_length=40)
    provenance = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source_type", "source_id", "target_type"], name="knowledge_legacy_mapping_unique")]


class KnowledgeBlockDependency(UUIDTimeStampedModel):
    """Rebuildable current-page reference projection; never another page body."""
    page = models.ForeignKey(KnowledgePage, on_delete=models.CASCADE, related_name="dependencies")
    block_id = models.UUIDField()
    source_type = models.CharField(max_length=32)
    source_id = models.UUIDField()
    source_hash = models.CharField(max_length=64)
    stale = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["page", "block_id", "source_type", "source_id"], name="knowledge_block_dependency_unique")]
        indexes = [models.Index(fields=["source_type", "source_id"], name="knowledge_dep_source_idx")]
