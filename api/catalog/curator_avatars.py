"""Account portraits exposed only in the context of an attributed issue."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from accounts import avatars
from accounts.models import AccountAvatar
from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanAccessBackOffice


def account_link(value, *, actor, previous=None):
    if value is None:
        return None
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise ValidationError({"curator_account_id": "请选择本人账号头像。"})
    value = int(value)
    # Collaborators may preserve an existing attribution, never expose another
    # reader's private portrait by entering an arbitrary account ID.
    if actor is None or value != actor.pk and value != previous:
        raise ValidationError({"curator_account_id": "只能关联本人的账号头像。"})
    return value


def portrait(payload):
    raw = payload.get("article_metadata") or {}
    account_id = raw.get("curator_account_id")
    if not payload.get("public_byline") or not isinstance(account_id, int):
        return None
    return AccountAvatar.objects.filter(user_id=account_id, user__is_active=True).exclude(image_ciphertext=b"").only("user_id", "revision").first()


def portrait_url(payload, issue, *, public):
    row = portrait(payload)
    if row is None or issue is None:
        return ""
    path = f"recommendation-issues/{issue.slug}" if public else f"admin/recommendation-issues/{issue.pk}"
    return f"/api/catalog/{path}/curator-avatar/?v={row.revision}"


def image_response(payload):
    row = portrait(payload)
    if row is None:
        raise NotFound("尚未设置策展人头像。")
    response = HttpResponse(avatars.image_data(row.user), content_type="image/png")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="curator-avatar.png"'
    return response


class PublicCuratorAvatarView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, slug):
        from catalog.services.editorial_issues import published_issues, public_issue_revision
        issue = get_object_or_404(published_issues(), slug=slug)
        return image_response(public_issue_revision(issue).materialized_preview)


class AdminCuratorAvatarView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, issue_id):
        from catalog.services.curation_projects import visible_issues
        from catalog.services.editorial_issues import issue_draft_payload
        issue = get_object_or_404(visible_issues(request.user), pk=issue_id)
        return image_response(issue_draft_payload(issue))
