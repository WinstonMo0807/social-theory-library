from django.conf import settings


def is_library_owner(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    configured = settings.LIBRARY_OWNER_EMAIL.strip().lower()
    return bool(configured and str(getattr(user, "email", "")).strip().lower() == configured)
