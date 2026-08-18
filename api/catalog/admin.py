from django import forms
from django.contrib import admin, messages
from django.db.models import Count

from .models import (
    Asset,
    Concept,
    Contribution,
    Edition,
    EnrichmentCandidate,
    EnrichmentEvidence,
    FeaturedSlot,
    KnowledgeNode,
    KnowledgeNodeAlias,
    NewAuthorityCandidate,
    UnknownEntityObservation,
    OrganizationAuthority,
    OrganizationContribution,
    Page,
    Passage,
    Person,
    PersonNameVariant,
    PersonKnowledgeRelation,
    PublicationEvent,
    PublicationMetadataRevision,
    PublicationPlaceEvidence,
    PublisherAuthority,
    ScholarProfile,
    SiteSetting,
    SemanticChunk,
    SemanticIndexJob,
    SemanticSearchFeedback,
    QueryLexiconChangeEvent,
    QueryLexiconCandidate,
    QueryLexiconCandidateEvidence,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    TextBlock,
    TheorySchool,
    Topic,
    Work,
    WorkKnowledgeRelation,
)


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 0


class AssetInline(admin.TabularInline):
    model = Asset
    extra = 0
    readonly_fields = ("sha256", "byte_size", "page_count")


class PersonNameVariantInline(admin.TabularInline):
    model = PersonNameVariant
    extra = 0
    readonly_fields = ("normalized_name", "created_at", "updated_at")


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ("title", "original_title", "document_type", "language", "is_featured", "updated_at")
    list_filter = ("document_type", "language", "is_featured")
    search_fields = ("title", "subtitle", "original_title", "uniform_title", "abstract")


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ("work", "publication_year", "state", "metadata_confidence", "published_at")
    list_filter = ("state", "work__document_type", "publication_year")
    search_fields = (
        "work__title",
        "isbn",
        "isbn10",
        "isbn13",
        "doi",
        "publisher",
        "publisher_authority__canonical_name",
        "journal_title",
    )
    inlines = (ContributionInline, AssetInline)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("preferred_name", "authority_status", "birth_year", "death_year")
    list_filter = ("authority_status",)
    search_fields = ("preferred_name", "original_name", "aliases")
    inlines = (PersonNameVariantInline,)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, PersonNameVariant) and not instance.created_by_id:
                instance.created_by = request.user
            instance.save()
        for instance in formset.deleted_objects:
            instance.delete()
        formset.save_m2m()


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "kind", "status", "access_status", "page_count", "updated_at")
    list_filter = ("kind", "status", "access_status", "validation_status")
    search_fields = ("original_filename", "file", "sha256", "edition__work__title")
    readonly_fields = ("sha256", "byte_size", "page_count")
    actions = ("discover_query_lexicon_candidates",)

    @admin.action(description="从所选 PDF 发现 QueryLexicon 候选")
    def discover_query_lexicon_candidates(self, request, queryset):
        from ingestion.services.processing import queue_query_lexicon_candidate_job

        queued = 0
        skipped = 0
        failures = []
        for asset in queryset.select_related("edition"):
            if asset.kind != Asset.Kind.NORMALIZED or asset.status != Asset.Status.READY:
                skipped += 1
                continue
            try:
                queue_query_lexicon_candidate_job(
                    asset,
                    actor=request.user,
                    force=True,
                )
                queued += 1
            except Exception as exc:
                failures.append(f"{asset.id}: {str(exc)[:180]}")
        if queued:
            self.message_user(request, f"已排队 {queued} 个术语候选提取任务。")
        if skipped:
            self.message_user(
                request,
                f"已跳过 {skipped} 个非当前就绪规范 PDF。",
                level=messages.WARNING,
            )
        if failures:
            self.message_user(
                request,
                "；".join(failures[:5]),
                level=messages.ERROR,
            )


@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(admin.ModelAdmin):
    list_display = ("canonical_name_zh", "node_type", "parent", "status", "updated_at")
    list_filter = ("node_type", "status")
    search_fields = ("canonical_name_zh", "canonical_name_en", "aliases__alias")


@admin.register(KnowledgeNodeAlias)
class KnowledgeNodeAliasAdmin(admin.ModelAdmin):
    """Aliases are authority input; evidence is visible but the derived entry is read-only."""

    list_display = ("alias", "node", "language", "alias_type", "source_kind", "is_verified")
    list_filter = ("alias_type", "source_kind", "is_verified")
    search_fields = ("alias", "normalized_alias", "node__canonical_name_zh", "node__canonical_name_en")


class DerivedQueryLexiconAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(QueryLexiconGeneration)
class QueryLexiconGenerationAdmin(DerivedQueryLexiconAdmin):
    list_display = ("id", "status", "entry_count", "cutover_event_seq", "created_at")
    list_filter = ("status", "normalization_version", "source_registry_version")


@admin.register(QueryLexiconState)
class QueryLexiconStateAdmin(DerivedQueryLexiconAdmin):
    list_display = ("key", "revision", "active_generation", "updated_at")


@admin.register(QueryLexiconEntry)
class QueryLexiconEntryAdmin(DerivedQueryLexiconAdmin):
    list_display = (
        "term",
        "entity_type",
        "term_type",
        "trust_level",
        "public_active",
        "admin_resolvable",
    )
    list_filter = (
        "entity_type",
        "term_type",
        "source_kind",
        "trust_level",
        "public_active",
        "admin_resolvable",
    )
    search_fields = ("term", "normalized_term", "entity_id")


@admin.register(QueryLexiconChangeEvent)
class QueryLexiconChangeEventAdmin(DerivedQueryLexiconAdmin):
    list_display = (
        "event_seq",
        "entity_type",
        "entity_id",
        "action",
        "processed_at",
        "attempts",
    )
    list_filter = ("entity_type", "action", "processed_at", "dead_lettered_at")


class QueryLexiconCandidateAdminForm(forms.ModelForm):
    class Meta:
        model = QueryLexiconCandidate
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        linking_status = cleaned.get("linking_status")
        entity_type = (
            cleaned.get("target_entity_type")
            or self.instance.target_entity_type
        )
        entity_id = cleaned.get("target_entity_id")
        if linking_status == QueryLexiconCandidate.LinkingStatus.LINKED:
            if not entity_type or not entity_id:
                raise forms.ValidationError("已关联候选必须选择 canonical entity。")
        elif linking_status == QueryLexiconCandidate.LinkingStatus.AMBIGUOUS:
            if not entity_type or entity_id:
                raise forms.ValidationError("歧义候选保留 entity type，但不能预选 target ID。")
        elif entity_type or entity_id:
            raise forms.ValidationError("未解析候选不能预先写入 canonical target。")
        return cleaned


class QueryLexiconCandidateEvidenceInline(admin.StackedInline):
    model = QueryLexiconCandidateEvidence
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = tuple(
        field.name for field in QueryLexiconCandidateEvidence._meta.fields
    )

    def has_add_permission(self, request, obj=None):
        return False


class EnrichmentEvidenceInline(admin.StackedInline):
    model = EnrichmentEvidence
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = tuple(field.name for field in EnrichmentEvidence._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EnrichmentCandidate)
class EnrichmentCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "field_name",
        "target_type",
        "target_id",
        "candidate_kind",
        "source_class",
        "identity_status",
        "confidence",
        "status",
        "evidence_count",
    )
    list_filter = (
        "status",
        "candidate_kind",
        "target_type",
        "field_name",
        "source_class",
        "identity_status",
        "requested_mode",
    )
    search_fields = (
        "target_id",
        "field_name",
        "evidence_records__source_title",
        "evidence_records__supporting_text",
        "evidence_records__canonical_url",
    )
    readonly_fields = (
        "target_type",
        "target_id",
        "field_name",
        "candidate_kind",
        "proposed_value",
        "normalized_value",
        "current_value",
        "request_context",
        "source_class",
        "confidence",
        "confidence_factors",
        "conflicts",
        "identity_status",
        "identity_evidence",
        "status",
        "requested_mode",
        "request_id",
        "conflict_group",
        "policy_version",
        "extraction_version",
        "fingerprint",
        "refresh_after",
        "created_by",
        "reviewed_by",
        "reviewed_at",
        "accepted_authority_model",
        "accepted_authority_id",
        "created_at",
        "updated_at",
    )
    inlines = (EnrichmentEvidenceInline,)
    actions = ("accept_candidates", "reject_candidates")

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(self.readonly_fields)
        if obj is not None and obj.status != EnrichmentCandidate.Status.PENDING:
            return tuple(field.name for field in self.model._meta.fields)
        return fields

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_evidence_count=Count("evidence_records", distinct=True))

    @admin.display(ordering="_evidence_count", description="证据")
    def evidence_count(self, obj):
        return getattr(obj, "_evidence_count", 0)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="接受所选字段候选并写入 authority")
    def accept_candidates(self, request, queryset):
        from catalog.services.field_enrichment.mutations import accept_enrichment_candidate

        accepted = 0
        errors = []
        for candidate in queryset.order_by("created_at"):
            try:
                result = accept_enrichment_candidate(
                    candidate,
                    actor=request.user,
                    reason=candidate.review_reason or "Django Admin 接受",
                )
            except ValueError as exc:
                errors.append(f"{candidate.field_name}: {exc}")
                continue
            accepted += int(not result.idempotent)
        self.message_user(request, f"已处理 {accepted} 个字段候选。")
        if errors:
            self.message_user(request, "；".join(errors[:8]), level=messages.ERROR)

    @admin.action(description="拒绝所选字段候选并保留证据")
    def reject_candidates(self, request, queryset):
        from catalog.services.field_enrichment.mutations import reject_enrichment_candidate

        rejected = 0
        errors = []
        for candidate in queryset.order_by("created_at"):
            try:
                _candidate, repeated = reject_enrichment_candidate(
                    candidate,
                    actor=request.user,
                    reason=candidate.review_reason or "Django Admin 拒绝",
                )
            except ValueError as exc:
                errors.append(f"{candidate.field_name}: {exc}")
                continue
            rejected += int(not repeated)
        self.message_user(request, f"已拒绝 {rejected} 个字段候选。")
        if errors:
            self.message_user(request, "；".join(errors[:8]), level=messages.ERROR)


@admin.register(EnrichmentEvidence)
class EnrichmentEvidenceAdmin(admin.ModelAdmin):
    list_display = (
        "candidate",
        "source_title",
        "source_class",
        "provider",
        "retrieved_at",
        "is_current",
    )
    list_filter = ("source_class", "provider", "is_current", "extraction_method")
    search_fields = ("source_title", "supporting_text", "canonical_url", "external_identifier")
    readonly_fields = tuple(field.name for field in EnrichmentEvidence._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UnknownEntityObservationInline(admin.TabularInline):
    model = UnknownEntityObservation
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = tuple(field.name for field in UnknownEntityObservation._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(NewAuthorityCandidate)
class NewAuthorityCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "primary_term",
        "entity_type",
        "confidence",
        "status",
        "evidence_count",
        "independent_work_count",
        "created_at",
    )
    list_filter = ("status", "entity_type")
    search_fields = ("primary_term", "normalized_primary_term", "observations__evidence_text")
    readonly_fields = tuple(field.name for field in NewAuthorityCandidate._meta.fields)
    inlines = (UnknownEntityObservationInline,)
    actions = ("reject_candidates",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _evidence_count=Count("observations", distinct=True),
            _work_count=Count("observations__work", distinct=True),
        )

    @admin.display(ordering="_evidence_count", description="证据")
    def evidence_count(self, obj):
        return getattr(obj, "_evidence_count", 0)

    @admin.display(ordering="_work_count", description="独立作品")
    def independent_work_count(self, obj):
        return getattr(obj, "_work_count", 0)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="拒绝所选未知实体候选并保留证据")
    def reject_candidates(self, request, queryset):
        from catalog.services.knowledge_growth import decide_new_authority_candidate

        changed = 0
        for candidate in queryset.filter(status=NewAuthorityCandidate.Status.PENDING):
            decide_new_authority_candidate(
                candidate,
                action="reject",
                actor=request.user,
                reason="Django Admin 拒绝",
            )
            changed += 1
        self.message_user(request, f"已拒绝 {changed} 个未知实体候选，原始证据仍然保留。")


@admin.register(UnknownEntityObservation)
class UnknownEntityObservationAdmin(admin.ModelAdmin):
    list_display = (
        "candidate",
        "work",
        "page_number",
        "entity_guess",
        "confidence",
        "is_current",
        "created_at",
    )
    list_filter = ("entity_guess", "is_current", "extraction_method")
    search_fields = ("terms", "evidence_text", "work__title", "document_id")
    readonly_fields = tuple(field.name for field in UnknownEntityObservation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QueryLexiconCandidate)
class QueryLexiconCandidateAdmin(admin.ModelAdmin):
    form = QueryLexiconCandidateAdminForm
    list_display = (
        "proposed_term",
        "candidate_type",
        "canonical_target",
        "linking_status",
        "proposed_term_type",
        "language",
        "confidence",
        "status",
        "evidence_count",
        "work_count",
    )
    list_filter = (
        "status",
        "linking_status",
        "candidate_type",
        "proposed_term_type",
        "language",
        "extraction_version",
    )
    search_fields = (
        "proposed_term",
        "normalized_term",
        "anchor_term",
        "target_entity_id",
        "evidence_records__work__title",
        "evidence_records__evidence_text",
    )
    readonly_fields = (
        "candidate_type",
        "target_entity_type",
        "anchor_term",
        "normalized_anchor_term",
        "normalized_term",
        "source_kind",
        "status",
        "confidence",
        "confidence_factors",
        "possible_targets",
        "ambiguity",
        "extraction_version",
        "fingerprint",
        "reviewed_by",
        "reviewed_at",
        "accepted_authority_model",
        "accepted_authority_id",
        "created_at",
        "updated_at",
    )
    inlines = (QueryLexiconCandidateEvidenceInline,)
    actions = ("accept_candidates", "reject_candidates")
    list_select_related = ("reviewed_by",)

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(self.readonly_fields)
        if obj is not None and obj.status != QueryLexiconCandidate.Status.PENDING:
            return tuple(field.name for field in self.model._meta.fields)
        return fields

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _evidence_count=Count("evidence_records", distinct=True),
            _work_count=Count("evidence_records__work", distinct=True),
        )

    @admin.display(ordering="_evidence_count", description="证据")
    def evidence_count(self, obj):
        return getattr(obj, "_evidence_count", 0)

    @admin.display(ordering="_work_count", description="独立作品")
    def work_count(self, obj):
        return getattr(obj, "_work_count", 0)

    @admin.display(description="Canonical target")
    def canonical_target(self, obj):
        for row in obj.possible_targets or []:
            if str(row.get("entity_id") or "") == str(obj.target_entity_id or ""):
                return row.get("canonical_label") or str(obj.target_entity_id)
        if obj.linking_status == QueryLexiconCandidate.LinkingStatus.AMBIGUOUS:
            return f"歧义 · {len(obj.possible_targets or [])} 项"
        return str(obj.target_entity_id or "—")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="接受所选候选并写入 authority")
    def accept_candidates(self, request, queryset):
        from catalog.services.query_lexicon.candidates import (
            accept_query_lexicon_candidate,
        )

        accepted = 0
        idempotent = 0
        errors = []
        for candidate in queryset.order_by("created_at"):
            try:
                result = accept_query_lexicon_candidate(
                    candidate,
                    actor=request.user,
                    reason=candidate.review_reason or "Django Admin 接受",
                )
            except ValueError as exc:
                errors.append(f"{candidate.proposed_term}: {exc}")
                continue
            accepted += int(not result.idempotent)
            idempotent += int(result.idempotent)
        self.message_user(
            request,
            f"已接受 {accepted} 个候选，重复操作 {idempotent} 个。",
        )
        if errors:
            self.message_user(
                request,
                "；".join(errors[:8]),
                level=messages.ERROR,
            )

    @admin.action(description="拒绝所选候选并保留证据")
    def reject_candidates(self, request, queryset):
        from catalog.services.query_lexicon.candidates import (
            reject_query_lexicon_candidate,
        )

        rejected = 0
        idempotent = 0
        errors = []
        for candidate in queryset.order_by("created_at"):
            try:
                _candidate, repeated = reject_query_lexicon_candidate(
                    candidate,
                    actor=request.user,
                    reason=candidate.review_reason or "Django Admin 拒绝",
                )
            except ValueError as exc:
                errors.append(f"{candidate.proposed_term}: {exc}")
                continue
            rejected += int(not repeated)
            idempotent += int(repeated)
        self.message_user(
            request,
            f"已拒绝 {rejected} 个候选，重复操作 {idempotent} 个。",
        )
        if errors:
            self.message_user(
                request,
                "；".join(errors[:8]),
                level=messages.ERROR,
            )


@admin.register(QueryLexiconCandidateEvidence)
class QueryLexiconCandidateEvidenceAdmin(DerivedQueryLexiconAdmin):
    list_display = (
        "candidate",
        "work",
        "page_number",
        "extraction_method",
        "confidence",
        "is_current",
    )
    list_filter = ("is_current", "extraction_method", "extraction_version")
    search_fields = (
        "candidate__proposed_term",
        "work__title",
        "evidence_text",
        "document_id",
    )


@admin.register(ScholarProfile)
class ScholarProfileAdmin(admin.ModelAdmin):
    list_display = ("person", "slug", "editorial_status")
    list_filter = ("editorial_status",)


for model in (
    Page,
    TextBlock,
    Passage,
    Contribution,
    TheorySchool,
    Topic,
    Concept,
    WorkKnowledgeRelation,
    PersonKnowledgeRelation,
    PublicationEvent,
    SiteSetting,
    FeaturedSlot,
    SemanticChunk,
    SemanticIndexJob,
    SemanticSearchFeedback,
    PublisherAuthority,
    OrganizationAuthority,
    OrganizationContribution,
    PublicationPlaceEvidence,
    PublicationMetadataRevision,
):
    admin.site.register(model)
