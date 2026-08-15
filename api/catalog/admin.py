from django.contrib import admin

from .models import (
    Asset,
    Concept,
    Contribution,
    Edition,
    FeaturedSlot,
    KnowledgeNode,
    OrganizationAuthority,
    OrganizationContribution,
    Page,
    Passage,
    Person,
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


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "kind", "status", "access_status", "page_count", "updated_at")
    list_filter = ("kind", "status", "access_status", "validation_status")
    search_fields = ("original_filename", "file", "sha256", "edition__work__title")
    readonly_fields = ("sha256", "byte_size", "page_count")


@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(admin.ModelAdmin):
    list_display = ("canonical_name_zh", "node_type", "parent", "status", "updated_at")
    list_filter = ("node_type", "status")
    search_fields = ("canonical_name_zh", "canonical_name_en", "aliases__alias")


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
