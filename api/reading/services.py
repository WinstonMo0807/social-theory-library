import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings

from catalog.models import Asset, PublicationState

from .models import ReadingProgress


RECENT_READING_LIMIT = 5


def _fernet() -> Fernet:
    configured = settings.PRIVATE_DATA_ENCRYPTION_KEY.strip()
    if configured:
        key = configured.encode()
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_private_text(value: str) -> bytes:
    if not value:
        return b""
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt_private_text(value: bytes) -> str:
    if not value:
        return ""
    return _fernet().decrypt(bytes(value)).decode("utf-8")


def readable_progress_for_user(user):
    """Return progress rows that still point to a usable public reader asset."""

    return ReadingProgress.objects.filter(
        user=user,
        asset__edition__state=PublicationState.PUBLISHED,
        asset__kind=Asset.Kind.NORMALIZED,
        asset__status=Asset.Status.READY,
        asset__is_current=True,
    )


def current_reader_asset_for_work(work):
    """Select the preferred readable asset without changing any stored record."""

    return (
        Asset.objects.filter(
            edition__work=work,
            edition__state=PublicationState.PUBLISHED,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
        .order_by(
            "-edition__is_primary",
            "-edition__last_published_at",
            "-edition__published_at",
            "-version",
            "-updated_at",
        )
        .first()
    )


def ensure_saved_work_progress(*, user, work, fallback_asset=None):
    """Keep a durable progress row behind a saved work.

    A saved work is independent from the five-row recent-reading view. Existing
    progress on any currently readable edition wins, so saving never resets a
    reader who already opened another edition of the same work.
    """

    existing = (
        readable_progress_for_user(user)
        .filter(asset__edition__work=work)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if existing is not None:
        return existing

    asset = fallback_asset or current_reader_asset_for_work(work)
    if asset is None:
        return None
    progress, _ = ReadingProgress.objects.get_or_create(
        user=user,
        asset=asset,
        defaults={
            "current_page": 1,
            "progress_ratio": 0,
            "last_position": {"page": 1},
        },
    )
    return progress
