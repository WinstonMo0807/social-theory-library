"""Reader collaboration is separate from administrative permission groups."""
from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel
from .research_models import PrivateResearchRecord

COLLABORATION_CATEGORIES = ("reader_groups", "group_memberships", "group_invitations", "reader_shares", "share_notices")


class ReaderGroup(PrivateResearchRecord):
    kind = models.CharField(max_length=12, choices=[("campus", "Campus"), ("team", "Team")])
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="reader_group_request_unique")]


class ReaderGroupMember(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(ReaderGroup, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "group"], name="reader_group_member_unique")]


class ReaderGroupInvite(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(ReaderGroup, on_delete=models.CASCADE, related_name="invitations")
    token_hash = models.CharField(max_length=64, unique=True)
    token_ciphertext = models.BinaryField(default=bytes)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    membership = models.ForeignKey(ReaderGroupMember, null=True, on_delete=models.SET_NULL)


class ReaderShare(PrivateResearchRecord):
    source_kind = models.CharField(max_length=12, choices=[("research", "Research"), ("booklist", "Booklist")])
    source_id = models.UUIDField()
    destination = models.CharField(max_length=12, choices=[("group", "Group"), ("public", "Public"), ("proposal", "Proposal")])
    group = models.ForeignKey(ReaderGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="shares")
    token_hash = models.CharField(max_length=64, blank=True)
    token_ciphertext = models.BinaryField(default=bytes, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    review_state = models.CharField(max_length=12, default="submitted", choices=[("submitted", "Submitted"), ("considering", "Considering"), ("declined", "Declined")])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="reader_share_request_unique")]
        indexes = [models.Index(fields=["user", "-created_at"], name="reader_share_owner_idx")]


class ReaderShareNotice(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    share = models.ForeignKey(ReaderShare, on_delete=models.CASCADE, related_name="notices")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "share"], name="reader_share_notice_unique")]
