from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from catalog.models import (
    Asset,
    Discipline,
    Edition,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeMergeRecord,
    KnowledgeNodeVersion,
    KnowledgeRelation,
    KnowledgeRelationVersion,
    PersonNodeRelation,
    PublicationState,
    ReadingPath,
    ReadingPathItem,
    RelationReviewStatus,
    TheoryReviewTask,
    TheoryTimelineEvent,
    TimelineEventRelation,
    Work,
    WorkNodeRelation,
)
from catalog.services.knowledge_nodes import record_node_version, record_relation_version
from catalog.services.relation_registry import (
    relation_has_evidence,
    relation_policy,
    relation_would_create_cycle,
)


def _media_url(request, field):
    if not field:
        return ""
    try:
        url = field.url
    except ValueError:
        return ""
    return request.build_absolute_uri(url) if request else url


def _published_edition(work):
    return (
        work.editions.filter(state=PublicationState.PUBLISHED)
        .prefetch_related("contributions__person", "assets")
        .order_by("-is_primary", "-publication_year")
        .first()
    )


def compact_work(work, request=None):
    edition = _published_edition(work)
    if edition is None:
        return None
    authors = [
        row.person.preferred_name
        for row in edition.contributions.all()
        if row.role == "author"
    ]
    asset = next(
        (
            item
            for item in edition.assets.all()
            if item.kind == Asset.Kind.NORMALIZED
            and item.is_current
            and item.status == Asset.Status.READY
        ),
        None,
    )
    return {
        "id": str(work.id),
        "slug": edition.public_slug or "",
        "title": work.title,
        "subtitle": work.subtitle,
        "document_type": work.document_type,
        "language": work.language,
        "author": "、".join(authors),
        "year": edition.publication_year,
        "publisher": edition.publisher,
        "cover_url": (
            reverse("public-work-cover", kwargs={"work_id": work.id})
            if work.cover
            else ""
        ),
        "asset_id": str(asset.id) if asset else None,
        "reader_href": f"/reader/{asset.id}" if asset else None,
        "detail_href": f"/works/{edition.public_slug}" if edition.public_slug else None,
    }


class DisciplineCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discipline
        fields = ("id", "code", "name", "foreign_name", "slug", "description", "hero_image")


class KnowledgeNodeAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeNodeAlias
        fields = ("id", "alias", "language", "alias_type", "normalized_alias")
        read_only_fields = ("id", "normalized_alias")


class KnowledgeNodeDisciplineSerializer(serializers.ModelSerializer):
    discipline = DisciplineCompactSerializer(read_only=True)
    discipline_id = serializers.PrimaryKeyRelatedField(
        source="discipline",
        queryset=Discipline.objects.all(),
        write_only=True,
    )

    class Meta:
        model = KnowledgeNodeDiscipline
        fields = (
            "id",
            "discipline",
            "discipline_id",
            "relation_type",
            "discipline_specific_summary",
            "sort_order",
            "status",
        )
        read_only_fields = ("id",)


class PersonNodeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="person.id", read_only=True)
    name = serializers.CharField(source="person.preferred_name", read_only=True)
    original_name = serializers.CharField(source="person.original_name", read_only=True)
    birth_year = serializers.IntegerField(source="person.birth_year", read_only=True)
    death_year = serializers.IntegerField(source="person.death_year", read_only=True)
    portrait_url = serializers.SerializerMethodField()
    scholar_slug = serializers.SerializerMethodField()

    class Meta:
        model = PersonNodeRelation
        fields = (
            "id",
            "name",
            "original_name",
            "birth_year",
            "death_year",
            "portrait_url",
            "scholar_slug",
            "relation_label",
            "is_representative",
            "sort_order",
        )

    def get_portrait_url(self, obj):
        return _media_url(self.context.get("request"), obj.person.portrait)

    def get_scholar_slug(self, obj):
        profile = getattr(obj.person, "scholar_profile", None)
        return profile.slug if profile and profile.editorial_status == "published" else ""


class EvidenceSnippetSerializer(serializers.ModelSerializer):
    work_title = serializers.CharField(source="work.title", read_only=True)
    node_name = serializers.CharField(source="node.canonical_name_zh", read_only=True)
    relation_role = serializers.SerializerMethodField()
    reader_href = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceSnippet
        fields = (
            "id",
            "work",
            "work_title",
            "file",
            "node",
            "node_name",
            "work_node_relation",
            "knowledge_relation",
            "relation_role",
            "page_number",
            "page_end",
            "printed_page_label",
            "quote",
            "bounding_box",
            "extraction_method",
            "ocr_confidence",
            "semantic_confidence",
            "review_status",
            "reader_href",
        )

    def get_relation_role(self, obj):
        if obj.work_node_relation_id:
            return obj.work_node_relation.role
        if obj.knowledge_relation_id:
            return obj.knowledge_relation.relation_type
        return ""

    def get_reader_href(self, obj):
        query = f"page={obj.page_number}&evidence={obj.id}"
        return f"/reader/{obj.file_id}?{query}"


class WorkNodeRelationSerializer(serializers.ModelSerializer):
    work_data = serializers.SerializerMethodField()
    node_name = serializers.CharField(source="node.canonical_name_zh", read_only=True)
    node_slug = serializers.CharField(source="node.slug", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    evidence = EvidenceSnippetSerializer(many=True, read_only=True)

    class Meta:
        model = WorkNodeRelation
        fields = (
            "id",
            "work",
            "work_data",
            "node",
            "node_name",
            "node_slug",
            "role",
            "role_label",
            "is_primary",
            "strength",
            "confidence",
            "status",
            "source",
            "evidence",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("reviewed_at", "created_at", "updated_at")

    def get_work_data(self, obj):
        return compact_work(obj.work, self.context.get("request"))


class KnowledgeRelationSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source_node.canonical_name_zh", read_only=True)
    source_slug = serializers.CharField(source="source_node.slug", read_only=True)
    target_name = serializers.CharField(source="target_node.canonical_name_zh", read_only=True)
    target_slug = serializers.CharField(source="target_node.slug", read_only=True)
    relation_label = serializers.CharField(source="get_relation_type_display", read_only=True)

    class Meta:
        model = KnowledgeRelation
        fields = (
            "id",
            "source_node",
            "source_name",
            "source_slug",
            "target_node",
            "target_name",
            "target_slug",
            "relation_type",
            "relation_label",
            "direction",
            "description",
            "evidence_source",
            "confidence",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("published_at", "created_at", "updated_at")

    def validate(self, attrs):
        source = attrs.get("source_node", getattr(self.instance, "source_node", None))
        target = attrs.get("target_node", getattr(self.instance, "target_node", None))
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError("理论关系的起点和终点不能相同。")
        predicate = attrs.get(
            "relation_type",
            getattr(self.instance, "relation_type", ""),
        )
        if not predicate:
            return attrs
        try:
            policy = relation_policy(predicate)
        except ValueError as exc:
            raise serializers.ValidationError({"relation_type": str(exc)}) from exc
        if source and source.node_type not in policy.allowed_subject_types:
            raise serializers.ValidationError({"source_node": "该节点类型不能作为此关系的起点。"})
        if target and target.node_type not in policy.allowed_object_types:
            raise serializers.ValidationError({"target_node": "该节点类型不能作为此关系的终点。"})
        expected_direction = (
            KnowledgeRelation.Direction.DIRECTED
            if policy.directed
            else KnowledgeRelation.Direction.UNDIRECTED
        )
        direction = attrs.get(
            "direction",
            getattr(self.instance, "direction", expected_direction),
        )
        if direction != expected_direction:
            label = "有方向" if policy.directed else "无方向"
            raise serializers.ValidationError({"direction": f"此关系必须设为{label}关系。"})
        if source and target and relation_would_create_cycle(
            source_node_id=source.pk,
            target_node_id=target.pk,
            predicate=predicate,
            exclude_relation_id=getattr(self.instance, "pk", None),
        ):
            raise serializers.ValidationError({"target_node": "该层级关系会形成循环。"})
        status_value = attrs.get("status", getattr(self.instance, "status", "pending"))
        evidence_source = str(
            attrs.get("evidence_source", getattr(self.instance, "evidence_source", ""))
            or ""
        )
        if (
            status_value == "published"
            and policy.requires_evidence
            and not relation_has_evidence(self.instance, evidence_source)
        ):
            raise serializers.ValidationError(
                {"evidence_source": "公开解释性关系前必须提供来源说明或审核通过的馆藏证据。"}
            )
        return attrs


class KnowledgeNodeListSerializer(serializers.ModelSerializer):
    primary_discipline = DisciplineCompactSerializer(read_only=True)
    related_disciplines = serializers.SerializerMethodField()
    aliases_count = serializers.IntegerField(source="aliases.count", read_only=True)
    work_count = serializers.SerializerMethodField()
    relation_count = serializers.SerializerMethodField()
    representative_scholars = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeNode
        fields = (
            "id",
            "node_type",
            "canonical_name_zh",
            "canonical_name_en",
            "slug",
            "summary",
            "core_questions",
            "start_year",
            "end_year",
            "period_label",
            "parent",
            "primary_discipline",
            "related_disciplines",
            "status",
            "sort_order",
            "aliases_count",
            "work_count",
            "relation_count",
            "representative_scholars",
            "cover_url",
            "updated_at",
        )

    def get_related_disciplines(self, obj):
        return DisciplineCompactSerializer(
            [
                link.discipline
                for link in obj.discipline_links.all()
                if link.status == "published" and link.relation_type != "primary"
            ],
            many=True,
            context=self.context,
        ).data

    def get_work_count(self, obj):
        return obj.work_relations.filter(
            status="published",
            work__editions__state=PublicationState.PUBLISHED,
        ).values("work_id").distinct().count()

    def get_relation_count(self, obj):
        return (
            obj.outgoing_relations.filter(status="published").count()
            + obj.incoming_relations.filter(status="published").count()
        )

    def get_representative_scholars(self, obj):
        queryset = obj.person_relations.filter(
            status="published",
            is_representative=True,
        ).select_related("person", "person__scholar_profile")[:5]
        return PersonNodeSerializer(queryset, many=True, context=self.context).data

    def get_cover_url(self, obj):
        return _media_url(self.context.get("request"), obj.cover_asset)


class KnowledgeNodeDetailSerializer(KnowledgeNodeListSerializer):
    aliases = KnowledgeNodeAliasSerializer(many=True, read_only=True)
    discipline_links = KnowledgeNodeDisciplineSerializer(many=True, read_only=True)
    definition = serializers.CharField()
    basic_propositions = serializers.JSONField()
    theoretical_boundary = serializers.CharField()
    direct_relations = serializers.SerializerMethodField()
    work_groups = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()

    class Meta(KnowledgeNodeListSerializer.Meta):
        fields = KnowledgeNodeListSerializer.Meta.fields + (
            "aliases",
            "discipline_links",
            "definition",
            "basic_propositions",
            "theoretical_boundary",
            "direct_relations",
            "work_groups",
            "evidence",
            "published_at",
        )

    def get_direct_relations(self, obj):
        queryset = KnowledgeRelation.objects.filter(
            Q(source_node=obj) | Q(target_node=obj),
            status="published",
            source_node__status="published",
            target_node__status="published",
        ).select_related("source_node", "target_node")[:24]
        return KnowledgeRelationSerializer(queryset, many=True, context=self.context).data

    def get_work_groups(self, obj):
        groups = {}
        for role, _label in WorkNodeRelation.Role.choices:
            queryset = obj.work_relations.filter(
                role=role,
                status="published",
                work__editions__state=PublicationState.PUBLISHED,
            ).select_related("work").distinct()[:12]
            if queryset:
                groups[role] = WorkNodeRelationSerializer(
                    queryset,
                    many=True,
                    context=self.context,
                ).data
        return groups

    def get_evidence(self, obj):
        queryset = obj.evidence.filter(
            review_status=RelationReviewStatus.APPROVED,
            work__editions__state=PublicationState.PUBLISHED,
        ).select_related("work", "file", "work_node_relation", "knowledge_relation")[:40]
        return EvidenceSnippetSerializer(queryset, many=True, context=self.context).data


class AdminKnowledgeNodeSerializer(serializers.ModelSerializer):
    aliases = KnowledgeNodeAliasSerializer(many=True, required=False)
    discipline_links = KnowledgeNodeDisciplineSerializer(many=True, required=False)
    primary_discipline_data = DisciplineCompactSerializer(source="primary_discipline", read_only=True)
    work_count = serializers.SerializerMethodField()
    relation_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeNode
        fields = (
            "id",
            "node_type",
            "canonical_name_zh",
            "canonical_name_en",
            "slug",
            "summary",
            "definition",
            "core_questions",
            "basic_propositions",
            "theoretical_boundary",
            "start_year",
            "end_year",
            "period_label",
            "parent",
            "primary_discipline",
            "primary_discipline_data",
            "status",
            "sort_order",
            "cover_asset",
            "cover_url",
            "aliases",
            "discipline_links",
            "work_count",
            "relation_count",
            "created_by",
            "reviewed_by",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "created_by",
            "reviewed_by",
            "published_at",
            "created_at",
            "updated_at",
        )

    def get_work_count(self, obj):
        return obj.work_relations.values("work_id").distinct().count()

    def get_relation_count(self, obj):
        return obj.outgoing_relations.count() + obj.incoming_relations.count()

    def get_cover_url(self, obj):
        return _media_url(self.context.get("request"), obj.cover_asset)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is None:
            return attrs
        seen = {self.instance.pk} if self.instance is not None else set()
        current = parent
        while current is not None:
            if current.pk in seen:
                raise serializers.ValidationError({"parent": "知识节点层级不能形成循环。"})
            seen.add(current.pk)
            current = current.parent
        return attrs

    def validate_status(self, value):
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        if value in {"published", "archived"} and role != "admin":
            raise serializers.ValidationError("只有管理员可以发布或下线理论节点。")
        return value

    def _sync_aliases(self, node, rows):
        node.aliases.all().delete()
        actor = getattr(self.context.get("request"), "user", None)
        for row in rows:
            KnowledgeNodeAlias.objects.create(node=node, created_by=actor, **row)

    def _sync_disciplines(self, node, rows):
        node.discipline_links.all().delete()
        for row in rows:
            KnowledgeNodeDiscipline.objects.create(node=node, **row)

    @transaction.atomic
    def create(self, validated_data):
        aliases = validated_data.pop("aliases", [])
        discipline_links = validated_data.pop("discipline_links", [])
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        validated_data["created_by"] = actor
        if validated_data.get("status") == "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        node = super().create(validated_data)
        self._sync_aliases(node, aliases)
        self._sync_disciplines(node, discipline_links)
        record_node_version(node, actor, "建立理论节点")
        return node

    @transaction.atomic
    def update(self, instance, validated_data):
        aliases = validated_data.pop("aliases", None)
        discipline_links = validated_data.pop("discipline_links", None)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        new_status = validated_data.get("status", instance.status)
        if new_status == "published" and instance.status != "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        elif new_status != "published":
            validated_data["published_at"] = None
        node = super().update(instance, validated_data)
        if aliases is not None:
            self._sync_aliases(node, aliases)
        if discipline_links is not None:
            self._sync_disciplines(node, discipline_links)
        record_node_version(node, actor, self.context.get("change_note", "更新理论节点"))
        return node


class AdminKnowledgeRelationSerializer(KnowledgeRelationSerializer):
    def validate_status(self, value):
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        if value in {"published", "rejected"} and role not in {"admin", "reviewer"}:
            raise serializers.ValidationError("只有管理员或审核者可以确认理论关系。")
        if value == "archived" and role != "admin":
            raise serializers.ValidationError("只有管理员可以下线理论关系。")
        return value

    def create(self, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        validated_data["created_by"] = actor
        if validated_data.get("status") == "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        relation = super().create(validated_data)
        record_relation_version(relation, actor, "建立理论关系")
        return relation

    def update(self, instance, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        status_value = validated_data.get("status", instance.status)
        if status_value == "published" and instance.status != "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        relation = super().update(instance, validated_data)
        record_relation_version(relation, actor, "更新理论关系")
        return relation


class AdminWorkNodeRelationSerializer(WorkNodeRelationSerializer):
    def validate_status(self, value):
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        if value in {"published", "rejected"} and role not in {"admin", "reviewer"}:
            raise serializers.ValidationError("只有管理员或审核者可以确认文献关系。")
        return value

    def create(self, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        validated_data["created_by"] = actor
        if validated_data.get("status") == "published":
            validated_data["reviewed_by"] = actor
            validated_data["reviewed_at"] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        if validated_data.get("status") == "published":
            validated_data["reviewed_by"] = actor
            validated_data["reviewed_at"] = timezone.now()
        return super().update(instance, validated_data)


class TheoryReviewTaskSerializer(serializers.ModelSerializer):
    work_title = serializers.CharField(source="work.title", read_only=True)
    node_name = serializers.CharField(source="candidate_node.canonical_name_zh", read_only=True)
    file_page_count = serializers.IntegerField(source="file.page_count", read_only=True)
    viewer_href = serializers.SerializerMethodField()

    class Meta:
        model = TheoryReviewTask
        fields = (
            "id",
            "task_type",
            "work",
            "work_title",
            "file",
            "file_page_count",
            "candidate_node",
            "node_name",
            "suggested_node_name",
            "suggested_relation_type",
            "confidence",
            "evidence_pages",
            "evidence_text",
            "status",
            "assigned_to",
            "submitted_at",
            "reviewed_at",
            "review_note",
            "viewer_href",
            "created_at",
            "updated_at",
        )

    def get_viewer_href(self, obj):
        page = next(iter(obj.evidence_pages or []), 1)
        return f"/reader/{obj.file_id}?page={page}" if obj.file_id else None


class ReadingPathItemSerializer(serializers.ModelSerializer):
    node_data = KnowledgeNodeListSerializer(source="node", read_only=True)
    work_data = serializers.SerializerMethodField()

    class Meta:
        model = ReadingPathItem
        fields = (
            "id",
            "stage_name",
            "stage_description",
            "node",
            "node_data",
            "work",
            "work_data",
            "recommendation_reason",
            "reading_order",
            "is_required",
            "editorial_note",
        )

    def get_work_data(self, obj):
        return compact_work(obj.work, self.context.get("request")) if obj.work_id else None


class ReadingPathSerializer(serializers.ModelSerializer):
    primary_discipline_data = DisciplineCompactSerializer(source="primary_discipline", read_only=True)
    items = ReadingPathItemSerializer(many=True, required=False)
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = ReadingPath
        fields = (
            "id",
            "title",
            "slug",
            "introduction",
            "primary_discipline",
            "primary_discipline_data",
            "audience",
            "difficulty",
            "estimated_reading",
            "cover_asset",
            "cover_url",
            "status",
            "sort_order",
            "items",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("published_at", "created_at", "updated_at")

    def get_cover_url(self, obj):
        return _media_url(self.context.get("request"), obj.cover_asset)

    def validate_status(self, value):
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        if value in {"published", "archived"} and role != "admin":
            raise serializers.ValidationError("只有管理员可以发布或下线阅读路径。")
        return value

    def _sync_items(self, path, items):
        path.items.all().delete()
        for row in items:
            ReadingPathItem.objects.create(reading_path=path, **row)

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items", [])
        actor = getattr(self.context.get("request"), "user", None)
        validated_data["created_by"] = actor
        if validated_data.get("status") == "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        path = super().create(validated_data)
        self._sync_items(path, items)
        return path

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        actor = getattr(self.context.get("request"), "user", None)
        if validated_data.get("status") == "published" and instance.status != "published":
            validated_data["reviewed_by"] = actor
            validated_data["published_at"] = timezone.now()
        path = super().update(instance, validated_data)
        if items is not None:
            self._sync_items(path, items)
        return path


class KnowledgeNodeVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True)

    class Meta:
        model = KnowledgeNodeVersion
        fields = (
            "id",
            "version_number",
            "snapshot",
            "change_note",
            "created_by_name",
            "created_at",
        )


class KnowledgeRelationVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True)

    class Meta:
        model = KnowledgeRelationVersion
        fields = (
            "id",
            "version_number",
            "snapshot",
            "change_note",
            "created_by_name",
            "created_at",
        )


class KnowledgeNodeMergeRecordSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source_node.canonical_name_zh", read_only=True)
    target_name = serializers.CharField(source="target_node.canonical_name_zh", read_only=True)

    class Meta:
        model = KnowledgeNodeMergeRecord
        fields = (
            "id",
            "source_node",
            "source_name",
            "target_node",
            "target_name",
            "affected_counts",
            "merged_by",
            "created_at",
            "rolled_back_at",
            "rolled_back_by",
        )


class NormalizedTimelineEventSerializer(serializers.ModelSerializer):
    relations = serializers.SerializerMethodField()
    reader_href = serializers.SerializerMethodField()

    class Meta:
        model = TheoryTimelineEvent
        fields = (
            "id",
            "title",
            "description",
            "event_type",
            "start_year",
            "end_year",
            "date_label",
            "source",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
            "relations",
            "reader_href",
        )

    def get_relations(self, obj):
        rows = []
        for relation in obj.normalized_relations.all():
            target = None
            if relation.node_id:
                target = {
                    "type": "node",
                    "id": str(relation.node_id),
                    "name": relation.node.canonical_name_zh,
                    "slug": relation.node.slug,
                }
            elif relation.discipline_id:
                target = {
                    "type": "discipline",
                    "id": str(relation.discipline_id),
                    "name": relation.discipline.name,
                    "slug": relation.discipline.slug,
                }
            elif relation.scholar_id:
                target = {
                    "type": "scholar",
                    "id": str(relation.scholar_id),
                    "name": relation.scholar.person.preferred_name,
                    "slug": relation.scholar.slug,
                }
            elif relation.work_id:
                target = {
                    "type": "work",
                    "id": str(relation.work_id),
                    "name": relation.work.title,
                }
            if target:
                rows.append({"relation_type": relation.relation_type, **target})
        return rows

    def get_reader_href(self, obj):
        if obj.evidence_asset_id and obj.evidence_page:
            return f"/reader/{obj.evidence_asset_id}?page={obj.evidence_page}"
        return None
