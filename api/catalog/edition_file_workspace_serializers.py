"""Named, reviewable contracts for edition and file operations."""
from rest_framework import serializers


class FileFormatCapabilityOutput(serializers.Serializer):
    extension = serializers.ChoiceField(choices=["pdf", "docx", "tiff"])
    max_bytes = serializers.IntegerField()
    max_derived_bytes = serializers.IntegerField(allow_null=True)
    available = serializers.BooleanField()
    can_generate_reader = serializers.BooleanField()
    service_verified = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)


class WorkFilePublicPreparationOutput(serializers.Serializer):
    required = serializers.BooleanField()
    status = serializers.CharField()
    can_prepare = serializers.BooleanField()
    prepare_url = serializers.CharField(allow_blank=True)
    detail = serializers.CharField()


class WorkFilePublicPreparationResult(serializers.Serializer):
    request_key = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    status = serializers.CharField()
    detail = serializers.CharField()


class WorkFileOutput(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    filename = serializers.CharField(allow_blank=True)
    mime_type = serializers.CharField(allow_blank=True)
    byte_size = serializers.IntegerField()
    page_count = serializers.IntegerField()
    sha256 = serializers.CharField()
    version = serializers.IntegerField()
    source_asset_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    created_by = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    validation_status = serializers.CharField()
    is_current = serializers.BooleanField()
    is_public_reader = serializers.BooleanField()
    preview_url = serializers.CharField(allow_blank=True)
    download_url = serializers.CharField()
    generate_reader_url = serializers.CharField(allow_blank=True)
    can_adopt = serializers.BooleanField()
    rights_note = serializers.CharField(allow_blank=True)
    public_preparation = WorkFilePublicPreparationOutput()
    access_status = serializers.CharField()


class WorkEditionContributorOutput(serializers.Serializer):
    name = serializers.CharField(allow_blank=True)
    role = serializers.CharField()
    role_label = serializers.CharField()


class WorkEditionOutput(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    version_label = serializers.CharField(allow_blank=True)
    publication_year = serializers.IntegerField(allow_null=True)
    publisher = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)
    is_primary = serializers.BooleanField()
    state = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    contributors = WorkEditionContributorOutput(many=True)
    searchable = serializers.BooleanField()
    original_count = serializers.IntegerField()
    reader_count = serializers.IntegerField()
    current_reader_asset_id = serializers.UUIDField(allow_null=True)


class WorkFileTaskOutput(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    dispatch_status = serializers.CharField()
    progress = serializers.IntegerField()
    is_active = serializers.BooleanField()
    error_message = serializers.CharField(allow_blank=True)
    retry_url = serializers.CharField(allow_blank=True)
    resume_url = serializers.CharField(allow_blank=True)
    processing_href = serializers.CharField()
    source_filename = serializers.CharField(allow_blank=True)
    original_asset_id = serializers.UUIDField(allow_null=True)
    reader_asset_id = serializers.UUIDField(allow_null=True)
    generate_reader = serializers.BooleanField()
    action = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class FileImpactRowOutput(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    asset_id = serializers.UUIDField()
    file_page_index = serializers.IntegerField(allow_null=True, help_text="1-based PDF page index.")
    printed_page_label = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    href = serializers.CharField()


class FileImpactSummaryOutput(serializers.Serializer):
    catalog_evidence = serializers.IntegerField()
    reader_annotations = serializers.IntegerField()
    reader_bookmarks = serializers.IntegerField()
    reader_progress = serializers.IntegerField()


class FilePageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class WorkFilePageOutput(FilePageOutput):
    results = WorkFileOutput(many=True)


class FileImpactOutput(FilePageOutput):
    results = FileImpactRowOutput(many=True)
    summary = FileImpactSummaryOutput()
    notice = serializers.CharField()
    export_url = serializers.CharField(allow_blank=True)


class WorkFilesWorkOutput(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()
    cover_url = serializers.CharField(allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField())
    document_type = serializers.CharField()
    original_publication_year = serializers.IntegerField(allow_null=True)


class WorkFileRightsOutput(serializers.Serializer):
    note = serializers.CharField(allow_blank=True)
    access_status = serializers.CharField(allow_blank=True)
    source_asset_id = serializers.UUIDField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    can_edit = serializers.BooleanField()


class WorkFileRightsUpdateOutput(serializers.Serializer):
    request_key = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    rights_note = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


class WorkFilesEditionOutput(serializers.Serializer):
    id = serializers.UUIDField()
    updated_at = serializers.DateTimeField()
    active_revision_id = serializers.UUIDField(allow_null=True)
    current_reader_asset_id = serializers.UUIDField(allow_null=True)
    public_reader_asset_id = serializers.UUIDField(allow_null=True)
    rights = WorkFileRightsOutput()
    workbench_url = serializers.CharField()


class WorkFilesCapabilitiesOutput(serializers.Serializer):
    formats = FileFormatCapabilityOutput(many=True)
    can_edit = serializers.BooleanField()
    can_publish = serializers.BooleanField()
    max_active_tasks_per_edition = serializers.IntegerField()


class WorkFileHistoryRowOutput(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    activated_at = serializers.DateTimeField(allow_null=True)
    is_current = serializers.BooleanField()
    can_rollback = serializers.BooleanField()


class WorkFileHistoryOutput(FilePageOutput):
    results = WorkFileHistoryRowOutput(many=True)


class WorkFilesStateOutput(serializers.Serializer):
    work = WorkFilesWorkOutput()
    editions = WorkEditionOutput(many=True)
    selected_edition_id = serializers.UUIDField(allow_null=True)
    edition = WorkFilesEditionOutput(allow_null=True)
    files = WorkFilePageOutput()
    current_reader_file = WorkFileOutput(allow_null=True)
    inspected_file = WorkFileOutput(allow_null=True)
    public_reader_file = WorkFileOutput(allow_null=True)
    tasks = WorkFileTaskOutput(many=True)
    task_count = serializers.IntegerField()
    capabilities = WorkFilesCapabilitiesOutput()
    history = WorkFileHistoryOutput()
    impact = FileImpactOutput()


class NewWorkEditionOutput(serializers.Serializer):
    created = serializers.BooleanField()
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    request_key = serializers.UUIDField()
    workbench_url = serializers.CharField()


class FileAdoptionPreviewOutput(serializers.Serializer):
    edition_id = serializers.UUIDField()
    target_asset_id = serializers.UUIDField()
    current_reader_asset_id = serializers.UUIDField(allow_null=True)
    request_key = serializers.UUIDField()
    fingerprint = serializers.CharField()
    can_adopt = serializers.BooleanField()
    already_current = serializers.BooleanField()
    blocking = serializers.ListField(child=serializers.CharField())
    impact = serializers.ListField(child=serializers.CharField())


class FileAdoptionResultOutput(serializers.Serializer):
    request_key = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    target_asset_id = serializers.UUIDField()
    event_id = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    command_accepted = serializers.BooleanField()
    effective = serializers.BooleanField()
    public_effective = serializers.BooleanField()
    publication_required = serializers.BooleanField()
    detail = serializers.CharField()


class WorkFileUploadOutput(serializers.Serializer):
    accepted = serializers.BooleanField()
    created = serializers.BooleanField()
    request_key = serializers.UUIDField()
    item_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    status = serializers.CharField()
    dispatch_status = serializers.CharField()
    workbench_url = serializers.CharField()
    detail = serializers.CharField()
