from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers
from uuid import UUID

from .models import (
    AboutPageBlock,
    Asset,
    Concept,
    Contribution,
    CoverCandidate,
    Discipline,
    Edition,
    KnowledgePublicationStatus,
    Person,
    Passage,
    PublicationState,
    RecommendationItem,
    RecommendationOverride,
    RecommendationPolicy,
    RecommendationSnapshot,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheoryDisciplineRelation,
    TheoryHierarchyRelation,
    TheoryRelation,
    TheorySchool,
    TheorySubdisciplineRelation,
    TheoryTimelineEvent,
    TimelineEventRelation,
    Topic,
    TopicDisciplineRelation,
    TopicSubdisciplineRelation,
    TopicTheoryRelation,
    Work,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkSubdisciplineRelation,
)
from .services.text import clean_page_label, normalize_search_text


def _available_slug(model, value: str, instance=None) -> str:
    base = slugify(value)[:150] or f"item-{abs(hash(value))}"
    candidate = base
    suffix = 1
    queryset = model.objects.all()
    if instance is not None:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _ordered_objects(queryset, identifiers):
    identifiers = [
        str(value)
        for value in identifiers
        if value and _is_uuid(value)
    ]
    objects = {str(item.id): item for item in queryset.filter(pk__in=identifiers)}
    return [objects[identifier] for identifier in identifiers if identifier in objects]


def _is_uuid(value):
    try:
        UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _validate_reference_list(value, key, queryset, label):
    identifiers = value.get(key, [])
    if identifiers in (None, ""):
        value[key] = []
        return
    if not isinstance(identifiers, list):
        raise serializers.ValidationError({key: [f"{label}必须是列表。"]})
    normalized = list(dict.fromkeys(str(identifier) for identifier in identifiers if identifier))
    if any(not _is_uuid(identifier) for identifier in normalized):
        raise serializers.ValidationError({key: [f"{label}包含无效标识。"]})
    existing = {
        str(identifier)
        for identifier in queryset.filter(pk__in=normalized).values_list("pk", flat=True)
    }
    missing = [identifier for identifier in normalized if identifier not in existing]
    if missing:
        raise serializers.ValidationError({key: [f"{label}包含不存在的馆藏对象。"]})
    value[key] = normalized


def _work_rows(queryset, reason="馆藏中已建立关联", source_label="馆藏关系"):
    return [
        {
            "id": str(work.id),
            "title": work.title,
            "document_type": work.document_type,
            "source_label": source_label,
            "reason": reason,
            "confidence": 1,
            "approved": True,
        }
        for work in queryset.distinct()[:80]
    ]


def _relation_work_rows(queryset, label):
    rows = []
    seen = set()
    for relation in queryset.select_related("work").order_by("-approved", "-confidence", "work__title")[:160]:
        work = relation.work
        identifier = str(work.id)
        if identifier in seen:
            continue
        seen.add(identifier)
        rows.append(
            {
                "id": identifier,
                "title": work.title,
                "document_type": work.document_type,
                "source": relation.source,
                "source_label": relation.source or "PDF 自动识别",
                "reason": f"{label}{'已由管理员确认' if relation.approved else '由系统识别，等待人工确认'}",
                "confidence": round(float(relation.confidence), 3),
                "approved": relation.approved,
            }
        )
        if len(rows) >= 80:
            break
    return rows


def _scholar_rows(queryset, reason="相关馆藏的作者或研究对象", source_label="作者贡献关系"):
    return [
        {
            "id": str(profile.id),
            "name": profile.person.preferred_name,
            "slug": profile.slug,
            "source_label": source_label,
            "reason": reason,
            "confidence": 1,
            "approved": True,
        }
        for profile in queryset.select_related("person").distinct()[:80]
    ]


def _knowledge_rows(queryset, reason="与同一批馆藏共同出现", source_label="馆藏知识关系"):
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "slug": item.slug,
            "description": item.description,
            "source_label": source_label,
            "reason": reason,
            "confidence": 1,
            "approved": True,
        }
        for item in queryset.distinct()[:80]
    ]


def _concept_rows(works, seed_names=()):
    rows = []
    seen = set()

    def add(name, description="", source=""):
        normalized = str(name).strip()
        key = normalized.casefold()
        if not normalized or key in seen or len(rows) >= 80:
            return
        seen.add(key)
        rows.append(
            {
                "id": f"concept-candidate-{len(rows) + 1}",
                "name": normalized,
                "description": str(description).strip(),
                "source": source,
                "source_label": source or "系统概念候选",
                "reason": "来自关联 PDF、主题词或已确认概念",
                "confidence": 0.78 if source else 0.62,
                "approved": source.startswith("已确认"),
            }
        )

    for concept in Concept.objects.filter(
        workknowledgerelation__work__in=works,
        workknowledgerelation__approved=True,
    ).distinct():
        add(concept.name, concept.definition or concept.description, "已确认馆藏概念")
    for name in seed_names:
        add(name, "", "现有关键主题")
    related_topics = Topic.objects.filter(
        workknowledgerelation__work__in=works,
        workknowledgerelation__approved=True,
    ).distinct()
    for topic in related_topics:
        for name in topic.key_concepts:
            add(name, topic.description, f"关联主题：{topic.name}")
    return rows


def _ranked_passage_rows(works, terms):
    normalized_terms = [
        normalize_search_text(term)
        for term in terms
        if normalize_search_text(term)
    ]
    social_terms = [
        "社会", "权力", "制度", "结构", "关系", "阶级", "身份", "国家", "资本",
        "society", "power", "institution", "structure", "class", "identity", "state", "capital",
    ]
    passages = (
        Passage.objects.filter(
            page__asset__edition__work__in=works,
            page__asset__edition__state=PublicationState.PUBLISHED,
            page__asset__kind=Asset.Kind.NORMALIZED,
            page__asset__status=Asset.Status.READY,
            page__asset__is_current=True,
        )
        .select_related("page__asset__edition__work")
        .order_by("page__asset__edition", "page__index")[:800]
    )
    ranked = []
    for passage in passages:
        text = passage.text.strip()
        if not 90 <= len(text) <= 1400:
            continue
        folded = normalize_search_text(text)
        if folded.startswith(("references", "bibliography", "参考文献", "注释")):
            continue
        matched = [term for term in normalized_terms if term and term in folded]
        social_hits = [term for term in social_terms if term in folded]
        complete = text.rstrip().endswith(("。", "！", "？", ".", "!", "?", "”", "’"))
        score = (
            0.35
            + min(len(matched), 4) * 0.12
            + min(len(social_hits), 4) * 0.035
            + (0.08 if complete else 0)
            + (0.07 if 160 <= len(text) <= 760 else 0)
        )
        if normalized_terms and not matched and not social_hits:
            continue
        reasons = []
        if matched:
            reasons.append(f"命中主题词：{'、'.join(matched[:4])}")
        if social_hits:
            reasons.append(f"包含社会科学判断词：{'、'.join(social_hits[:4])}")
        if complete:
            reasons.append("段落边界完整")
        ranked.append(
            (
                score,
                {
                    "id": str(passage.id),
                    "title": passage.page.asset.edition.work.title,
                    "description": text[:260],
                    "page_index": passage.page.index,
                    "printed_label": clean_page_label(passage.page.printed_label),
                    "source_label": passage.page.asset.edition.work.title,
                    "reason": "；".join(reasons) or "来自已关联馆藏全文",
                    "confidence": round(min(score, 0.99), 3),
                    "approved": False,
                    "evidence": {
                        "asset_id": str(passage.page.asset_id),
                        "pdf_page": passage.page.index,
                        "printed_label": clean_page_label(passage.page.printed_label),
                        "matched_terms": matched,
                    },
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]["page_index"]))
    return [row for _score, row in ranked[:40]]


def _structured_entries(value, key):
    entries = value.get(key, [])
    if entries in (None, ""):
        value[key] = []
        return []
    if not isinstance(entries, list):
        raise serializers.ValidationError({key: ["该字段必须是列表。"]})
    if any(not isinstance(entry, (dict, str)) for entry in entries):
        raise serializers.ValidationError({key: ["该字段包含无法识别的条目。"]})
    return entries


class PersonCompactSerializer(serializers.ModelSerializer):
    scholar_slug = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = (
            "id",
            "preferred_name",
            "original_name",
            "aliases",
            "authority_status",
            "birth_year",
            "death_year",
            "biography",
            "portrait",
            "scholar_slug",
        )

    def get_scholar_slug(self, obj):
        profile = getattr(obj, "scholar_profile", None)
        if profile and profile.editorial_status == "published":
            return profile.slug
        return None


class ContributionSerializer(serializers.ModelSerializer):
    person = PersonCompactSerializer()

    class Meta:
        model = Contribution
        fields = ("role", "order", "person")


class AssetCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = (
            "id",
            "kind",
            "original_filename",
            "mime_type",
            "page_count",
            "byte_size",
            "sha256",
            "text_layer_quality",
            "language_guess",
            "access_status",
            "rights_note",
        )


class CoverCandidateSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = CoverCandidate
        fields = (
            "id",
            "work",
            "asset",
            "page_index",
            "thumbnail_url",
            "score",
            "reasons",
            "metrics",
            "selected",
            "created_at",
            "updated_at",
        )

    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return ""
        request = self.context.get("request")
        url = reverse(
            "admin-cover-candidate-thumbnail",
            kwargs={
                "work_id": obj.work_id,
                "candidate_id": obj.id,
            },
        )
        return request.build_absolute_uri(url) if request else url


class EditionCompactSerializer(serializers.ModelSerializer):
    contributors = serializers.SerializerMethodField()
    readable_asset = serializers.SerializerMethodField()
    edition_statement = serializers.CharField(source="version_label", read_only=True)
    publisher_verbatim = serializers.CharField(source="publisher", read_only=True)
    publication_place_verbatim = serializers.CharField(source="publication_place", read_only=True)

    class Meta:
        model = Edition
        fields = (
            "id",
            "public_slug",
            "version_label",
            "edition_statement",
            "publication_year",
            "publisher",
            "publisher_verbatim",
            "publisher_authority",
            "publication_place",
            "publication_place_verbatim",
            "distribution_place",
            "distributor",
            "manufacture_place",
            "manufacturer",
            "journal_title",
            "volume",
            "issue",
            "page_range",
            "isbn",
            "isbn10",
            "isbn13",
            "doi",
            "series",
            "extent",
            "responsibility_statement",
            "contributors",
            "readable_asset",
        )

    def get_contributors(self, obj):
        queryset = obj.contributions.filter(approved=True).select_related("person")
        return ContributionSerializer(queryset, many=True).data

    def get_readable_asset(self, obj):
        asset = obj.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        return AssetCompactSerializer(asset).data if asset else None


class WorkCardSerializer(serializers.ModelSerializer):
    cover = serializers.SerializerMethodField()
    recommendation_image = serializers.SerializerMethodField()
    edition = serializers.SerializerMethodField()
    theories = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    disciplines = serializers.SerializerMethodField()
    subdisciplines = serializers.SerializerMethodField()

    class Meta:
        model = Work
        fields = (
            "id",
            "document_type",
            "title",
            "subtitle",
            "original_title",
            "uniform_title",
            "abstract",
            "language",
            "original_language",
            "first_publication_date",
            "translation_of",
            "cover",
            "recommendation_image",
            "edition",
            "theories",
            "topics",
            "disciplines",
            "subdisciplines",
        )

    def get_cover(self, obj):
        if not obj.cover:
            return ""
        # Public pages and LAN access both enter through the edge proxy.  Keep
        # browser-facing resources on that same origin instead of leaking the
        # API container hostname or a development default such as
        # ``http://localhost:8000`` into server-rendered HTML.
        return reverse("public-work-cover", kwargs={"work_id": obj.id})

    def get_recommendation_image(self, obj):
        if not obj.recommendation_image and not obj.cover:
            return ""
        return reverse(
            "public-work-recommendation-image",
            kwargs={"work_id": obj.id},
        )

    def get_edition(self, obj):
        edition = next(
            (
                edition
                for edition in obj.editions.all()
                if edition.state == PublicationState.PUBLISHED and edition.is_primary
            ),
            None,
        )
        return EditionCompactSerializer(edition, context=self.context).data if edition else None

    def _relations(self, obj, kind):
        values = []
        for relation in obj.knowledge_relations.all():
            if not relation.approved or relation.kind != kind:
                continue
            target = getattr(relation, kind)
            if target:
                values.append({"id": str(target.id), "name": target.name, "slug": target.slug})
        return values

    def get_theories(self, obj):
        return self._relations(obj, WorkKnowledgeRelation.Kind.THEORY_SCHOOL)

    def get_topics(self, obj):
        return self._relations(obj, WorkKnowledgeRelation.Kind.TOPIC)

    def get_disciplines(self, obj):
        return [
            {
                "id": str(relation.discipline_id),
                "name": relation.discipline.name,
                "slug": relation.discipline.slug,
                "is_primary": relation.is_primary,
            }
            for relation in obj.discipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
            ).select_related("discipline")
        ]

    def get_subdisciplines(self, obj):
        return [
            {
                "id": str(relation.subdiscipline_id),
                "name": relation.subdiscipline.name,
                "slug": relation.subdiscipline.slug,
                "is_primary": relation.is_primary,
            }
            for relation in obj.subdiscipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
            ).select_related("subdiscipline")
        ]


class WorkDetailSerializer(WorkCardSerializer):
    editions = serializers.SerializerMethodField()
    outline = serializers.SerializerMethodField()
    theory_associations = serializers.SerializerMethodField()

    class Meta(WorkCardSerializer.Meta):
        fields = WorkCardSerializer.Meta.fields + ("editions", "outline", "theory_associations")

    def get_editions(self, obj):
        editions = obj.editions.filter(state="published").prefetch_related("contributions__person", "assets")
        return EditionCompactSerializer(editions, many=True, context=self.context).data

    def get_outline(self, obj):
        edition = obj.editions.filter(
            state=PublicationState.PUBLISHED,
            is_primary=True,
        ).first()
        if not edition:
            return []
        asset = edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        if not asset:
            return []
        return [
            {
                "index": page.index,
                "printed_label": clean_page_label(page.printed_label),
                "chapter_title": page.chapter_title,
            }
            for page in asset.pages.exclude(chapter_title="").order_by("index")
        ]

    def get_theory_associations(self, obj):
        relations = (
            obj.node_relations.filter(
                status=KnowledgePublicationStatus.PUBLISHED,
                node__status=KnowledgePublicationStatus.PUBLISHED,
            )
            .select_related("node")
            .prefetch_related("evidence")
            .order_by("role", "node__sort_order", "node__canonical_name_zh")
        )
        return [
            {
                "id": str(relation.id),
                "node": {
                    "id": str(relation.node_id),
                    "name": relation.node.canonical_name_zh,
                    "foreign_name": relation.node.canonical_name_en,
                    "slug": relation.node.slug,
                    "type": relation.node.node_type,
                },
                "role": relation.role,
                "role_label": relation.get_role_display(),
                "strength": relation.strength,
                "evidence": [
                    {
                        "id": str(evidence.id),
                        "page_number": evidence.page_number,
                        "page_end": evidence.page_end,
                        "printed_page_label": evidence.printed_page_label,
                        "quote": evidence.quote,
                        "reader_href": (
                            f"/reader/{evidence.file_id}?page={evidence.page_number}"
                            f"&evidence={evidence.id}"
                        ),
                    }
                    for evidence in relation.evidence.all()
                    if evidence.review_status == RelationReviewStatus.APPROVED
                ],
            }
            for relation in relations
        ]


class TheorySchoolSerializer(serializers.ModelSerializer):
    work_count = serializers.IntegerField(read_only=True)
    scholar_count = serializers.SerializerMethodField()
    curated = serializers.SerializerMethodField()
    disciplines = serializers.SerializerMethodField()
    subdisciplines = serializers.SerializerMethodField()
    hierarchy = serializers.SerializerMethodField()
    relations = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = TheorySchool
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "symbol",
            "foreign_name",
            "entity_level",
            "formation_period",
            "core_questions",
            "key_themes",
            "hero_image",
            "disciplines",
            "subdisciplines",
            "hierarchy",
            "relations",
            "timeline",
            "work_count",
            "scholar_count",
            "curated",
        )

    def get_disciplines(self, obj):
        return [
            {
                "id": str(relation.discipline_id),
                "name": relation.discipline.name,
                "slug": relation.discipline.slug,
                "role": relation.role,
            }
            for relation in obj.discipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                discipline__editorial_status="published",
            ).select_related("discipline")
        ]

    def get_subdisciplines(self, obj):
        return [
            {
                "id": str(relation.subdiscipline_id),
                "name": relation.subdiscipline.name,
                "slug": relation.subdiscipline.slug,
                "role": relation.role,
            }
            for relation in obj.subdiscipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                subdiscipline__editorial_status="published",
            ).select_related("subdiscipline")
        ]

    def get_hierarchy(self, obj):
        return {
            "parents": [
                {"id": str(item.parent_id), "name": item.parent.name, "slug": item.parent.slug}
                for item in obj.parent_relations.filter(
                    review_status=RelationReviewStatus.APPROVED,
                    parent__editorial_status="published",
                ).select_related("parent")
            ],
            "branches": [
                {"id": str(item.child_id), "name": item.child.name, "slug": item.child.slug}
                for item in obj.child_relations.filter(
                    review_status=RelationReviewStatus.APPROVED,
                    child__editorial_status="published",
                ).select_related("child")
            ],
        }

    def get_relations(self, obj):
        rows = []
        outgoing = obj.outgoing_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            target_theory__editorial_status="published",
        ).select_related("target_theory")
        incoming = obj.incoming_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            source_theory__editorial_status="published",
        ).select_related("source_theory")
        for relation in outgoing:
            rows.append({
                "id": str(relation.id),
                "direction": "outgoing",
                "relation_type": relation.relation_type,
                "strength": relation.strength,
                "theory": {
                    "id": str(relation.target_theory_id),
                    "name": relation.target_theory.name,
                    "slug": relation.target_theory.slug,
                },
                "evidence_page": relation.evidence_page,
                "evidence_text": relation.evidence_text,
            })
        for relation in incoming:
            rows.append({
                "id": str(relation.id),
                "direction": "incoming",
                "relation_type": relation.relation_type,
                "strength": relation.strength,
                "theory": {
                    "id": str(relation.source_theory_id),
                    "name": relation.source_theory.name,
                    "slug": relation.source_theory.slug,
                },
                "evidence_page": relation.evidence_page,
                "evidence_text": relation.evidence_text,
            })
        return rows

    def get_timeline(self, obj):
        return TheoryTimelineEventSerializer(
            obj.timeline_events.filter(review_status=RelationReviewStatus.APPROVED),
            many=True,
            context=self.context,
        ).data

    def get_scholar_count(self, obj):
        return (
            ScholarProfile.objects.filter(editorial_status="published")
            .filter(
                Q(
                    person__knowledge_relations__theory_school=obj,
                    person__knowledge_relations__approved=True,
                )
                | Q(
                    person__contributions__approved=True,
                    person__contributions__edition__state=PublicationState.PUBLISHED,
                    person__contributions__edition__work__knowledge_relations__theory_school=obj,
                    person__contributions__edition__work__knowledge_relations__approved=True,
                )
            )
            .distinct()
            .count()
        )

    def get_curated(self, obj):
        curation = obj.curation if isinstance(obj.curation, dict) else {}
        foundational_works = _ordered_objects(
            Work.objects.filter(editions__state=PublicationState.PUBLISHED),
            curation.get("foundational_work_ids", []),
        )
        reading_works = _ordered_objects(
            Work.objects.filter(editions__state=PublicationState.PUBLISHED),
            curation.get("curated_reading_work_ids", []),
        )
        scholars = _ordered_objects(
            ScholarProfile.objects.filter(editorial_status="published").select_related("person"),
            curation.get("key_scholar_ids", []),
        )
        neighbors = _ordered_objects(
            TheorySchool.objects.filter(editorial_status="published"),
            curation.get("neighbor_school_ids", []),
        )
        neighbor_relations = {
            str(entry.get("school_id")): entry
            for entry in curation.get("neighbor_relations", [])
            if isinstance(entry, dict) and entry.get("school_id")
        }
        neighbor_rows = []
        for neighbor in neighbors:
            relation = neighbor_relations.get(str(neighbor.id), {})
            neighbor_rows.append(
                {
                    "id": str(neighbor.id),
                    "name": neighbor.name,
                    "slug": neighbor.slug,
                    "description": neighbor.description,
                    "relation": relation.get("relation", ""),
                    "source": relation.get("source", ""),
                }
            )
        core_concepts = curation.get("core_concepts", [])
        if not core_concepts:
            core_concepts = [
                {"name": theme, "description": "", "source": ""}
                for theme in obj.key_themes
            ]
        return {
            "hero_caption": curation.get("hero_caption", ""),
            "foundational_works": WorkCardSerializer(
                foundational_works,
                many=True,
                context=self.context,
            ).data,
            "curated_reading_works": WorkCardSerializer(
                reading_works,
                many=True,
                context=self.context,
            ).data,
            "key_scholars": _scholar_rows(ScholarProfile.objects.filter(pk__in=[item.pk for item in scholars])),
            "neighbors": neighbor_rows,
            "core_concepts": core_concepts,
            "conceptual_map": curation.get("conceptual_map", []),
        }


class TopicSerializer(serializers.ModelSerializer):
    work_count = serializers.IntegerField(read_only=True)
    curated = serializers.SerializerMethodField()
    disciplines = serializers.SerializerMethodField()
    subdisciplines = serializers.SerializerMethodField()
    linked_theories = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "problem_statement",
            "core_questions",
            "research_dimensions",
            "methods",
            "formation_context",
            "key_concepts",
            "timeline",
            "hero_image",
            "disciplines",
            "subdisciplines",
            "linked_theories",
            "work_count",
            "curated",
        )

    def get_disciplines(self, obj):
        return [
            {
                "id": str(relation.discipline_id),
                "name": relation.discipline.name,
                "slug": relation.discipline.slug,
                "is_primary": relation.is_primary,
            }
            for relation in obj.discipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                discipline__editorial_status="published",
            ).select_related("discipline")
        ]

    def get_subdisciplines(self, obj):
        return [
            {
                "id": str(relation.subdiscipline_id),
                "name": relation.subdiscipline.name,
                "slug": relation.subdiscipline.slug,
                "relation_label": relation.relation_label,
            }
            for relation in obj.subdiscipline_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                subdiscipline__editorial_status="published",
            ).select_related("subdiscipline")
        ]

    def get_linked_theories(self, obj):
        return [
            {
                "id": str(relation.theory_school_id),
                "name": relation.theory_school.name,
                "slug": relation.theory_school.slug,
                "relation_label": relation.relation_label,
            }
            for relation in obj.theory_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                theory_school__editorial_status="published",
            ).select_related("theory_school")
        ]

    def get_curated(self, obj):
        curation = obj.curation if isinstance(obj.curation, dict) else {}
        foundational = _ordered_objects(
            Work.objects.filter(editions__state=PublicationState.PUBLISHED),
            curation.get("foundational_work_ids", []),
        )
        recent = _ordered_objects(
            Work.objects.filter(editions__state=PublicationState.PUBLISHED),
            curation.get("recent_work_ids", []),
        )
        scholars = _ordered_objects(
            ScholarProfile.objects.filter(editorial_status="published").select_related("person"),
            curation.get("related_scholar_ids", []),
        )
        theories = _ordered_objects(
            TheorySchool.objects.filter(editorial_status="published"),
            curation.get("linked_theory_ids", []),
        )
        reading_paths = []
        for path in curation.get("reading_paths", []):
            if not isinstance(path, dict):
                continue
            path_works = _ordered_objects(
                Work.objects.filter(editions__state=PublicationState.PUBLISHED),
                path.get("work_ids", []),
            )
            reading_paths.append(
                {
                    "title": path.get("title", ""),
                    "description": path.get("description", ""),
                    "level": path.get("level", ""),
                    "works": WorkCardSerializer(path_works, many=True, context=self.context).data,
                }
            )
        return {
            "hero_caption": curation.get("hero_caption", ""),
            "foundational_works": WorkCardSerializer(foundational, many=True, context=self.context).data,
            "recent_works": WorkCardSerializer(recent, many=True, context=self.context).data,
            "related_scholars": _scholar_rows(ScholarProfile.objects.filter(pk__in=[item.pk for item in scholars])),
            "linked_theories": _knowledge_rows(TheorySchool.objects.filter(pk__in=[item.pk for item in theories])),
            "reading_paths": reading_paths,
            "featured_passage_id": curation.get("featured_passage_id", ""),
            "featured_passage_reason": curation.get("featured_passage_reason", ""),
            "featured_passage_evidence": curation.get("featured_passage_evidence", {}),
        }


class ScholarProfileSerializer(serializers.ModelSerializer):
    person = PersonCompactSerializer()
    works = serializers.SerializerMethodField()
    curated = serializers.SerializerMethodField()

    class Meta:
        model = ScholarProfile
        fields = (
            "id",
            "slug",
            "person",
            "short_description",
            "affiliations",
            "key_concerns",
            "timeline",
            "featured_quote",
            "quote_source",
            "works",
            "curated",
        )

    def get_works(self, obj):
        works = Work.objects.filter(
            editions__contributions__person=obj.person,
            editions__contributions__approved=True,
            editions__state="published",
        ).distinct()[:24]
        return WorkCardSerializer(works, many=True, context=self.context).data

    def get_curated(self, obj):
        curation = obj.curation if isinstance(obj.curation, dict) else {}
        works = _ordered_objects(
            Work.objects.filter(editions__state=PublicationState.PUBLISHED),
            curation.get("essential_work_ids", []),
        )
        frequent = _ordered_objects(
            ScholarProfile.objects.filter(editorial_status="published").select_related("person"),
            curation.get("frequently_read_scholar_ids", []),
        )
        related_theories = _ordered_objects(
            TheorySchool.objects.filter(editorial_status="published"),
            curation.get("related_theory_ids", []),
        )
        network = []
        network_entries = curation.get("network", [])
        profile_ids = [
            entry.get("scholar_id")
            for entry in network_entries
            if isinstance(entry, dict) and entry.get("scholar_id")
        ]
        profiles = {
            str(profile.id): profile
            for profile in ScholarProfile.objects.filter(
                pk__in=profile_ids,
                editorial_status="published",
            ).select_related("person")
        }
        for entry in network_entries:
            if not isinstance(entry, dict):
                continue
            profile = profiles.get(str(entry.get("scholar_id", "")))
            if profile is None:
                continue
            network.append(
                {
                    "scholar": {
                        "id": str(profile.id),
                        "name": profile.person.preferred_name,
                        "slug": profile.slug,
                    },
                    "relation": entry.get("relation", ""),
                    "source": entry.get("source", ""),
                }
            )
        return {
            "essential_works": WorkCardSerializer(works, many=True, context=self.context).data,
            "key_concepts": curation.get("key_concepts", []),
            "concept_map": curation.get("concept_map", []),
            "network": network,
            "frequently_read_scholars": _scholar_rows(
                ScholarProfile.objects.filter(pk__in=[item.pk for item in frequent])
            ),
            "related_theories": [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "slug": item.slug,
                    "description": item.description,
                    "symbol": item.symbol,
                }
                for item in related_theories
            ],
        }


class DisciplineSerializer(serializers.ModelSerializer):
    theory_count = serializers.SerializerMethodField()
    subdiscipline_count = serializers.SerializerMethodField()
    topic_count = serializers.SerializerMethodField()
    work_count = serializers.SerializerMethodField()
    scholar_count = serializers.SerializerMethodField()

    class Meta:
        model = Discipline
        fields = (
            "id",
            "code",
            "name",
            "foreign_name",
            "slug",
            "description",
            "introduction",
            "hero_image",
            "sort_order",
            "theory_count",
            "subdiscipline_count",
            "topic_count",
            "work_count",
            "scholar_count",
        )

    def get_theory_count(self, obj):
        return obj.theory_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            theory_school__editorial_status="published",
        ).values("theory_school_id").distinct().count()

    def get_subdiscipline_count(self, obj):
        return obj.subdisciplines.filter(editorial_status="published").count()

    def get_topic_count(self, obj):
        return obj.topic_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            topic__editorial_status="published",
        ).values("topic_id").distinct().count()

    def get_work_count(self, obj):
        return obj.work_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            work__editions__state=PublicationState.PUBLISHED,
        ).values("work_id").distinct().count()

    def get_scholar_count(self, obj):
        direct = obj.person_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            person__scholar_profile__editorial_status="published",
        ).values("person_id")
        return direct.distinct().count()


class SubdisciplineSerializer(serializers.ModelSerializer):
    discipline = DisciplineSerializer(read_only=True)
    parent = serializers.SerializerMethodField()
    theories = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    works = serializers.SerializerMethodField()
    scholars = serializers.SerializerMethodField()

    class Meta:
        model = Subdiscipline
        fields = (
            "id",
            "name",
            "foreign_name",
            "slug",
            "description",
            "hero_image",
            "discipline",
            "parent",
            "research_object",
            "core_questions",
            "formation_period",
            "research_directions",
            "methods",
            "representative_issues",
            "theories",
            "topics",
            "works",
            "scholars",
        )

    def get_parent(self, obj):
        if not obj.parent:
            return None
        return {"id": str(obj.parent_id), "name": obj.parent.name, "slug": obj.parent.slug}

    def get_theories(self, obj):
        return [
            {
                "id": str(relation.theory_school_id),
                "name": relation.theory_school.name,
                "slug": relation.theory_school.slug,
                "role": relation.role,
            }
            for relation in obj.theory_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                theory_school__editorial_status="published",
            ).select_related("theory_school")
        ]

    def get_topics(self, obj):
        return [
            {
                "id": str(relation.topic_id),
                "name": relation.topic.name,
                "slug": relation.topic.slug,
                "relation_label": relation.relation_label,
            }
            for relation in obj.topic_relations.filter(
                review_status=RelationReviewStatus.APPROVED,
                topic__editorial_status="published",
            ).select_related("topic")
        ]

    def get_works(self, obj):
        works = Work.objects.filter(
            subdiscipline_relations__subdiscipline=obj,
            subdiscipline_relations__review_status=RelationReviewStatus.APPROVED,
            editions__state=PublicationState.PUBLISHED,
        ).distinct()[:48]
        return WorkCardSerializer(works, many=True, context=self.context).data

    def get_scholars(self, obj):
        profiles = ScholarProfile.objects.filter(
            person__subdiscipline_relations__subdiscipline=obj,
            person__subdiscipline_relations__review_status=RelationReviewStatus.APPROVED,
            editorial_status="published",
        )
        return _scholar_rows(profiles, reason="管理员确认的子学科关联")


class TheoryTimelineEventSerializer(serializers.ModelSerializer):
    theory = serializers.SerializerMethodField()
    discipline = serializers.SerializerMethodField()
    subdiscipline = serializers.SerializerMethodField()
    scholar = serializers.SerializerMethodField()
    work = serializers.SerializerMethodField()

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
            "orientation",
            "image",
            "theory",
            "discipline",
            "subdiscipline",
            "scholar",
            "work",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
        )

    def _named(self, value):
        if value is None:
            return None
        return {"id": str(value.id), "name": value.name, "slug": value.slug}

    def get_theory(self, obj):
        return self._named(obj.theory_school)

    def get_discipline(self, obj):
        return self._named(obj.discipline)

    def get_subdiscipline(self, obj):
        return self._named(obj.subdiscipline)

    def get_scholar(self, obj):
        if obj.scholar is None:
            return None
        return {
            "id": str(obj.scholar_id),
            "name": obj.scholar.person.preferred_name,
            "slug": obj.scholar.slug,
        }

    def get_work(self, obj):
        if obj.work is None:
            return None
        return {"id": str(obj.work_id), "title": obj.work.title}


class RecommendationSnapshotSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = RecommendationSnapshot
        fields = ("id", "starts_at", "expires_at", "source", "seed", "items")

    def get_items(self, obj):
        request = self.context.get("request")

        def public_url(field):
            if not field:
                return ""
            url = field.url
            return request.build_absolute_uri(url) if request else url

        rows = []
        for item in obj.items.all().order_by("position"):
            if item.work_id:
                target_type = "work"
                target = WorkCardSerializer(item.work, context=self.context).data
            elif item.theory_school_id:
                target_type = "theory_school"
                target = {
                    "id": str(item.theory_school_id),
                    "name": item.theory_school.name,
                    "slug": item.theory_school.slug,
                    "description": item.theory_school.description,
                    "symbol": item.theory_school.symbol,
                    "hero_image": public_url(item.theory_school.hero_image),
                }
            elif item.topic_id:
                target_type = "topic"
                target = {
                    "id": str(item.topic_id),
                    "name": item.topic.name,
                    "slug": item.topic.slug,
                    "description": item.topic.description,
                    "hero_image": public_url(item.topic.hero_image),
                }
            elif item.scholar_id:
                if item.scholar.editorial_status != "published":
                    continue
                target_type = "scholar"
                target = {
                    "id": str(item.scholar_id),
                    "name": item.scholar.person.preferred_name,
                    "slug": item.scholar.slug,
                    "description": item.scholar.short_description,
                }
            else:
                continue
            rows.append(
                {
                    "id": str(item.id),
                    "position": item.position,
                    "reason": item.reason,
                    "image_override": public_url(item.image_override),
                    "target_type": target_type,
                    "target": target,
                }
            )
        return rows


class RecommendationPolicySerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    class Meta:
        model = RecommendationPolicy
        fields = (
            "id",
            "placement",
            "title",
            "item_count",
            "rotation_days",
            "rules",
            "enabled",
            "last_generated_at",
            "next_refresh_at",
            "current",
        )

    def get_current(self, obj):
        snapshot = getattr(obj, "resolved_snapshot", None)
        if snapshot is None:
            snapshot = obj.snapshots.filter(is_current=True).first()
        return RecommendationSnapshotSerializer(snapshot, context=self.context).data if snapshot else None


class AboutPageBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = AboutPageBlock
        fields = (
            "id",
            "key",
            "block_type",
            "title",
            "body",
            "icon",
            "action_label",
            "action_href",
            "sort_order",
            "visible",
            "configuration",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class AdminDisciplineSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, allow_blank=True)
    code = serializers.SlugField(required=False, allow_blank=True)
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Discipline
        fields = (
            "id",
            "code",
            "name",
            "foreign_name",
            "slug",
            "search_aliases",
            "description",
            "introduction",
            "hero_image",
            "sort_order",
            "curation_level",
            "editorial_status",
            "counts",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "counts", "created_at", "updated_at")

    def get_counts(self, obj):
        public = DisciplineSerializer(obj, context=self.context).data
        return {
            "theories": public["theory_count"],
            "subdisciplines": public["subdiscipline_count"],
            "topics": public["topic_count"],
            "works": public["work_count"],
            "scholars": public["scholar_count"],
        }

    def _complete_identity(self, validated_data, instance=None):
        name = validated_data.get("name", instance.name if instance else "")
        if not validated_data.get("slug"):
            validated_data["slug"] = _available_slug(Discipline, name, instance)
        if not validated_data.get("code"):
            validated_data["code"] = validated_data["slug"][:80]
        return validated_data

    def create(self, validated_data):
        return super().create(self._complete_identity(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._complete_identity(validated_data, instance))


class AdminSubdisciplineSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, allow_blank=True)

    class Meta:
        model = Subdiscipline
        fields = (
            "id",
            "name",
            "foreign_name",
            "slug",
            "search_aliases",
            "description",
            "hero_image",
            "discipline",
            "parent",
            "research_object",
            "core_questions",
            "formation_period",
            "research_directions",
            "methods",
            "representative_issues",
            "curation_level",
            "editorial_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_parent(self, value):
        if value and self.instance and value.pk == self.instance.pk:
            raise serializers.ValidationError("子学科不能以自身作为上级。")
        return value

    def validate(self, attrs):
        parent = attrs.get("parent", self.instance.parent if self.instance else None)
        discipline = attrs.get("discipline", self.instance.discipline if self.instance else None)
        if parent and parent.discipline_id != discipline.id:
            raise serializers.ValidationError({"parent": ["上级子学科必须属于同一学科。"]})
        return attrs

    def create(self, validated_data):
        validated_data["slug"] = validated_data.get("slug") or _available_slug(
            Subdiscipline,
            validated_data["name"],
        )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data["slug"] = _available_slug(
                Subdiscipline,
                validated_data.get("name", instance.name),
                instance,
            )
        return super().update(instance, validated_data)


class AdminTimelineEventRelationSerializer(serializers.ModelSerializer):
    node_name = serializers.CharField(source="node.canonical_name_zh", read_only=True)
    discipline_name = serializers.CharField(source="discipline.name", read_only=True)
    scholar_name = serializers.CharField(source="scholar.person.preferred_name", read_only=True)
    work_title = serializers.CharField(source="work.title", read_only=True)

    class Meta:
        model = TimelineEventRelation
        fields = (
            "id",
            "relation_type",
            "node",
            "node_name",
            "discipline",
            "discipline_name",
            "scholar",
            "scholar_name",
            "work",
            "work_title",
            "evidence",
            "description",
            "sort_order",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        instance = self.instance
        targets = [
            attrs.get("node", getattr(instance, "node", None)),
            attrs.get("discipline", getattr(instance, "discipline", None)),
            attrs.get("scholar", getattr(instance, "scholar", None)),
            attrs.get("work", getattr(instance, "work", None)),
        ]
        if sum(bool(value) for value in targets) != 1:
            raise serializers.ValidationError("时间轴关联必须且只能选择一个对象。")
        return attrs


class AdminTheoryTimelineEventSerializer(serializers.ModelSerializer):
    relations = AdminTimelineEventRelationSerializer(
        source="normalized_relations",
        many=True,
        required=False,
    )

    class Meta:
        model = TheoryTimelineEvent
        fields = tuple(
            field.name
            for field in TheoryTimelineEvent._meta.fields
        ) + ("relations",)
        read_only_fields = ("reviewed_by", "reviewed_at")

    def validate(self, attrs):
        normalized_relations = attrs.get("normalized_relations")
        has_existing_relations = bool(
            self.instance
            and normalized_relations is None
            and self.instance.normalized_relations.exists()
        )
        if not any(attrs.get(name, getattr(self.instance, f"{name}_id", None) if self.instance else None) for name in (
            "discipline",
            "theory_school",
            "subdiscipline",
            "scholar",
            "work",
        )) and not normalized_relations and not has_existing_relations:
            raise serializers.ValidationError("时间轴事件至少需要关联一个学术实体或文献。")
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        review_status = attrs.get(
            "review_status",
            getattr(self.instance, "review_status", RelationReviewStatus.SUGGESTED),
        )
        if review_status in {RelationReviewStatus.APPROVED, RelationReviewStatus.REJECTED} and role not in {
            "admin",
            "reviewer",
        }:
            raise serializers.ValidationError({"review_status": ["只有管理员或审核者可以确认时间轴事件。"]})
        return attrs

    def _sync_relations(self, event, rows):
        event.normalized_relations.all().delete()
        for row in rows:
            TimelineEventRelation.objects.create(event=event, **row)

    @transaction.atomic
    def create(self, validated_data):
        relations = validated_data.pop("normalized_relations", [])
        event = super().create(validated_data)
        self._sync_relations(event, relations)
        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        relations = validated_data.pop("normalized_relations", None)
        event = super().update(instance, validated_data)
        if relations is not None:
            self._sync_relations(event, relations)
        return event


class AdminRecommendationOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationOverride
        fields = "__all__"
        read_only_fields = ("created_by",)

    def validate(self, attrs):
        instance = self.instance
        target_count = sum(
            attrs.get(field) is not None
            if field in attrs
            else bool(getattr(instance, f"{field}_id", None)) if instance else False
            for field in ("work", "theory_school", "topic", "scholar", "discipline", "subdiscipline")
        )
        if target_count != 1:
            raise serializers.ValidationError("策展规则必须且只能关联一个对象。")
        return attrs


class ReviewedRelationSerializer(serializers.ModelSerializer):
    def save(self, **kwargs):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            kwargs.setdefault("reviewed_by", request.user)
            kwargs.setdefault("reviewed_at", timezone.now())
        return super().save(**kwargs)


class AdminTheoryDisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TheoryDisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminTheorySubdisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TheorySubdisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminTheoryHierarchyRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TheoryHierarchyRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")

    def validate(self, attrs):
        parent = attrs.get("parent", self.instance.parent if self.instance else None)
        child = attrs.get("child", self.instance.child if self.instance else None)
        if parent and child and parent.pk == child.pk:
            raise serializers.ValidationError("理论传统不能以自身作为上位传统。")
        return attrs


class AdminTheoryRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TheoryRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")

    def validate(self, attrs):
        source = attrs.get("source_theory", self.instance.source_theory if self.instance else None)
        target = attrs.get("target_theory", self.instance.target_theory if self.instance else None)
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError("理论关系的两端不能是同一实体。")
        return attrs


class AdminTopicDisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TopicDisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminTopicTheoryRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TopicTheoryRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminTopicSubdisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = TopicSubdisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminWorkDisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = WorkDisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminWorkSubdisciplineRelationSerializer(ReviewedRelationSerializer):
    class Meta:
        model = WorkSubdisciplineRelation
        fields = "__all__"
        read_only_fields = ("reviewed_by", "reviewed_at")


class AdminWorkTheoryRelationSerializer(ReviewedRelationSerializer):
    theory_name = serializers.CharField(source="theory_school.name", read_only=True)

    class Meta:
        model = WorkKnowledgeRelation
        fields = (
            "id",
            "work",
            "kind",
            "theory_school",
            "theory_name",
            "role",
            "strength",
            "is_primary",
            "source",
            "confidence",
            "evidence_asset",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "approved",
        )
        read_only_fields = ("reviewed_by", "reviewed_at", "approved")

    def validate(self, attrs):
        if attrs.get("kind", getattr(self.instance, "kind", None)) != WorkKnowledgeRelation.Kind.THEORY_SCHOOL:
            raise serializers.ValidationError({"kind": ["此接口只管理文献与理论传统的关系。"]})
        if not attrs.get("theory_school", getattr(self.instance, "theory_school", None)):
            raise serializers.ValidationError({"theory_school": ["请选择理论传统。"]})
        return attrs

    def save(self, **kwargs):
        status_value = self.validated_data.get(
            "review_status",
            self.instance.review_status if self.instance else RelationReviewStatus.SUGGESTED,
        )
        kwargs["approved"] = status_value == RelationReviewStatus.APPROVED
        return super().save(**kwargs)


class SiteConfigSerializer(serializers.Serializer):
    site_name = serializers.CharField(max_length=120)
    wordmark_lines = serializers.ListField(
        child=serializers.CharField(max_length=80),
        min_length=1,
        max_length=5,
    )
    home_title_left_lines = serializers.ListField(
        child=serializers.CharField(max_length=160),
        min_length=1,
        max_length=4,
    )
    home_title_right_lines = serializers.ListField(
        child=serializers.CharField(max_length=160),
        min_length=1,
        max_length=4,
    )
    intro_lines = serializers.ListField(
        child=serializers.CharField(max_length=500),
        min_length=1,
        max_length=6,
    )
    about_label = serializers.CharField(max_length=120)
    about_title = serializers.CharField(max_length=240)
    about_body = serializers.CharField(max_length=5000)
    about_why_title = serializers.CharField(max_length=240)
    about_why_body = serializers.CharField(max_length=5000)
    about_feature_search_title = serializers.CharField(max_length=240)
    about_feature_search_body = serializers.CharField(max_length=1500)
    about_feature_read_title = serializers.CharField(max_length=240)
    about_feature_read_body = serializers.CharField(max_length=1500)
    about_feature_knowledge_title = serializers.CharField(max_length=240)
    about_feature_knowledge_body = serializers.CharField(max_length=1500)
    about_ingestion_title = serializers.CharField(max_length=240)
    about_ingestion_body = serializers.CharField(max_length=5000)
    about_access_title = serializers.CharField(max_length=240)
    about_access_body = serializers.CharField(max_length=3000)
    about_rights_title = serializers.CharField(max_length=240)
    about_rights_body = serializers.CharField(max_length=3000)
    about_privacy_title = serializers.CharField(max_length=240)
    about_privacy_body = serializers.CharField(max_length=3000)
    about_warning_title = serializers.CharField(max_length=240)
    about_warning_body = serializers.CharField(max_length=3000)
    copyright_text = serializers.CharField(max_length=240)
    navigation = serializers.DictField(child=serializers.CharField(max_length=80))
    sections = serializers.DictField(child=serializers.CharField(max_length=120))


class ReaderSubmissionSettingsSerializer(serializers.Serializer):
    email = serializers.EmailField()


class AdminTheorySchoolSerializer(serializers.ModelSerializer):
    work_count = serializers.SerializerMethodField()
    suggestions = serializers.SerializerMethodField()
    slug = serializers.SlugField(required=False, allow_blank=True)
    normalized_relations = serializers.SerializerMethodField()

    class Meta:
        model = TheorySchool
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "symbol",
            "foreign_name",
            "entity_level",
            "formation_period",
            "core_questions",
            "key_themes",
            "hero_image",
            "curation_level",
            "curation",
            "normalized_relations",
            "suggestions",
            "editorial_status",
            "work_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "work_count", "suggestions", "created_at", "updated_at")

    def get_normalized_relations(self, obj):
        return {
            "disciplines": [
                {
                    "id": str(relation.id),
                    "discipline_id": str(relation.discipline_id),
                    "name": relation.discipline.name,
                    "role": relation.role,
                    "review_status": relation.review_status,
                    "confidence": relation.confidence,
                }
                for relation in obj.discipline_relations.select_related("discipline")
            ],
            "subdisciplines": [
                {
                    "id": str(relation.id),
                    "subdiscipline_id": str(relation.subdiscipline_id),
                    "name": relation.subdiscipline.name,
                    "role": relation.role,
                    "review_status": relation.review_status,
                    "confidence": relation.confidence,
                }
                for relation in obj.subdiscipline_relations.select_related("subdiscipline")
            ],
            "parents": [
                {
                    "id": str(relation.id),
                    "theory_id": str(relation.parent_id),
                    "name": relation.parent.name,
                    "review_status": relation.review_status,
                    "evidence_text": relation.evidence_text,
                }
                for relation in obj.parent_relations.select_related("parent")
            ],
            "branches": [
                {
                    "id": str(relation.id),
                    "theory_id": str(relation.child_id),
                    "name": relation.child.name,
                    "review_status": relation.review_status,
                    "evidence_text": relation.evidence_text,
                }
                for relation in obj.child_relations.select_related("child")
            ],
            "timeline": AdminTheoryTimelineEventSerializer(
                obj.timeline_events.all(),
                many=True,
                context=self.context,
            ).data,
        }

    def get_work_count(self, obj):
        return obj.workknowledgerelation_set.filter(approved=True).values("work_id").distinct().count()

    def get_suggestions(self, obj):
        relations = WorkKnowledgeRelation.objects.filter(
            theory_school=obj,
        )
        works = Work.objects.filter(knowledge_relations__theory_school=obj)
        scholars = ScholarProfile.objects.filter(
            person__contributions__edition__work__in=works,
        )
        neighbors = TheorySchool.objects.filter(
            workknowledgerelation__work__in=works,
        ).exclude(pk=obj.pk)
        return {
            "works": _relation_work_rows(relations, "流派关系"),
            "scholars": _scholar_rows(scholars),
            "neighbors": _knowledge_rows(neighbors),
            "concepts": _concept_rows(works, obj.key_themes),
        }

    def validate_curation(self, value):
        value = value if isinstance(value, dict) else {}
        _validate_reference_list(value, "foundational_work_ids", Work.objects.all(), "奠基文献")
        _validate_reference_list(value, "curated_reading_work_ids", Work.objects.all(), "策展书目")
        _validate_reference_list(value, "key_scholar_ids", ScholarProfile.objects.all(), "代表学者")
        _validate_reference_list(value, "neighbor_school_ids", TheorySchool.objects.all(), "相邻流派")
        _structured_entries(value, "core_concepts")
        _structured_entries(value, "conceptual_map")
        relations = _structured_entries(value, "neighbor_relations")
        for entry in relations:
            if not isinstance(entry, dict):
                raise serializers.ValidationError({"neighbor_relations": ["相邻流派关系格式无效。"]})
            school_id = entry.get("school_id")
            if school_id and not TheorySchool.objects.filter(pk=school_id).exists():
                raise serializers.ValidationError({"neighbor_relations": ["相邻流派关系包含不存在的流派。"]})
        return value

    def create(self, validated_data):
        validated_data["slug"] = validated_data.get("slug") or _available_slug(
            TheorySchool,
            validated_data["name"],
        )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data["slug"] = _available_slug(
                TheorySchool,
                validated_data.get("name", instance.name),
                instance,
            )
        return super().update(instance, validated_data)


class AdminTopicSerializer(serializers.ModelSerializer):
    work_count = serializers.SerializerMethodField()
    suggestions = serializers.SerializerMethodField()
    slug = serializers.SlugField(required=False, allow_blank=True)
    normalized_relations = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "problem_statement",
            "core_questions",
            "research_dimensions",
            "methods",
            "formation_context",
            "key_concepts",
            "timeline",
            "hero_image",
            "curation_level",
            "curation",
            "normalized_relations",
            "suggestions",
            "editorial_status",
            "work_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "work_count", "suggestions", "created_at", "updated_at")

    def get_normalized_relations(self, obj):
        return {
            "disciplines": [
                {
                    "id": str(relation.id),
                    "discipline_id": str(relation.discipline_id),
                    "name": relation.discipline.name,
                    "is_primary": relation.is_primary,
                    "review_status": relation.review_status,
                }
                for relation in obj.discipline_relations.select_related("discipline")
            ],
            "theories": [
                {
                    "id": str(relation.id),
                    "theory_id": str(relation.theory_school_id),
                    "name": relation.theory_school.name,
                    "relation_label": relation.relation_label,
                    "review_status": relation.review_status,
                }
                for relation in obj.theory_relations.select_related("theory_school")
            ],
            "subdisciplines": [
                {
                    "id": str(relation.id),
                    "subdiscipline_id": str(relation.subdiscipline_id),
                    "name": relation.subdiscipline.name,
                    "relation_label": relation.relation_label,
                    "review_status": relation.review_status,
                }
                for relation in obj.subdiscipline_relations.select_related("subdiscipline")
            ],
        }

    def get_work_count(self, obj):
        return obj.workknowledgerelation_set.filter(approved=True).values("work_id").distinct().count()

    def get_suggestions(self, obj):
        relations = WorkKnowledgeRelation.objects.filter(
            topic=obj,
        )
        works = Work.objects.filter(knowledge_relations__topic=obj)
        scholars = ScholarProfile.objects.filter(
            person__contributions__edition__work__in=works,
        )
        theories = TheorySchool.objects.filter(
            workknowledgerelation__work__in=works,
        )
        return {
            "works": _relation_work_rows(relations, "主题关系"),
            "scholars": _scholar_rows(scholars),
            "theories": _knowledge_rows(theories),
            "passages": _ranked_passage_rows(
                works,
                [obj.name, *obj.key_concepts],
            ),
        }

    def validate_curation(self, value):
        value = value if isinstance(value, dict) else {}
        _validate_reference_list(value, "foundational_work_ids", Work.objects.all(), "奠基文献")
        _validate_reference_list(value, "recent_work_ids", Work.objects.all(), "最近入库文献")
        _validate_reference_list(value, "related_scholar_ids", ScholarProfile.objects.all(), "相关学者")
        _validate_reference_list(value, "linked_theory_ids", TheorySchool.objects.all(), "关联流派")
        featured_passage_id = value.get("featured_passage_id")
        if featured_passage_id and not Passage.objects.filter(pk=featured_passage_id).exists():
            raise serializers.ValidationError({"featured_passage_id": ["摘录候选不存在。"]})
        paths = value.get("reading_paths", [])
        if not isinstance(paths, list):
            raise serializers.ValidationError({"reading_paths": ["阅读路径必须是列表。"]})
        for path in paths:
            if not isinstance(path, dict):
                raise serializers.ValidationError({"reading_paths": ["阅读路径格式无效。"]})
            _validate_reference_list(path, "work_ids", Work.objects.all(), "阅读路径文献")
        return value

    def create(self, validated_data):
        validated_data["slug"] = validated_data.get("slug") or _available_slug(
            Topic,
            validated_data["name"],
        )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data["slug"] = _available_slug(
                Topic,
                validated_data.get("name", instance.name),
                instance,
            )
        return super().update(instance, validated_data)


class AdminScholarSerializer(serializers.ModelSerializer):
    person_id = serializers.UUIDField(source="person.id", read_only=True)
    preferred_name = serializers.CharField(source="person.preferred_name", max_length=240)
    original_name = serializers.CharField(source="person.original_name", max_length=240, required=False, allow_blank=True)
    aliases = serializers.ListField(source="person.aliases", child=serializers.CharField(max_length=240), required=False)
    birth_year = serializers.IntegerField(source="person.birth_year", min_value=1000, max_value=2100, required=False, allow_null=True)
    death_year = serializers.IntegerField(source="person.death_year", min_value=1000, max_value=2100, required=False, allow_null=True)
    biography = serializers.CharField(source="person.biography", required=False, allow_blank=True)
    portrait = serializers.ImageField(source="person.portrait", required=False, allow_null=True)
    slug = serializers.SlugField(required=False, allow_blank=True)
    suggestions = serializers.SerializerMethodField()

    class Meta:
        model = ScholarProfile
        fields = (
            "id",
            "person_id",
            "slug",
            "preferred_name",
            "original_name",
            "aliases",
            "birth_year",
            "death_year",
            "biography",
            "portrait",
            "short_description",
            "affiliations",
            "key_concerns",
            "timeline",
            "featured_quote",
            "quote_source",
            "curation",
            "suggestions",
            "editorial_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "suggestions", "created_at", "updated_at")

    def get_suggestions(self, obj):
        works = Work.objects.filter(
            editions__contributions__person=obj.person,
        )
        theories = TheorySchool.objects.filter(
            workknowledgerelation__work__in=works,
            workknowledgerelation__approved=True,
        )
        topics = Topic.objects.filter(
            workknowledgerelation__work__in=works,
            workknowledgerelation__approved=True,
        )
        related = ScholarProfile.objects.filter(
            person__contributions__edition__work__knowledge_relations__in=(
                WorkKnowledgeRelation.objects.filter(work__in=works, approved=True)
            ),
        ).exclude(pk=obj.pk)
        return {
            "works": _work_rows(
                works,
                reason="该学者作为作者、编者、译者或研究对象出现在馆藏元数据中",
                source_label="PDF 作者贡献识别",
            ),
            "theories": _knowledge_rows(theories),
            "topics": _knowledge_rows(topics),
            "related_scholars": _scholar_rows(related),
            "concepts": _concept_rows(works, obj.key_concerns),
        }

    def validate_curation(self, value):
        value = value if isinstance(value, dict) else {}
        _validate_reference_list(value, "essential_work_ids", Work.objects.all(), "重要文献")
        _validate_reference_list(
            value,
            "frequently_read_scholar_ids",
            ScholarProfile.objects.all(),
            "经常连着阅读的学者",
        )
        _validate_reference_list(
            value,
            "related_theory_ids",
            TheorySchool.objects.all(),
            "相关理论流派",
        )
        network = value.get("network", [])
        if not isinstance(network, list):
            raise serializers.ValidationError({"network": ["学术关系必须是列表。"]})
        for entry in network:
            if not isinstance(entry, dict):
                raise serializers.ValidationError({"network": ["学术关系格式无效。"]})
            scholar_id = entry.get("scholar_id")
            if scholar_id and not ScholarProfile.objects.filter(pk=scholar_id).exists():
                raise serializers.ValidationError({"network": ["学术关系包含不存在的学者。"]})
        _structured_entries(value, "key_concepts")
        _structured_entries(value, "concept_map")
        return value

    @transaction.atomic
    def create(self, validated_data):
        person_data = validated_data.pop("person")
        preferred_name = person_data["preferred_name"]
        person = Person.objects.create(
            sort_name=preferred_name,
            **person_data,
        )
        validated_data["slug"] = validated_data.get("slug") or _available_slug(
            ScholarProfile,
            preferred_name,
        )
        return ScholarProfile.objects.create(person=person, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        person_data = validated_data.pop("person", {})
        for field_name, value in person_data.items():
            setattr(instance.person, field_name, value)
        if "preferred_name" in person_data and not instance.person.sort_name:
            instance.person.sort_name = person_data["preferred_name"]
        if person_data:
            instance.person.save()
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data["slug"] = _available_slug(
                ScholarProfile,
                person_data.get("preferred_name", instance.person.preferred_name),
                instance,
            )
        return super().update(instance, validated_data)
