import hashlib
import json
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def create_initial_query_lexicon_state(apps, schema_editor):
    Generation = apps.get_model("catalog", "QueryLexiconGeneration")
    State = apps.get_model("catalog", "QueryLexiconState")
    now = timezone.now()
    empty_payload = json.dumps(
        {
            "normalization_version": "query-lexicon-normalize-v1",
            "source_registry_version": "query-lexicon-registry-v1",
            "entries": [],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    empty_hash = hashlib.sha256(empty_payload.encode("utf-8")).hexdigest()
    generation = Generation.objects.create(
        status="active",
        normalization_version="query-lexicon-normalize-v1",
        source_registry_version="query-lexicon-registry-v1",
        effective_content_hash=empty_hash,
        entry_count=0,
        built_at=now,
        activated_at=now,
    )
    State.objects.create(
        key="default",
        revision=0,
        active_generation=generation,
        normalization_version="query-lexicon-normalize-v1",
        source_registry_version="query-lexicon-registry-v1",
        last_reconciled_content_hash=empty_hash,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0026_semantic_feedback_deduplication"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonNameVariant",
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
                ("name", models.CharField(max_length=240)),
                ("normalized_name", models.CharField(db_index=True, max_length=500)),
                ("language", models.CharField(default="und", max_length=24)),
                (
                    "variant_type",
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
                        choices=[
                            ("editorial", "编辑确认"),
                            ("authority_import", "权威库导入"),
                            ("legacy_review", "历史名称复核"),
                            ("other", "其他已记录来源"),
                        ],
                        default="editorial",
                        max_length=32,
                    ),
                ),
                ("source_note", models.TextField(blank=True)),
                ("displayable", models.BooleanField(default=False)),
                ("is_verified", models.BooleanField(db_index=True, default=False)),
            ],
            options={"ordering": ["person__preferred_name", "name"]},
        ),
        migrations.CreateModel(
            name="QueryLexiconChangeEvent",
            fields=[
                ("event_seq", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("person", "人物"),
                            ("knowledge_node", "知识节点"),
                            ("discipline", "学科"),
                            ("theory_school", "理论流派"),
                            ("topic", "主题"),
                            ("concept", "概念"),
                            ("subdiscipline", "子学科"),
                        ],
                        max_length=32,
                    ),
                ),
                ("entity_id", models.UUIDField()),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "创建"),
                            ("update", "更新"),
                            ("delete", "删除"),
                        ],
                        max_length=16,
                    ),
                ),
                ("source_model", models.CharField(max_length=120)),
                ("source_object_id", models.UUIDField()),
                ("correlation_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("applied_revision", models.PositiveBigIntegerField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.UUIDField(blank=True, db_index=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=120)),
                ("last_error_message", models.TextField(blank=True)),
                ("dead_lettered_at", models.DateTimeField(blank=True, db_index=True, null=True)),
            ],
            options={"ordering": ["event_seq"]},
        ),
        migrations.CreateModel(
            name="QueryLexiconEntry",
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
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("person", "人物"),
                            ("knowledge_node", "知识节点"),
                            ("discipline", "学科"),
                            ("theory_school", "理论流派"),
                            ("topic", "主题"),
                            ("concept", "概念"),
                            ("subdiscipline", "子学科"),
                        ],
                        max_length=32,
                    ),
                ),
                ("entity_id", models.UUIDField()),
                ("term", models.CharField(max_length=500)),
                ("normalized_term", models.CharField(max_length=500)),
                ("language", models.CharField(default="und", max_length=24)),
                (
                    "term_type",
                    models.CharField(
                        choices=[
                            ("canonical", "规范名称"),
                            ("translation", "译名"),
                            ("alias", "别名"),
                            ("abbreviation", "简称"),
                            ("historical", "历史名称"),
                            ("transliteration", "音译"),
                            ("search_variant", "检索变体"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("authority_field", "权威字段"),
                            ("person_name_variant", "结构化人物名称"),
                            ("knowledge_node_alias", "结构化知识别名"),
                            ("legacy_authority_field", "旧权威字段"),
                            ("legacy_mixed_alias", "历史混合别名"),
                            ("generated_search_variant", "机器检索变体"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "trust_level",
                    models.CharField(
                        choices=[
                            ("authoritative", "权威规范"),
                            ("verified", "人工或权威来源确认"),
                            ("unverified", "结构化但未确认"),
                            ("legacy", "历史来源不明"),
                            ("generated", "机器派生"),
                        ],
                        max_length=24,
                    ),
                ),
                ("source_ref", models.CharField(max_length=320)),
                ("source_fingerprint", models.CharField(max_length=64)),
                ("provenance", models.JSONField(blank=True, default=dict)),
                ("displayable", models.BooleanField(default=False)),
                ("public_active", models.BooleanField(default=False)),
                ("admin_resolvable", models.BooleanField(default=False)),
            ],
            options={"ordering": ["entity_type", "entity_id", "normalized_term"]},
        ),
        migrations.CreateModel(
            name="QueryLexiconGeneration",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("staging", "构建中"),
                            ("active", "活动"),
                            ("retired", "已退役"),
                            ("failed", "构建失败"),
                            ("discarded", "内容未变化"),
                        ],
                        db_index=True,
                        default="staging",
                        max_length=20,
                    ),
                ),
                ("start_event_seq", models.PositiveBigIntegerField(default=0)),
                ("cutover_event_seq", models.PositiveBigIntegerField(default=0)),
                ("normalization_version", models.CharField(max_length=80)),
                ("source_registry_version", models.CharField(max_length=80)),
                ("effective_content_hash", models.CharField(blank=True, max_length=64)),
                ("entry_count", models.PositiveBigIntegerField(default=0)),
                ("build_stats", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("built_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="QueryLexiconState",
            fields=[
                (
                    "key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=32,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("revision", models.PositiveBigIntegerField(default=0)),
                ("normalization_version", models.CharField(max_length=80)),
                ("source_registry_version", models.CharField(max_length=80)),
                ("last_successful_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_reconciled_at", models.DateTimeField(blank=True, null=True)),
                ("last_reconciled_content_hash", models.CharField(blank=True, max_length=64)),
                ("last_reconciled_revision", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="person",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="merged_people",
                to="catalog.person",
            ),
        ),
        migrations.AddConstraint(
            model_name="person",
            constraint=models.CheckConstraint(
                condition=~models.Q(id=models.F("merged_into_id")),
                name="person_merge_target_not_self",
            ),
        ),
        migrations.AddField(
            model_name="personnamevariant",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_person_name_variants",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="personnamevariant",
            name="person",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="name_variants",
                to="catalog.person",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconchangeevent",
            index=models.Index(
                condition=models.Q(
                    dead_lettered_at__isnull=True,
                    processed_at__isnull=True,
                ),
                fields=["next_attempt_at", "event_seq"],
                name="ql_event_pending_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconchangeevent",
            index=models.Index(
                fields=["entity_type", "entity_id", "event_seq"],
                name="ql_event_entity_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexicongeneration",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="active"),
                fields=("status",),
                name="single_active_query_lexicon_generation",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconentry",
            name="generation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="entries",
                to="catalog.querylexicongeneration",
            ),
        ),
        migrations.AddField(
            model_name="querylexiconstate",
            name="active_generation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="active_states",
                to="catalog.querylexicongeneration",
            ),
        ),
        migrations.AddConstraint(
            model_name="personnamevariant",
            constraint=models.UniqueConstraint(
                fields=("person", "normalized_name"),
                name="unique_person_name_variant",
            ),
        ),
        migrations.AddConstraint(
            model_name="personnamevariant",
            constraint=models.CheckConstraint(
                condition=models.Q(displayable=False) | models.Q(is_verified=True),
                name="displayable_person_variant_verified",
            ),
        ),
        migrations.AddConstraint(
            model_name="personnamevariant",
            constraint=models.CheckConstraint(
                condition=~models.Q(name="") & ~models.Q(normalized_name=""),
                name="person_variant_name_not_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="personnamevariant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    variant_type__in=[
                        "translation",
                        "alias",
                        "abbreviation",
                        "historical",
                        "transliteration",
                    ]
                ),
                name="person_variant_type_allowed",
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
                        "other",
                    ]
                ),
                name="person_variant_source_allowed",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconentry",
            index=models.Index(
                fields=["generation", "public_active", "normalized_term"],
                name="ql_public_term_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconentry",
            index=models.Index(
                fields=["generation", "admin_resolvable", "normalized_term"],
                name="ql_admin_term_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="querylexiconentry",
            index=models.Index(
                fields=["generation", "entity_type", "entity_id"],
                name="ql_entity_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconentry",
            constraint=models.UniqueConstraint(
                fields=("generation", "entity_type", "entity_id", "normalized_term"),
                name="unique_query_lexicon_entity_term",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(term="") & ~models.Q(normalized_term=""),
                name="query_lexicon_term_not_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconentry",
            constraint=models.CheckConstraint(
                condition=models.Q(public_active=False)
                | models.Q(admin_resolvable=True),
                name="public_query_term_admin_resolvable",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconentry",
            constraint=models.CheckConstraint(
                condition=models.Q(displayable=False)
                | ~models.Q(
                    source_kind__in=[
                        "legacy_mixed_alias",
                        "generated_search_variant",
                    ]
                ),
                name="untrusted_query_term_not_displayable",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(source_kind="generated_search_variant")
                | models.Q(term_type="search_variant", displayable=False),
                name="generated_query_term_is_search_variant",
            ),
        ),
        migrations.AddConstraint(
            model_name="querylexiconstate",
            constraint=models.CheckConstraint(
                condition=models.Q(key="default"),
                name="query_lexicon_state_default_key",
            ),
        ),
        migrations.RunPython(create_initial_query_lexicon_state, migrations.RunPython.noop),
    ]
