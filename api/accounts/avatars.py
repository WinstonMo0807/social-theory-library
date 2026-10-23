"""Bounded, encrypted profile images; never a public catalog media asset."""
import base64
from hashlib import sha256
from io import BytesIO

from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac
from PIL import Image, ImageOps
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from catalog.services.media import MediaValidationError, _inspect
from ingestion.models import AuditEvent
from reading.services import decrypt_private_text, encrypt_private_text
from .models import AccountAvatar, User
from .user_management import AccountConflict, digest

MAX_UPLOAD = 2 * 1024 * 1024
MAX_STORED = 300 * 1024
ACTIONS = ("profile_avatar_set", "profile_avatar_remove", "profile_avatar_stop")


def state(user):
    row = AccountAvatar.objects.filter(user=user).first()
    revision = row.revision if row else 0
    return {"owner_id": str(user.pk), "has_avatar": bool(row and row.image_ciphertext), "revision": revision,
        "expected_version": salted_hmac("stl-profile-avatar-v1", f"{user.pk}:{user.token_version}:{revision}", algorithm="sha256").hexdigest(),
        "updated_at": row.updated_at if row else None,
        "notice": "仅本人和获准管理账户的管理员可查看。不会加入公开素材或学者肖像。"}


def image_data(user):
    row = AccountAvatar.objects.filter(user=user).first()
    if not row or not row.image_ciphertext:
        raise NotFound("尚未设置头像。")
    return base64.b64decode(decrypt_private_text(row.image_ciphertext), validate=True)


def export(user):
    row = AccountAvatar.objects.filter(user=user).first()
    if not row or not row.image_ciphertext:
        return None
    return {"mime_type": "image/png", "image_base64": decrypt_private_text(row.image_ciphertext),
        "revision": row.revision, "updated_at": row.updated_at}


def normalize(upload):
    if upload.size > MAX_UPLOAD:
        raise ValidationError("头像不能超过2 MB。")
    source = upload.read(MAX_UPLOAD + 1)
    if not source or len(source) > MAX_UPLOAD:
        raise ValidationError("图片为空或超过2 MB。")
    try:
        _inspect(source, upload.name, upload.content_type)
        with Image.open(BytesIO(source)) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValidationError("请选择单张静态图片，不支持动图。")
            resized = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGBA"), (256, 256), Image.Resampling.LANCZOS)
            # A new pixel canvas strips EXIF, comments and source metadata.
            clean = Image.new("RGBA", (256, 256)); clean.paste(resized)
            output = BytesIO(); clean.save(output, format="PNG")
            data = output.getvalue()
    except (MediaValidationError, OSError, ValueError) as exc:
        raise ValidationError(str(exc) if isinstance(exc, MediaValidationError) else "图片无法安全读取，请换一张图片。") from exc
    if len(data) > MAX_STORED:
        raise ValidationError("处理后的头像超出保存范围，请换一张图片。")
    return source, data


def locked_user(actor):
    current = User.objects.select_for_update().filter(pk=actor.pk).first()
    if current is None or not current.is_active or current.token_version != actor.token_version:
        raise PermissionDenied("账户凭证已变化，请重新登录后核对头像。")
    return current


def receipt(user, request_id):
    event = AuditEvent.objects.filter(pk=request_id, actor=user, action__in=ACTIONS,
        object_type="AccountAvatar", object_id=str(user.pk)).first()
    if not event:
        raise NotFound("尚未查到原头像操作，请保留编号继续核对。")
    return {**state(user), "request_id": str(request_id), "state": "cancelled" if event.action == "profile_avatar_stop" else "applied"}


@transaction.atomic
def stop(actor, request_id):
    user = locked_user(actor)
    prior = AuditEvent.objects.filter(pk=request_id).first()
    if prior:
        if prior.actor_id != user.pk or prior.action not in ACTIONS or prior.object_type != "AccountAvatar" or prior.object_id != str(user.pk):
            raise AccountConflict("原编号不属于本人的头像操作。")
    else:
        AuditEvent.objects.create(pk=request_id, actor=user, action="profile_avatar_stop", object_type="AccountAvatar", object_id=str(user.pk), request_id=str(request_id))
    return receipt(user, request_id)


def command(actor, data, upload=None):
    if data.get("confirmed") is not True or (data["action"] == "set") != (upload is not None):
        raise ValidationError("请确认头像操作并提供匹配的图片。")
    source, image = normalize(upload) if upload is not None else (b"", b"")
    fingerprint = digest({**data, "source_hash": sha256(source).hexdigest()})
    with transaction.atomic():
        user = locked_user(actor)
        prior = AuditEvent.objects.filter(pk=data["request_id"]).first()
        if prior:
            if prior.actor_id != user.pk or prior.action not in ACTIONS or prior.object_type != "AccountAvatar" or prior.object_id != str(user.pk):
                raise AccountConflict("原编号不属于本人的头像操作。")
            if prior.action != "profile_avatar_stop" and prior.after.get("command_fingerprint") != fingerprint:
                raise AccountConflict("原请求输入已经变化，请先查回原结果。")
            return receipt(user, data["request_id"])
        snapshot = state(user)
        if not constant_time_compare(snapshot["expected_version"], data["expected_version"]):
            raise AccountConflict("头像已在其他页面更新，请重新读取后决定。")
        row, _ = AccountAvatar.objects.get_or_create(user=user, defaults={"revision": 0})
        row.image_ciphertext = encrypt_private_text(base64.b64encode(image).decode("ascii")) if image else b""
        row.revision += 1
        row.save(update_fields=["image_ciphertext", "revision", "updated_at"])
        AuditEvent.objects.create(pk=data["request_id"], actor=user, action="profile_avatar_" + data["action"], object_type="AccountAvatar",
            object_id=str(user.pk), before={"revision": snapshot["revision"]},
            after={"revision": row.revision, "command_fingerprint": fingerprint}, request_id=str(data["request_id"]))
        return receipt(user, data["request_id"])
