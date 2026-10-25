from rest_framework import serializers
from catalog.media_views import PublicCoverMediaSerializer


class GroupSummary(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    kind = serializers.ChoiceField(choices=["campus", "team"])
    revision = serializers.IntegerField()
    is_owner = serializers.BooleanField()
    archived = serializers.BooleanField()
    member_count = serializers.IntegerField()


class GroupMember(serializers.Serializer):
    user_id = serializers.CharField()
    membership_id = serializers.CharField()
    name = serializers.CharField()
    is_owner = serializers.BooleanField()


class GroupInvite(serializers.Serializer):
    id = serializers.UUIDField()
    group_id = serializers.UUIDField()
    recipient = serializers.CharField()
    expires_at = serializers.DateTimeField()
    accepted = serializers.BooleanField()
    revoked = serializers.BooleanField()
    expired = serializers.BooleanField()
    token = serializers.CharField(allow_null=True)
    title = serializers.CharField(required=False)


class PageOutput(serializers.Serializer):
    page = serializers.IntegerField()
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()


class GroupPage(PageOutput):
    results = GroupSummary(many=True)


class InvitePage(PageOutput):
    results = GroupInvite(many=True)


class GroupDirectory(serializers.Serializer):
    owner_id = serializers.CharField()
    groups = GroupPage()
    invitations = InvitePage()


class GroupDetail(serializers.Serializer):
    owner_id = serializers.CharField()
    group = GroupSummary()
    members = GroupMember(many=True)
    invitations = GroupInvite(many=True)


class GroupAcceptOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    group_id = serializers.UUIDField()


class GroupResult(GroupAcceptOutput):
    request_id = serializers.UUIDField()
    available = serializers.BooleanField()
    group = GroupSummary(allow_null=True)


class ShareSourceTitle(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["research", "booklist"])
    title = serializers.CharField()


class ShareSource(ShareSourceTitle):
    id = serializers.UUIDField()
    version = serializers.CharField()


class ShareWorkSummary(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    title = serializers.CharField(allow_null=True)
    authors = serializers.ListField(child=serializers.CharField(), required=False)
    year = serializers.IntegerField(allow_null=True, required=False)
    href = serializers.CharField(allow_null=True, required=False)
    cover_url = serializers.CharField(allow_null=True, required=False)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)


class ShareDirectorySource(ShareSource):
    material_count = serializers.IntegerField()
    first_material = ShareWorkSummary(allow_null=True)


class ShareSourcesPage(PageOutput):
    owner_id = serializers.CharField()
    results = ShareDirectorySource(many=True)


class ShareContentItem(serializers.Serializer):
    title = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    available = serializers.BooleanField()
    truncated = serializers.BooleanField(required=False)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    work = ShareWorkSummary(required=False)
    reference = serializers.DictField(child=serializers.JSONField(), required=False, allow_null=True)
    origin_kind = serializers.ChoiceField(choices=['research','booklist'],required=False)
    origin_title = serializers.CharField(required=False)


class ShareCandidateItem(ShareContentItem):
    id = serializers.CharField()
    version = serializers.CharField()


class ShareSelectionOutput(PageOutput):
    owner_id = serializers.CharField()
    source = ShareSource()
    section = serializers.ChoiceField(choices=["questions", "materials", "notes"])
    results = ShareCandidateItem(many=True)


class ShareContentSections(serializers.Serializer):
    questions = ShareContentItem(many=True)
    materials = ShareContentItem(many=True)
    notes = ShareContentItem(many=True)


class ShareCandidateSections(serializers.Serializer):
    questions = ShareCandidateItem(many=True)
    materials = ShareCandidateItem(many=True)
    notes = ShareCandidateItem(many=True)


class ShareRecipientBinding(serializers.Serializer):
    user_id = serializers.CharField()
    membership_id = serializers.CharField()


class ShareDestination(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["group", "public", "proposal"])
    title = serializers.CharField()
    group_id = serializers.UUIDField(allow_null=True)
    members = ShareRecipientBinding(many=True)
    sender_binding = ShareRecipientBinding(required=False)


class SharePreviewOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    source = ShareSource()
    sources = ShareSource(many=True,required=False)
    sections = ShareCandidateSections()
    message = serializers.CharField(allow_blank=True)
    excluded = serializers.ListField(child=serializers.CharField())
    destination = ShareDestination()
    expires_days = serializers.IntegerField()
    preview_hash = serializers.CharField()


class ShareBrief(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    title = serializers.CharField()
    request_id = serializers.UUIDField(allow_null=True)
    source_kind = serializers.ChoiceField(choices=["research", "booklist"])
    source_id = serializers.UUIDField(allow_null=True)
    source_count = serializers.IntegerField()
    destination = serializers.ChoiceField(choices=["group", "public", "proposal"])
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    revoked = serializers.BooleanField()
    is_owner = serializers.BooleanField()
    review_state = serializers.ChoiceField(choices=["submitted", "considering", "declined"])


class ShareReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    share = ShareBrief()
    token = serializers.CharField(allow_null=True)


class ShareRecoveryResult(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=['applied','cancelled'])
    receipt = ShareReceipt(allow_null=True)


class ShareDirectory(PageOutput):
    owner_id = serializers.CharField()
    results = ShareBrief(many=True)


class ShareContent(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    source = ShareSourceTitle()
    sources = ShareSourceTitle(many=True,required=False)
    sections = ShareContentSections()
    message = serializers.CharField(allow_blank=True)
    excluded = serializers.ListField(child=serializers.CharField())
    expires_at = serializers.DateTimeField()
    destination = serializers.ChoiceField(choices=["group", "public", "proposal"])
    review_state = serializers.CharField()


class ShareDetail(serializers.Serializer):
    owner_id = serializers.CharField()
    share = ShareBrief()
    content = ShareContent()


class ShareNotifyResult(serializers.Serializer):
    owner_id = serializers.CharField()
    created = serializers.IntegerField()
    total = serializers.IntegerField()
    channel = serializers.CharField()
    message = serializers.CharField()


class ShareNotice(serializers.Serializer):
    id = serializers.UUIDField()
    share_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    read_at = serializers.DateTimeField(allow_null=True)


class ShareNoticePage(PageOutput):
    owner_id = serializers.CharField()
    unread = serializers.IntegerField()
    results = ShareNotice(many=True)


class ShareNoticeRead(serializers.Serializer):
    owner_id = serializers.CharField()
    marked = serializers.IntegerField()
