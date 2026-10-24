"""Single-use mail links on the original recovery credentials and account locks."""
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, unquote
from uuid import UUID

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, ValidationError

from .models import RecoveryCode, User
from .ownership import normalize_email_identity

PURPOSES = (RecoveryCode.Purpose.PASSWORD_LINK, RecoveryCode.Purpose.VERIFY_EMAIL)
NOTICE = "请求已受理。如果邮箱符合条件，将收到24小时有效的链接。未收到时请检查垃圾邮件，或稍后重新申请。"
log = logging.getLogger(__name__)


class MailUnavailable(APIException):
    status_code = 503
    default_detail = "暂时无法受理邮件请求，请稍后重试或使用账户找回申请。"


def mail_available():
    backend = settings.EMAIL_BACKEND
    try:
        url = urlsplit(settings.PUBLIC_WEB_URL)
        valid_url = url.scheme in {"http", "https"} and bool(url.netloc) and not (url.username or url.password or url.query or url.fragment or url.path.strip("/"))
        if settings.PUBLIC_DEPLOYMENT_MODE and url.scheme != "https":
            return False
    except ValueError:
        return False
    if not valid_url:
        return False
    if backend == "common.email_backend.BrevoEmailBackend":
        return bool(settings.BREVO_API_KEY and settings.DEFAULT_FROM_EMAIL and not settings.DEFAULT_FROM_EMAIL.endswith(".invalid"))
    if backend == "django.core.mail.backends.smtp.EmailBackend":
        return bool(settings.EMAIL_HOST and not settings.DEFAULT_FROM_EMAIL.endswith(".invalid"))
    # Console/file/dummy backends must never leak bearer links or claim delivery.
    return bool(settings.DEBUG and backend == "django.core.mail.backends.locmem.EmailBackend")


def destination(value):
    value = str(value or "/account")
    if len(value) > 2000 or not value.startswith("/") or value.startswith("//"):
        return "/account"
    try:
        decoded = value
        for _ in range(4):
            result = unquote(decoded, errors="strict")
            if result == decoded:
                break
            decoded = result
        if decoded.startswith("//") or any(c == "\\" or ord(c) <= 32 or ord(c) == 127 for c in decoded):
            return "/account"
        path = urlsplit(decoded).path
        if any(part in {".", ".."} for part in path.split("/")) or path.rstrip("/") in {"/login", "/register", "/reset-password", "/verify-email", "/activate"}:
            return "/account"
    except (ValueError, UnicodeError):
        return "/account"
    return value


def fingerprint(user):
    return salted_hmac("stl.auth-link-account", json.dumps([user.pk, user.email, user.password,
        user.token_version, user.is_active], ensure_ascii=False), algorithm="sha256").hexdigest()


def enqueue(email, purpose, next_path="/account"):
    from reading.services import encrypt_private_text
    from .tasks import deliver_account_link
    if not mail_available():
        raise MailUnavailable()
    address = normalize_email_identity(email)
    key = "stl.auth-mail:" + salted_hmac("stl.auth-mail", f"{purpose}:{address}", algorithm="sha256").hexdigest()
    try:
        if not cache.add(key, True, timeout=60):
            return
        payload = encrypt_private_text(json.dumps({"email": address, "purpose": purpose,
            "next": destination(next_path), "requested_at": timezone.now().isoformat()})).decode("ascii")
        deliver_account_link.apply_async(args=[payload], expires=120, retry=False)
    except Exception:
        # No provider/broker exception, address or credential enters API output/logs.
        try:
            cache.delete(key)
        except Exception:
            log.warning("Account mail request could not release its rate limit; retry after one minute.")
        raise MailUnavailable() from None


def deliver(payload):
    from reading.services import decrypt_private_text
    data = json.loads(decrypt_private_text(payload.encode("ascii")))
    requested = parse_datetime(data["requested_at"])
    if data["purpose"] not in PURPOSES or not requested or not timezone.is_aware(requested) or not (timedelta(0) <= timezone.now() - requested <= timedelta(minutes=2)):
        return
    if not mail_available():
        raise MailUnavailable()
    with transaction.atomic():
        users = list(User.objects.select_for_update().filter(email__iexact=data["email"], is_active=True).order_by("pk")[:2])
        if len(users) != 1:
            return
        user = users[0]
        if data["purpose"] == RecoveryCode.Purpose.VERIFY_EMAIL and user.email_verified_at:
            return
        # A delayed/duplicate task cannot replace a more recently issued link.
        if user.recovery_codes.filter(purpose=data["purpose"], created_at__gte=requested).exists():
            return
        secret = secrets.token_urlsafe(32)
        user.recovery_codes.filter(purpose=data["purpose"], used_at__isnull=True).update(expires_at=timezone.now())
        if data["purpose"] == RecoveryCode.Purpose.PASSWORD_LINK:
            user.recovery_codes.filter(purpose=RecoveryCode.Purpose.PASSWORD_CODE, used_at__isnull=True).update(expires_at=timezone.now())
        row = RecoveryCode.objects.create(user=user, purpose=data["purpose"], code_hash=hashlib.sha256(secret.encode()).hexdigest(),
            account_fingerprint=fingerprint(user), expires_at=timezone.now() + timedelta(hours=24))
        address = user.email
    route, title = ("reset-password", "重置密码") if row.purpose == RecoveryCode.Purpose.PASSWORD_LINK else ("verify-email", "验证邮箱")
    link = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/{route}?{urlencode({'next': destination(data.get('next'))})}#{urlencode({'token': f'{row.pk}:{secret}'})}"
    try:
        sent = send_mail(f"社会理论书库 · {title}", f"请在24小时内打开以下链接，由本人确认{title}：\n\n{link}\n\n链接仅供本人使用，重新申请后旧链接失效。若非本人操作，请忽略；不会自动登录或修改账户。",
            None, [address], fail_silently=False)
        if sent != 1:
            raise MailUnavailable()
    except Exception:
        RecoveryCode.objects.filter(pk=row.pk, used_at__isnull=True).update(expires_at=timezone.now())
        log.warning("Account mail delivery failed; issued credential invalidated; resubmission required.")
        raise MailUnavailable() from None


def resolve(token, purpose):
    try:
        identity, secret = token.split(":", 1)
        identity = UUID(identity)
        if len(secret) != 43:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("链接无效，请使用邮件中的完整链接或重新申请。") from None
    row = RecoveryCode.objects.filter(pk=identity, purpose=purpose).first()
    if not row or not constant_time_compare(row.code_hash, hashlib.sha256(secret.encode()).hexdigest()):
        raise ValidationError("链接无效，请使用邮件中的完整链接或重新申请。")
    return row


def output(row, user):
    if row.used_at:
        return {"state": "completed", "detail": "此链接已完成操作。请使用本人密码登录；如仍无法登录，请重新申请恢复。"}
    if row.expires_at <= timezone.now():
        return {"state": "expired", "detail": "链接已过期或被新申请替代，请重新申请。"}
    if not user.is_active or not constant_time_compare(row.account_fingerprint, fingerprint(user)):
        return {"state": "unavailable", "detail": "账户状态已变化，链接不再可用。请重新申请或联系管理员。"}
    return {"state": "ready", "detail": "链接有效，请由本人确认后继续。", "expires_at": row.expires_at}


@transaction.atomic
def operate(token, purpose, action, password=None):
    row = resolve(token, purpose)
    user = User.objects.select_for_update().filter(pk=row.user_id).first()
    row = RecoveryCode.objects.select_for_update().filter(pk=row.pk).first()
    if user is None or row is None:
        raise ValidationError("链接已失效，请重新申请或联系管理员。")
    state = output(row, user)
    if action == "inspect" or state["state"] != "ready":
        return state
    if purpose == RecoveryCode.Purpose.PASSWORD_LINK:
        try:
            password_validation.validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from None
        user.set_password(password)
        user.token_version += 1
        user.save(update_fields=["password", "token_version"])
        user.recovery_codes.filter(used_at__isnull=True).update(expires_at=timezone.now())
    else:
        if not user.email_verified_at:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
    row.used_at = timezone.now()
    row.save(update_fields=["used_at", "updated_at"])
    return output(row, user)
