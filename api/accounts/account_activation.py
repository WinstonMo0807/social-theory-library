"""Account invitations use the original account command and audit receipt.

The bearer link is reconstructed with a keyed signature; neither the link nor
password is stored in audit data. A change to the account invalidates the link.
"""
from datetime import timedelta
from uuid import UUID

from django.contrib.auth import password_validation
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import CharField, OuterRef, Subquery, Value
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from .models import User
from .ownership import is_library_owner

INVITE_ACTIONS = ("account_create", "account_invite", "account_revoke_invite")
SIGNER_SALT = "stl-account-activation-v1"


def invitation_rows():
    return AuditEvent.objects.filter(object_type="User", action__in=INVITE_ACTIONS,
        after__invited=True).select_related("actor").order_by("-created_at", "-id")


def latest(user):
    return invitation_rows().filter(object_id=str(user.pk)).first()


def with_invitation_action(rows):
    latest_action = invitation_rows().filter(object_id=Cast(OuterRef("pk"), output_field=CharField())).values("action")[:1]
    return rows.annotate(_invitation_action=Coalesce(Subquery(latest_action), Value("")))


def latest_for_accounts(identities):
    latest_ids = invitation_rows().filter(object_id=OuterRef("object_id")).values("pk")[:1]
    return invitation_rows().filter(object_id__in=identities, pk=Subquery(latest_ids))


def can_renew(user, event):
    return bool(event and not user.is_active and not user.has_usable_password() and user.last_login is None)


def status(user, event):
    from .user_management import version
    if user.is_active:
        return "active"
    if not can_renew(user, event):
        return "inactive"
    if event.action == "account_revoke_invite":
        return "invitation_revoked"
    expiry = parse_datetime(event.after.get("activation_expires_at", ""))
    if not constant_time_compare(event.after.get("activation_version", ""), version(user)):
        return "invitation_changed"
    if not event.actor or not event.actor.is_active or not has_capability(event.actor, Capability.MANAGE_USERS) or (user.role != "reader" and not is_library_owner(event.actor)):
        return "invitation_changed"
    return "pending_activation" if expiry and expiry > timezone.now() else "invitation_expired"


def issue_metadata(user):
    from .user_management import version
    return {"invited": True, "activation_version": version(user),
        "activation_expires_at": (timezone.now() + timedelta(hours=24)).isoformat()}


def management_output(actor, user):
    from .user_management import authority
    authority(actor, user, user.role, user.is_active)
    event = latest(user)
    state = status(user, event)
    token = signing.Signer(salt=SIGNER_SALT).sign(str(event.pk)) if state == "pending_activation" else ""
    return {"actor_id": str(actor.pk), "user_id": user.pk, "state": state,
        "token": token, "expires_at": event.after.get("activation_expires_at") if event else None,
        "can_renew": can_renew(user, event), "notice": "邀请24小时有效；请由你将链接交给本人。系统不会自动发送邮件。"}


def resolve(token):
    try:
        invitation_id = UUID(signing.Signer(salt=SIGNER_SALT).unsign(token))
    except (signing.BadSignature, ValueError, TypeError) as exc:
        raise ValidationError("邀请链接无效，请向创建账户的管理员索取最新链接。") from exc
    event = invitation_rows().filter(pk=invitation_id).first()
    if not event:
        raise ValidationError("邀请链接已失效，请联系管理员。")
    return event


def activation_output(user, event):
    from .user_management import ROLE_LABELS
    if AuditEvent.objects.filter(action="account_activate", object_type="User", object_id=str(user.pk),
            request_id=str(event.pk)).exists():
        return {"state": "activated", "detail": "该邀请已使用，请用本人设置的密码登录。如账户后来被停用，请联系管理员。"}
    state = status(user, event)
    if state != "pending_activation":
        return {"state": "expired" if state == "invitation_expired" else "unavailable",
            "detail": "邀请已过期，请联系管理员重新生成。" if state == "invitation_expired" else "账户或邀请已变化，请联系管理员核对。"}
    return {"state": "ready", "detail": "请核对本人账户并设置密码，激活后再登录。",
        "username": user.username, "email": user.email, "display_name": user.display_name,
        "role_label": ROLE_LABELS[user.role],
        "expires_at": event.after["activation_expires_at"]}


def inspect(token):
    event = resolve(token)
    user = User.objects.filter(pk=event.object_id).first()
    if user is None:
        raise ValidationError("邀请账户已不存在，请联系管理员。")
    return activation_output(user, event)


@transaction.atomic
def activate(token, password):
    event = resolve(token)
    # Same ascending account locks as administrative changes. Recheck the
    # issuing account too, so its revocation cannot race an activation.
    identities = {int(event.object_id)}
    if event.actor_id:
        identities.add(event.actor_id)
    locked = {row.pk: row for row in User.objects.select_for_update().filter(pk__in=identities).order_by("pk")}
    user = locked.get(int(event.object_id))
    if user is None:
        raise ValidationError("邀请账户已不存在，请联系管理员。")
    event.actor = locked.get(event.actor_id)
    output = activation_output(user, event)
    if output["state"] != "ready":
        return output
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc
    user.set_password(password)
    user.is_active = True
    user.token_version += 1
    user.save(update_fields=["password", "is_active", "token_version"])
    # Possession of a manually delivered link does not verify the email address.
    AuditEvent.objects.create(actor=user, action="account_activate", object_type="User", object_id=str(user.pk),
        before={"is_active": False}, after={"is_active": True}, request_id=str(event.pk))
    return {"state": "activated", "detail": "账户已激活，请用刚设置的密码登录。"}
