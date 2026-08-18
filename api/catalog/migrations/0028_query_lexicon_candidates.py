import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0027_query_lexicon_core"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QueryLexiconCandidate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "candidate_type",
                    models.CharField(
                        choices=[
                            ("person_name_variant", "人物名称变体"),
                            ("knowledge_node_alias", "知识节点别名"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "target_entity_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("person", "人物"),
                            ("knowledge_node", "知识节点"),
                        ],
                        max_length=32,
                    ),
                ),
                ("target_entity_id", models.UUIDField(blank=True, null=True)),
                ("anchor_term", models.CharField(max_length=500)),
                (
                    "normalized_anchor_term",
                    models.CharField(db_index=True, max_length=500),
                ),
                ("proposed_term", models.CharField(max_length=500)),
                (
                    "normalized_term",
                    models.CharField(db_index=True, max_length=500),
                ),
                ("language", models.CharField(default="und", max_length=24)),
                (
                    "proposed_term_type",
                    models.CharField(
                        choices=[
                            ("translation", "译名"),
                            ("alias", "别名"),
                            ("abbreviation", "简称"),
                            ("historical", "历史名称"),
                            ("transliteration", "音译"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[("pdf", "馆藏 PDF")],
                        default="pdf",
                        max_length=24,
                    ),
                ),
                (
                    "confidence",
                    models.FloatField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ],
                    ),
                ),
                ("confidence_factors", models.JSONField(blank=True, default=dict)),
                (
                    "linking_status",
                    models.CharField(
                        choices=[
                            ("linked", "已唯一关联"),
                            ("ambiguous", "存在歧义"),
                            ("unresolved", "未解析"),
                        ],
                        db_index=True,
                        default="linked",
                        max_length=20,
                    ),
                ),
                ("possible_targets", models.JSONField(blank=True, default=list)),
                ("ambiguity", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待审核"),
                            ("accepted", "已接受"),
                            ("rejected", "已拒绝"),
                            ("superseded", "证据已过期"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("displayable", models.BooleanField(default=False)),
                ("extraction_version", models.CharField(max_length=80)),
                (
                    "fingerprint",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_reason", models.TextField(blank=True)),
                (
                    "accepted_authority_model",
                    models.CharField(blank=True, max_length=120),
                ),
                (
                    "accepted_authority_id",
                    models.UUIDField(blank=True, null=True),
                ),
            ],
            options={"ordering": ["-confidence", "created_at"]},
        ),
        migrations.CreateModel(
            name="QueryLexiconCandidateEvidence",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document_id",
                    models.CharField(blank=True, db_index=True, max_length=64),
                ),
                ("page_number", models.PositiveIntegerField(blank=True, null=True)),
                ("printed_page_label", models.CharField(blank=True, max_length=40)),
                ("bbox", models.JSONField(blank=True, default=list)),
                ("evidence_text", models.TextField()),
                ("start_offset", models.PositiveIntegerField(default=0)),
                ("end_offset", models.PositiveIntegerField(default=0)),
                ("left_term", models.CharField(max_length=500)),
                ("right_term", models.CharField(max_length=500)),
                ("detected_pair", models.JSONField(blank=True, default=dict)),
                ("extraction_method", models.CharField(max_length=80)),
                (
                    "confidence",
                    models.FloatField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ],
                    ),
                ),
                ("confidence_factors", models.JSONField(blank=True, default=dict)),
                (
                    "ocr_quality",
                    models.FloatField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ],
                    ),
                ),
                ("quality_flags", models.JSONField(blank=True, default=list)),
                ("source_text_checksum", models.CharField(max_length=64)),
                ("extraction_version", models.CharField(max_length=80)),
                ("fingerprint", models.CharField(editable=False, max_length=64)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("superseded_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["work__title", "page_number", "created_at"]},
        ),
        migrations.RemoveConstraint(
            model_name="personnamevariant",
            name="person_variant_source_allowed",
        ),
        migrations.AlterField(
            model_name="knowledgenodealias",
            name="alias_type",
            field=models.CharField(
                choices=[
                    ("alias", "别名"),
                    ("translation", "译名"),
                    ("abbreviation", "简称"),
                    ("historical", "历史名称"),
                    ("transliteration", "音译"),
                ],
                default="alias",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="personnamevariant",
            name="source_kind",
            field=models.CharField(
                choices=[
                    ("editorial", "编辑确认"),
                    ("authority_import", "权威库导入"),
                    ("legacy_review", "历史名称复核"),
                    ("pdf_evidence", "馆藏 PDF 证据"),
                    ("other", "其他已记录来源"),
                ],
                default="editorial",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="personnamevariant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    source_kind__in=[
                        "editorial",
                        "authority_import",
                        "legacy_review",
                        "pdf_evidence",
                        "other",
                    ]
                ),
                name="person_variant_source_allowed",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidate",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_query_lexicon_candidates",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="query_lexicon_candidate_evidence",
                to="catalog.asset",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="candidate",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="evidence_records",
                to="catalog.querylexiconcandidate",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="edition",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="query_lexicon_candidate_evidence",
                to="catalog.edition",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="page",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="query_lexicon_candidate_evidence",
                to="catalog.page",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="semantic_chunk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="query_lexicon_candidate_evidence",
                to="catalog.semanticchunk",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconcandidateevidence",
            name="work",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="query_lexicon_candidate_evidence",
                to="catalog.work",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidate",
            index=models.Index(
                fields=["status", "linking_status", "-confidence"],
                name="ql_candidate_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidate",
            index=models.Index(
                fields=["target_entity_type", "target_entity_id"],
                name="ql_candidate_target_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidate",
            index=models.Index(
                fields=["normalized_term", "language"],
                name="ql_candidate_term_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidate",
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(anchor_term="")
                    & ~models.Q(normalized_anchor_term="")
                    & ~models.Q(proposed_term="")
                    & ~models.Q(normalized_term="")
                ),
                name="ql_candidate_terms_not_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidate",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        linking_status="linked",
                        target_entity_type__in=["person", "knowledge_node"],
                        target_entity_id__isnull=False,
                    )
                    | models.Q(
                        linking_status="ambiguous",
                        target_entity_type__in=["person", "knowledge_node"],
                        target_entity_id__isnull=True,
                    )
                    | models.Q(
                        linking_status="unresolved",
                        target_entity_type="",
                        target_entity_id__isnull=True,
                    )
                ),
                name="ql_candidate_link_target_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidate",
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status="accepted")
                    | models.Q(
                        linking_status="linked",
                        target_entity_id__isnull=False,
                    )
                ),
                name="ql_candidate_accept_requires_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidate",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    proposed_term_type__in=[
                        "translation",
                        "alias",
                        "abbreviation",
                        "historical",
                        "transliteration",
                    ]
                ),
                name="ql_candidate_term_type_allowed",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidate",
            constraint=models.CheckConstraint(
                condition=models.Q(source_kind="pdf"),
                name="ql_candidate_source_is_pdf",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidateevidence",
            index=models.Index(
                fields=["candidate", "is_current"],
                name="ql_evidence_current_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidateevidence",
            index=models.Index(
                fields=["asset", "page_number"],
                name="ql_evidence_asset_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconcandidateevidence",
            index=models.Index(
                fields=["work", "is_current"],
                name="ql_evidence_work_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidateevidence",
            constraint=models.UniqueConstraint(
                fields=("candidate", "fingerprint"),
                name="unique_ql_candidate_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidateevidence",
            constraint=models.CheckConstraint(
                condition=models.Q(end_offset__gte=models.F("start_offset")),
                name="ql_evidence_offsets_ordered",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconcandidateevidence",
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(evidence_text="")
                    & ~models.Q(source_text_checksum="")
                ),
                name="ql_evidence_source_not_empty",
            ),
        ),
    ]
