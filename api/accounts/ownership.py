from django.conf import settings


def normalize_email_identity(value) -> str:
    return str(value or "").strip().casefold()


def configured_library_owner_email() -> str:
    return normalize_email_identity(getattr(settings, "LIBRARY_OWNER_EMAIL", ""))


def is_library_owner_email(value) -> bool:
    configured = configured_library_owner_email()
    return bool(configured and normalize_email_identity(value) == configured)


def is_library_owner_identity(user) -> bool:
    if not user:
        return False
    return is_library_owner_email(getattr(user, "email", ""))


def is_library_owner(user) -> bool:
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False
    return is_library_owner_identity(user)


def library_owner_display_name() -> str:
    return str(getattr(settings, "LIBRARY_OWNER_DISPLAY_NAME", "Winston") or "Winston").strip()
